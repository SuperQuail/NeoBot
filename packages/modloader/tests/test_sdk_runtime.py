"""统一动作必须绑定当前运行代，离线契约读取不得导入插件。"""

import json

import pytest

from neobot_modloader.sdk.actions import ActionError, ActionInvocation

from runtime_regression_helpers import make_plugin, make_runtime, start_runtime


async def test_surface_invocation_uses_runtime_context_and_rejects_stopped_plugin(tmp_path):
    make_plugin(
        tmp_path / "plugins",
        "demo",
        defaults={"value": 7},
        body="@plugin.action('inspect', permission='read')\n"
        "def inspect(values, invocation):\n"
        "    return {'value': invocation.context.config['value'], 'identity': invocation.identity}\n",
    )
    runtime = make_runtime(tmp_path)
    await start_runtime(runtime)
    try:
        description = runtime.control.surface("demo")
        assert description["available"] is True
        invocation = ActionInvocation("test-user", frozenset({"read"}), context=object())
        assert await runtime.control.invoke_action("demo", "inspect", {}, invocation) == {
            "value": 7,
            "identity": "test-user",
        }
        await runtime.set_enabled("demo", False)
        with pytest.raises(ActionError) as error:
            await runtime.control.invoke_action("demo", "inspect", {}, invocation)
        assert error.value.code == "plugin_not_ready"
    finally:
        await runtime.stop_all()


async def test_disabled_plugin_reads_bundled_contract_without_executing_code(tmp_path):
    directory = make_plugin(tmp_path / "plugins", "demo", enabled=False)
    manifest = directory / "plugin.toml"
    manifest.write_text(manifest.read_text() + '\n[sdk]\nversion = 1\ncontract = "plugin.contract.json"\n')
    contract = {
        "schema_version": 1,
        "plugin": {"name": "demo", "version": "1.0.0"},
        "config": None,
        "actions": [],
        "resources": [],
        "guides": [],
    }
    (directory / "plugin.contract.json").write_text(json.dumps(contract))
    (directory / "__init__.py").write_text("raise RuntimeError('must never execute')\n")
    runtime = make_runtime(tmp_path)
    description = runtime.control.surface("demo")
    assert description["contract"] == contract
    assert description["available"] is False
    assert description["source"] == "package"
    assert runtime.manager.names() == () or not runtime.manager.names()


def test_contract_path_escape_is_rejected(tmp_path):
    directory = make_plugin(tmp_path / "plugins", "demo", enabled=False)
    manifest = directory / "plugin.toml"
    manifest.write_text(manifest.read_text() + '\n[sdk]\nversion = 1\ncontract = "../outside.json"\n')
    runtime = make_runtime(tmp_path)
    with pytest.raises(ActionError) as error:
        runtime.control.surface("demo")
    assert error.value.code == "contract_invalid"
