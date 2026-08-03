from __future__ import annotations

import asyncio
import sys

import loguru
import pytest

from neobot_app.observability.logging import (
    configure_loguru,
    _redacting_filter,
    redact_sensitive,
    register_self_heal_manager,
)


class _FakeSelfHealManager:
    """记录 payload 的假 SelfHealManager，由 loguru 线程经 call_soon_threadsafe 投递。"""

    def __init__(self) -> None:
        self.items: list[dict] = []

    async def record(self, payload: dict) -> None:
        self.items.append(payload)


def test_redact_sk_prefix_keys() -> None:
    assert redact_sensitive("key is sk-abc1234567890xyz") == "key is ***REDACTED***"
    assert redact_sensitive("sk-ant-abcdefghijklmnop") == "***REDACTED***"


def test_redact_key_value_pairs() -> None:
    assert redact_sensitive("api_key = sk-abc1234567890") == "***REDACTED***"
    assert redact_sensitive("api_key=sk-abc1234567890, other=1") == "***REDACTED***, other=1"
    assert redact_sensitive("APIKey:abc123") == "***REDACTED***"
    assert redact_sensitive("password=secret123") == "***REDACTED***"
    assert redact_sensitive("secret: hunter2") == "***REDACTED***"
    assert redact_sensitive("token: abc.def.ghi") == "***REDACTED***"


def test_redact_authorization_and_bearer() -> None:
    assert (
        redact_sensitive("Authorization: Bearer sk-abcdefgh12345678")
        == "***REDACTED***"
    )
    assert redact_sensitive("bearer abcDEF123.xyz") == "***REDACTED***"
    assert redact_sensitive("Authorization: token abcdef123456") == "***REDACTED***"


def test_keep_plain_words_unmodified() -> None:
    assert redact_sensitive("请刷新 token 后重试") == "请刷新 token 后重试"
    assert redact_sensitive("password strength is weak") == "password strength is weak"
    assert redact_sensitive("normal message") == "normal message"


def test_redact_empty_and_short_text() -> None:
    assert redact_sensitive("") == ""
    assert redact_sensitive("sk-abc") == "sk-abc"


def test_file_sink_output_is_redacted(tmp_path) -> None:
    log_dir = tmp_path / "logs"
    configure_loguru(log_dir)
    try:
        loguru.logger.error(
            "认证失败 Authorization: Bearer sk-abcdefgh12345678, api_key=sk-zyxwvuts12345678"
        )
        try:
            raise ValueError("连接失败 key=sk-qwertyui12345678")
        except ValueError:
            loguru.logger.exception("请求异常")
    finally:
        loguru.logger.remove()

    content = (log_dir / "neobot.log").read_text(encoding="utf-8")
    assert "sk-abcdefgh12345678" not in content
    assert "sk-zyxwvuts12345678" not in content
    assert "sk-qwertyui12345678" not in content
    assert content.count("***REDACTED***") >= 4


def test_redacting_filter_redacts_traceback_in_exception_records() -> None:
    """带异常的日志记录经 _redacting_filter 后，message 必须追加脱敏 traceback 且无密钥。"""
    try:
        raise ValueError("连接失败 api_key=sk-traceback12345678xyz")
    except ValueError:
        exc_type, exc_value, exc_tb = sys.exc_info()

    record = {
        "message": "请求异常",
        "exception": (exc_type, exc_value, exc_tb),
    }

    assert _redacting_filter(record) is True

    assert record["exception"] is None
    assert "sk-traceback12345678xyz" not in record["message"]
    assert "***REDACTED***" in record["message"]
    assert "Traceback" in record["message"]


async def test_self_heal_sink_forwards_redacted_records_with_traceback() -> None:
    """注册自修复管理器后，ERROR 日志（含异常）必须被脱敏转发且保留结构化 traceback。"""
    manager = _FakeSelfHealManager()
    register_self_heal_manager(manager)
    configure_loguru(None)
    try:
        try:
            raise ValueError("连接失败 key=sk-selfheal12345678xyz")
        except ValueError:
            loguru.logger.bind(module_name="app.some_module").exception("请求异常")
        await asyncio.sleep(0.3)
    finally:
        loguru.logger.remove()
        register_self_heal_manager(None)

    assert len(manager.items) == 1
    payload = manager.items[0]
    assert payload["module"] == "app.some_module"
    assert payload["level"] == "ERROR"
    assert "sk-selfheal12345678xyz" not in str(payload)
    assert payload["traceback"] is not None
    assert "***REDACTED***" in payload["traceback"]


async def test_self_heal_sink_excludes_self_heal_and_transient_modules() -> None:
    """自修复自身日志与瞬时抖动模块（adapter_receiver/image_parse）不得进入自修复累积。"""
    manager = _FakeSelfHealManager()
    register_self_heal_manager(manager)
    configure_loguru(None)
    try:
        loguru.logger.bind(module_name="app.self_heal").error("自身日志-不应进入")
        loguru.logger.bind(module_name="adapter_receiver").error("上游超时-不应进入")
        loguru.logger.bind(module_name="app.image_parse").error("图片解码失败-不应进入")
        loguru.logger.bind(module_name="app.other").error("真实错误 key=sk-excluded-ok")
        await asyncio.sleep(0.3)
    finally:
        loguru.logger.remove()
        register_self_heal_manager(None)

    assert len(manager.items) == 1
    assert manager.items[0]["module"] == "app.other"
    assert "sk-excluded-ok" not in str(manager.items[0])


async def test_self_heal_sink_is_noop_without_manager() -> None:
    """未注册自修复管理器时，ERROR 日志不得抛错（no-op 路径）。"""
    register_self_heal_manager(None)
    configure_loguru(None)
    try:
        loguru.logger.error("没有管理器的错误日志")
        await asyncio.sleep(0.1)
    finally:
        loguru.logger.remove()


@pytest.mark.xfail(
    reason=(
        "BUG-0001 启用文件 sink（configure_loguru(log_dir)）时，文件 sink 的 _redacting_filter "
        "将共享 record 的 exception 置为 None，导致自修复 sink 拿不到结构化 traceback "
        "（payload['traceback'] 为 None），自修复 traceback 计数/判定失效"
    ),
    strict=False,
)
async def test_self_heal_sink_keeps_traceback_when_file_sink_enabled(tmp_path) -> None:
    """文件 sink 启用时自修复记录仍必须携带结构化 traceback（当前实现丢失，BUG-0001）。"""
    manager = _FakeSelfHealManager()
    register_self_heal_manager(manager)
    configure_loguru(tmp_path / "logs")
    try:
        try:
            raise ValueError("连接失败 key=sk-filetrace12345678xyz")
        except ValueError:
            loguru.logger.bind(module_name="app.other").exception("请求异常")
        await asyncio.sleep(0.3)
    finally:
        loguru.logger.remove()
        register_self_heal_manager(None)

    assert len(manager.items) == 1
    assert manager.items[0]["traceback"] is not None
    assert "sk-filetrace12345678xyz" not in str(manager.items[0])
