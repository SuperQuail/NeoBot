from __future__ import annotations

import asyncio
import inspect
import io
import json
import logging
from pathlib import Path

import loguru
import pytest
from rich.console import Console

from neobot_app.observability.log_console import RichConsoleSink
from neobot_app.observability.log_delivery import AsyncLogDelivery
from neobot_app.observability.log_records import safe_fields
from neobot_app.observability.logging import (
    LoguruLoggerFactory,
    configure_loguru,
    flush_log_sinks,
    register_self_heal_manager,
    set_runtime_event_dispatcher,
)


@pytest.fixture(autouse=True)
async def isolated_logging():
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    set_runtime_event_dispatcher(None)
    register_self_heal_manager(None)
    yield
    await flush_log_sinks()
    set_runtime_event_dispatcher(None)
    register_self_heal_manager(None)
    loguru.logger.remove()
    loguru.logger.configure(patcher=None, extra={})
    root.handlers, root.level = handlers, level


async def test_context_fields_are_structured_and_caller_is_preserved():
    captured = []

    async def dispatch(envelope):
        captured.append(envelope.payload)

    set_runtime_event_dispatcher(dispatch)
    configure_loguru(runtime_events=True)
    logger = LoguruLoggerFactory().get_logger("app.reply").bind(chat_flow_id="group:12", plugin_name="drawing")
    expected_line = inspect.currentframe().f_lineno + 1
    logger.info("回复已发出", event="reply.sent", event_id="r1", chat_flow_id="private:34", count=2)
    assert await flush_log_sinks()
    payload = captured[0]
    assert payload["message"] == "回复已发出"
    assert payload["fields"] == {
        "chat_flow_id": "private:34",
        "plugin_name": "drawing",
        "event": "reply.sent",
        "event_id": "r1",
        "count": 2,
    }
    assert payload["file"] == Path(__file__).name
    assert payload["line"] == expected_line
    assert payload["function"] == "test_context_fields_are_structured_and_caller_is_preserved"
    assert payload["timestamp"] > 0
    assert payload["exception"] is None
    json.dumps(payload, allow_nan=False)


async def test_all_outputs_share_redacted_fields_and_one_safe_exception(tmp_path, capsys):
    captured, errors = [], []

    async def dispatch(envelope):
        captured.append(envelope.payload)

    class Manager:
        async def record(self, payload):
            errors.append(payload)

    set_runtime_event_dispatcher(dispatch)
    register_self_heal_manager(Manager())
    configure_loguru(tmp_path, runtime_events=True)
    logger = LoguruLoggerFactory().get_logger("app.reply")
    try:
        # 未标记的局部变量和源码常量也不能通过诊断输出泄露。
        private_local = "RAW_LOCAL_VALUE_MUST_NOT_APPEAR"
        raise ValueError("认证失败 token=secret123")
    except ValueError:
        assert private_local
        logger.exception("工具执行失败", tool="render", args={"headers": {"Authorization": "secret123"}})
    assert await flush_log_sinks()
    console = capsys.readouterr()
    content = (tmp_path / "neobot.log").read_text()
    for output in (console.out, content, str(captured), str(errors)):
        assert "secret123" not in output
        assert "RAW_LOCAL_VALUE_MUST_NOT_APPEAR" not in output
        assert "***REDACTED***" in output
    assert console.err == ""
    assert console.out.count("Traceback (most recent call last):") == 1
    assert content.count("Traceback (most recent call last):") == 1
    assert captured[0]["message"] == "工具执行失败"
    assert captured[0]["exception"] == errors[0]["exception"]
    assert errors[0]["traceback"] == captured[0]["exception"]["traceback"]


async def test_worker_thread_reaches_both_async_outputs():
    captured, errors = [], []

    async def dispatch(envelope):
        captured.append(envelope.payload)

    class Manager:
        async def record(self, payload):
            errors.append(payload)

    set_runtime_event_dispatcher(dispatch)
    register_self_heal_manager(Manager())
    configure_loguru(runtime_events=True)
    logger = LoguruLoggerFactory().get_logger("app.worker")
    await asyncio.to_thread(logger.error, "后台任务失败", task_id="t1")
    assert await flush_log_sinks()
    assert len(captured) == len(errors) == 1
    assert captured[0]["fields"]["task_id"] == errors[0]["fields"]["task_id"] == "t1"


