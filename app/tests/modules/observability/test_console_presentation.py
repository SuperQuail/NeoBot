from __future__ import annotations

import io
import logging
import re
import sys
from datetime import datetime, timezone

import loguru
import pytest
from rich.cells import cell_len
from rich.console import Console

from neobot_app.observability.log_console import RichConsoleSink, get_console
from neobot_app.observability.logging import configure_loguru, set_console_show_module


@pytest.fixture(autouse=True)
def isolated_logging():
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    loguru.logger.remove()
    loguru.logger.configure(patcher=None, extra={})
    root.handlers, root.level = handlers, level


@pytest.mark.parametrize(
    ("level", "label"),
    [
        ("TRACE", "TRCE"),
        ("DEBUG", "DBUG"),
        ("INFO", "INFO"),
        ("SUCCESS", "SUCC"),
        ("WARNING", "WARN"),
        ("ERROR", "ERRO"),
        ("CRITICAL", "CRIT"),
    ],
)
def test_console_levels_are_four_characters(level, label, capsys):
    configure_loguru(console_level="TRACE")
    loguru.logger.bind(module_name="app.demo").log(level, "示例记录")
    output = capsys.readouterr().out
    assert re.match(rf"^\d{{2}}:\d{{2}}:\d{{2}} {label} \| 示例记录\n$", output)
    assert len(output.split()[1]) == 4


def test_console_has_seconds_and_keeps_detailed_metadata_in_file(tmp_path, capsys):
    configure_loguru(tmp_path, console_show_module=True)

    def fixed_time(record):
        record["time"] = datetime(2026, 10, 31, 12, 27, 2, 799123, tzinfo=timezone.utc)

    loguru.logger.patch(fixed_time).bind(
        module_name="app.config",
        event="config.loaded",
        path="/a/long/config/path.toml",
        duration_seconds=0.077,
        keys=["bot.account"],
    ).info("配置文件加载完成")
    output = capsys.readouterr().out
    assert output.startswith("12:27:02 INFO config | 配置文件加载完成\n")
    assert "耗时 77 ms" in output
    assert "799123" not in output
    assert "config.loaded" not in output
    assert "/a/long/config/path.toml" not in output
    assert "keys=" not in output
    detailed = (tmp_path / "neobot.log").read_text()
    assert "2026-10-31 12:27:02.799123+00:00" in detailed
    assert 'event="config.loaded"' in detailed
    assert 'path="/a/long/config/path.toml"' in detailed
    assert 'keys=["bot.account"]' in detailed


@pytest.mark.parametrize("width", [60, 100, 160])
@pytest.mark.parametrize("show_module", [False, True])
def test_terminal_columns_align_and_long_messages_wrap_under_body(width, show_module):
    stream = io.StringIO()
    console = Console(file=stream, force_terminal=True, no_color=True, width=width, height=40, record=True)
    configure_loguru()
    loguru.logger.remove()
    loguru.logger.add(RichConsoleSink(stream, console=console, show_module=show_module), format="{message}")
    loguru.logger.bind(module_name="app.config").info("BODY_A")
    loguru.logger.bind(module_name="a.very.long.module.name").warning("BODY_B")
    message = "长消息需要在正文列换行，保持时间与级别清晰。" * 5
    loguru.logger.bind(module_name="app.reply").info(message)
    output = console.export_text()
    lines = output.splitlines()
    assert lines[0].index("BODY_A") == lines[1].index("BODY_B")
    assert all(cell_len(line) <= width for line in lines)
    assert message in "".join(line.strip().replace(" ", "") for line in lines)
    assert "WARN" in lines[1]


def test_module_display_can_be_enabled_without_replacing_sinks(capsys):
    configure_loguru()
    logger = loguru.logger.bind(module_name="app.example")
    logger.info("默认记录")
    set_console_show_module(True)
    logger.info("诊断记录")
    lines = capsys.readouterr().out.splitlines()
    assert "example" not in lines[0]
    assert "example" in lines[1]


@pytest.mark.parametrize("name", ["alembic.runtime.plugins", "alembic.runtime.migration"])
def test_alembic_diagnostics_go_to_file_but_warning_stays_visible(name, tmp_path, capsys):
    configure_loguru(tmp_path)
    logger = logging.getLogger(name)
    logger.info("setup plugin alembic.autogenerate.schemas")
    logger.warning("迁移插件不可用")
    console = capsys.readouterr().out
    assert "setup plugin" not in console
    assert "迁移插件不可用" in console
    detailed = (tmp_path / "neobot.log").read_text()
    assert "DEBUG" in detailed
    assert "setup plugin alembic.autogenerate.schemas" in detailed


def test_console_retains_human_error_reason_without_dumping_args(capsys):
    configure_loguru()
    loguru.logger.bind(module_name="app.tools", error="连接被拒绝", args={"large": "unneeded payload"}).warning(
        "工具执行失败"
    )
    output = capsys.readouterr().out
    assert "工具执行失败" in output
    assert "原因：连接被拒绝" in output
    assert "unneeded payload" not in output


def test_console_reports_missing_configuration_as_human_list(capsys):
    configure_loguru()
    loguru.logger.bind(module_name="config_loader", keys=["bot.account", "models.assignments"]).warning(
        "配置项仍为占位符"
    )
    output = capsys.readouterr().out
    assert "待填写：bot.account、models.assignments" in output
    assert "keys=" not in output


def test_console_singleton_tracks_stdout_replacement(monkeypatch):
    original = io.StringIO()
    monkeypatch.setattr(sys, "stdout", original)
    first = get_console()
    assert get_console() is first
    replacement = io.StringIO()
    monkeypatch.setattr(sys, "stdout", replacement)
    second = get_console()
    assert second is not first
    second.print("当前终端")
    assert "当前终端" in replacement.getvalue()
    assert original.getvalue() == ""
