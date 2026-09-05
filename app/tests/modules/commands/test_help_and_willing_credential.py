"""help 命令 markdown 图片渲染 + 全局回复意愿凭据/配置工具测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from neobot_app.commands.builtin import (
    _render_command_detail_markdown,
    _render_command_list_markdown,
)
from neobot_app.commands.model import PERM_EVERYONE, PERM_SUB_ADMIN, Command


class _FakePerm:
    def __init__(self, allowed: bool = True) -> None:
        self._allowed = allowed

    def can(self, user_id: int, level: int) -> bool:
        return self._allowed


class _FakeRegistry:
    def __init__(self, commands: list[Command]) -> None:
        self._commands = {c.name: c for c in commands}

    def commands(self) -> list[Command]:
        return list(self._commands.values())

    def get(self, name: str) -> Command | None:
        return self._commands.get(name)


class _FakeService:
    def __init__(self, *, sent: list, converter_ok: bool = True) -> None:
        self.permissions = _FakePerm()
        self.registry = _FakeRegistry(
            [
                Command(
                    name="help",
                    description="查看可用命令列表",
                    permission=PERM_EVERYONE,
                    usage="[命令名]",
                    params=(("命令名", "查看指定命令详情"),),
                    handler=lambda ctx: "x",
                ),
                Command(
                    name="add_admin",
                    description="添加次级管理员",
                    permission=PERM_SUB_ADMIN,
                    usage="<QQ号|@某人>",
                    params=(("QQ号|@某人", "必填目标"),),
                    handler=lambda ctx: "x",
                ),
            ]
        )
        self._sent = sent
        self._converter_ok = converter_ok

    async def send_markdown_image(self, kind, conv_id, markdown, *, at_user_id=None):
        self._sent.append(("image", markdown))
        return self._converter_ok


def _ctx(service, args=None):
    from neobot_app.commands.model import CommandContext

    return CommandContext(
        service=service,
        kind="group",
        conv_id="111111",
        user_id=12345,
        command=service.registry.get("help"),
        raw_args=" ".join(args or []),
        args=args or [],
        at_qqs=[],
    )


@pytest.mark.asyncio
async def test_help_list_renders_image() -> None:
    from neobot_app.commands.builtin import _handle_help

    sent: list = []
    service = _FakeService(sent=sent)
    result = await _handle_help(_ctx(service))
    assert result is None  # 已自行发送
    assert len(sent) == 1
    kind, markdown = sent[0]
    assert "# 可用命令" in markdown
    assert "`/add_admin <QQ号|@某人>`" in markdown
    assert "权限" in markdown


@pytest.mark.asyncio
async def test_help_detail_renders_params() -> None:
    from neobot_app.commands.builtin import _handle_help

    sent: list = []
    service = _FakeService(sent=sent)
    result = await _handle_help(_ctx(service, ["add_admin"]))
    assert result is None
    kind, markdown = sent[0]
    assert "`/add_admin`" in markdown
    assert "## 参数" in markdown
    assert "`QQ号|@某人`" in markdown
    assert "权限" in markdown


@pytest.mark.asyncio
async def test_help_unknown_command_falls_back() -> None:
    from neobot_app.commands.builtin import _handle_help

    sent: list = []
    service = _FakeService(sent=sent, converter_ok=False)
    result = await _handle_help(_ctx(service, ["nope"]))
    assert result is not None
    assert "未找到命令" in result


@pytest.mark.asyncio
async def test_help_list_text_fallback_on_converter_failure() -> None:
    from neobot_app.commands.builtin import _handle_help

    sent: list = []
    service = _FakeService(sent=sent, converter_ok=False)
    result = await _handle_help(_ctx(service))
    assert result is not None
    assert "可用命令:" in result


def test_render_command_detail_markdown() -> None:
    md = _render_command_detail_markdown(
        Command(
            name="reboot",
            description="重启 Bot",
            permission=PERM_SUB_ADMIN,
            handler=lambda ctx: "x",
        )
    )
    assert "`/reboot`" in md
    assert "次级管理员" in md


def test_render_command_list_markdown() -> None:
    md = _render_command_list_markdown(
        [Command(name="help", description="查看帮助", permission=PERM_EVERYONE, handler=lambda ctx: "x")]
    )
    assert "`/help`" in md


# ── 全局回复意愿凭据工具 ──


class _FakeWilling:
    def __init__(self) -> None:
        self.global_coeff: float | None = None

    def set_runtime_global_coefficient(self, value: float) -> str:
        self.global_coeff = value
        return f"全局回复系数已设为 {value:.3f}"


class _FakeCredentialManager:
    def __init__(self, available: bool = True) -> None:
        self._available = available
        self.consumed: list[tuple[str, str]] = []

    def consume(self, *, chat_flow: str, action: str, commit: bool = True):
        if not self._available:
            return None
        self.consumed.append((chat_flow, action))
        return object()


def _build_tools(**overrides):
    from neobot_app.reply.tools import ReplyToolExecutor

    defaults = dict(
        willing_service=_FakeWilling(),
        credential_manager=_FakeCredentialManager(available=True),
        config=_FakeConfig(),
        config_update_callback=lambda key, value: "ok",
        conv_kind="group",
        conv_id="111111",
    )
    defaults.update(overrides)
    return ReplyToolExecutor(**defaults)


class _FakeConfig:
    class _Chat:
        reply_mode = "agent"
        willing_agent_global_coefficient = 1.0
        willing_global_coefficient = 1.0

    chat = _Chat()


def test_set_global_without_credential_guides() -> None:
    tools = _build_tools(credential_manager=_FakeCredentialManager(available=False))
    result = tools._execute_set_global_willing({"value": 0.5})
    assert "凭据" in result
    assert "willing_global" in result
    assert "one_time" in result
    assert "timed" in result


def test_set_global_with_credential_succeeds() -> None:
    willing = _FakeWilling()
    cred = _FakeCredentialManager(available=True)
    tools = _build_tools(willing_service=willing, credential_manager=cred)
    result = tools._execute_set_global_willing({"value": 0.4})
    assert "已设为 0.400" in result
    assert willing.global_coeff == 0.4
    assert cred.consumed == [("group:111111", "willing_global")]


def test_set_global_requires_value() -> None:
    tools = _build_tools()
    assert "value" in tools._execute_set_global_willing({})


@pytest.mark.asyncio
async def test_manage_willing_config_get_requires_credential() -> None:
    tools = _build_tools(credential_manager=_FakeCredentialManager(available=False))
    result = await tools._execute_manage_willing_config({"action": "get"})
    assert "凭据" in result
    assert "willing_config" in result


@pytest.mark.asyncio
async def test_manage_willing_config_get() -> None:
    tools = _build_tools()
    result = await tools._execute_manage_willing_config({"action": "get"})
    assert "agent 模式系数" in result
    assert "willing_agent_global_coefficient" in result


@pytest.mark.asyncio
async def test_manage_willing_config_set_updates_config() -> None:
    updated: list = []

    async def update_callback(key, value):
        updated.append((key, value))
        return "ok"

    tools = _build_tools(config_update_callback=update_callback)
    result = await tools._execute_manage_willing_config(
        {"action": "set", "target": "agent", "value": 0.3}
    )
    assert "已更新" in result
    assert updated == [("willing_agent_global_coefficient", 0.3)]


@pytest.mark.asyncio
async def test_manage_willing_config_set_rejects_bad_value() -> None:
    tools = _build_tools()
    result = await tools._execute_manage_willing_config(
        {"action": "set", "target": "agent", "value": 1.5}
    )
    assert "0.0 到 1.0" in result


def test_credential_levels() -> None:
    from neobot_app.credentials.model import ACTION_REQUIRED_LEVEL
    from neobot_app.commands.model import PERM_SUB_ADMIN, PERM_SUPER_ADMIN

    assert ACTION_REQUIRED_LEVEL["willing_global"] == PERM_SUB_ADMIN
    assert ACTION_REQUIRED_LEVEL["willing_config"] == PERM_SUPER_ADMIN


def test_builtin_help_has_params() -> None:
    from neobot_app.commands.builtin import build_builtin_commands
    from neobot_app.commands.service import CommandService

    service = object.__new__(CommandService)
    commands = {c.name: c for c in build_builtin_commands(service)}
    assert commands["help"].params
    assert commands["add_admin"].params
