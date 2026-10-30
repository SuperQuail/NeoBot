"""源码保存必须在落盘前校验，不能依赖重载失败保留内存配置。"""

import json
import tomllib
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import BaseModel, Field, field_validator, model_validator

from neobot_app.builtin_plugins.dashboard.api import DashboardApi
from neobot_app.builtin_plugins.dashboard.plugin_config import PluginConfigEditor, PluginConfigError
from neobot_contracts.ports.logging import NullLogger

from test_dashboard_api import _FakeControl
from test_speaking_schedule_runtime import runtime as runtime


def _api(control):
    return DashboardApi(
        console=SimpleNamespace(
            plugin_control=control, manage_plugins=True, allow_remote_manage=True, logger=NullLogger()
        )
    )


@pytest.mark.parametrize("reload", [False, True])
@pytest.mark.parametrize("include_form", [False, True])
async def test_invalid_schedule_source_preserves_disk_and_runtime(runtime, monkeypatch, reload, include_form):
    rt, _, _ = runtime
    assert (await rt.set_enabled("speaking_schedule", True)).ok
    consumer = rt.control.config_consumer("speaking_schedule")
    config = {
        "timezone": "UTC",
        "windows": [dict(weekdays=[1], start="09:00", end="10:00", next_day=False)],
        "overrides": [],
    }
    await consumer.save_config(config)
    path = rt.control.plugin_config_path("speaking_schedule")
    original = path.read_bytes()
    backup = path.with_name(path.name + ".dashboard.bak")
    backup.write_bytes(b"previous backup\n")
    apply = AsyncMock(wraps=consumer.apply_config)
    monkeypatch.setattr(consumer, "apply_config", apply)
    reloader = AsyncMock(side_effect=AssertionError("invalid config must not trigger reload"))
    monkeypatch.setattr(rt.control, "reload", reloader)
    api = _api(rt.control)
    request = SimpleNamespace(match_info={"name": "speaking_schedule"})
    before = json.loads((await api.plugin_config_get(request)).text)
    payload = {
        "source": 'timezone = "UTC"\n[[windows]]\nweekdays = [1]\nstart = "20:00"\nend = "10:00"\n',
        "revision": before["revision"],
        "reload": reload,
    }
    if include_form:
        # source 优先，不能通过同时附带一份合法表单绕过原文校验。
        payload["config"] = config
    request.can_read_body = True
    request.json = AsyncMock(return_value=payload)

    response = await api.plugin_config_save(request)
    rejected = json.loads(response.text)
    assert response.status == 400, rejected
    assert rejected["ok"] is False
    assert rejected["errors"][0]["path"] == "windows.0"
    assert path.read_bytes() == original
    assert backup.read_bytes() == b"previous backup\n"
    assert json.loads((await api.plugin_config_get(request)).text)["revision"] == before["revision"]
    assert consumer.config.model_dump() == consumer.ctx.config == config
    assert rt.control.plugin_config_values("speaking_schedule") == config
    apply.assert_not_awaited()
    reloader.assert_not_awaited()

    # 停用再启用会重新从磁盘加载，仍保留原来的限制，而非回退成 windows=[]。
    assert (await rt.set_enabled("speaking_schedule", False)).ok
    assert (await rt.set_enabled("speaking_schedule", True)).ok
    recovered = rt.control.config_consumer("speaking_schedule")
    assert recovered is not consumer
    assert recovered.config.model_dump() == config
    assert rt.plugin_config_error("speaking_schedule") is None


async def test_valid_schedule_source_keeps_comments_and_applies(runtime):
    rt, _, _ = runtime
    assert (await rt.set_enabled("speaking_schedule", True)).ok
    api = _api(rt.control)
    request = SimpleNamespace(match_info={"name": "speaking_schedule"})
    before = json.loads((await api.plugin_config_get(request)).text)
    source = (
        "# 用户手写的时段说明\n"
        'timezone = "UTC" # 行尾说明\n'
        "\n[[windows]]\nweekdays = [1]\n"
        'start = "20:00"\nend = "10:00"\nnext_day = true\n'
    )
    request.can_read_body = True
    request.json = AsyncMock(return_value={"source": source, "revision": before["revision"], "reload": True})
    response = await api.plugin_config_save(request)
    saved = json.loads(response.text)
    assert response.status == 200 and saved["ok"] and saved["applied"], saved
    assert rt.control.plugin_config_path("speaking_schedule").read_text(encoding="utf-8") == source
    consumer = rt.control.config_consumer("speaking_schedule")
    assert consumer.config.windows[0].next_day is True
    assert consumer.config.overrides == []


