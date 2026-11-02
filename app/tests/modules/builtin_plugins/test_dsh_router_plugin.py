"""dsh_router 插件入口：真 modloader 装载、缺服务降级、生命周期清理、归属性校验。

两类测试：

1. 直接用假 ctx 调 ``on_load/on_startup/on_shutdown``（快，能断言接线细节）；
2. 用真 ``PluginRuntime`` 装一份插件副本（能断言最终工具名 ``dsh_router__*``
   与 /dsh 命令真的进了宿主注册表）。
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from neobot_app.builtin_plugins import dsh_router
from neobot_app.builtin_plugins.dsh_router import tools
from neobot_app.commands.registry import CommandRegistry
from neobot_app.dsh_gateway.models import SyncReport
from neobot_app.skills.base import SkillManager
from neobot_contracts.ports.logging import NullLogger
from neobot_modloader.context import PluginCommandRegistrar
from neobot_modloader.host import DefaultServiceRegistry, PluginHostFacade
from neobot_modloader.runtime import PluginRuntime

from test_dsh_router_service import FakeGateway, FakeHub, FakeRouterMode


class _Services:
    """只实现插件会用到的那一个方法。"""

    def __init__(self, mapping: dict[str, Any]) -> None:
        self._mapping = mapping

    def get(self, name: str, default: Any = None) -> Any:
        return self._mapping.get(name, default)


def _task_id(text: str) -> str:
    match = re.search(r"dsh-[0-9a-f]{8}", text)
    assert match is not None, text
    return match.group(0)


def _make_ctx(tmp_path: Path, services: dict[str, Any], *, workspaces: list[str] | None = None):
    registrar = PluginCommandRegistrar(
        plugin_name="dsh_router",
        registry=CommandRegistry(),
        record_cleanup=None,
        logger=NullLogger(),
    )
    ctx = SimpleNamespace(
        plugin_name="dsh_router",
        data_dir=tmp_path / "data",
        config={"workspaces": workspaces} if workspaces is not None else {},
        logger=NullLogger(),
        plugin_host=SimpleNamespace(services=_Services(services)),
        app_commands=registrar,
    )
    return ctx, registrar


@pytest.fixture()
def wired(tmp_path: Path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    gateway = FakeGateway()
    router = FakeRouterMode()
    hub = FakeHub()
    ctx, registrar = _make_ctx(
        tmp_path,
        {"dsh_gateway": gateway, "router_mode": router, "notification_hub": hub},
        workspaces=[str(workspace)],
    )
    return SimpleNamespace(
        ctx=ctx,
        registrar=registrar,
        gateway=gateway,
        router=router,
        hub=hub,
        workspace=workspace,
        tmp=tmp_path,
    )


async def test_on_load_wires_services_tools_and_commands(wired) -> None:
    await dsh_router._on_load(wired.ctx)
    try:
        service = dsh_router.state.service
        assert service is not None and tools.get_service() is service
        assert wired.gateway.handlers["dsh_router"] is service
        assert wired.router.provider == service.task_table
        # Router 模式预激活 dsh_router 技能（核心无该钩子时这一行在别处会被跳过）
        assert wired.router.required == ("dsh_router",)

        command = wired.registrar._registry.get("dsh")
        assert command is not None and command.permission == 2
        assert command.source == "dsh_router"

        names = [registration.name for registration in dsh_router.plugin._tool_registrations]
        assert names == ["propose", "dispatch", "tasks", "status", "send", "cancel", "approve", "exit"]

        # 走工具层跑一遍：propose -> dispatch 会入队命令并唤醒已知 daemon
        await service.on_reports("devbox-01", [SyncReport(kind="daemon.health", payload={"sessions": 1})])
        proposed = await tools.propose(
            task="修一个 bug", cwd=str(wired.workspace), pipeline_key="private:1001", _requester_id=1001
        )
        assert "【DSH 任务提案】" in proposed
        dispatched = await tools.dispatch(pipeline_key="private:1001", _requester_id=1001)
        assert dispatched.startswith("已派发 DSH 任务 dsh-")
        assert wired.gateway.notified == ["devbox-01"]
        commands = await service.drain_commands("devbox-01")
        assert commands[-1].kind == "task.dispatch"
    finally:
        await dsh_router._on_shutdown(wired.ctx)


async def test_missing_services_degrade_without_crashing(tmp_path: Path) -> None:
    ctx, registrar = _make_ctx(tmp_path, {})
    await dsh_router._on_load(ctx)
    try:
        assert registrar._registry.get("dsh") is not None
        text = await tools.dispatch(pipeline_key="private:1001", _requester_id=1001)
        assert "DSH 网关未启用" in text
        assert await tools.tasks(pipeline_key="private:1001") == "当前会话没有 DSH 任务。"
        assert "Router 模式服务未启用" in await tools.exit(pipeline_key="private:1001")
    finally:
        await dsh_router._on_shutdown(ctx)
    assert tools.get_service() is None


async def test_tools_require_chat_context(wired) -> None:
    await dsh_router._on_load(wired.ctx)
    try:
        assert await tools.propose(task="x") == tools.NO_CHAT_TEXT
        assert await tools.tasks() == tools.NO_CHAT_TEXT
    finally:
        await dsh_router._on_shutdown(wired.ctx)


async def test_owner_guard_on_send_cancel_and_approve(wired) -> None:
    await dsh_router._on_load(wired.ctx)
    try:
        await tools.propose(task="修 bug", pipeline_key="private:1001", _requester_id=1001)
        dispatched = await tools.dispatch(pipeline_key="private:1001", _requester_id=1001)
        task_id = _task_id(dispatched)

        # 非 owner 被拒
        assert (
            await tools.send(task_id, "hi", pipeline_key="private:1001", _requester_id=2002) == tools.OWNER_DENIED_TEXT
        )
        assert await tools.cancel(task_id, pipeline_key="private:1001", _requester_id=2002) == tools.OWNER_DENIED_TEXT
        # 后台触发（requester 为空）放行
        assert "已把输入转给" in await tools.send(task_id, "hi", pipeline_key="private:1001")
        # owner 本人放行
        assert "已请求取消" in await tools.cancel(task_id, pipeline_key="private:1001", _requester_id=1001)
    finally:
        await dsh_router._on_shutdown(wired.ctx)


async def test_exit_tool_refuses_while_tasks_active(wired) -> None:
    await dsh_router._on_load(wired.ctx)
    try:
        await tools.propose(task="修 bug", pipeline_key="private:1001", _requester_id=1001)
        dispatched = await tools.dispatch(pipeline_key="private:1001", _requester_id=1001)
        task_id = _task_id(dispatched)
        blocked = await tools.exit(pipeline_key="private:1001", _requester_id=1001)
        assert "未结束任务" in blocked
        dsh_router.state.service.store.update(task_id, status="done")
        assert "已退出 Router 模式" in await tools.exit(pipeline_key="private:1001", _requester_id=1001)
        assert not wired.router.is_active("private:1001")
    finally:
        await dsh_router._on_shutdown(wired.ctx)


async def test_heartbeat_starts_and_is_cancelled(wired) -> None:
    await dsh_router._on_load(wired.ctx)
    await dsh_router._on_startup(wired.ctx)
    heartbeat = dsh_router.state.heartbeat
    assert heartbeat is not None and not heartbeat.done()
    await dsh_router._on_shutdown(wired.ctx)
    assert dsh_router.state.heartbeat is None
    assert heartbeat.done()
    assert wired.gateway.handlers == {}
    assert wired.router.provider is None
    assert wired.router.required == ()


class _LoggerFactory:
    def get_logger(self, name: str) -> NullLogger:
        return NullLogger()


async def test_real_runtime_registers_prefixed_tools_and_command(tmp_path: Path) -> None:
    """真 modloader 装一份插件副本：验证最终工具名与 /dsh 注册结果。"""
    source = Path(dsh_router.__file__).parent
    plugin_dir = tmp_path / "plugins" / "dsh_router"
    shutil.copytree(source, plugin_dir, ignore=shutil.ignore_patterns("__pycache__"))

    gateway = FakeGateway()
    router = FakeRouterMode()
    hub = FakeHub()
    services = DefaultServiceRegistry()
    services.register("dsh_gateway", gateway)
    services.register("router_mode", router)
    services.register("notification_hub", hub)
    skills = SkillManager()
    host = PluginHostFacade(services=services, skills=skills)
    registry = CommandRegistry()

    runtime = PluginRuntime(
        plugin_dir=plugin_dir.parent,
        data_dir=tmp_path / "data",
        adapter=SimpleNamespace(),
        logger_factory=_LoggerFactory(),
        host=host,
        app_commands=registry,
    )
    runtime.load_all()
    await runtime.load_registered()
    await runtime.start_all()
    try:
        assert gateway.handlers.get("dsh_router") is not None
        assert router.provider is not None
        tool_names = {definition["function"]["name"] for definition in skills.get_tools()}
        assert {
            "dsh_router__propose",
            "dsh_router__dispatch",
            "dsh_router__tasks",
            "dsh_router__status",
            "dsh_router__send",
            "dsh_router__cancel",
            "dsh_router__approve",
            "dsh_router__exit",
        } <= tool_names
        command = registry.get("dsh")
        assert command is not None and command.permission == 2
    finally:
        await runtime.stop_all()
    assert gateway.handlers == {}
    assert router.provider is None
