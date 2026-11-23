from __future__ import annotations

import asyncio
import logging as stdlib_logging
import sys
from types import SimpleNamespace

import loguru
import pytest

from neobot_app.observability.logging import (
    configure_loguru,
    resolve_verbose_logging,
    set_verbose_logging,
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


def test_redact_prefixed_key_names() -> None:
    """键名常带前缀；下划线是词字符，旧实现的 \\b 让这类整类漏脱敏。"""
    for text in (
        "DEEPSEEK_APIKEY=abcdef123456",
        "client_secret=abcdef123456",
        "NEOBOT_LOCAL_ADAPTER_TOKEN=abcdef123456",
        "csrf_token=abcdef123456",
        "credential=abcdef123456",
    ):
        assert "abcdef123456" not in redact_sensitive(text), text


def test_redact_bare_password_phrase() -> None:
    """无分隔符的异常文本形态（密钥会随错误信息回给模型）。"""
    assert "hunter2" not in redact_sensitive("invalid password hunter2")


def test_redact_url_userinfo() -> None:
    redacted = redact_sensitive("url=https://admin:hunter2@example.com/x")

    assert "hunter2" not in redacted
    assert "https://" in redacted


def test_redact_authorization_and_bearer() -> None:
    assert redact_sensitive("Authorization: Bearer sk-abcdefgh12345678") == "***REDACTED***"
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
        loguru.logger.error("认证失败 Authorization: Bearer sk-abcdefgh12345678, api_key=sk-zyxwvuts12345678")
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
    # 每个值仅脱敏一次，源码行不再被异常 formatter 读取、重复输出。
    assert content.count("***REDACTED***") == 3
    assert content.count("Traceback (most recent call last):") == 1
    assert "raise ValueError(" not in content


def test_console_sink_output_is_redacted(capsys) -> None:
    """控制台 sink 也必须脱敏：stdout 会被容器/重定向落到日志文件。"""
    configure_loguru()
    try:
        loguru.logger.error("认证失败 client_secret=abcdef123456")
    finally:
        loguru.logger.remove()

    assert "abcdef123456" not in capsys.readouterr().out


def test_console_sink_writes_to_stdout_not_stderr(capsys) -> None:
    """控制台日志走 stdout。

    宿主（容器日志、进程管理器、NapCatQQ Desktop 这类把实例输出重定向到日志
    文件再 tail 的前端）通常只收集一路流；stderr 混在其中的话，行会被归到
    「错误通道」、级别色也会被带偏。这里锁住「普通日志只出现在 stdout」。
    """
    configure_loguru()
    try:
        loguru.logger.info("启动完成")
        loguru.logger.warning("配置缺失")
    finally:
        loguru.logger.remove()

    captured = capsys.readouterr()
    assert "启动完成" in captured.out
    assert "配置缺失" in captured.out
    assert captured.err == "", "控制台日志不该再往 stderr 写"


def test_redacting_filter_redacts_traceback_in_exception_records() -> None:
    """异常独立于正文，保留脱敏堆栈，禁止下游重新渲染原异常的源码与 locals。"""
    try:
        raise ValueError("连接失败 api_key=sk-traceback12345678xyz")
    except ValueError:
        exc_type, exc_value, exc_tb = sys.exc_info()

    record = {
        "message": "请求异常",
        "exception": (exc_type, exc_value, exc_tb),
    }

    assert _redacting_filter(record) is True

    assert record["message"] == "请求异常"
    assert record["exception"] is None
    exc = record["extra"]["_neobot_exception"]
    assert exc["type"] == "ValueError"
    assert exc["message"] == "连接失败 ***REDACTED***"
    assert "Traceback" in exc["traceback"]
    assert "sk-traceback12345678xyz" not in str(exc)
    assert "raise ValueError" not in exc["traceback"]
    assert "test_redacting_filter_redacts_traceback_in_exception_records" in exc["traceback"]
    # 多出口重复调用处理函数，不追加第二份异常。
    original = dict(exc)
    assert _redacting_filter(record) is True
    assert record["extra"]["_neobot_exception"] == original


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


async def test_self_heal_sink_keeps_traceback_when_file_sink_enabled(tmp_path) -> None:
    """文件 sink 启用时自修复记录仍必须携带结构化 traceback（修复 BUG-0001）。"""
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


# ── 详细日志开关：第三方库 DEBUG 默认不落盘 ──────────────────────────


@pytest.fixture(autouse=True)
def _reset_verbose_logging():
    """详细日志是模块级开关，用例之间必须复位，避免顺序依赖。"""
    set_verbose_logging(False)
    yield
    set_verbose_logging(False)


def test_third_party_debug_filtered_by_default(tmp_path) -> None:
    log_dir = tmp_path / "logs"
    configure_loguru(log_dir)
    try:
        stdlib_logging.getLogger("aiosqlite").debug("executing functools.partial(...)")
        stdlib_logging.getLogger("aiosqlite").info("aiosqlite 连接关闭异常")
    finally:
        loguru.logger.remove()

    content = (log_dir / "neobot.log").read_text(encoding="utf-8")
    # DEBUG 被默认过滤，INFO 及以上仍保留（关闭异常要能看见）。
    assert "executing functools.partial" not in content
    assert "aiosqlite 连接关闭异常" in content


def test_verbose_logging_on_keeps_third_party_debug(tmp_path) -> None:
    log_dir = tmp_path / "logs"
    configure_loguru(log_dir)
    try:
        set_verbose_logging(True)
        stdlib_logging.getLogger("websockets.server").debug("> PING keepalive")
    finally:
        loguru.logger.remove()

    content = (log_dir / "neobot.log").read_text(encoding="utf-8")
    # 切换时留一条分界标记，文件体积突变时能看出原因。
    assert "详细日志已开启" in content
    assert "> PING keepalive" in content


@pytest.mark.parametrize("name", ["httpx", "aiohttp.access"])
def test_verbose_logging_off_drops_per_request_info(name, tmp_path) -> None:
    """off 时逐请求 INFO 不落盘：过滤必须发生在其降级为 DEBUG 之前。"""
    log_dir = tmp_path / "logs"
    configure_loguru(log_dir)
    try:
        set_verbose_logging(False)
        stdlib_logging.getLogger(name).info('HTTP Request: GET https://example.invalid "HTTP/1.1 200 OK"')
    finally:
        loguru.logger.remove()

    assert "HTTP Request" not in (log_dir / "neobot.log").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["httpx", "aiohttp.access"])
