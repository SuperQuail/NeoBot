"""服务选择必须与依赖图、代际回滚和面板状态一致。"""

import pytest

from neobot_modloader import Plugin
from neobot_modloader.loading.manifest import read_services
from neobot_modloader.host import PluginHostFacade, TrackedPluginHostFacade
from runtime_regression_helpers import make_plugin, make_runtime, start_runtime


def package(root, name, *, provides=(), required=(), optional=(), body="", priority=0, **kwargs):
    path = make_plugin(root / "plugins", name, body=body, **kwargs)
    with (path / "plugin.toml").open("a", encoding="utf-8") as stream:
        stream.write(
            f"provides = {list(provides)!r}\nrequired = {list(required)!r}\noptional = {list(optional)!r}\npriority = {priority}\n"
        )
    return path


@pytest.mark.parametrize(
    "declaration",
    [
        {"required": ["Upper"]},
        {"provides": ["9clock"]},
        {"provides": ["x__y"]},
        {"provides": [f"s{i}" for i in range(17)]},
        {"provides": ["clock"], "optional": ["clock"]},
        {"required": ["clock"], "optional": ["clock"]},
        {"required": ["clock", "clock>=1"]},
        {"required": "clock"},
    ],
)
def test_invalid_service_declaration_rejected(declaration):
    with pytest.raises((ValueError, TypeError)):
        read_services(declaration)


def test_explicit_empty_code_conflicts_with_manifest():
    with pytest.raises(ValueError):
        read_services({"required": ["clock"]}, Plugin("consumer", required=[]))


async def test_disabled_winner_falls_back_to_next_provider(tmp_path):
    body = "@plugin.on_load\nasync def load(ctx):\n    ctx.services.provide('clock', ctx.plugin_name)\n"
    package(tmp_path, "a_low", provides=["clock"], body=body, priority=1)
    package(tmp_path, "z_high", provides=["clock"], body=body, priority=10)
    package(tmp_path, "consumer", required=["clock"])
    rt = make_runtime(tmp_path)
    await start_runtime(rt)
    try:
        assert rt.host.services.require("clock") == "z_high"
        assert rt.dependency_report("consumer")["services"][0]["provider"] == "z_high"
        assert "consumer" in rt.control.get("z_high").dependents
        assert (await rt.set_enabled("z_high", False)).ok
        # 停用的声明赢家不再占位：使用方落到次选提供者并保持运行
        assert rt.host.services.require("clock") == "a_low"
        assert rt.dependency_report("consumer")["services"][0]["provider"] == "a_low"
        assert rt.control.get("consumer").state == "running"
        assert not rt.control.get("consumer").auto_disabled
        assert (await rt.set_enabled("z_high", True)).ok
        assert rt.host.services.require("clock") == "z_high"
        assert rt.control.get("consumer").state == "running"
    finally:
        await rt.stop_all()


async def test_missing_provider_installed_recovers_consumer(tmp_path):
    package(tmp_path, "consumer", required=["clock"])
    rt = make_runtime(tmp_path)
    await start_runtime(rt)
    assert rt.control.get("consumer").auto_disabled
    provider = package(
        tmp_path,
        "provider",
        provides=["clock"],
        body="@plugin.on_load\nasync def load(ctx):\n    ctx.services.provide('clock', object())\n",
    )
    try:
        assert (await rt.load_plugin_path(provider)).ok
        assert rt.control.get("consumer").state == "running"
    finally:
        await rt.stop_all()


async def test_failed_reload_restores_provider_and_consumers(tmp_path):
    path = package(
        tmp_path,
        "provider",
        provides=["clock"],
        body="@plugin.on_load\nasync def load(ctx):\n    ctx.services.provide('clock', 'old')\n",
    )
    package(tmp_path, "consumer", required=["clock"])
    rt = make_runtime(tmp_path)
    await start_runtime(rt)
    (path / "__init__.py").write_text(
        "from neobot_modloader import Plugin\nplugin = Plugin('provider', version='1.0.0')\n@plugin.on_load\nasync def load(ctx):\n    ctx.services.provide('clock', 'new')\n    raise RuntimeError('new generation failed')\n",
        encoding="utf-8",
    )
    try:
        assert not (await rt.reload_plugin_result("provider")).ok
        assert rt.host.services.require("clock") == "old"
        assert rt.control.get("consumer").state == "running"
    finally:
        await rt.stop_all()


