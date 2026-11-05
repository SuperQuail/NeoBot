"""面向人的控制台视图：短时间、四字符级别、对齐正文与精选上下文。"""

from __future__ import annotations

import sys
from threading import Lock
from typing import Any, TextIO

from rich.console import Console
from rich.table import Table
from rich.text import Text

from .log_records import record_payload
from .log_exceptions import rich_traceback

_LEVELS = {
    "TRACE": ("TRCE", "dim"),
    "DEBUG": ("DBUG", "dim"),
    "INFO": ("INFO", "bold blue"),
    "SUCCESS": ("SUCC", "bold green"),
    "WARNING": ("WARN", "bold yellow"),
    "ERROR": ("ERRO", "bold red"),
    "CRITICAL": ("CRIT", "bold white on red"),
}
_console: Console | None = None
_console_stream: TextIO | None = None
_console_lock = Lock()
_console_show_module = False


def set_console_show_module(enabled: bool) -> None:
    """应用控制台显示偏好，不改变文件与运行时记录的模块字段。"""
    global _console_show_module
    _console_show_module = bool(enabled)


def get_console() -> Console:
    """日志、启动标题与就绪卡共享一个 stdout Console。"""
    global _console, _console_stream
    with _console_lock:
        if _console is None or _console_stream is not sys.stdout:
            _console = Console(file=sys.stdout, markup=False, highlight=False)
            _console_stream = sys.stdout
        return _console


def _clock_text(value: str) -> str:
    clock = value[11:19] if len(value) >= 19 else value[:8]
    return clock if len(clock) == 8 else "--:--:--"


def _source_text(module: str) -> str:
    if module.startswith("app."):
        return module[4:]
    if module.startswith("alembic.runtime."):
        return "alembic." + module.removeprefix("alembic.runtime.")
    return module


def _short(value: Any, limit: int = 80) -> str:
    text = str(value).replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _context_text(payload: dict[str, Any]) -> str:
    fields = payload["fields"]
    parts = []
    for key, label in (("chat_flow_id", "会话"), ("task_id", "任务"), ("plugin_name", "插件"), ("tool", "工具")):
        if fields.get(key) is not None:
            parts.append(f"{label} {_short(fields[key], 48)}")
    seconds = fields.get("duration_seconds")
    millis = fields.get("duration_ms")
    if isinstance(seconds, (float, int)):
        elapsed = f"{seconds * 1000:.0f} ms" if seconds < 1 else f"{seconds:.2f} s"
        parts.append(f"耗时 {elapsed}")
    elif isinstance(millis, (float, int)):
        parts.append(f"耗时 {millis:g} ms")
    # 定位 id 仅在需要处理的告警中提示，完整字段在文件与面板保留。
    if payload["level"] in {"WARNING", "ERROR", "CRITICAL"} and fields.get("event_id"):
        parts.append(f"事件 {_short(fields['event_id'], 16)}")
    return " · ".join(parts)


def _cause_text(payload: dict[str, Any]) -> str:
    fields = payload["fields"]
    if payload["exception"]:
        return ""
    for key, label in (("error", "原因"), ("reason", "原因"), ("hint", "提示")):
        value = fields.get(key)
        if value and str(value) not in payload["message"]:
            return f"{label}：{_short(value, 240)}"
    if payload["level"] in {"WARNING", "ERROR", "CRITICAL"}:
        for key in ("missing_keys", "keys", "missing_variable"):
            value = fields.get(key)
            if isinstance(value, list) and value:
                summary = "、".join(_short(item, 60) for item in value[:3])
                if len(value) > 3:
                    summary += f" 等 {len(value)} 项"
                return f"待填写：{summary}"
            if isinstance(value, str) and value:
                return f"待填写：{_short(value, 120)}"
    return ""


class RichConsoleSink:
    def __init__(self, stream: TextIO, *, console: Console | None = None, show_module: bool | None = None) -> None:
        self.console = console or (
            get_console() if stream is sys.stdout else Console(file=stream, markup=False, highlight=False)
        )
        self.stream = stream
        self._show_module = show_module
        self._lock = Lock()

    def __call__(self, message: Any) -> None:
        payload = record_payload(message.record)
        clock = _clock_text(payload["time"])
        level, style = _LEVELS.get(payload["level"], (payload["level"][:4].ljust(4), ""))
        source = _source_text(payload["module"])
        context, cause = _context_text(payload), _cause_text(payload)
        show_module = _console_show_module if self._show_module is None else self._show_module
        with self._lock:
            if not self.console.is_terminal:
                prefix = f"{clock} {level}" + (f" {source}" if show_module else "")
                line = f"{prefix} | {payload['message']}"
                for detail in (context, cause):
                    if detail:
                        line += "\n    " + detail
                if payload["exception"]:
                    line += "\n" + payload["exception"]["traceback"]
                self.stream.write(line + "\n")
                self.stream.flush()
                return
            body = Text(payload["message"])
            if context:
                body.append("\n" + context, style="dim")
            if cause:
                cause_style = "yellow" if level == "WARN" else "red" if level in {"ERRO", "CRIT"} else "dim"
                body.append("\n" + cause, style=cause_style)
            trace = message.record["extra"].get("_neobot_rich_trace")
            if payload["exception"] and trace is None:
                body.append("\n" + payload["exception"]["traceback"], style="red")
            source_width = 16 if self.console.width >= 100 else 12 if self.console.width >= 70 else 8
            row = Table.grid(padding=(0, 1), expand=True)
            row.add_column(width=8, no_wrap=True)
            row.add_column(width=4, no_wrap=True)
            cells = [Text(clock, style="dim"), Text(level, style=style)]
            if show_module:
                row.add_column(width=source_width, no_wrap=True, overflow="ellipsis")
                cells.append(Text(source, style="cyan"))
            row.add_column(ratio=1, overflow="fold")
            row.add_row(*cells, body)
            self.console.print(row)
            if trace is not None:
                self.console.print(rich_traceback(trace))