class _SourceConfig(BaseModel):
    required: int
    lower: int = Field(ge=0)
    upper: int

    @model_validator(mode="after")
    def valid_range(self):
        if self.lower > self.upper:
            raise ValueError("范围起点不能超过终点")
        return self


@pytest.mark.parametrize("source", ["lower = -1\nupper = 10\n", "lower = 20\nupper = 10\n"])
def test_source_validates_effective_defaults_before_creating_file(tmp_path, source):
    path = tmp_path / "config.toml"
    editor = PluginConfigEditor(path, model=_SourceConfig, defaults={"required": 5, "lower": 1, "upper": 10})
    with pytest.raises(PluginConfigError, match="插件配置校验失败"):
        editor.save(source=source, expected_revision="")
    assert not path.exists()
    assert not path.with_name(path.name + ".dashboard.bak").exists()
    # 必需字段不在原文中时仍使用打包默认值校验，不把默认值补写到用户原文。
    source = "# 范围说明\nlower = 2\nupper = 10\n"
    assert editor.save(source=source, expected_revision="")["config"]["required"] == 5
    assert path.read_text(encoding="utf-8") == source


def test_source_validation_does_not_reuse_deleted_stored_values(tmp_path):
    path = tmp_path / "config.toml"
    original = "required = 5\nlower = 1\nupper = 10\n"
    path.write_text(original, encoding="utf-8")
    editor = PluginConfigEditor(path, model=_SourceConfig, defaults={"lower": 1, "upper": 10})
    with pytest.raises(PluginConfigError, match="插件配置校验失败"):
        editor.save(source="lower = 2\nupper = 10\n", expected_revision=editor.revision())
    assert path.read_text(encoding="utf-8") == original


async def test_source_model_errors_never_return_submitted_secrets(tmp_path, monkeypatch):
    class Config(BaseModel):
        value: str = Field(default="", json_schema_extra={"sensitive": True})

        @field_validator("value")
        @classmethod
        def reject(cls, value):
            raise ValueError(f"拒绝凭据 {value}")

    control = _FakeControl(tmp_path)
    monkeypatch.setattr(control, "config_model", lambda name: Config)
    api = _api(control)
    request = SimpleNamespace(
        match_info={"name": "demo"},
        can_read_body=True,
        json=AsyncMock(return_value={"source": 'value = "synthetic-source-private"\n', "revision": ""}),
    )
    response = await api.plugin_config_save(request)
    assert response.status == 400, response.text
    assert json.loads(response.text)["errors"] == [{"path": "value", "message": "字段值不符合配置要求"}]
    assert "synthetic-source-private" not in response.text
    assert not control.plugin_config_path("demo").exists()


async def test_stale_source_revision_remains_conflict(runtime):
    rt, _, _ = runtime
    assert (await rt.set_enabled("speaking_schedule", True)).ok
    consumer = rt.control.config_consumer("speaking_schedule")
    await consumer.save_config({"timezone": "UTC", "windows": [], "overrides": []})
    path = rt.control.plugin_config_path("speaking_schedule")
    original = path.read_bytes()
    api = _api(rt.control)
    request = SimpleNamespace(
        match_info={"name": "speaking_schedule"},
        can_read_body=True,
        json=AsyncMock(return_value={"source": 'timezone = "invalid timezone"\n', "revision": "stale"}),
    )
    response = await api.plugin_config_save(request)
    assert response.status == 409, response.text
    assert path.read_bytes() == original


def test_source_without_model_keeps_syntax_only_support(tmp_path):
    editor = PluginConfigEditor(tmp_path / "config.toml")
    source = "# 第三方纯 TOML 插件\ninterval = -1\n"
    assert editor.save(source=source)["source"] == source