async def test_failed_provider_start_blocks_consumer(tmp_path):
    package(
        tmp_path,
        "provider",
        provides=["clock"],
        body="@plugin.on_load\nasync def load(ctx):\n    ctx.services.provide('clock', object())\n@plugin.on_startup\nasync def start():\n    raise RuntimeError('start failed')\n",
    )
    package(tmp_path, "consumer", required=["clock"])
    rt = make_runtime(tmp_path)
    await start_runtime(rt)
    try:
        assert not rt.host.services.has("clock")
        assert rt.control.get("consumer").auto_disabled
        assert rt.control.get("consumer").state != "running"
    finally:
        await rt.stop_all()


def test_old_generation_cleanup_cannot_remove_replacement():
    host = PluginHostFacade()
    old_cleanup, new_cleanup = [], []
    plugin = Plugin("provider", provides=["clock"])
    old = TrackedPluginHostFacade(host, old_cleanup.append, plugin=plugin)
    new = TrackedPluginHostFacade(host, new_cleanup.append, plugin=plugin)
    old.services.register("clock", "old")
    new.services.register("clock", "new", override=True)
    old_cleanup[0]()
    assert host.services.require("clock") == "new"
    new_cleanup[0]()
    assert host.services.get("clock") is None


async def test_optional_cycle_does_not_block(tmp_path):
    package(tmp_path, "a", provides=["aa"], optional=["bb"])
    package(tmp_path, "b", provides=["bb"], optional=["aa"])
    rt = make_runtime(tmp_path)
    await start_runtime(rt)
    try:
        assert {item.state for item in rt.control.snapshot()} == {"running"}
    finally:
        await rt.stop_all()


async def test_import_failure_keeps_declared_winner_visible(tmp_path):
    package(tmp_path, "high", provides=["clock"], priority=5, body="raise RuntimeError('failed import')")
    package(
        tmp_path,
        "low",
        provides=["clock"],
        body="@plugin.on_load\nasync def load(ctx):\n    ctx.services.provide('clock', object())\n",
    )
    package(tmp_path, "consumer", required=["clock"])
    rt = make_runtime(tmp_path)
    await start_runtime(rt)
    try:
        assert rt.control.get("high").services[0]["status"] == "unloaded"
        assert rt.control.get("consumer").services[0]["provider"] == "high"
        assert rt.control.get("consumer").auto_disabled
        assert not rt.host.services.has("clock")
    finally:
        await rt.stop_all()


async def test_registration_failure_leaves_no_provider_declaration(tmp_path, monkeypatch):
    body = "@plugin.on_load\nasync def load(ctx):\n    ctx.services.provide('clock', ctx.plugin_name)\n"
    package(tmp_path, "a_low", provides=["clock"], body=body, priority=1)
    package(tmp_path, "consumer", required=["clock"])
    rt = make_runtime(tmp_path)
    await start_runtime(rt)
    ghost = package(tmp_path, "z_ghost", provides=["clock"], body=body, priority=10)
    register = rt.manager.register
    attempts: list[str] = []

    def flaky(plugin, context):
        attempts.append(context.plugin_name)
        if len(attempts) == 1:
            raise RuntimeError("register boom")
        register(plugin, context)

    monkeypatch.setattr(rt.manager, "register", flaky)
    try:
        assert not (await rt.load_plugin_path(ghost)).ok
        # 注册失败不得留下幽灵提供者：使用方继续用次选，下一轮复查可重试
        assert rt.dependency_report("consumer")["services"][0]["provider"] == "a_low"
        assert rt.host.services.require("clock") == "a_low"
        assert rt.control.get("consumer").state == "running"
        assert (await rt.load_plugin_path(ghost)).ok
        assert rt.host.services.require("clock") == "z_ghost"
    finally:
        await rt.stop_all()