async def test_warning_exc_info_preserves_level_and_error_details():
    captured = []

    async def dispatch(envelope):
        captured.append(envelope.payload)

    set_runtime_event_dispatcher(dispatch)
    configure_loguru(runtime_events=True)
    logger = LoguruLoggerFactory().get_logger("app.reply")
    try:
        raise RuntimeError("后续步骤失败")
    except RuntimeError:
        logger.warning("回复已发出，后续步骤失败", exc_info=True, event_id="r1")
    assert await flush_log_sinks()
    assert captured[0]["level"] == "WARNING"
    assert captured[0]["exception"]["type"] == "RuntimeError"
    assert "exc_info" not in captured[0]["fields"]


async def test_stdlib_extra_stacklevel_and_exception_are_preserved():
    captured = []

    async def dispatch(envelope):
        captured.append(envelope.payload)

    set_runtime_event_dispatcher(dispatch)
    configure_loguru(runtime_events=True)
    logger = logging.getLogger("third_party")

    def helper():
        logger.warning("请求 %s", "失败", extra={"task_id": "t2"}, stacklevel=2, exc_info=True)

    try:
        raise ValueError("password=secret123")
    except ValueError:
        expected_line = inspect.currentframe().f_lineno + 1
        helper()
    assert await flush_log_sinks()
    payload = captured[0]
    assert payload["module"] == "third_party"
    assert payload["message"] == "请求 失败"
    assert payload["line"] == expected_line
    assert payload["function"] == "test_stdlib_extra_stacklevel_and_exception_are_preserved"
    assert payload["fields"] == {"task_id": "t2"}
    assert "secret123" not in json.dumps(payload)


async def test_output_levels_are_independent(tmp_path, capsys):
    captured = []

    async def dispatch(envelope):
        captured.append(envelope.payload)

    set_runtime_event_dispatcher(dispatch)
    configure_loguru(tmp_path, runtime_events=True)
    logger = LoguruLoggerFactory().get_logger("app.reply")
    logger.debug("模型请求详情", event_id="r1")
    logger.info("回复完成", event_id="r1")
    assert await flush_log_sinks()
    assert "模型请求详情" not in capsys.readouterr().out
    assert [item["message"] for item in captured] == ["回复完成"]
    assert "模型请求详情" in (tmp_path / "neobot.log").read_text()


async def test_api_metric_is_independent_of_visible_log_level():
    captured = []

    async def dispatch(envelope):
        captured.append(envelope)

    set_runtime_event_dispatcher(dispatch)
    configure_loguru(runtime_events=True)
    logger = LoguruLoggerFactory().get_logger("adapter_receiver")
    logger.debug("OneBot 请求已写入连接", event="onebot.api.sent", action="send_group_msg")
    logger.debug("普通调试详情")
    assert await flush_log_sinks()
    assert len(captured) == 1
    assert captured[0].kind == "metric"
    assert captured[0].stage == "onebot.api.sent"
    assert captured[0].payload == {"action": "send_group_msg"}


def test_rich_console_keeps_markup_literal_and_redirection_unwrapped():
    stream = io.StringIO()
    configure_loguru()
    loguru.logger.remove()
    console = Console(file=stream, force_terminal=True, width=120, no_color=False, color_system="standard")
    loguru.logger.add(RichConsoleSink(stream, console=console), format="{message}")
    loguru.logger.info("[red]literal[/red]", event_id="r1")
    assert "[red]literal[/red]" in stream.getvalue()
    assert "\x1b[" in stream.getvalue()
    loguru.logger.remove()
    stream = io.StringIO()
    loguru.logger.add(RichConsoleSink(stream), format="{message}")
    long_message = "single-line-" * 30
    loguru.logger.info(long_message)
    assert "\x1b[" not in stream.getvalue()
    assert stream.getvalue().count("\n") == 1
    assert long_message in stream.getvalue()


def test_nested_fields_are_bounded_serializable_and_redacted():
    recursive = {}
    recursive["self"] = recursive
    value = safe_fields(
        {"args": {"token": "secret123"}, "output_tokens": 123, "recursive": recursive, "nan": float("nan")}
    )
    assert value["args"]["token"] == "***REDACTED***"
    assert value["output_tokens"] == 123
    assert "<max depth>" in str(value)
    json.dumps(value, allow_nan=False)


@pytest.mark.parametrize("key", ["accessToken", "clientSecret", "apiKey", "X-API-Key", "password", "Set-Cookie"])
def test_secret_field_names_cover_camel_case_and_headers(key):
    assert safe_fields({"args": {key: "PRIVATE_FIELD_VALUE"}}) == {"args": {key: "***REDACTED***"}}