@pytest.mark.parametrize("previously_enabled", [False, True])
async def test_disabled_schedule_rejects_source_without_running_entry(runtime, monkeypatch, previously_enabled):
    rt, _, _ = runtime
    config = {
        "timezone": "UTC",
        "windows": [dict(weekdays=[1], start="09:00", end="10:00", next_day=False)],
        "overrides": [],
    }
    if previously_enabled:
        assert (await rt.set_enabled("speaking_schedule", True)).ok
        await rt.control.config_consumer("speaking_schedule").save_config(config)
        assert (await rt.set_enabled("speaking_schedule", False)).ok
    else:
        path = rt.control.plugin_config_path("speaking_schedule")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            'timezone = "UTC"\noverrides = []\n[[windows]]\nweekdays = [1]\n'
            'start = "09:00"\nend = "10:00"\nnext_day = false\n',
            encoding="utf-8",
        )
    assert rt.control.config_model("speaking_schedule") is None
    path = rt.control.plugin_config_path("speaking_schedule")
    original = path.read_bytes()
    importer = rt.official_loader._importer
    import_module = Mock(wraps=importer.import_module)
    monkeypatch.setattr(importer, "import_module", import_module)
    api = _api(rt.control)
    request = SimpleNamespace(match_info={"name": "speaking_schedule"})
    before = json.loads((await api.plugin_config_get(request)).text)
    request.can_read_body = True
    request.json = AsyncMock(
        return_value={
            "source": 'timezone = "UTC"\n[[windows]]\nweekdays = [1]\nstart = "20:00"\nend = "10:00"\n',
            "revision": before["revision"],
            "reload": True,
        }
    )
    payload = request.json.return_value
    payload["revision"] = "stale"
    assert (await api.plugin_config_save(request)).status == 409
    payload["revision"] = before["revision"]
    response = await api.plugin_config_save(request)
    assert response.status == 400, response.text
    assert path.read_bytes() == original
    assert before["source_available"] is False
    assert "请先启用并加载插件" in before["source_disabled_reason"]
    assert rt.control.config_consumer("speaking_schedule") is None
    import_module.assert_not_called()
    request.json = AsyncMock(return_value={"config": {"timezone": "UTC"}, "revision": before["revision"]})
    assert (await api.plugin_config_save(request)).status == 200
    import_module.assert_not_called()
    assert (await rt.set_enabled("speaking_schedule", True)).ok
    assert rt.control.config_consumer("speaking_schedule").config.model_dump() == config


@pytest.mark.parametrize(
    ("annotation", "literal"),
    [("date", "2026-11-01"), ("time", "09:00:00"), ("datetime", "2026-11-01T09:00:00Z")],
)
async def test_source_validates_native_toml_defaults_without_json_coercion(runtime, annotation, literal):
    rt, _, _ = runtime
    root = rt.plugin_dir / "strict_defaults"
    root.mkdir(parents=True)
    (root / "plugin.toml").write_text(
        f'name = "strict_defaults"\nversion = "1.0.0"\n[config]\ndeadline = {literal}\ninterval = 10\n',
        encoding="utf-8",
    )
    (root / "__init__.py").write_text(
        f"from datetime import {annotation}\n"
        "from pydantic import BaseModel, ConfigDict\n"
        "from neobot_modloader import Plugin\n"
        "class Config(BaseModel):\n"
        "    model_config = ConfigDict(strict=True)\n"
        f"    deadline: {annotation}\n"
        "    interval: int\n"
        "plugin = Plugin('strict_defaults', version='1.0.0', config=Config)\n",
        encoding="utf-8",
    )
    rt.load_all()
    await rt.load_registered()
    await rt.start_all()
    control = rt.control
    defaults = tomllib.loads(f"deadline = {literal}\ninterval = 10\n")
    # 同一份 TOML 打包默认值直接交给模型可通过，原文只更改普通字段。
    model = control.config_model("strict_defaults")
    assert model.model_validate({**defaults, "interval": 15}).interval == 15
    api = _api(control)
    before = json.loads((await api.plugin_config_get(SimpleNamespace(match_info={"name": "strict_defaults"}))).text)
    assert tomllib.loads(before["source"])["deadline"] == defaults["deadline"]
    request = SimpleNamespace(
        match_info={"name": "strict_defaults"},
        can_read_body=True,
        json=AsyncMock(return_value={"source": "interval = 15\n", "revision": ""}),
    )
    response = await api.plugin_config_save(request)
    assert response.status == 200, response.text
    assert control.plugin_config_path("strict_defaults").read_text(encoding="utf-8") == "interval = 15\n"
    assert json.loads(response.text)["config"]["deadline"] == str(defaults["deadline"])