async def test_explicit_service_version_can_exceed_plugin_version(tmp_path):
    package(
        tmp_path,
        "provider",
        provides=["clock"],
        body="@plugin.on_load\nasync def load(ctx):\n    ctx.services.provide('clock', object(), version='2.0')\n",
    )
    package(tmp_path, "consumer", required=["clock>=2"])
    rt = make_runtime(tmp_path)
    await start_runtime(rt)
    try:
        assert rt.control.get("consumer").state == "running"
    finally:
        await rt.stop_all()


async def test_host_provider_has_no_plugin_cascade_edge(tmp_path):
    host = PluginHostFacade()
    host.services.register("clock", object())
    package(tmp_path, "provider", provides=["clock"])
    package(tmp_path, "consumer", required=["clock"])
    rt = make_runtime(tmp_path, host=host)
    await start_runtime(rt)
    try:
        await rt.stop_plugin("provider")
        assert rt.control.get("consumer").state == "running"
    finally:
        await rt.stop_all()


async def test_host_registered_after_scan_recovers_chain(tmp_path):
    package(tmp_path, "consumer", required=["clock"])
    package(tmp_path, "child", dependencies=["consumer"])
    rt = make_runtime(tmp_path)
    rt.load_all()
    rt.host.services.register("clock", object())
    await rt.load_registered()
    await rt.start_all()
    try:
        assert rt.control.get("consumer").state == rt.control.get("child").state == "running"
    finally:
        await rt.stop_all()


async def test_install_waiting_consumer_before_provider(tmp_path):
    rt = make_runtime(tmp_path)
    await start_runtime(rt)
    consumer = package(tmp_path, "consumer", required=["clock"])
    try:
        assert not (await rt.load_plugin_path(consumer)).ok
        assert rt.control.get("consumer").services[0]["status"] == "missing"
        provider = package(
            tmp_path,
            "provider",
            provides=["clock"],
            body="@plugin.on_load\nasync def load(ctx):\n    ctx.services.provide('clock', object())\n",
        )
        assert (await rt.load_plugin_path(provider)).ok
        assert rt.control.get("consumer").state == "running"
    finally:
        await rt.stop_all()


@pytest.mark.parametrize("failure", [False, True])
async def test_install_new_winner_rechecks_running_consumers(tmp_path, failure):
    publish = "@plugin.on_load\nasync def load(ctx):\n    ctx.services.provide('clock', object())\n"
    package(tmp_path, "low", provides=["clock"], version="2.0", body=publish)
    package(tmp_path, "consumer", required=["clock>=2"])
    rt = make_runtime(tmp_path)
    await start_runtime(rt)
    try:
        assert rt.control.get("consumer").state == "running"
        body = publish + (
            "@plugin.on_startup\nasync def start():\n    raise RuntimeError('broken')\n" if failure else ""
        )
        path = package(tmp_path, "high", provides=["clock"], body=body, priority=10)
        assert (await rt.load_plugin_path(path)).ok is not failure
        assert rt.control.get("consumer").auto_disabled
        assert rt.control.get("consumer").state != "running"
    finally:
        await rt.stop_all()


async def test_reload_preserves_working_generation_if_new_requirement_missing(tmp_path):
    path = package(tmp_path, "consumer")
    rt = make_runtime(tmp_path)
    await start_runtime(rt)
    manifest = path / "plugin.toml"
    manifest.write_text(manifest.read_text().replace("required = []", "required = ['unavailable']"))
    try:
        assert not (await rt.reload_plugin_result("consumer")).ok
        assert rt.control.get("consumer").state == "running"
    finally:
        await rt.stop_all()


async def test_snapshot_includes_code_only_provider(tmp_path):
    path = make_plugin(tmp_path / "plugins", "provider")
    (path / "__init__.py").write_text(
        "from neobot_modloader import Plugin\nplugin=Plugin('provider',version='1.0.0',provides=['clock'])\n"
        "@plugin.on_load\nasync def load(ctx):\n    ctx.services.provide('clock', object())\n"
    )
    package(tmp_path, "consumer", required=["clock"])
    rt = make_runtime(tmp_path)
    await start_runtime(rt)
    try:
        snapshot = rt.control.get("consumer")
        assert snapshot.state == "running"
        assert not snapshot.auto_disabled
        assert snapshot.dependency_status == "ok"
    finally:
        await rt.stop_all()


