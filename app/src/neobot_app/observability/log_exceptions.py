"""Rich 异常展示：保留调用链，渲染前清除原始源码与局部变量。"""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from typing import Any

from rich.traceback import Trace, Traceback


def safe_rich_trace(exc: Any, redact: Callable[[str], str]) -> Trace | None:
    if not exc or not exc[0]:
        return None

    def clean(item: Trace) -> None:
        for stack in item.stacks:
            stack.exc_type = redact(stack.exc_type)
            stack.exc_value = redact(stack.exc_value)
            stack.notes = [redact(note) for note in stack.notes]
            stack.syntax_error = None
            for frame in stack.frames:
                frame.filename = redact(frame.filename)
                frame.name = redact(frame.name)
                frame.line = ""
                frame.locals = None
            for child in stack.exceptions:
                clean(child)

    try:
        trace = Traceback.extract(*exc, show_locals=False)
        clean(trace)
        return trace
    except Exception:
        return None


def rich_traceback(trace: Trace) -> Traceback:
    # Rich 仍显示文件、行号、函数及异常链；禁止重新读取未脱敏源码/locals。
    return Traceback(trace, width=None, show_locals=False, suppress=("",), word_wrap=True, max_frames=100)


def display_uncaught_exception(exc_type: type[BaseException], value: BaseException, tb: Any) -> None:
    from .log_console import get_console
    from .log_records import _safe_exception, redact_sensitive

    console = get_console()
    exc = (exc_type, value, tb)
    if console.is_terminal:
        trace = safe_rich_trace(exc, redact_sensitive)
        if trace is not None:
            console.print(rich_traceback(trace))
            return
    snapshot = _safe_exception(exc)
    if snapshot is not None:
        console.out(snapshot["traceback"], highlight=False)


def install_exception_hooks() -> None:
    """仅 CLI 安装，库调用不会替换宿主的异常处理器。"""
    sys.excepthook = display_uncaught_exception

    def thread_exception(args: Any) -> None:
        if args.exc_type is not SystemExit:
            display_uncaught_exception(args.exc_type, args.exc_value, args.exc_traceback)

    threading.excepthook = thread_exception
