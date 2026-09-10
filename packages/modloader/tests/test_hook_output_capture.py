"""插件钩子输出的捕获必须是「按任务隔离」的。

旧实现用 contextlib.redirect_stdout（进程级）包住 await：并发钩子会互相串台，
异常退出顺序不巧时 sys.stdout 还会被还原成已失效的 StringIO。
"""

from __future__ import annotations

import asyncio
import io
import sys

import pytest

from neobot_modloader.hooks import (
    _CAPTURE_STDOUT,
    _ContextRoutedStream,
    _capture_output,
    _install_context_routed_streams,
)


class _RecordingOutput:
    def __init__(self) -> None:
        self.writes: list[tuple[str, str]] = []
        self.errors: list[tuple[str, str]] = []

    def write(self, text: str, *, source: str = "", target: str | None = None) -> None:
        self.writes.append((source, text))

    def error(self, text: str, *, source: str = "", target: str | None = None) -> None:
        self.errors.append((source, text))


async def test_concurrent_captures_do_not_cross_contaminate() -> None:
    """两个**重叠**的捕获上下文各自 print，必须只落到自己的 source 下。"""
    output = _RecordingOutput()
    a_in_capture = asyncio.Event()
    b_done = asyncio.Event()

    async def handler_a() -> None:
        with _capture_output(output, source="a"):
            print("hello-a")
            a_in_capture.set()
            # a 停留在捕获上下文中，等待 b 完成自己那段
            await b_done.wait()
            print("bye-a")

    async def handler_b() -> None:
        await a_in_capture.wait()  # 确保 a 已经进入捕获
        with _capture_output(output, source="b"):
            print("hello-b")
            print("bye-b")
        b_done.set()

    await asyncio.wait_for(asyncio.gather(handler_a(), handler_b()), timeout=5)

    by_source: dict[str, str] = {}
    for source, text in output.writes:
        by_source[source] = by_source.get(source, "") + text

    assert set(by_source) == {"a", "b"}
    assert "hello-a" in by_source["a"] and "bye-a" in by_source["a"]
    assert "hello-b" in by_source["b"] and "bye-b" in by_source["b"]
    # 关键：a 的输出里不能出现 b 的内容（旧实现会串台）
    assert "hello-b" not in by_source["a"]
    assert "hello-a" not in by_source["b"]


async def test_output_is_emitted_even_when_handler_raises() -> None:
    output = _RecordingOutput()

    with pytest.raises(RuntimeError):
        with _capture_output(output, source="boom"):
            print("before failure")
            raise RuntimeError("handler exploded")

    assert output.writes == [("boom", "before failure")]


async def test_stderr_goes_to_error_channel() -> None:
    output = _RecordingOutput()

    with _capture_output(output, source="err"):
        print("to-stderr", file=sys.stderr)

    assert output.errors == [("err", "to-stderr")]
    assert output.writes == []


async def test_nested_capture_restores_outer_sink() -> None:
    """嵌套捕获结束后，外层上下文必须重新生效。"""
    output = _RecordingOutput()

    with _capture_output(output, source="outer"):
        print("outer-1")
        with _capture_output(output, source="inner"):
            print("inner-1")
        print("outer-2")

    by_source: dict[str, list[str]] = {}
    for source, text in output.writes:
        by_source.setdefault(source, []).append(text)

    # 内层单独上报；外层把进入内层前后产生的输出合并成一次上报
    assert by_source["inner"] == ["inner-1"]
    assert by_source["outer"] == ["outer-1\nouter-2"]


async def test_capture_does_not_swallow_prints_outside_capture() -> None:
    """捕获之外（无上下文）的 print 必须回到原流，而不是被丢弃。"""
    original = sys.stdout
    buffer = io.StringIO()
    sys.stdout = buffer
    try:
        _install_context_routed_streams()
        print("outside")
    finally:
        sys.stdout = original

    assert "outside" in buffer.getvalue()


async def test_stdout_is_not_replaced_by_a_dead_buffer() -> None:
    """捕获结束后 sys.stdout 仍是可用代理（不会变成失效的 StringIO）。"""
    output = _RecordingOutput()

    with _capture_output(output, source="x"):
        print("captured")

    assert isinstance(sys.stdout, _ContextRoutedStream)
    assert _CAPTURE_STDOUT.get() is None
    # 代理的 write 仍可用（写向安装时捕获的底层流）
    sys.stdout.write("")
    sys.stdout.flush()
