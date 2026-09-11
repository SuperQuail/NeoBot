"""核心对象复用契约：默认不缓存（测试隔离），显式开启后只构建一次。

软重启依赖这条契约：核心对象（日志/配置/数据库/适配器/插件主机/命令服务/插件运行时/
文件服务/待机服务）必须复用，bot 侧对象必须重建。
"""

from __future__ import annotations

import pytest

from neobot_app.bootstrap import (
    _CORE_CACHE,
    _reuse_or,
    _run_once,
    disable_core_reuse,
    enable_core_reuse,
    get_cached_core,
)


@pytest.fixture(autouse=True)
def _clean_cache():
    disable_core_reuse()
    try:
        yield
    finally:
        disable_core_reuse()


def test_no_cache_by_default() -> None:
    calls: list[int] = []

    def factory():
        calls.append(1)
        return object()

    first = _reuse_or("k", factory)
    second = _reuse_or("k", factory)

    assert first is not second, "默认不开启复用时每次都应新建对象"
    assert len(calls) == 2
    assert get_cached_core("k") is None


def test_caches_when_enabled() -> None:
    enable_core_reuse()
    calls: list[int] = []

    def factory():
        calls.append(1)
        return object()

    first = _reuse_or("k", factory)
    second = _reuse_or("k", factory)

    assert first is second, "开启复用后同一 key 必须拿到同一个对象"
    assert len(calls) == 1
    assert get_cached_core("k") is first


def test_run_once_executes_once_when_enabled() -> None:
    enable_core_reuse()
    calls: list[int] = []

    _run_once("once", lambda: calls.append(1))
    _run_once("once", lambda: calls.append(1))

    assert len(calls) == 1, "软重启不得重复执行日志配置等一次性副作用"


def test_disable_clears_cache() -> None:
    enable_core_reuse()
    _reuse_or("k", object)

    disable_core_reuse()

    assert get_cached_core("k") is None
    assert _CORE_CACHE == {}


def test_core_keys_documented() -> None:
    """核心对象清单：这些 key 必须走 _reuse_or（bot 侧对象不进缓存）。"""
    import inspect

    from neobot_app import bootstrap

    source = inspect.getsource(bootstrap.create_application)

    for key in (
        "logger_factory",
        "config",
        "prompt_store",
        "sleep_service",
        "standby_service",
        "debug_recorder",
        "storage",
        "usage",
        "adapter",
        "hot_reload_registry",
        "plugin",
        "file_server",
        "command_service",
        "plugin_runtime",
    ):
        assert f'"{key}"' in source, f"核心对象未纳入复用: {key}"


def test_soft_restart_rebinds_plugin_generation() -> None:
    """软重启重建的注册表/截图端口必须显式绑定给核心持有的插件运行时。

    只断言核心对象清单不够：注册表不在清单里，却必须每代重新绑定，否则插件
    注册会落在上一代对象上（Agent/Skill 静默消失）。
    """
    import inspect

    from neobot_app import bootstrap

    source = inspect.getsource(bootstrap.create_application)

    assert ".bind_generation(" in source
    for binding in (
        "agent_registry=agent_registry",
        "skills_registry=markdown_skill_registry",
        'screenshots=browser["screenshots"]',
    ):
        assert binding in source, f"bind_generation 未绑定: {binding}"
