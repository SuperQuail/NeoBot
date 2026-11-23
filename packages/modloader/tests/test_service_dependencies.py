from pathlib import Path
import pytest
from neobot_modloader import Plugin
from neobot_modloader.host import DefaultServiceRegistry
from neobot_modloader.loader import FilesystemPluginLoader
from neobot_modloader.loading.models import LoadedPlugin
from neobot_modloader.loading.ordering import resolve_load_order
from runtime_regression_helpers import make_plugin, make_runtime, start_runtime


def test_manifest_and_code_services(tmp_path):
    plugin = Plugin("consumer", required=["clock>=1"], optional=["cache"])
    assert plugin.required == ("clock>=1",)
    path = make_plugin(tmp_path, "consumer")
    with (path / "plugin.toml").open("a") as stream:
        stream.write("required = ['clock>=1']\noptional = ['cache']\n")
    loaded = FilesystemPluginLoader().load_one(path)
    assert loaded.required == ("clock>=1",)
    assert loaded.plugin.optional == ("cache",)


def test_service_order_and_missing():
    def entry(name, **kwargs):
        return LoadedPlugin(name, "1.0", object(), Path("."), {}, **kwargs)

    result = resolve_load_order([entry("consumer", required=("clock",)), entry("provider", provides=("clock",))])
    assert result.ordered == ("provider", "consumer")
    result = resolve_load_order([entry("consumer", required=("clock",))])
    assert result.blocked["consumer"].code == "service-missing"


def test_registry_deterministic_and_generation_cleanup():
    registry = DefaultServiceRegistry()
    registry.register("clock", "b", provider="b", priority=1, version="1")
    registry.register("clock", "a", provider="a", priority=1, version="2")
    assert registry.require("clock") == "a"
    assert registry.describe()[0]["provider"] == "a"


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["load", "startup"])
async def test_runtime_service_startup_and_cascade(tmp_path, stage):
    root = tmp_path / "plugins"
    provider = make_plugin(
        root,
        "z_provider",
        body=f"@plugin.on_{stage}\nasync def provide(ctx):\n    ctx.services.provide('clock', object())\n",
    )
    with (provider / "plugin.toml").open("a") as stream:
        stream.write("provides = ['clock']\n")
    consumer = make_plugin(
        root,
        "a_consumer",
        body="@plugin.on_startup\nasync def consume(ctx):\n    assert ctx.services.require('clock') is not None\n",
    )
    with (consumer / "plugin.toml").open("a") as stream:
        stream.write("required = ['clock']\n")
    runtime = make_runtime(tmp_path)
    await start_runtime(runtime)
    assert runtime.manager.get_record("a_consumer").state.value == "running"
    assert runtime.dependency_report("a_consumer")["services"][0]["status"] == "loaded"
    await runtime.stop_plugin("z_provider")
    assert runtime.manager.get_record("a_consumer") is None
    assert not runtime.host.services.has("clock")
    assert (await runtime.start_plugin("z_provider")).ok
    assert runtime.manager.get_record("a_consumer").state.value == "running"


@pytest.mark.asyncio
async def test_missing_and_optional_service_snapshot(tmp_path):
    root = tmp_path / "plugins"
    for name, kind in [("consumer", "required"), ("optional", "optional")]:
        path = make_plugin(root, name)
        with (path / "plugin.toml").open("a") as stream:
            stream.write(f"{kind} = ['clock']\n")
    runtime = make_runtime(tmp_path)
    await start_runtime(runtime)
    snapshots = {item.name: item for item in runtime.snapshot_plugins()}
    assert snapshots["consumer"].dependency_status == "blocked"
    assert snapshots["optional"].state == "running"
    assert snapshots["optional"].services[0]["status"] == "missing"


@pytest.fixture(autouse=True)
def clean_imported_generations():
    import sys

    previous = set(sys.modules)
    yield
    for name in set(sys.modules) - previous:
        if name.startswith("neobot_user_plugins."):
            sys.modules.pop(name, None)