def test_verbose_logging_on_keeps_per_request_info(name, tmp_path) -> None:
    log_dir = tmp_path / "logs"
    configure_loguru(log_dir)
    try:
        set_verbose_logging(True)
        stdlib_logging.getLogger(name).info('HTTP Request: GET https://example.invalid "HTTP/1.1 200 OK"')
    finally:
        loguru.logger.remove()

    assert "HTTP Request" in (log_dir / "neobot.log").read_text(encoding="utf-8")


def test_app_debug_not_filtered_when_verbose_off(tmp_path) -> None:
    """过滤只针对第三方库根名，NeoBot 自己的 DEBUG 不受影响。"""
    log_dir = tmp_path / "logs"
    configure_loguru(log_dir)
    try:
        loguru.logger.bind(module_name="app.reply").debug("应用层调试细节")
    finally:
        loguru.logger.remove()

    assert "应用层调试细节" in (log_dir / "neobot.log").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("debug_cfg", "expected"),
    [
        (SimpleNamespace(enabled=True, verbose_logging="auto"), True),
        (SimpleNamespace(enabled=False, verbose_logging="auto"), False),
        (SimpleNamespace(enabled=False, verbose_logging="on"), True),
        (SimpleNamespace(enabled=True, verbose_logging="off"), False),
        # 大小写与空白宽容；None 视为 auto。
        (SimpleNamespace(enabled=True, verbose_logging=" ON "), True),
        # 布尔与 on/off 等价；配置加载器会把 TOML 布尔转成 "True"/"False"。
        (SimpleNamespace(enabled=False, verbose_logging=True), True),
        (SimpleNamespace(enabled=True, verbose_logging=False), False),
        (SimpleNamespace(enabled=False, verbose_logging="True"), True),
        (SimpleNamespace(enabled=True, verbose_logging="False"), False),
        (SimpleNamespace(enabled=True, verbose_logging=None), True),
        # 未知取值按 auto 处理（配置校验只查类型，不查枚举）。
        (SimpleNamespace(enabled=True, verbose_logging="nonsense"), True),
        (SimpleNamespace(enabled=False, verbose_logging="nonsense"), False),
        # 旧配置没有该字段 → auto。
        (SimpleNamespace(enabled=False), False),
    ],
)
def test_resolve_verbose_logging_modes(debug_cfg, expected) -> None:
    assert resolve_verbose_logging(debug_cfg) is expected


