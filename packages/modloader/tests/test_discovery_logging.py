from types import SimpleNamespace
from unittest.mock import Mock

from neobot_contracts.ports.logging import NullLogger
from neobot_modloader.runtime import PluginRuntime


def test_repeated_discovery_does_not_log_loading_failures(tmp_path):
    official_dir = tmp_path / "official"
    plugin_dir = tmp_path / "plugins"
    for root in (official_dir, plugin_dir):
        package = root / "future"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text(
            "raise AssertionError('discovery must not import plugins')\n", encoding="utf-8"
        )
        (package / "plugin.toml").write_text('name = "future"\nmin_neobot_version = "9.0.0"\n', encoding="utf-8")
    recorder = Mock(spec=NullLogger)
    runtime = PluginRuntime(
        plugin_dir=plugin_dir,
        data_dir=tmp_path / "data",
        adapter=object(),
        logger=recorder,
        logger_factory=SimpleNamespace(get_logger=lambda name: recorder),
        builtin_plugin_dirs=[official_dir],
        host_version="2.0.0",
    )

    for _ in range(3):
        discovered = runtime.discover_all()
        assert [plugin.name for plugin in discovered] == ["future"]
        assert discovered[0].source == "official"
    assert recorder.mock_calls == []

    # 真正尝试加载仍应拒绝不兼容插件并告警。
    runtime.load_all()
    assert runtime.manager.names() == []
    assert recorder.error.called
