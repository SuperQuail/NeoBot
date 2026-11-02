"""dsh_router 服务层：提案校验 / 派发 / 命令 / 通知节流 / 回收。

全部用替身：网关只记录注册与唤醒、Router 模式只记激活、通知中枢可模拟发言策略拦截。
时间由可注入时钟控制，不 sleep。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import re

import pytest

from neobot_app.builtin_plugins.dsh_router.config import DshRouterConfig
from neobot_app.builtin_plugins.dsh_router.service import DshRouterService
from neobot_app.builtin_plugins.dsh_router.store import TaskRecord, TaskStore
from neobot_app.dsh_gateway.models import SyncReport
from neobot_contracts.ports.speaking import SpeechBlocked


class FakeGateway:
    def __init__(self) -> None:
        self.handlers: dict[str, object] = {}
        self.notified: list[str] = []

    def register_handler(self, name: str, handler: object) -> None:
        self.handlers[name] = handler

    def unregister_handler(self, name: str) -> bool:
        return self.handlers.pop(name, None) is not None

    def notify(self, daemon_id: str) -> None:
        self.notified.append(daemon_id)


class FakeRouterMode:
    def __init__(self) -> None:
        self.sessions: dict[str, SimpleNamespace] = {}
        self.provider = None
        self.deactivated: list[tuple[str, str]] = []
        self.required: tuple[str, ...] = ()

    def set_context_provider(self, provider) -> None:
        self.provider = provider

    def set_required_skills(self, names) -> None:
        self.required = tuple(str(item) for item in (names or ()) if str(item).strip())

    def activate(self, pipeline_key, *, owner_user_id=None, task_ids=(), reason=""):
        self.sessions[pipeline_key] = SimpleNamespace(
            pipeline_key=pipeline_key,
            owner_user_id=owner_user_id,
            task_ids=tuple(task_ids),
            reason=reason,
        )

    def deactivate(self, pipeline_key, *, reason="") -> bool:
        self.deactivated.append((pipeline_key, reason))
        return self.sessions.pop(pipeline_key, None) is not None

    def is_active(self, pipeline_key) -> bool:
        return pipeline_key in self.sessions

    def session(self, pipeline_key):
        return self.sessions.get(pipeline_key)

    def snapshot(self):
        return [{"pipeline_key": key, "owner_user_id": value.owner_user_id} for key, value in self.sessions.items()]


class FakeHub:
    def __init__(self, *, blocked: bool = False) -> None:
        self.published: list[dict] = []
        self.blocked = blocked

    async def publish(self, **kwargs):
        if self.blocked:
            raise SpeechBlocked("不在发言时段")
        self.published.append(kwargs)
        return True


class Clock:
    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    (root / "proj").mkdir(parents=True)
    return root


@pytest.fixture()
def env(tmp_path: Path, workspace: Path):
    clock = Clock()
    gateway = FakeGateway()
    router = FakeRouterMode()
    hub = FakeHub()
    config = DshRouterConfig(workspaces=[str(workspace)])
    store = TaskStore(tmp_path / "data" / "tasks.json")
    service = DshRouterService(
        config=config,
        store=store,
        gateway=gateway,
        router_mode=router,
        notification_hub=hub,
        clock=clock,
    )
    return SimpleNamespace(
        service=service,
        config=config,
        store=store,
        gateway=gateway,
        router=router,
        hub=hub,
        clock=clock,
        workspace=workspace,
        tmp=tmp_path,
    )


PIPELINE = "private:1001"


def _propose(env, *, task: str = "修一个 bug", cwd: str = "", mode: str = "write") -> str:
    return env.service.propose(PIPELINE, 1001, task, cwd=cwd, mode=mode)


def _dispatch(env, **kwargs) -> str:
    return env.service.dispatch(PIPELINE, 1001, **kwargs)


def _task_id(text: str) -> str:
    match = re.search(r"dsh-[0-9a-f]{8}", text)
    assert match is not None, text
    return match.group(0)


# ── 提案 ────────────────────────────────────────────────────────


def test_propose_rejects_empty_workspaces(env) -> None:
    env.service._config = DshRouterConfig(workspaces=[])
    text = _propose(env, cwd=str(env.workspace))
    assert "未配置工作区" in text
    assert _dispatch(env).startswith("还没有有效的任务提案")


def test_propose_rejects_cwd_outside_workspace(env) -> None:
    outside = env.tmp / "outside"
    outside.mkdir()
    text = _propose(env, cwd=str(outside))
    assert "必须在 config.workspaces 之内" in text


def test_propose_accepts_subdirectory_and_defaults_to_single_workspace(env) -> None:
    nested = env.workspace / "proj"
    text = _propose(env, cwd=str(nested))
    assert "【DSH 任务提案】" in text
    assert str(nested.resolve()) in text
    # 只有一个工作区时可以省 cwd
    assert "【DSH 任务提案】" in _propose(env)


def test_propose_rejects_unknown_mode(env) -> None:
    assert "不支持的模式" in _propose(env, mode="admin")


def test_proposal_expires(env) -> None:
    _propose(env)
    env.clock.advance(11 * 60)
    assert "还没有有效的任务提案" in _dispatch(env)


# ── 派发 ────────────────────────────────────────────────────────


async def test_dispatch_requires_proposal(env) -> None:
    assert "propose" in _dispatch(env)


async def test_dispatch_enqueues_command_and_activates_router(env) -> None:
    _propose(env)
    text = _dispatch(env)
    assert text.startswith("已派发 DSH 任务 dsh-")
    task_id = _task_id(text)

    commands = await env.service.drain_commands("devbox-01")
    assert len(commands) == 1
    command = commands[0]
    assert command.kind == "task.dispatch"
    assert command.task_id == task_id
    assert command.payload["mode"] == "write"
    assert command.payload["prompt"] == "修一个 bug"
    assert command.payload["cwd"] == str(env.workspace.resolve())

    record = env.store.get(task_id)
    assert record is not None and record.status == "dispatched"
    assert env.router.is_active(PIPELINE)
    assert env.router.sessions[PIPELINE].task_ids == (task_id,)
    assert env.router.sessions[PIPELINE].owner_user_id == 1001

    # 提案已消费，再派发必须重新提案
    assert "还没有有效的任务提案" in _dispatch(env)


async def test_dispatch_rejects_mismatched_task(env) -> None:
    _propose(env, task="任务 A")
    assert "不一致" in _dispatch(env, task="任务 B")


async def test_dispatch_respects_max_tasks_per_chat(env) -> None:
    env.service._config = DshRouterConfig(workspaces=[str(env.workspace)], max_tasks_per_chat=1)
    _propose(env, task="第一个")
    assert _dispatch(env).startswith("已派发")
    _propose(env, task="第二个")
    assert "上限" in _dispatch(env)
    assert len(env.store.list(PIPELINE)) == 1


# ── 输入 / 取消 / 审批 ──────────────────────────────────────────


async def test_send_enqueues_input(env) -> None:
    _propose(env)
    task_id = _task_id(_dispatch(env))
    await env.service.drain_commands("devbox-01")
    env.gateway.notified.clear()
    text = env.service.send(task_id, "先跑测试", mode="queue")
    assert "mode=queue" in text
    commands = await env.service.drain_commands("devbox-01")
    assert [(item.kind, item.payload["text"], item.payload["mode"]) for item in commands] == [
        ("task.input", "先跑测试", "queue")
    ]


async def test_send_rejects_finished_task(env) -> None:
    _propose(env)
    task_id = _task_id(_dispatch(env))
    env.store.update(task_id, status="done")
    assert "已结束" in env.service.send(task_id, "还在吗")


async def test_cancel_enqueues_and_marks_cancelling(env) -> None:
    _propose(env)
    task_id = _task_id(_dispatch(env))
    assert "已请求取消" in env.service.cancel(task_id, "不需要了")
    commands = await env.service.drain_commands("devbox-01")
    assert commands[-1].kind == "task.cancel"
    assert commands[-1].payload["reason"] == "不需要了"
    record = env.store.get(task_id)
    assert record.status == "cancelling"
    # 时间戳走注入时钟，reap 的 stale 判断才不会和测试时钟错位
    assert record.updated_at == env.clock.now


async def test_approve_clears_pending_and_enqueues_answer(env) -> None:
    _propose(env)
    task_id = _task_id(_dispatch(env))
    env.store.update(
        task_id,
        pending_permission={"request_id": "req-1", "prompt": "可以删库吗", "created_at": 1000},
    )
    assert env.service.find_by_request("req-1") is not None
    assert "已允许" in env.service.approve("req-1", True)
    commands = await env.service.drain_commands("devbox-01")
    assert commands[-1].kind == "perm.answer"
    assert commands[-1].payload == {"request_id": "req-1", "allow": True}
    assert env.store.get(task_id).pending_permission is None


# ── 报告：事件节流 / 完成 / 审批 ────────────────────────────────


async def test_events_are_throttled(env) -> None:
    _propose(env)
    task_id = _task_id(_dispatch(env))
    await env.service.on_reports(
        "devbox-01",
        [SyncReport(kind="task.event", task_id=task_id, payload={"phase": "progress", "summary": "第一步"})],
    )
    assert len(env.hub.published) == 1
    await env.service.on_reports(
        "devbox-01",
        [SyncReport(kind="task.event", task_id=task_id, payload={"phase": "progress", "summary": "第二步"})],
    )
    assert len(env.hub.published) == 1
    env.clock.advance(env.config.event_min_interval_seconds)
    await env.service.on_reports(
        "devbox-01",
        [SyncReport(kind="task.event", task_id=task_id, payload={"phase": "stage", "summary": "第三步"})],
    )
    assert len(env.hub.published) == 2
    assert env.store.get(task_id).summary == "第三步"


async def test_blocker_event_bypasses_throttle(env) -> None:
    _propose(env)
    task_id = _task_id(_dispatch(env))
    await env.service.on_reports(
        "devbox-01", [SyncReport(kind="task.event", task_id=task_id, payload={"phase": "progress"})]
    )
    await env.service.on_reports(
        "devbox-01",
        [SyncReport(kind="task.event", task_id=task_id, payload={"phase": "blocker", "summary": "缺凭据"})],
    )
    assert len(env.hub.published) == 2
    assert env.hub.published[-1]["metadata"]["phase"] == "blocker"


async def test_done_updates_status_and_summary(env) -> None:
    _propose(env)
    task_id = _task_id(_dispatch(env))
    await env.service.on_reports(
        "devbox-01",
        [SyncReport(kind="task.done", task_id=task_id, payload={"ok": True, "summary": "改完了"})],
    )
    record = env.store.get(task_id)
    assert (record.status, record.summary) == ("done", "改完了")
    assert env.hub.published[-1]["metadata"]["noticeKind"] == "done"


async def test_failed_done_in_private_chat_forces_publish(env) -> None:
    _propose(env)
    task_id = _task_id(_dispatch(env))
    await env.service.on_reports(
        "devbox-01",
        [SyncReport(kind="task.done", task_id=task_id, payload={"ok": False, "summary": "编译失败"})],
    )
    assert env.store.get(task_id).status == "failed"
    assert env.hub.published[-1]["force"] is True
    assert env.hub.published[-1]["kind"] == "private"


async def test_group_task_done_does_not_force(env) -> None:
    env.service.propose("group:777", 1001, "群里的任务")
    task_id = _task_id(env.service.dispatch("group:777", 1001))
    await env.service.on_reports(
        "devbox-01",
        [SyncReport(kind="task.done", task_id=task_id, payload={"ok": False})],
    )
    assert env.hub.published[-1]["force"] is False


async def test_perm_request_sets_pending_and_notifies(env) -> None:
    _propose(env)
    task_id = _task_id(_dispatch(env))
    await env.service.on_reports(
        "devbox-01",
        [
            SyncReport(
                kind="perm.request",
                task_id=task_id,
                id="r-1",
                payload={"request_id": "req-9", "prompt": "能改 config 吗"},
            )
        ],
    )
    record = env.store.get(task_id)
    assert record.pending_permission["request_id"] == "req-9"
    assert env.hub.published[-1]["metadata"]["noticeKind"] == "permission"
    assert env.hub.published[-1]["force"] is True


async def test_group_notice_blocked_by_speech_policy_falls_to_pending(env) -> None:
    env.hub.blocked = True
    env.service.propose("group:777", 1001, "群里的任务")
    task_id = _task_id(env.service.dispatch("group:777", 1001))
    await env.service.on_reports(
        "devbox-01",
        [SyncReport(kind="perm.request", task_id=task_id, id="r-1", payload={"prompt": "能改吗"})],
    )
    assert env.hub.published == []
    pending = env.service.pending_notices("group:777")
    assert len(pending) == 1 and pending[0]["kind"] == "permission"
    text = env.service.pending_text("group:777")
    assert "待处理" in text and "能改吗" in text


async def test_health_report_is_stored(env) -> None:
    await env.service.on_reports("devbox-01", [SyncReport(kind="daemon.health", payload={"sessions": 2})])
    assert env.service.health()["devbox-01"] == {"sessions": 2}


# ── 任务表 / 回收 ───────────────────────────────────────────────


async def test_task_table_lists_active_tasks_only(env) -> None:
    assert env.service.task_table(PIPELINE) is None
    _propose(env)
    task_id = _task_id(_dispatch(env))
    await env.service.on_reports(
        "devbox-01",
        [SyncReport(kind="task.event", task_id=task_id, payload={"phase": "stage", "summary": "正在改 store"})],
    )
    table = env.service.task_table(PIPELINE)
    assert table is not None
    assert task_id in table and "running" in table and "正在改 store" in table
    assert len(table.splitlines()) <= 8
    # 结束后不再注入
    await env.service.on_reports("devbox-01", [SyncReport(kind="task.done", task_id=task_id, payload={"ok": True})])
    assert env.service.task_table(PIPELINE) is None


async def test_reap_marks_stale(env) -> None:
    _propose(env)
    task_id = _task_id(_dispatch(env))
    env.clock.advance(env.config.task_stale_seconds + 1)
    stale = await env.service.reap()
    assert stale == [task_id]
    assert env.store.get(task_id).status == "stale"


async def test_reap_deactivates_idle_router(env) -> None:
    _propose(env)
    task_id = _task_id(_dispatch(env))
    await env.service.on_reports("devbox-01", [SyncReport(kind="task.done", task_id=task_id, payload={"ok": True})])
    env.clock.advance(env.config.auto_exit_idle_minutes * 60 + 1)
    await env.service.reap()
    assert not env.router.is_active(PIPELINE)
    assert env.router.deactivated


async def test_reap_keeps_router_when_task_active(env) -> None:
    # 把 stale 窗口调大，只验证「有活跃任务时不做空闲退出」
    env.service._config = DshRouterConfig(
        workspaces=[str(env.workspace)], task_stale_seconds=7200, auto_exit_idle_minutes=30
    )
    _propose(env)
    _dispatch(env)
    env.clock.advance(env.config.auto_exit_idle_minutes * 60 + 1)
    await env.service.reap()
    assert env.router.is_active(PIPELINE)


async def test_overview_reports_mode_and_tasks(env) -> None:
    _propose(env)
    _dispatch(env)
    text = env.service.overview(PIPELINE)
    assert "Router 模式：已启用" in text
    assert "活跃 1" in text


async def test_exit_mode_deactivates(env) -> None:
    _propose(env)
    _dispatch(env)
    env.store.update(env.store.active(PIPELINE)[0].task_id, status="done")
    assert "已退出 Router 模式" in env.service.exit_mode(PIPELINE)
    assert not env.router.is_active(PIPELINE)


# ── 存储 ───────────────────────────────────────────────────────


def test_store_roundtrip_and_corruption(tmp_path: Path) -> None:
    path = tmp_path / "tasks.json"
    store = TaskStore(path)
    store.create(TaskRecord(task_id="dsh-1", pipeline_key=PIPELINE, status="dispatched"))
    reloaded = TaskStore(path)
    assert reloaded.get("dsh-1").pipeline_key == PIPELINE

    path.write_text("{不是 JSON", encoding="utf-8")
    broken = TaskStore(path)
    assert broken.all() == []


# ── 与 daemon bundle 的 payload 兼容 ──────────────────────────────


async def test_event_payload_text_is_used(env) -> None:
    """bundle 侧 task.event 用 payload.text（不是 summary），不能被丢掉。"""
    _propose(env)
    task_id = _task_id(_dispatch(env))
    env.hub.published.clear()

    await env.service.on_reports(
        "devbox-01",
        [
            SyncReport(
                kind="task.event",
                task_id=task_id,
                payload={"phase": "stage", "text": "改了 3 个文件"},
            )
        ],
    )

    record = env.store.get(task_id)
    assert record is not None
    assert "改了 3 个文件" in record.summary
    assert any("改了 3 个文件" in item["content"] for item in env.hub.published)


async def test_done_outcome_failed_and_cancelled(env) -> None:
    """bundle 的 task.done 用 outcome 表达失败/取消，不能一律当成完成。"""
    _propose(env, task="任务一")
    failed_id = _task_id(_dispatch(env))
    await env.service.on_reports(
        "devbox-01",
        [
            SyncReport(
                kind="task.done",
                task_id=failed_id,
                payload={"outcome": "failed", "summary": "测试没过"},
            )
        ],
    )
    assert env.store.get(failed_id).status == "failed"
    assert env.hub.published[-1]["force"] is True

    env.router.sessions.clear()
    env.clock.advance(60)
    _propose(env, task="任务二")
    cancelled_id = _task_id(_dispatch(env))
    await env.service.on_reports(
        "devbox-01",
        [
            SyncReport(
                kind="task.done",
                task_id=cancelled_id,
                payload={"outcome": "cancelled", "summary": "用户取消"},
            )
        ],
    )
    assert env.store.get(cancelled_id).status == "cancelled"


async def test_permission_payload_action_and_detail(env) -> None:
    """bundle 的 perm.request 用 action/detail，审批文案要带上。"""
    _propose(env)
    task_id = _task_id(_dispatch(env))
    env.hub.published.clear()

    await env.service.on_reports(
        "devbox-01",
        [
            SyncReport(
                kind="perm.request",
                id="r-1",
                task_id=task_id,
                payload={
                    "request_id": "req-9",
                    "action": "写入授权目录之外",
                    "detail": "/etc/hosts",
                    "timeout_seconds": 600,
                },
            )
        ],
    )

    record = env.store.get(task_id)
    assert record is not None
    assert record.pending_permission["request_id"] == "req-9"
    assert "写入授权目录之外" in record.pending_permission["prompt"]
    assert "/etc/hosts" in record.pending_permission["prompt"]
    assert env.hub.published[-1]["force"] is True