@pytest.mark.parametrize(("loaded", "declared_model"), [(False, False), (True, False), (False, True)])
async def test_contracts_distinguish_model_availability(runtime, loaded, declared_model):
    from neobot_modloader import Plugin

    rt, _, _ = runtime
    root = rt.plugin_dir / "plain"
    root.mkdir(parents=True)
    (root / "plugin.toml").write_text(
        f'name = "plain"\nversion = "1.0.0"\nenabled = {str(loaded).lower()}\n'
        + ("" if loaded else "[sdk]\nversion = 1\n"),
        encoding="utf-8",
    )
    (root / "__init__.py").write_text(
        "from neobot_modloader import Plugin\nplugin = Plugin('plain', version='1.0.0')\n"
        if loaded
        else "raise AssertionError('disabled plugin entry must not execute')\n",
        encoding="utf-8",
    )
    if not loaded:
        plugin = Plugin("plain", version="1.0.0", config=_SourceConfig if declared_model else None)
        (root / "plugin.contract.json").write_text(json.dumps(plugin.surface.describe(plugin)), encoding="utf-8")
    rt.load_all()
    await rt.load_registered()
    await rt.start_all()
    api = _api(rt.control)
    request = SimpleNamespace(match_info={"name": "plain"})
    before = json.loads((await api.plugin_config_get(request)).text)
    assert before["source_available"] is not declared_model, before
    request.can_read_body = True
    request.json = AsyncMock(return_value={"source": "interval = -1\n", "revision": before["revision"]})
    response = await api.plugin_config_save(request)
    assert response.status == (400 if declared_model else 200), response.text
    if declared_model:
        assert not rt.control.plugin_config_path("plain").exists()
    else:
        assert rt.control.plugin_config_path("plain").read_text(encoding="utf-8") == "interval = -1\n"


async def test_restarted_disabled_schedule_keeps_valid_file(runtime):
    from neobot_modloader.runtime import PluginRuntime

    rt, _, commands = runtime
    assert (await rt.set_enabled("speaking_schedule", True)).ok
    config = {
        "timezone": "UTC",
        "windows": [dict(weekdays=[1], start="09:00", end="10:00", next_day=False)],
        "overrides": [],
    }
    await rt.control.config_consumer("speaking_schedule").save_config(config)
    assert (await rt.set_enabled("speaking_schedule", False)).ok
    restarted = PluginRuntime(
        plugin_dir=rt.plugin_dir,
        data_dir=rt.data_dir,
        builtin_plugin_dirs=rt.builtin_plugin_dirs,
        state_store=rt.state_store,
        adapter=rt.adapter,
        logger_factory=rt.logger_factory,
        host=rt.host,
        app_commands=commands,
    )
    restarted.load_all()
    await restarted.load_registered()
    await restarted.start_all()
    try:
        assert restarted.control.config_model("speaking_schedule") is None
        path = restarted.control.plugin_config_path("speaking_schedule")
        original = path.read_bytes()
        api = _api(restarted.control)
        request = SimpleNamespace(match_info={"name": "speaking_schedule"})
        before = json.loads((await api.plugin_config_get(request)).text)
        request.can_read_body = True
        request.json = AsyncMock(
            return_value={
                "source": '[[windows]]\nweekdays = [1]\nstart = "20:00"\nend = "10:00"\n',
                "revision": before["revision"],
            }
        )
        response = await api.plugin_config_save(request)
        assert response.status == 400, response.text
        assert path.read_bytes() == original
        assert (await restarted.set_enabled("speaking_schedule", True)).ok
        assert restarted.control.config_consumer("speaking_schedule").config.model_dump() == config
    finally:
        for name in reversed(restarted.manager.names()):
            await restarted.unload_plugin(name)