def test_unknown_verbose_logging_warns_and_bool_does_not() -> None:
    """未知取值按 auto 处理但必须告警；布尔是已知取值，不再落进未知分支。"""
    messages: list[str] = []
    sink_id = loguru.logger.add(lambda message: messages.append(message.record["message"]), level="WARNING")
    try:
        assert resolve_verbose_logging(SimpleNamespace(enabled=True, verbose_logging="nonsense")) is True
        assert resolve_verbose_logging(SimpleNamespace(enabled=True, verbose_logging=False)) is False
    finally:
        loguru.logger.remove(sink_id)

    unknown = [message for message in messages if "未知的 debug.verbose_logging" in message]
    assert unknown == ["未知的 debug.verbose_logging 取值 'nonsense'，按 auto 处理"]


@pytest.mark.parametrize(
    "root", ["aiosqlite", "websockets", "PIL", "httpcore", "httpx", "urllib3"]
)
def test_all_noisy_roots_drop_debug(tmp_path, root) -> None:
    """噪声清单里的每个根名都要真正被过滤，漏一个就会继续放大日志。"""
    log_dir = tmp_path / "logs"
    configure_loguru(log_dir)
    try:
        stdlib_logging.getLogger(f"{root}.child").debug(f"{root}-debug-should-hide")
    finally:
        loguru.logger.remove()

    assert f"{root}-debug-should-hide" not in (log_dir / "neobot.log").read_text(
        encoding="utf-8"
    )


def test_non_noisy_stdlib_debug_still_lands(tmp_path) -> None:
    """过滤条件必须只匹配噪声根名；不能退化成「过滤所有第三方 DEBUG」。"""
    log_dir = tmp_path / "logs"
    configure_loguru(log_dir)
    try:
        stdlib_logging.getLogger("asyncio").debug("asyncio-debug-should-keep")
    finally:
        loguru.logger.remove()

    assert "asyncio-debug-should-keep" in (log_dir / "neobot.log").read_text(encoding="utf-8")


def test_set_verbose_logging_is_idempotent(tmp_path) -> None:
    """重复设置同一状态不应重复写分界标记（否则每次启动都刷一条）。"""
    log_dir = tmp_path / "logs"
    configure_loguru(log_dir)
    try:
        set_verbose_logging(True)
        set_verbose_logging(True)
        set_verbose_logging(False)
        set_verbose_logging(False)
    finally:
        loguru.logger.remove()

    content = (log_dir / "neobot.log").read_text(encoding="utf-8")
    assert content.count("详细日志已开启") == 1
    assert content.count("详细日志已关闭") == 1


def test_resolve_auto_follows_active_recorder() -> None:
    """auto 跟随实际生效的 DebugRecorder，而不是配置里的 enabled。"""
    auto_on = SimpleNamespace(enabled=True, verbose_logging="auto")
    auto_off = SimpleNamespace(enabled=False, verbose_logging="auto")
    force_on = SimpleNamespace(enabled=False, verbose_logging="on")
    force_off = SimpleNamespace(enabled=True, verbose_logging="off")

    assert resolve_verbose_logging(auto_on, recorder_active=False) is False
    assert resolve_verbose_logging(auto_off, recorder_active=True) is True
    # 显式 on/off 优先于 recorder 状态。
    assert resolve_verbose_logging(force_on, recorder_active=False) is True
    assert resolve_verbose_logging(force_off, recorder_active=True) is False


def test_bootstrap_wires_verbose_logging_to_active_recorder() -> None:
    """装配接线：启动时 auto 必须按实际生效的 DebugRecorder 解析，而非只读配置。"""
    import inspect

    from neobot_app.bootstrap.parts.core_services import _build_core_services

    source = inspect.getsource(_build_core_services)
    assert "set_verbose_logging(resolve_verbose_logging(" in source
    assert "recorder_active=debug_recorder is not None" in source
