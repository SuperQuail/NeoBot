"""插件配置「原地生效」通道（bugfixes/feat(2) §6 的 modloader 侧）。

守住：登记/注销/幂等；未登记时返回 None（面板维持「需要重启」语义）；
插件卸载时自动移除消费者，避免把配置喂给已释放的对象。
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from neobot_modloader.management import PluginControlFacade
from neobot_modloader.runtime import PluginRuntime


class _Logger:
    def info(self, *args: Any, **kwargs: Any) -> None: ...
    def error(self, *args: Any, **kwargs: Any) -> None: ...
    def exception(self, *args: Any, **kwargs: Any) -> None: ...
    def warning(self, *args: Any, **kwargs: Any) -> None: ...
    def debug(self, *args: Any, **kwargs: Any) -> None: ...


class _LoggerFactory:
    def get_logger(self, name: str) -> Any:
        return _Logger()


class _Consumer:
    config_paths = ("plugin.demo",)

    def __init__(self) -> None:
        self.applied: list[Any] = []

    async def apply_config(self, config: Any) -> None:
        self.applied.append(config)


@pytest.fixture()
def runtime() -> Any:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        plugin_dir = root / "plugins"
        plugin_dir.mkdir()
        yield PluginRuntime(
            plugin_dir=plugin_dir,
            data_dir=root / "data",
            adapter=object(),
            logger_factory=_LoggerFactory(),
        )


def test_register_and_lookup(runtime: PluginRuntime) -> None:
    consumer = _Consumer()

    assert runtime.plugin_config_consumer("demo") is None
    assert runtime.register_plugin_config_consumer("demo", consumer) is True

    assert runtime.plugin_config_consumer("demo") is consumer
    # 幂等：重复登记覆盖旧值而不是留下两份
    other = _Consumer()
    assert runtime.register_plugin_config_consumer("demo", other) is True
    assert runtime.plugin_config_consumer("demo") is other


def test_register_rejects_consumer_without_apply_config(runtime: PluginRuntime) -> None:
    with pytest.raises(TypeError, match="apply_config"):
        runtime.register_plugin_config_consumer("demo", object())


def test_register_ignores_empty_inputs(runtime: PluginRuntime) -> None:
    assert runtime.register_plugin_config_consumer("", _Consumer()) is False
    assert runtime.register_plugin_config_consumer("demo", None) is False
    assert runtime.plugin_config_consumer("") is None


def test_unregister(runtime: PluginRuntime) -> None:
    runtime.register_plugin_config_consumer("demo", _Consumer())

    assert runtime.unregister_plugin_config_consumer("demo") is True
    assert runtime.plugin_config_consumer("demo") is None
    assert runtime.unregister_plugin_config_consumer("demo") is False


def test_facade_exposes_the_channel(runtime: PluginRuntime) -> None:
    facade = PluginControlFacade(runtime)
    consumer = _Consumer()

    assert facade.config_consumer("demo") is None
    assert facade.register_config_consumer("demo", consumer) is True
    assert facade.config_consumer("demo") is consumer
    assert facade.unregister_config_consumer("demo") is True
    assert facade.config_consumer("demo") is None


def test_facade_tolerates_runtime_without_channel() -> None:
    """宿主未提供通道时（旧运行时替身）门面必须安全退化，不能抛异常。"""
    facade = PluginControlFacade(object())

    assert facade.config_consumer("demo") is None
    assert facade.register_config_consumer("demo", _Consumer()) is False
    assert facade.unregister_config_consumer("demo") is False


def test_unregister_is_idempotent_on_empty_name(runtime: PluginRuntime) -> None:
    runtime.register_plugin_config_consumer("demo", _Consumer())

    assert runtime.unregister_plugin_config_consumer("") is False
    assert runtime.plugin_config_consumer("demo") is not None
