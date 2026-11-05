"""Router 模式的工具面裁剪、执行期兜底与任务表注入。"""

from __future__ import annotations

import json
from types import SimpleNamespace

from neobot_app.config.schemas.bot_parts.agent import Agent
from neobot_app.reply.orchestrator_parts.prompt_blocks import PromptBlocksMixin
from neobot_app.reply.tools import ReplyToolExecutor
from neobot_app.runtime.router_mode import RouterModeService


def _router_config(**overrides):
    config = SimpleNamespace(allowed_tools=["read", "send_reply"], inject_task_table=True)
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def _make_executor(
    *,
    service: RouterModeService | None = None,
    conv_id: str = "123",
    router_config=None,
) -> ReplyToolExecutor:
    return ReplyToolExecutor(
        conv_kind="group",
        conv_id=conv_id,
        poke_user_handler=lambda **_kwargs: None,
        router_mode=service,
        router_config=router_config or _router_config(),
    )


def _tool_names(executor: ReplyToolExecutor) -> list[str]:
    return [definition["function"]["name"] for definition in executor.definitions()]


def test_dsh_config_is_opt_in_by_default():
    agent = Agent()

    assert agent.dsh.gateway.enabled is False
    assert agent.dsh.gateway.host == "127.0.0.1"
    assert agent.dsh.router.enabled is False
    assert agent.dsh.router.inject_task_table is True
    assert "read" in agent.dsh.router.allowed_tools
    assert "write" not in agent.dsh.router.allowed_tools


def test_router_mode_hides_execution_tools_and_keeps_reply_tools():
    service = RouterModeService()
    executor = _make_executor(service=service)

    # 未激活：普通工具面（poke_user 来自注入的 handler）
    assert "poke_user" in _tool_names(executor)

    service.activate("group:123")
    names = _tool_names(executor)

    assert "poke_user" not in names
    assert "send_reply" in names
    assert "split_reply" in names


def test_router_mode_is_scoped_to_one_chat_flow():
    service = RouterModeService()
    service.activate("group:123")

    active_executor = _make_executor(service=service, conv_id="123")
    other_executor = _make_executor(service=service, conv_id="456")

    assert "poke_user" not in _tool_names(active_executor)
    assert "poke_user" in _tool_names(other_executor)


async def test_router_mode_denies_execution_at_runtime():
    service = RouterModeService()
    service.activate("group:123")
    executor = _make_executor(service=service)

    result = await executor.execute("poke_user", {"user_id": 10001})

    payload = json.loads(result)
    assert payload["ok"] is False
    assert payload["code"] == "ROUTER_MODE_DENIED"


def test_router_mode_allows_dsh_tools_and_configured_tools():
    service = RouterModeService()
    service.activate("group:123")
    executor = _make_executor(service=service)

    assert executor._router_tool_allowed("dsh_router__dispatch") is True
    assert executor._router_tool_allowed("read") is True
    assert executor._router_tool_allowed("send_reply") is True
    assert executor._router_tool_allowed("poke_user") is False
    assert executor._router_tool_allowed("agents__delegate") is False


class _PromptStub(PromptBlocksMixin):
    def __init__(self, service, *, inject: bool = True) -> None:
        self._router_mode = service
        self._config = SimpleNamespace(
            agent=SimpleNamespace(
                dsh=SimpleNamespace(router=_router_config(inject_task_table=inject))
            )
        )


def test_router_context_message_contains_task_table():
    service = RouterModeService()
    service.set_context_provider(lambda _key: "#1 running · 改 login 模块")
    service.activate("group:123")

    message = _PromptStub(service)._build_router_context_message("group:123")

    assert message is not None
    assert message["role"] == "user"
    assert "[Router 任务表]" in message["content"]
    assert "#1 running" in message["content"]


def test_router_context_message_absent_when_inactive_or_disabled():
    service = RouterModeService()
    service.set_context_provider(lambda _key: "#1 running")

    assert _PromptStub(service)._build_router_context_message("group:123") is None

    service.activate("group:123")
    assert (
        _PromptStub(service, inject=False)._build_router_context_message("group:123")
        is None
    )
