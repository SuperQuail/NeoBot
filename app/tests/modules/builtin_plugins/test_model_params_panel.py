"""spec(4) Part B：面板侧参数目录（两条渲染路径 + params 折叠 + 旧配置提示）。

覆盖：
- 模型库面板 entry_schema 与本体配置页 read() schema 都过共享后处理器（A17/A18）；
- 面板伪字段 settings.params 在保存时折叠回 enabled_params / extra_body / 参数值；
- 旧配置推断过的模型在模型库视图里带 params_inferred 标记（R12）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from neobot_app.builtin_plugins.dashboard.config_manager import (
    BotConfigManager,
    models_view,
)
from neobot_app.config.loader.manager import Config
from neobot_app.config.model_params import clear_inferred
from neobot_app.config.schemas.bot import BotConfig
from neobot_chat import get_model_registry

_DEEPSEEK_ENV = {
    "DeepSeek_URL": "https://api.deepseek.com",
    "DeepSeek_APIKey": "sk-deepseek-test",
}

_OLD_CONFIG = (
    "[bot]\naccount = 10001\n\n[chat]\n\n"
    "[[models.registry]]\n"
    'key = "ds-a"\n'
    'model_type = "chat"\n'
    'description = "测试模型 ds-a"\n'
    'provider = "DeepSeek"\n'
    'model_name = "deepseek-flash"\n'
    "[models.registry.settings]\n"
    'deepseek_thinking_mode = "enabled"\n'
    'deepseek_reasoning_effort = "max"\n'
    "frequency_penalty = 0.0\n"
    "\n[models.assignments]\n"
    'primary_chat_model = "ds-a"\n'
)


@pytest.fixture(autouse=True)
def _clean_registry():
    get_model_registry().clear()
    clear_inferred()
    yield
    get_model_registry().clear()
    clear_inferred()


def _make_manager(tmp_path: Path, monkeypatch) -> tuple[BotConfigManager, Path]:
    for key, value in _DEEPSEEK_ENV.items():
        monkeypatch.setenv(key, value)
    config_path = tmp_path / "bot.toml"
    config_path.write_text(_OLD_CONFIG, encoding="utf-8")
    manager = BotConfigManager(config_path=config_path, backup_dir=tmp_path / "backup")
    return manager, config_path


def _settings_field(fields: list[dict[str, Any]]) -> dict[str, Any]:
    return next(item for item in fields if item["name"] == "settings")


def _pseudo_field(fields: list[dict[str, Any]]) -> dict[str, Any]:
    settings = _settings_field(fields)
    return next(item for item in settings["fields"] if item.get("kind") == "model_params")


def test_entry_schema_and_config_page_schema_both_carry_param_catalog(tmp_path, monkeypatch) -> None:
    """两条渲染路径都出现 hidden 标记与 model_params 伪字段（不新增载荷键）。"""
    manager, _ = _make_manager(tmp_path, monkeypatch)

    # 路径 1：模型库面板 entry_schema
    payload = models_view(manager.instance())
    entry_fields = payload["entry_schema"]
    settings = _settings_field(entry_fields)
    hidden = {item["name"] for item in settings["fields"] if item.get("hidden")}
    assert {
        "frequency_penalty",
        "image_api",
        "deepseek_thinking_mode",
        "enabled_params",
        "extra_body",
    } <= hidden
    pseudo = _pseudo_field(entry_fields)
    assert pseudo["base_param_names"] == [
        "temperature",
        "max_output_tokens",
        "timeout_seconds",
        "top_p",
    ]
    assert {item["name"] for item in pseudo["catalog"]} == {
        "frequency_penalty",
        "presence_penalty",
        "image_api",
        "image_reference_param",
        "deepseek_thinking_mode",
        "deepseek_reasoning_effort",
        "deepseek_random_thinking_probability",
    }
    # 模型库面板不新增顶层载荷键（目录内嵌在伪字段里）
    assert "param_catalog" not in payload

    # 路径 2：本体配置页 read() 的 schema（models.registry 是 model_list）
    document = manager.read()
    schema = document["schema"]
    models_group = next(item for item in schema if item["name"] == "models")
    registry_group = next(
        item for item in models_group["fields"] if item["name"] == "registry"
    )
    assert registry_group["kind"] == "model_list"
    entry_fields_page = registry_group["items"][0]["fields"]
    pseudo_page = _pseudo_field(entry_fields_page)
    assert pseudo_page["kind"] == "model_params"
    assert pseudo_page["path"][-1] == "params"
    hidden_page = {
        item["name"] for item in _settings_field(entry_fields_page)["fields"] if item.get("hidden")
    }
    assert "deepseek_thinking_mode" in hidden_page

    # 伪字段自带当前值（面板据此渲染已添加参数）
    assert pseudo_page["enabled_params"] == []
    assert pseudo_page["unknown_params"] == []
    assert pseudo_page["inapplicable_params"] == []
    assert "values" in pseudo_page["value"]


def test_legacy_inference_marks_model_in_models_view(tmp_path, monkeypatch) -> None:
    """R12：旧配置推断后，模型库视图给出 params_inferred 提示位。"""
    manager, config_path = _make_manager(tmp_path, monkeypatch)
    Config.load(config_path, BotConfig)

    payload = models_view(manager.instance())
    entry = next(item for item in payload["library"] if item["key"] == "ds-a")
    assert entry["params_inferred"] is True
    assert entry["entry"]["settings"]["enabled_params"] == ["deepseek_reasoning_effort"]


def test_config_page_save_folds_params_pseudo_field(tmp_path, monkeypatch) -> None:
    """本体配置页保存：settings.params 折叠回真实字段，不产生未知配置项。"""
    manager, config_path = _make_manager(tmp_path, monkeypatch)

    draft = {
        "models": {
            "registry": [
                {
                    "key": "ds-a",
                    "model_type": "chat",
                    "description": "测试模型 ds-a",
                    "provider": "DeepSeek",
                    "model_name": "deepseek-flash",
                    "settings": {
                        "temperature": 0.8,
                        "deepseek_reasoning_effort": "max",
                        "deepseek_thinking_mode": "enabled",
                        "frequency_penalty": 0.0,
                        "enabled_params": [],
                        "extra_body": {},
                        "params": {
                            "enabled_params": [
                                "deepseek_reasoning_effort",
                                "deepseek_thinking_mode",
                            ],
                            "extra_body": {"top_k": 40},
                            "values": {
                                "deepseek_thinking_mode": "disabled",
                                "deepseek_reasoning_effort": "high",
                                "no_such_param": 1,
                            },
                        },
                    },
                }
            ]
        }
    }
    # 折叠后不应有未知配置项错误
    errors = manager.validate(config=draft)
    assert errors == [], errors

    manager.save(config=draft, expected_revision=manager.revision())

    raw = config_path.read_text(encoding="utf-8")
    assert "[models.registry.settings.params]" not in raw
    assert not any(line.strip().startswith("params") for line in raw.splitlines())
    saved = manager.instance().models.by_key()["ds-a"].settings
    assert saved.enabled_params == ["deepseek_reasoning_effort", "deepseek_thinking_mode"]
    assert saved.extra_body == {"top_k": 40}
    assert saved.deepseek_thinking_mode == "disabled"
    assert saved.deepseek_reasoning_effort == "high"
    assert saved.temperature == 0.8


def test_model_library_upsert_folds_params_pseudo_field(tmp_path, monkeypatch) -> None:
    """模型库保存：即使前端漏了同步，后端也会折叠 settings.params。"""
    manager, config_path = _make_manager(tmp_path, monkeypatch)
    resolved: dict[str, Any] = {}
    manager.update_models(
        upsert={
            "key": "ds-a",
            "model_type": "chat",
            "provider": "DeepSeek",
            "model_name": "deepseek-flash",
            "settings": {
                "frequency_penalty": 0.0,
                "extra_body": {},
                "params": {
                    "enabled_params": ["frequency_penalty"],
                    "extra_body": {"top_k": 7},
                    "values": {"frequency_penalty": 0.25},
                },
            },
        },
        resolved=resolved,
        expected_revision=manager.revision(),
    )
    saved = manager.instance().models.by_key()["ds-a"].settings
    assert saved.enabled_params == ["frequency_penalty"]
    assert saved.frequency_penalty == 0.25
    assert saved.extra_body == {"top_k": 7}
    raw = config_path.read_text(encoding="utf-8")
    assert "[models.registry.settings.params]" not in raw
    assert not any(line.strip().startswith("params") for line in raw.splitlines())
