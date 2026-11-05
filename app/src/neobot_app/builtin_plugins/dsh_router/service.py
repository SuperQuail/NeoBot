"""dsh_router 核心服务：提案 / 派发 / 输入 / 审批 / 通知 / 回收。

分工：

- 本服务持有**业务状态**（任务表 + 提案 + outbox + 待投递通知）；
- ``DshGatewayService`` 只做传输（报告去重、命令 ack/重发、长轮询唤醒）；
- ``RouterModeService`` 只记录「哪个聊天流处于 Router 模式」。

所有状态只在事件循环内读写；``TaskStore`` 负责落盘（原子写）。
网关 / Router 模式服务可能为 None（本体未装配或关闭），此时工具返回提示而不是抛异常。
"""

from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from neobot_contracts.ports.logging import NullLogger
from neobot_contracts.ports.speaking import SpeechBlocked

from .config import MODES, DshRouterConfig
from .store import TaskRecord, TaskStore

#: 通知来源标识（面板/日志按它过滤）。
NOTICE_SOURCE = "dsh_router"

#: 任务输入的模式：steer 立刻插话，queue 排到当前轮之后。
INPUT_MODES = ("steer", "queue")

#: 任务表最多占几行（含表头）。
MAX_TABLE_LINES = 8

DISABLED_TEXT = "dsh_router 插件已在配置中禁用（enabled=false），不做任何派发。"
NO_GATEWAY_TEXT = "DSH 网关未启用（dsh.gateway.enabled=false 或服务未注册），无法派发任务。"
NO_ROUTER_TEXT = "Router 模式服务未启用，无法为这个会话启用受限工具面。"


@dataclass(slots=True)
class Proposal:
    """一次待确认的派发提案；按聊天流只保留最新一份。"""

    pipeline_key: str
    owner_user_id: int | None
    task: str
    cwd: str
    mode: str
    created_at: float
    expires_at: float

    def expired(self, now: float) -> bool:
        return now >= self.expires_at


def _clip(text: Any, limit: int = 80) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _split_pipeline_key(pipeline_key: str) -> tuple[str, str] | None:
    key = str(pipeline_key or "").strip()
    kind, _, conversation_id = key.partition(":")
    if kind not in {"group", "private"} or not conversation_id:
        return None
    return kind, conversation_id