async def test_optional_version_mismatch_is_unavailable_only_to_constrained_consumer(tmp_path):
    host = PluginHostFacade()
    host.services.register("clock", object(), version="1.0")
    package(tmp_path, "consumer", optional=["clock>=2"])
    rt = make_runtime(tmp_path, host=host)
    await start_runtime(rt)
    try:
        services = rt.manager.get_record("consumer").context.services
        assert not services.has("clock")
        assert services.get("clock") is None
        with pytest.raises(KeyError):
            services.require("clock")
        assert host.services.has("clock")
        assert rt.control.get("consumer").state == "running"
    finally:
        await rt.stop_all()


async def test_disabled_declared_winner_falls_back_to_enabled_provider(tmp_path):
    body = "@plugin.on_load\nasync def load(ctx):\n    ctx.services.provide('clock', ctx.plugin_name)\n"
    package(tmp_path, "winner", provides=["clock"], priority=10, enabled=False)
    package(tmp_path, "loser", provides=["clock"], priority=1, body=body)
    package(tmp_path, "consumer", required=["clock"])
    rt = make_runtime(tmp_path)
    await start_runtime(rt)
    try:
        assert rt.manager.get_record("winner") is None
        assert rt.control.get("consumer").state == "running"
        assert rt.control.get("consumer").dependency_status == "ok"
        assert rt.host.services.require("clock") == "loser"
    finally:
        await rt.stop_all()


async def test_code_only_required_recovers_after_provider_install(tmp_path):
    path = package(tmp_path, "consumer")
    (path / "__init__.py").write_text(
        "from neobot_modloader import Plugin\nplugin=Plugin('consumer',version='1.0.0',required=['clock'])\n",
        encoding="utf-8",
    )
    # Omitted TOML field allows the code declaration to apply.
    manifest = path / "plugin.toml"
    manifest.write_text(manifest.read_text(encoding="utf-8").replace("required = []\n", ""), encoding="utf-8")
    rt = make_runtime(tmp_path)
    await start_runtime(rt)
    provider = package(
        tmp_path,
        "provider",
        provides=["clock"],
        body="@plugin.on_load\nasync def load(ctx):\n    ctx.services.provide('clock', object())\n",
    )
    try:
        assert (await rt.load_plugin_path(provider)).ok
        assert rt.control.get("consumer").state == "running"
    finally:
        await rt.stop_all()


@pytest.fixture(autouse=True)
def clean_imported_generations():
    import sys

    previous = set(sys.modules)
    yield
    for name in set(sys.modules) - previous:
        if name.startswith("neobot_user_plugins."):
            sys.modules.pop(name, None)


async def test_failed_provider_start_cleans_transitive_loaded_dependents(tmp_path):
    package(
        tmp_path,
        "a",
        provides=["aa"],
        body="@plugin.on_load\nasync def load(ctx):\n    ctx.services.provide('aa', object())\n@plugin.on_startup\nasync def start():\n    raise RuntimeError('failed')\n",
    )
    package(
        tmp_path,
        "b",
        required=["aa"],
        provides=["bb"],
        body="@plugin.on_load\nasync def load(ctx):\n    ctx.services.provide('bb', object())\n",
    )
    package(
        tmp_path,
        "c",
        dependencies=["b"],
        provides=["cc"],
        body="@plugin.on_load\nasync def load(ctx):\n    ctx.services.provide('cc', object())\n",
    )
    package(tmp_path, "d", required=["cc"])
    rt = make_runtime(tmp_path)
    await start_runtime(rt)
    try:
        assert not rt.host.services.has("bb")
        assert not rt.host.services.has("cc")
        assert rt.control.get("c").state != "running"
        assert rt.control.get("d").state != "running"
    finally:
        await rt.stop_all()
