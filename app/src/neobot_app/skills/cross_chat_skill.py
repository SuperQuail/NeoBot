"""CrossChatSkill — 跨聊天通信 Skill（纯工具，无独立 LLM）。

投递语义（旧实现是错的，见下）：
    task 是「交给目标聊天**主 agent** 的任务」，不是要发到那个聊天的消息。
    投递走后台回复管线（ReplyOrchestrator.start_background_reply /
    BackgroundNotificationHub.publish），由目标聊天的主 agent 自己决定怎么回复。

    旧实现直接把 task 原文交给 adapter.send_group_msg/send_private_msg，于是
    「给 agent 的任务书」被原样贴进了目标聊天；工具描述还要求模型把
    [mode: ...] / [notify: ...] 写进 task，这些标记也跟着一起发到群里。
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neobot_app.skills.base import SkillModule

#: wait 模式等待目标聊天回复的上限。目标聊天要跑完整条回复管线（建提示词、
#: 调模型、发送），给太短会把「还没开始」误判成失败。
DEFAULT_WAIT_TIMEOUT_SECONDS = 90.0
_REPLY_POLL_INTERVAL_SECONDS = 0.2
_MAX_TRACKED_TASKS = 50
_MARKER_VALUE = r"[A-Za-z0-9_-]{1,24}"


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


# ── 旧式标记兜底 ───────────────────────────────────────────────────────────
#
# 旧工具描述要求模型把调用模式写进 task（"[mode: wait] [notify: response] ..."），
# 现在改成结构化参数。但模型会从对话历史里继续照抄旧写法，所以这里只做宽容兜底：
# 认出**开头连续一串**旧标记就取出来当参数用并删掉，避免它作为任务正文交给目标
# agent（进而在目标聊天里被复述）。值限定 ASCII 词，所以「[mode: 是什么]」这类
# 正常句子不会被吃掉。
_MARKER = re.compile(
    r"^\s*[\[【]?\s*(?P<key>mode|call_mode|notify|notification|notification_mode)"
    r"\s*[:：]\s*(?P<value>" + _MARKER_VALUE + r")\s*[\]】]?\s*",
    re.IGNORECASE,
)
_MARKER_KINDS = {
    "mode": "mode",
    "call_mode": "mode",
    "notify": "notification_mode",
    "notification": "notification_mode",
    "notification_mode": "notification_mode",
}


def extract_leading_markers(task: str) -> tuple[str, dict[str, str]]:
    """取出 task 开头的旧式调用模式标记，返回 (任务正文, {参数名: 值})。"""
    markers: dict[str, str] = {}
    rest = str(task or "")
    while True:
        match = _MARKER.match(rest)
        if match is None:
            return rest.strip(), markers
        markers[_MARKER_KINDS[match["key"].casefold()]] = match["value"].casefold()
        rest = rest[match.end():]


def _canonical_mode(value: Any) -> str:
    compact = re.sub(r"[^a-z0-9]", "", str(value or "").casefold())
    return "wait" if compact == "wait" else "fire_and_forget"


def _canonical_notification(value: Any) -> str:
    compact = re.sub(r"[^a-z0-9]", "", str(value or "").casefold())
    return "response" if compact == "response" else "no_response"


def _parse_pipeline_key(value: Any) -> tuple[str, str] | None:
    """解析宿主注入的 pipeline_key（"{kind}:{id}"）；只在 kind 合法时采信。"""
    text = str(value or "").strip()
    kind, _, conversation_id = text.partition(":")
    if kind in ("group", "private") and conversation_id:
        return kind, conversation_id
    return None


@dataclass
class _CrossChatTask:
    task_id: str
    target: str
    mode: str
    notification_mode: str
    status: str
    detail: str = ""
    reply: str = ""
    created_at: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "target": self.target,
            "mode": self.mode,
            "notification_mode": self.notification_mode,
            "status": self.status,
            "detail": self.detail,
            "reply": self.reply,
        }


class CrossChatSkill(SkillModule):
    """跨聊天通信 Skill — 把任务交给其他群/私聊的主 agent，并查询其他聊天记录。"""

    @property
    def name(self) -> str:
        return "cross_chat"

    @property
    def description(self) -> str:
        return "跨聊天通信：把任务交给其他群/私聊的主 agent 处理，查询其他聊天的记录"

    @property
    def instructions(self) -> str:
        return (
            "跨聊天通信 Skill 提供以下能力：\n\n"
            "## cross_chat_send\n"
            "把任务交给目标聊天的主 agent，由**它**决定怎么回复；参数不会被当成消息\n"
            "直接发到那个聊天。task 只写要传达的内容本身，不要写调用模式、\n"
            "不要带 [mode: ...] / [notify: ...] 这类标记 —— 模式用 mode 与\n"
            "notification_mode 参数表达。\n"
            "mode=fire_and_forget（默认）投递后立即返回；mode=wait 等目标 agent 出结果。\n"
            "notification_mode=no_response（默认）不回传；response 会把目标 agent 的\n"
            "回复回传到本聊天。\n\n"
            "## cross_chat_query\n"
            "查询指定聊天的聊天记录，了解其他聊天的讨论内容。\n"
            "任务示例：「获取群123456最近在聊什么」\n\n"
            "注意：收到跨聊天回复回传时，应直接回复，不要再次委托本 skill。"
        )

    def __init__(
        self,
        config: Any = None,
        adapter: Any = None,
        group_message_queue: Any = None,
        friend_message_queue: Any = None,
        notification_hub: Any = None,
        orchestrator: Any = None,
        wait_timeout_seconds: float = DEFAULT_WAIT_TIMEOUT_SECONDS,
    ) -> None:
        self._config = config
        self._adapter = adapter
        self._group_queue = group_message_queue
        self._friend_queue = friend_message_queue
        self._notification_hub = notification_hub
        self._orchestrator = orchestrator
        self._wait_timeout = float(wait_timeout_seconds)
        self._tasks: dict[str, _CrossChatTask] = {}
        self._watchers: set[asyncio.Task[None]] = set()

    def set_orchestrator(self, orchestrator: Any) -> None:
        self._orchestrator = orchestrator

    def set_notification_hub(self, hub: Any) -> None:
        self._notification_hub = hub

    def reset(self) -> None:
        # 只清任务档案：在途的结果回传不该因为开了新会话就被丢掉。
        self._tasks.clear()

    def get_tools(self) -> list[dict]:
        return [
            self._tool_def(
                "cross_chat_send",
                "把任务交给目标聊天的主 agent，由它自己决定怎么回复。"
                "参数只作为任务内容交给对方 agent，不会被当成消息直接发到那个聊天。"
                "task 只写要传达的内容本身，不要写调用模式、也不要带 "
                "[mode: ...] / [notify: ...] 这类标记；模式请用 mode 与 notification_mode 参数。",
                {
                    "properties": {
                        "target_kind": {
                            "type": "string", "enum": ["group", "private"],
                            "description": "目标聊天类型：group=群聊，private=私聊",
                        },
                        "target_id": {"type": "string", "description": "目标群号或QQ号"},
                        "task": {
                            "type": "string",
                            "description": "交给目标聊天主 agent 的任务内容，"
                            "例如：'告知群里明天上午十点集合'。只写要传达的内容本身，"
                            "不要写调用模式或通知模式，也不要带 [mode: ...] / [notify: ...] 标记。",
                        },
                        "mode": {
                            "type": "string", "enum": ["fire_and_forget", "wait"],
                            "description": "调用模式：fire_and_forget=投递后立即返回（默认），wait=等待目标聊天出结果",
                            "default": "fire_and_forget",
                        },
                        "notification_mode": {
                            "type": "string", "enum": ["no_response", "response"],
                            "description": "通知模式：no_response=不回传（默认），response=把目标聊天的回复回传到本聊天",
                            "default": "no_response",
                        },
                    },
                    "required": ["target_kind", "target_id", "task"],
                },
            ),
            self._tool_def(
                "cross_chat_query",
                "查询指定聊天的聊天记录，了解讨论内容或获取信息。",
                {
                    "properties": {
                        "target_kind": {
                            "type": "string", "enum": ["group", "private"],
                            "description": "目标聊天类型",
                        },
                        "target_id": {"type": "string", "description": "目标群号或QQ号"},
                        "query": {"type": "string", "description": "要查询的信息描述"},
                        "message_count": {"type": "integer", "description": "读取最近消息条数，默认 20", "default": 20},
                    },
                    "required": ["target_kind", "target_id", "query"],
                },
            ),
            self._tool_def(
                "cross_chat_status",
                "查询当前跨聊天通信任务的状态与回传结果。",
                {
                    "properties": {
                        "task_id": {"type": "string", "description": "可选，指定任务 ID"},
                    },
                    "required": [],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown cross_chat tool: {tool_name}"})
        return await handler(self, args)

    # ── 投递与回传 ─────────────────────────────────────────────────────

    def _remember(self, record: _CrossChatTask) -> None:
        self._tasks[record.task_id] = record
        while len(self._tasks) > _MAX_TRACKED_TASKS:
            oldest = min(self._tasks.values(), key=lambda item: item.created_at)
            self._tasks.pop(oldest.task_id, None)

    def _spawn(self, coro: Any) -> None:
        task = asyncio.create_task(coro)
        self._watchers.add(task)
        task.add_done_callback(self._watchers.discard)

    async def _deliver(
        self, kind: str, conversation_id: str, content: str, task_id: str,
        origin: tuple[str, str] | None,
    ) -> tuple[bool, Any, str]:
        """把任务交给目标聊天的主 agent，返回 (是否投递, ReplyEvent|None, 说明)。

        目标管线空闲时直接启动它并拿住 ReplyEvent，这样才能归属并取回回复；
        管线正忙时退化为通知注入（由 hub 排队），此时无法归属具体回复。
        """
        orchestrator = self._orchestrator
        if orchestrator is not None:
            try:
                event = orchestrator.start_background_reply(
                    kind=kind,
                    conversation_id=str(conversation_id),
                    content=content,
                    manager_name="cross_chat",
                    reasons=["跨聊天任务"],
                )
            except Exception as exc:
                return False, None, f"启动目标聊天回复失败：{type(exc).__name__}: {exc}"
            if event is not None:
                return True, event, "已交给目标聊天主 agent"

        hub = self._notification_hub
        if hub is None:
            return False, None, "跨聊天投递不可用：编排器与通知中心都不可用"
        try:
            await hub.publish(
                source="cross_chat",
                kind=kind,
                conversation_id=str(conversation_id),
                content=content,
                manager_name="cross_chat",
                reasons=["跨聊天任务"],
                metadata={
                    "task_id": task_id,
                    "origin": f"{origin[0]}:{origin[1]}" if origin else "",
                },
            )
        except Exception as exc:
            return False, None, f"通知中心投递失败：{type(exc).__name__}: {exc}"
        return True, None, "目标聊天正在回复中，任务已作为通知注入；本轮无法归属具体回复"

    async def _await_reply(self, event: Any, timeout: float) -> tuple[bool, str, str]:
        """等目标聊天的回复管线结束，返回 (是否结束, 回复正文, 说明)。"""
        deadline = time.monotonic() + max(0.0, timeout)
        while not getattr(event, "is_terminal", True):
            if time.monotonic() >= deadline:
                return False, "", f"等待目标聊天回复超时（{timeout:g}s）"
            await asyncio.sleep(_REPLY_POLL_INTERVAL_SECONDS)
        text = str(getattr(event, "generated_text", "") or "").strip()
        if text:
            return True, text, ""
        error = str(getattr(event, "error", "") or "").strip()
        return True, "", error or "目标聊天本轮没有产出正文"

    async def _publish_to_origin(
        self, origin: tuple[str, str], reply: str, task_id: str, detail: str = "",
    ) -> bool:
        """把目标聊天的回复回传到发起方聊天（由发起方 agent 决定怎么用）。"""
        hub = self._notification_hub
        if hub is None:
            return False
        kind, conversation_id = origin
        content = f"[跨聊天回复] {reply}" if reply else f"[跨聊天] 目标聊天未产出回复：{detail}"
        try:
            await hub.publish(
                source="cross_chat",
                kind=kind,
                conversation_id=conversation_id,
                content=content,
                manager_name="cross_chat",
                reasons=["跨聊天结果回传"],
                metadata={"task_id": task_id},
            )
        except Exception:
            return False
        return True

    async def _relay_later(
        self, record: _CrossChatTask, event: Any, origin: tuple[str, str],
    ) -> None:
        """fire_and_forget + response：后台等结果再回传，不阻塞发起方这一轮。"""
        finished, reply, detail = await self._await_reply(event, self._wait_timeout)
        record.reply = reply
        record.detail = detail
        record.status = "responded" if finished else "timeout"
        if finished:
            await self._publish_to_origin(origin, reply, record.task_id, detail)


# ── Handlers ──

async def _handle_cross_chat_send(self: CrossChatSkill, args: dict) -> str:
    target_kind = str(args.get("target_kind") or "").strip()
    target_id = str(args.get("target_id") or "").strip()
    raw_task = str(args.get("task") or "").strip()
    if not target_kind or not target_id or not raw_task:
        return _json({"ok": False, "error": "缺少必要参数 target_kind/target_id/task"})
    if target_kind not in ("group", "private"):
        return _json({"ok": False, "error": f"target_kind 必须是 group 或 private，收到 {target_kind!r}"})

    task_text, markers = extract_leading_markers(raw_task)
    mode = _canonical_mode(args.get("mode") if args.get("mode") else markers.get("mode"))
    notification_mode = _canonical_notification(
        args.get("notification_mode") if args.get("notification_mode") else markers.get("notification_mode")
    )
    if not task_text:
        return _json({
            "ok": False,
            "error": "task 里没有实际内容（只剩调用模式标记）。请写清楚要传达给目标聊天的内容。",
        })

    # pipeline_key 由宿主注入（模型伪造的一律被剥离），是发起方聊天的可信身份。
    origin = _parse_pipeline_key(args.get("pipeline_key"))
    task_id = uuid.uuid4().hex[:12]
    record = _CrossChatTask(
        task_id=task_id,
        target=f"{target_kind}:{target_id}",
        mode=mode,
        notification_mode=notification_mode,
        status="pending",
    )
    self._remember(record)

    delivered, event, detail = await self._deliver(
        target_kind, target_id, task_text, task_id, origin,
    )
    if not delivered:
        record.status = "failed"
        record.detail = detail
        return _json({"ok": False, "error": detail, "task_id": task_id})

    payload: dict[str, Any] = {
        "ok": True,
        "task_id": task_id,
        "mode": mode,
        "notification_mode": notification_mode,
        "target": record.target,
        "detail": detail,
    }

    if mode == "fire_and_forget":
        record.status = "delivered"
        payload["status"] = "delivered"
        if notification_mode == "response" and event is not None and origin is not None:
            self._spawn(self._relay_later(record, event, origin))
            payload["detail"] = detail + "；结果会在目标聊天回复后回传到本聊天"
        elif notification_mode == "response":
            payload["detail"] = detail + "；当前无法等待结果，不会回传"
        return _json(payload)

    # mode == "wait"：等目标聊天出结果，直接放进工具返回值。
    if event is None:
        record.status = "delegated"
        payload["status"] = "delegated"
        payload["detail"] = detail + "；无法等待具体回复，如需结果请稍后用 cross_chat_query 查看"
        return _json(payload)

    record.status = "waiting"
    finished, reply, wait_detail = await self._await_reply(event, self._wait_timeout)
    record.reply = reply
    record.detail = wait_detail
    if not finished:
        record.status = "timeout"
        payload["status"] = "timeout"
        payload["detail"] = wait_detail
        return _json(payload)

    record.status = "responded"
    payload["status"] = "responded"
    payload["reply"] = reply
    if wait_detail:
        payload["detail"] = wait_detail
    if notification_mode == "response" and origin is not None:
        relayed = await self._publish_to_origin(origin, reply, task_id, wait_detail)
        payload["relayed"] = relayed
    return _json(payload)


async def _handle_cross_chat_query(self: CrossChatSkill, args: dict) -> str:
    if self._adapter is None:
        return _json({"ok": False, "error": "adapter 未配置"})
    target_kind = str(args.get("target_kind", "")).strip()
    target_id = str(args.get("target_id", "")).strip()
    count = int(args.get("message_count", 20))
    try:
        queue = self._friend_queue if target_kind == "private" else self._group_queue
        if queue is None:
            return _json({"ok": False, "error": f"{target_kind} 类型的消息队列未配置"})

        if queue.size(target_id) == 0:
            if target_kind == "private":
                history = await self._adapter.get_friend_msg_history(int(target_id), count=count)
            else:
                history = await self._adapter.get_group_msg_history(int(target_id), count=count)
            messages = getattr(getattr(history, "data", None), "messages", None)
            if messages:
                for msg in messages:
                    queue.push_history(target_id, msg)

        text = queue.to_text(target_id)
        if not text:
            return _json({"ok": True, "history": f"（{target_kind} {target_id} 暂无消息记录）"})
        return _json({"ok": True, "history": text})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


async def _handle_cross_chat_status(self: CrossChatSkill, args: dict) -> str:
    task_id = str(args.get("task_id", "") or "").strip()
    if task_id:
        record = self._tasks.get(task_id)
        if record is None:
            return _json({"ok": True, "task_id": task_id, "status": "unknown", "note": "任务不存在或已被清理"})
        return _json({"ok": True, **record.as_dict()})
    tasks = sorted(self._tasks.values(), key=lambda item: item.created_at, reverse=True)
    return _json({"ok": True, "active_tasks": len(tasks), "tasks": [item.as_dict() for item in tasks]})


_HANDLERS = {
    "cross_chat_send": _handle_cross_chat_send,
    "cross_chat_query": _handle_cross_chat_query,
    "cross_chat_status": _handle_cross_chat_status,
}