class DshRouterService:
    def __init__(
        self,
        *,
        config: DshRouterConfig,
        store: TaskStore,
        logger: Any | None = None,
        gateway: Any | None = None,
        router_mode: Any | None = None,
        notification_hub: Any | None = None,
        clock: Any | None = None,
    ) -> None:
        self._config = config
        self._store = store
        self._logger = logger or NullLogger()
        self._gateway = gateway
        self._router_mode = router_mode
        self._notification_hub = notification_hub
        self._now = clock or time.time
        self._proposals: dict[str, Proposal] = {}
        self._outbox: list[Any] = []
        self._pending_notices: list[dict[str, Any]] = []
        self._health: dict[str, dict[str, Any]] = {}
        self._last_daemon_id = ""
        self._last_activity: dict[str, float] = {}

    # ── 只读视图 ────────────────────────────────────────────────

    @property
    def config(self) -> DshRouterConfig:
        return self._config

    @property
    def store(self) -> TaskStore:
        return self._store

    @property
    def gateway(self) -> Any | None:
        return self._gateway

    @property
    def router_mode(self) -> Any | None:
        return self._router_mode

    @property
    def last_daemon_id(self) -> str:
        return self._last_daemon_id

    def health(self) -> dict[str, dict[str, Any]]:
        return {key: dict(value) for key, value in self._health.items()}

    def pending_notices(self, pipeline_key: str | None = None) -> list[dict[str, Any]]:
        items = self._pending_notices
        if pipeline_key is not None:
            items = [item for item in items if item["pipeline_key"] == pipeline_key]
        return [dict(item) for item in items]

    # ── 提案 ────────────────────────────────────────────────────

    def propose(
        self,
        pipeline_key: str,
        owner_user_id: int | None,
        task: str,
        cwd: str = "",
        mode: str = "write",
    ) -> str:
        """校验工作区与模式，登记一份待确认提案；返回给用户看的提案文本。"""
        if not self._config.enabled:
            return DISABLED_TEXT
        text = " ".join(str(task or "").split())
        if not text:
            return "任务内容不能为空：请说明要做的事，再调用 propose。"
        mode = str(mode or "write").strip().lower()
        if mode not in MODES:
            return f"不支持的模式 {mode!r}：只能是 read（只读）或 write（可写）。"
        cwd, error = self._resolve_cwd(cwd)
        if error:
            return error
        now = self._now()
        ttl = max(1, int(self._config.proposal_ttl_minutes)) * 60
        self._proposals[pipeline_key] = Proposal(
            pipeline_key=pipeline_key,
            owner_user_id=owner_user_id,
            task=text,
            cwd=cwd,
            mode=mode,
            created_at=now,
            expires_at=now + ttl,
        )
        mode_text = "可写（read/write）" if mode == "write" else "只读（read）"
        return (
            f"【DSH 任务提案】\n任务：{text}\n工作区：{cwd}\n模式：{mode_text}\n"
            f"确认后我就派发；提案 {self._config.proposal_ttl_minutes} 分钟内有效，"
            "过期需重新 propose。"
        )

    def _resolve_cwd(self, cwd: str) -> tuple[str, str]:
        """把 cwd 规整为 realpath 并校验落在 workspaces 内；返回 (路径, 错误文案)。"""
        workspaces = list(self._config.workspaces)
        if not workspaces:
            return "", "未配置工作区（config.workspaces 为空），拒绝派发任务。"
        raw = str(cwd or "").strip()
        if raw:
            candidate = Path(raw).expanduser()
        elif len(workspaces) == 1:
            candidate = Path(workspaces[0]).expanduser()
        else:
            return "", "请指定 cwd（必须是 config.workspaces 下的一个目录）。"
        try:
            resolved = Path(os.path.realpath(candidate))
        except OSError:
            return "", f"工作区路径无法解析：{candidate}"
        if not resolved.is_dir():
            return "", f"工作区不存在或不是目录：{resolved}"
        allowed = [Path(os.path.realpath(Path(item).expanduser())) for item in workspaces]
        for base in allowed:
            try:
                if resolved == base or base in resolved.parents:
                    return str(resolved), ""
            except OSError:
                continue
        return "", f"工作区必须在 config.workspaces 之内；当前允许：{', '.join(str(item) for item in allowed)}"

    # ── 派发与命令 ──────────────────────────────────────────────

    def dispatch(
        self,
        pipeline_key: str,
        owner_user_id: int | None,
        task: str = "",
        cwd: str = "",
        mode: str = "",
    ) -> str:
        if not self._config.enabled:
            return DISABLED_TEXT
        if self._gateway is None:
            return NO_GATEWAY_TEXT
        if self._router_mode is None:
            return NO_ROUTER_TEXT
        proposal = self._proposals.get(pipeline_key)
        now = self._now()
        if proposal is None or proposal.expired(now):
            self._proposals.pop(pipeline_key, None)
            return "还没有有效的任务提案。请先调用 propose 并把提案给用户确认，再调用 dispatch。"
        if task and " ".join(str(task).split()) != proposal.task:
            return "提案内容与本次派发不一致：请重新 propose 并等用户确认。"
        if cwd:
            resolved = str(Path(os.path.realpath(Path(cwd).expanduser())))
            if resolved != proposal.cwd:
                return "本次派发的 cwd 与提案不一致：请重新 propose。"
        if mode and str(mode).strip().lower() != proposal.mode:
            return "本次派发的 mode 与提案不一致：请重新 propose。"
        active = self._store.active(pipeline_key)
        limit = int(self._config.max_tasks_per_chat)
        if len(active) >= limit:
            return f"本会话已有 {len(active)} 个未结束任务（上限 {limit}），请先等待完成或调用 cancel。"
        task_id = self._new_task_id()
        self._store.create(
            TaskRecord(
                task_id=task_id,
                pipeline_key=pipeline_key,
                owner_user_id=owner_user_id,
                cwd=proposal.cwd,
                mode=proposal.mode,
                prompt=proposal.task,
                status="dispatched",
                created_at=now,
                updated_at=now,
                last_event_at=now,
            )
        )
        self._proposals.pop(pipeline_key, None)
        self._enqueue(
            kind="task.dispatch",
            task_id=task_id,
            payload={"cwd": proposal.cwd, "mode": proposal.mode, "prompt": proposal.task},
        )
        active_ids = [record.task_id for record in self._store.active(pipeline_key)]
        self._activate(pipeline_key, owner_user_id, active_ids)
        self._last_activity[pipeline_key] = now
        return (
            f"已派发 DSH 任务 {task_id}\n工作区：{proposal.cwd}（{proposal.mode}）\n"
            "进度、卡点与结果会通知到本会话；需要插话用 send，取消用 cancel。"
        )

    def send(self, task_id: str, text: str, mode: str = "steer") -> str:
        if self._gateway is None:
            return NO_GATEWAY_TEXT
        record = self._store.get(task_id)
        if record is None:
            return f"找不到任务 {task_id}。"
        if not record.active:
            return f"任务 {record.task_id} 已结束（{record.status}），无法继续对话。"
        content = str(text or "").strip()
        if not content:
            return "发送内容不能为空。"
        chosen = str(mode or "steer").strip().lower()
        if chosen not in INPUT_MODES:
            chosen = "steer"
        self._enqueue(
            kind="task.input",
            task_id=record.task_id,
            payload={"text": content, "mode": chosen},
        )
        return f"已把输入转给 {record.task_id}（mode={chosen}）。"

    def cancel(self, task_id: str, reason: str = "") -> str:
        if self._gateway is None:
            return NO_GATEWAY_TEXT
        record = self._store.get(task_id)
        if record is None:
            return f"找不到任务 {task_id}。"
        if not record.active:
            return f"任务 {record.task_id} 已结束（{record.status}），无需取消。"
        self._enqueue(
            kind="task.cancel",
            task_id=record.task_id,
            payload={"reason": str(reason or "").strip()},
        )
        now = self._now()
        self._store.update(record.task_id, status="cancelling", last_event_at=now, updated_at=now)
        return f"已请求取消 {record.task_id}；收到 worker 的结束事件后状态会更新。"

    def approve(self, request_id: str, allow: bool) -> str:
        if self._gateway is None:
            return NO_GATEWAY_TEXT
        rid = str(request_id or "").strip()
        if not rid:
            return "缺少 request_id。"
        record = self.find_by_request(rid)
        if record is None:
            return f"找不到待审批请求 {rid}（可能已处理或已失效）。"
        self._enqueue(
            kind="perm.answer",
            task_id=record.task_id,
            payload={"request_id": rid, "allow": bool(allow)},
        )
        now = self._now()
        self._store.update(record.task_id, pending_permission=None, last_event_at=now, updated_at=now)
        return f"已{'允许' if allow else '拒绝'} {rid}（任务 {record.task_id}）。"

    def find_by_request(self, request_id: str) -> TaskRecord | None:
        rid = str(request_id or "").strip()
        if not rid:
            return None
        for record in self._store.all():
            permission = record.pending_permission or {}
            if str(permission.get("request_id") or "") == rid:
                return record
        return None

    def mode_owner(self, pipeline_key: str) -> int | None:
        if self._router_mode is None:
            return None
        try:
            session = self._router_mode.session(pipeline_key)
        except Exception:
            return None
        return getattr(session, "owner_user_id", None) if session is not None else None

    def exit_mode(self, pipeline_key: str) -> str:
        if self._router_mode is None:
            return NO_ROUTER_TEXT
        self._proposals.pop(pipeline_key, None)
        self._last_activity.pop(pipeline_key, None)
        self._router_mode.deactivate(pipeline_key, reason="dsh_router.exit")
        return "已退出 Router 模式；本会话恢复常规工具面。"

    # ── 文本视图 ────────────────────────────────────────────────

    def status(self, task_id: str) -> str:
        record = self._store.get(task_id)
        if record is None:
            return f"找不到任务 {task_id}。"
        now = self._now()
        lines = [
            f"【DSH 任务 {record.task_id}】",
            f"状态：{record.status}",
            f"工作区：{record.cwd}（{record.mode}）",
            f"创建：{self._clock_text(record.created_at)}｜最近事件：{self._age_text(now, record.last_event_at)}",
        ]
        if record.summary:
            lines.append(f"摘要：{_clip(record.summary, 200)}")
        if record.pending_permission:
            permission = record.pending_permission
            lines.append(f"待审批：{permission.get('request_id', '?')} — {_clip(permission.get('prompt'), 120)}")
        if record.artifacts:
            lines.append(f"产物：{', '.join(_clip(item, 60) for item in record.artifacts[:5])}")
        return "\n".join(lines)

    def tasks(self, pipeline_key: str) -> str:
        records = self._store.list(pipeline_key)
        if not records:
            return "当前会话没有 DSH 任务。"
        active = [record for record in records if record.active]
        lines = [f"本会话 DSH 任务：{len(records)} 个（活跃 {len(active)} 个）"]
        for record in records[-10:]:
            summary = f" {_clip(record.summary, 40)}" if record.summary else ""
            lines.append(f"- {record.task_id} [{record.status}]{summary}")
        return "\n".join(lines)

    def task_table(self, pipeline_key: str) -> str | None:
        """Router 模式注入的紧凑任务表；没有活跃任务返回 None。"""
        active = self._store.active(pipeline_key)
        if not active:
            return None
        rows: list[str] = []
        for record in active:
            row = f"- {record.task_id} [{record.status}]"
            if record.summary:
                row += f" {_clip(record.summary, 48)}"
            permission = record.pending_permission
            if permission:
                row += f"（待审批 {permission.get('request_id', '?')}）"
            rows.append(row)
        lines = ["【DSH 活跃任务】"]
        if len(rows) <= MAX_TABLE_LINES - 1:
            lines.extend(rows)
        else:
            lines.extend(rows[: MAX_TABLE_LINES - 2])
            lines.append(f"- …另有 {len(rows) - (MAX_TABLE_LINES - 2)} 个任务未列出")
        return "\n".join(lines[:MAX_TABLE_LINES])

    def pending_text(self, pipeline_key: str | None = None) -> str:
        lines: list[str] = []
        for record in self._store.all():
            if pipeline_key is not None and record.pipeline_key != pipeline_key:
                continue
            permission = record.pending_permission
            if not permission:
                continue
            lines.append(
                f"- 审批 {permission.get('request_id', '?')}（任务 {record.task_id}）："
                f"{_clip(permission.get('prompt'), 80)}"
            )
        for item in self._pending_notices:
            if pipeline_key is not None and item["pipeline_key"] != pipeline_key:
                continue
            lines.append(f"- 通知 {item['kind']}（任务 {item.get('task_id') or '—'}）：{_clip(item['content'], 80)}")
        if not lines:
            return "没有待处理的卡点或通知。"
        return "\n".join(["待处理："] + lines[:10])

    def overview(self, pipeline_key: str) -> str:
        """``/dsh status`` 用的会话总览。"""
        records = self._store.list(pipeline_key)
        active = [record for record in records if record.active]
        active_mode = bool(self._router_mode is not None and self._router_mode.is_active(pipeline_key))
        owner = self.mode_owner(pipeline_key)
        lines = [
            f"Router 模式：{'已启用' if active_mode else '未启用'}"
            + (f"（owner {owner}）" if active_mode and owner else ""),
            f"任务：{len(records)} 个（活跃 {len(active)}）",
        ]
        table = self.task_table(pipeline_key)
        if table:
            lines.append(table)
        return "\n".join(lines)

    # ── 报告处理 ────────────────────────────────────────────────

    async def on_reports(self, daemon_id: str, reports: list[Any]) -> None:
        self._last_daemon_id = str(daemon_id or "").strip()
        for report in reports or ():
            kind = str(getattr(report, "kind", "") or "")
            payload = dict(getattr(report, "payload", {}) or {})
            if kind == "daemon.health":
                self._health[self._last_daemon_id] = payload
                continue
            task_id = str(getattr(report, "task_id", "") or "")
            if not task_id:
                continue
            if kind == "task.event":
                await self._on_event(task_id, payload)
            elif kind == "task.done":
                await self._on_done(task_id, payload)
            elif kind == "perm.request":
                await self._on_permission(task_id, payload, getattr(report, "id", ""))

    async def _on_event(self, task_id: str, payload: dict[str, Any]) -> None:
        record = self._store.get(task_id)
        if record is None:
            return
        now = self._now()
        phase = str(payload.get("phase") or "progress").strip() or "progress"
        summary = _clip(
            payload.get("summary")
            or payload.get("text")
            or payload.get("message")
            or payload.get("detail"),
            200,
        )
        status = str(payload.get("status") or "").strip()
        if status not in {"dispatched", "running", "cancelling"}:
            status = "running" if record.status == "dispatched" else record.status
        self._store.update(
            record.task_id,
            status=status,
            summary=summary or record.summary,
            last_event_at=now,
            updated_at=now,
        )
        self._last_activity[record.pipeline_key] = now
        interval = float(self._config.event_min_interval_seconds)
        throttled = phase != "blocker" and (now - record.last_notice_at) < interval
        if throttled:
            return
        content = self._event_text(record, phase, summary, status)
        delivered = await self._notify(
            record.pipeline_key,
            content,
            task_id=record.task_id,
            notice_kind="event",
            phase=phase,
        )
        if delivered:
            self._store.update(record.task_id, last_notice_at=now)

    async def _on_done(self, task_id: str, payload: dict[str, Any]) -> None:
        record = self._store.get(task_id)
        if record is None:
            return
        now = self._now()
        ok = payload.get("ok")
        phase = str(payload.get("phase") or "").strip().lower()
        outcome = str(payload.get("outcome") or "").strip().lower()
        if outcome == "cancelled" or phase == "cancelled":
            status = "cancelled"
        elif (
            ok is False
            or outcome == "failed"
            or phase in {"failed", "error"}
            or str(payload.get("status") or "") == "failed"
        ):
            status = "failed"
        else:
            status = "done"
        summary = _clip(
            payload.get("summary")
            or payload.get("text")
            or payload.get("message")
            or payload.get("result"),
            200,
        )
        artifacts = payload.get("artifacts")
        merged = list(record.artifacts)
        if isinstance(artifacts, list):
            for item in artifacts:
                text = str(item or "").strip()
                if text and text not in merged:
                    merged.append(text)
        self._store.update(
            record.task_id,
            status=status,
            summary=summary or record.summary,
            artifacts=merged,
            worker_session_id=str(
                payload.get("session_id") or payload.get("worker_session_id") or record.worker_session_id
            ),
            last_event_at=now,
            updated_at=now,
        )
        private = record.pipeline_key.startswith("private:")
        label = {"failed": "失败", "cancelled": "已取消"}.get(status, "完成")
        content = f"【DSH 任务{label}】{record.task_id}"
        if summary:
            content += f"\n{summary}"
        content += "\n可以 /dsh status 查看详情，或让它继续做下一件事。"
        await self._notify(
            record.pipeline_key,
            content,
            task_id=record.task_id,
            notice_kind="done",
            phase=status,
            force=private,
        )
        self._last_activity[record.pipeline_key] = now

    async def _on_permission(self, task_id: str, payload: dict[str, Any], report_id: str) -> None:
        record = self._store.get(task_id)
        if record is None:
            return
        now = self._now()
        request_id = str(payload.get("request_id") or payload.get("id") or report_id or f"{task_id}-perm").strip()
        action = _clip(payload.get("action"), 120)
        detail = _clip(payload.get("detail"), 200)
        prompt = _clip(
            payload.get("prompt")
            or payload.get("summary")
            or payload.get("question"),
            200,
        )
        if not prompt:
            prompt = " · ".join(part for part in (action, detail) if part) or "worker 请求审批"
        self._store.update(
            record.task_id,
            pending_permission={
                "request_id": request_id,
                "prompt": prompt or "worker 请求审批",
                "created_at": now,
            },
            last_event_at=now,
            updated_at=now,
        )
        content = (
            f"【DSH 等待审批】{record.task_id}\n"
            f"request_id：{request_id}\n{prompt or 'worker 请求审批'}\n"
            f"允许请回复 /dsh approve {request_id} allow，拒绝用 deny。"
        )
        await self._notify(
            record.pipeline_key,
            content,
            task_id=record.task_id,
            notice_kind="permission",
            phase="blocker",
            force=True,
        )
        self._last_activity[record.pipeline_key] = now

    async def drain_commands(self, daemon_id: str) -> list[Any]:
        self._last_daemon_id = str(daemon_id or "").strip() or self._last_daemon_id
        pending, self._outbox = self._outbox, []
        return pending

    async def reap(self) -> list[str]:
        """标记 stale 任务，并按空闲时长退出 Router 模式；返回被标记的 task_id。"""
        now = self._now()
        stale: list[str] = []
        stale_after = float(self._config.task_stale_seconds)
        for record in self._store.all():
            if record.active and now - max(record.last_event_at, record.updated_at) > stale_after:
                self._store.update(record.task_id, status="stale", updated_at=now)
                stale.append(record.task_id)
        minutes = int(self._config.auto_exit_idle_minutes)
        if minutes <= 0 or self._router_mode is None:
            return stale
        for session in list(self._router_mode.snapshot()):
            pipeline_key = str(session.get("pipeline_key") or "")
            if not pipeline_key or self._store.active(pipeline_key):
                continue
            last = self._last_activity.get(pipeline_key)
            if last is None:
                last = max(
                    (record.updated_at for record in self._store.list(pipeline_key)),
                    default=0.0,
                )
            if now - last >= minutes * 60:
                self._router_mode.deactivate(pipeline_key, reason="dsh_router.idle")
                self._last_activity.pop(pipeline_key, None)
        return stale

    # ── 通知 ────────────────────────────────────────────────────

    async def _notify(
        self,
        pipeline_key: str,
        content: str,
        *,
        task_id: str = "",
        notice_kind: str = "event",
        phase: str = "",
        force: bool = False,
    ) -> bool:
        hub = self._notification_hub
        if hub is None:
            return False
        split = _split_pipeline_key(pipeline_key)
        if split is None:
            return False
        kind, conversation_id = split
        try:
            await hub.publish(
                source=NOTICE_SOURCE,
                kind=kind,
                conversation_id=conversation_id,
                content=content,
                manager_name=NOTICE_SOURCE,
                metadata={"task_id": task_id, "noticeKind": notice_kind, "phase": phase},
                force=force,
            )
            return True
        except SpeechBlocked as exc:
            # 群聊被发言策略拦下：落 pending，由 /dsh pending 兜底。
            self._pending_notices.append(
                {
                    "pipeline_key": pipeline_key,
                    "task_id": task_id,
                    "kind": notice_kind,
                    "phase": phase,
                    "content": content,
                    "created_at": self._now(),
                }
            )
            self._logger.info(f"DSH 通知被发言策略拦截，已转入待处理: {exc}")
            return False
        except Exception as exc:
            self._logger.warning(f"DSH 通知投递失败: {exc}")
            return False

    # ── 内部辅助 ────────────────────────────────────────────────

    def _event_text(self, record: TaskRecord, phase: str, summary: str, status: str) -> str:
        label = {"blocker": "卡点", "stage": "阶段", "artifact": "产物"}.get(phase, "进度")
        content = f"【DSH {label}】{record.task_id}（{status}）"
        if summary:
            content += f"\n{summary}"
        return content

    def _activate(self, pipeline_key: str, owner_user_id: int | None, task_ids: list[str]) -> None:
        if self._router_mode is None:
            return
        try:
            self._router_mode.activate(
                pipeline_key,
                owner_user_id=owner_user_id,
                task_ids=task_ids,
                reason="dsh_router.dispatch",
            )
        except Exception as exc:
            self._logger.warning(f"激活 Router 模式失败: {exc}")

    def _enqueue(self, *, kind: str, task_id: str, payload: dict[str, Any]) -> Any:
        from neobot_app.dsh_gateway.models import DaemonCommand

        command = DaemonCommand(
            id=f"c-{secrets.token_hex(5)}",
            kind=kind,
            task_id=task_id,
            payload=dict(payload),
        )
        self._outbox.append(command)
        if self._gateway is not None and self._last_daemon_id:
            try:
                self._gateway.notify(self._last_daemon_id)
            except Exception as exc:
                self._logger.warning(f"唤醒 daemon 长轮询失败: {exc}")
        return command

    @staticmethod
    def _new_task_id() -> str:
        return f"dsh-{secrets.token_hex(4)}"

    @staticmethod
    def _clock_text(value: float) -> str:
        return time.strftime("%m-%d %H:%M", time.localtime(value)) if value else "—"

    def _age_text(self, now: float, value: float) -> str:
        if not value:
            return "—"
        seconds = max(0, int(now - value))
        if seconds < 60:
            return f"{seconds} 秒前"
        if seconds < 3600:
            return f"{seconds // 60} 分钟前"
        return f"{seconds // 3600} 小时前"


__all__ = [
    "DISABLED_TEXT",
    "MAX_TABLE_LINES",
    "NOTICE_SOURCE",
    "NO_GATEWAY_TEXT",
    "NO_ROUTER_TEXT",
    "DshRouterService",
    "Proposal",
]