async def test_syntax_error_source_is_removed_from_every_output(tmp_path, capsys):
    captured = []

    async def dispatch(envelope):
        captured.append(envelope.payload)

    set_runtime_event_dispatcher(dispatch)
    configure_loguru(tmp_path, runtime_events=True)
    try:
        compile("client_secret = 'PRIVATE_SOURCE_VALUE' :", "plugin.py", "exec")
    except SyntaxError:
        LoguruLoggerFactory().get_logger("modloader").exception("插件编译失败")
    assert await flush_log_sinks()
    for output in (capsys.readouterr().out, (tmp_path / "neobot.log").read_text(), str(captured)):
        assert "PRIVATE_SOURCE_VALUE" not in output
        assert "SyntaxError" in output
        assert "plugin.py" in output


async def test_delivery_bounds_backlog_and_drains_in_order():
    delivery = AsyncLogDelivery(capacity=2)
    captured = []

    async def target(item):
        captured.append(item)

    delivery.set_target(target)
    for item in range(3):
        delivery.submit(item)
    assert delivery.stats() == {"pending": 2, "dropped": 1, "failed": 0}
    await delivery.flush()
    assert captured == [0, 1]
    assert delivery.stats()["pending"] == 0


async def test_delivery_failure_does_not_stop_later_records_or_recurse():
    delivery = AsyncLogDelivery()
    captured = []

    async def target(item):
        if item == 1:
            raise ValueError("consumer unavailable")
        captured.append(item)

    delivery.set_target(target)
    delivery.submit(1)
    delivery.submit(2)
    await delivery.flush()
    assert captured == [2]
    assert delivery.stats()["failed"] == 1


async def test_delivery_drops_consumer_feedback_and_remains_usable():
    delivery = AsyncLogDelivery()
    captured = []

    async def target(item):
        captured.append(item)
        delivery.submit("recursive")
        await asyncio.to_thread(delivery.submit, "thread-recursive")

    delivery.set_target(target)
    delivery.submit("first")
    await delivery.flush()
    delivery.submit("second")
    await delivery.flush()
    assert captured == ["first", "second"]
    assert delivery.stats() == {"pending": 0, "dropped": 4, "failed": 0}


async def test_delivery_yields_to_other_callbacks_during_a_synchronous_batch():
    delivery = AsyncLogDelivery(capacity=128)
    marker = asyncio.Event()
    marker_at_end = []

    async def target(item):
        if item == 0:
            asyncio.get_running_loop().call_soon(marker.set)
        if item == 127:
            marker_at_end.append(marker.is_set())

    delivery.set_target(target)
    for item in range(128):
        delivery.submit(item)
    await delivery.flush()
    assert marker_at_end == [True]


async def test_failing_runtime_subscriber_does_not_reenter_log_output(tmp_path):
    from neobot_modloader.hooks import PluginHookBus

    logger = LoguruLoggerFactory().get_logger("plugin.faulty")
    bus = PluginHookBus(logger=logger)
    received = []

    async def faulty(envelope):
        received.append(envelope)
        raise RuntimeError("subscriber unavailable")

    bus.subscribe_runtime(faulty, kind="log", logger=logger)
    set_runtime_event_dispatcher(bus.dispatch_envelope)
    configure_loguru(tmp_path, runtime_events=True)
    logger.info("original event")
    assert await flush_log_sinks()
    assert len(received) == 1
    content = (tmp_path / "neobot.log").read_text()
    assert "original event" in content
    assert "subscriber unavailable" in content


async def test_dispatcher_replacement_drops_previous_generation():
    delivery = AsyncLogDelivery()
    previous, current = [], []

    async def old_target(item):
        previous.append(item)

    async def new_target(item):
        current.append(item)

    delivery.set_target(old_target)
    delivery.submit("old")
    delivery.set_target(new_target)
    delivery.submit("new")
    await delivery.flush()
    assert previous == []
    assert current == ["new"]


async def test_cancelled_consumer_does_not_restart_during_loop_shutdown():
    delivery = AsyncLogDelivery()
    started = asyncio.Event()
    blocked = asyncio.Event()

    async def target(item):
        started.set()
        await blocked.wait()

    delivery.set_target(target)
    delivery.submit(1)
    delivery.submit(2)
    await started.wait()
    task = delivery._task
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)
    assert delivery._task is None
    assert delivery._scheduled is False
    assert delivery.stats()["pending"] == 1
