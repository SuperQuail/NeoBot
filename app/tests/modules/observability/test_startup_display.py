from __future__ import annotations

from io import StringIO

import pytest
from rich.cells import cell_len
from rich.console import Console

from neobot_app.observability.startup_display import display_banner, display_startup_result


def test_redirected_startup_output_has_banner_and_plain_actual_url():
    stream = StringIO()
    console = Console(file=stream, force_terminal=False, color_system=None)
    display_banner("2.0.0", console=console)
    display_startup_result(
        ready=True,
        version="2.0.0",
        duration_seconds=1.25,
        dashboard={"available": True, "local_url": "http://[::1]:12345/bot/"},
        console=console,
    )

    output = stream.getvalue()
    assert output.startswith("███╗   ██╗███████╗ ██████╗ ██████╗  ██████╗ ████████╗\n")
    assert "╚═╝  ╚═══╝╚══════╝ ╚═════╝ ╚═════╝  ╚═════╝    ╚═╝" in output
    assert "NeoBot 2.0.0" in output
    assert "[NeoBot 已就绪]" in output
    assert "启动耗时：1.25 秒" in output
    assert "面板地址：http://[::1]:12345/bot/" in output
    assert "\x1b" not in output
    assert "╭" not in output


@pytest.mark.parametrize("width", [28, 44, 80])
def test_terminal_startup_card_fits_narrow_console(width):
    stream = StringIO()
    console = Console(file=stream, force_terminal=True, color_system=None, width=width, height=40)
    display_banner("2.0.0", console=console)
    display_startup_result(
        ready=True,
        standby=True,
        version="2.0.0",
        duration_seconds=2.0,
        dashboard={"available": True, "local_url": "http://127.0.0.1:12345/long/base/path/"},
        detail="配置需要补齐，Bot 保持待机",
        console=console,
    )

    output = stream.getvalue()
    assert "待机" in output
    assert all(cell_len(line) <= width for line in output.splitlines())
    border = next(line for line in output.splitlines() if line.startswith("╭"))
    assert cell_len(border) == width


def test_failed_startup_never_claims_ready_or_guesses_dashboard_url():
    stream = StringIO()
    console = Console(file=stream, force_terminal=False, color_system=None)
    display_startup_result(
        ready=False,
        version="2.0.0",
        duration_seconds=0.2,
        dashboard={"available": False, "reason": "面板监听启动失败"},
        detail="初始化失败",
        console=console,
    )

    output = stream.getvalue()
    assert "NeoBot 启动未完成" in output
    assert "无可用面板（面板监听启动失败）" in output
    assert "已就绪" not in output
    assert "http://" not in output


def test_early_webui_card_does_not_claim_bot_is_ready():
    stream = StringIO()
    display_startup_result(
        ready=True,
        initializing=True,
        version="2.0.0",
        duration_seconds=0.5,
        dashboard={"available": True, "local_url": "http://127.0.0.1:12345/"},
        console=Console(file=stream, force_terminal=False, color_system=None),
    )
    output = stream.getvalue()
    assert "WebUI 已就绪" in output
    assert "Bot 正在初始化" in output
    assert "http://127.0.0.1:12345/" in output
    assert "Bot 运行时已启动" not in output
