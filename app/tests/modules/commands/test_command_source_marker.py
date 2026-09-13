"""spec(4) Part D / R26：插件来源命令在 /help 里的 [来源: <plugin>] 标记（A65）。"""

from __future__ import annotations

from types import SimpleNamespace

from neobot_app.commands.builtin import (
    _render_command_detail_markdown,
    _render_command_list_markdown,
)
from neobot_app.commands.model import Command


def _plugin_command() -> Command:
    return Command(
        name="status",
        description="查看运行状态",
        handler=lambda ctx: None,
        usage="[概况 用量 插件 错误]",
        source="dashboard",
    )


def _builtin_command() -> Command:
    return Command(name="help", description="查看命令列表", handler=lambda ctx: None)


def test_help_line_marks_plugin_source_only() -> None:
    assert _plugin_command().help_line.endswith("[来源: dashboard]")
    assert "[来源" not in _builtin_command().help_line
    assert _builtin_command().source_label == ""


def test_plugin_command_help_line_keeps_permission_marker() -> None:
    line = _plugin_command().help_line
    assert line.startswith("/status [概况 用量 插件 错误] — 查看运行状态")
    assert "[权限:所有人]" in line
    assert "[来源: dashboard]" in line


def test_help_list_markdown_marks_plugin_commands() -> None:
    bt = chr(96)  # 反引号：避免在测试源码里写 markdown 定界符
    markdown = _render_command_list_markdown([_builtin_command(), _plugin_command()])
    assert f"{bt}/help{bt}" in markdown
    assert "[来源: dashboard]" in markdown
    # 本体命令那一行没有来源标记
    builtin_line = next(
        line for line in markdown.splitlines() if line.startswith(f"- {bt}/help{bt}")
    )
    assert "[来源" not in builtin_line
    plugin_line = next(
        line for line in markdown.splitlines() if line.startswith(f"- {bt}/status")
    )
    assert "[来源: dashboard]" in plugin_line


def test_help_detail_markdown_adds_source_row() -> None:
    detail = _render_command_detail_markdown(_plugin_command())
    assert "| 来源 | dashboard |" in detail
    assert "来源" not in _render_command_detail_markdown(_builtin_command())


async def test_help_text_fallback_marks_plugin_commands() -> None:
    """无 markdown 渲染能力时，/help 的纯文本分支同样带来源标记。"""
    from neobot_app.commands.service import CommandService
    from neobot_app.commands.registry import CommandRegistry

    registry = CommandRegistry()
    registry.register(_plugin_command())
    replies: list[str] = []

    async def send_callback(kind: str, conv_id: str, text: str, at: int | None) -> None:
        replies.append(text)

    config = SimpleNamespace(
        chat=SimpleNamespace(admin_accounts=[], sub_admin_accounts=[]),
        bot=SimpleNamespace(account=1),
    )
    service = CommandService(
        config=config, registry=registry, register_builtins=True, send_callback=send_callback
    )
    message = SimpleNamespace(
        user_id=1, message=[{"type": "text", "data": {"text": "/help"}}]
    )

    await service.handle_message(message, kind="private", queue_key="1")

    assert replies
    assert "[来源: dashboard]" in replies[0]


if __name__ == "__main__":  # pragma: no cover
    import sys

    import pytest

    sys.exit(pytest.main([__file__]))
