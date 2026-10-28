"""0.8.0 -> 0.9.0：旧 settings.deepseek_reasoning_effort 搬到模型库顶层 reasoning_effort。

顶层字段是面板里可见可编辑的主入口；旧键原样保留（provider 仍兼容），升级不丢设置。
"""

from __future__ import annotations

from typing import Any

import pytest

from neobot_app.config.loader.manager import Config
from neobot_app.config.migrations import migrate_v8_to_v9
from neobot_app.config.schemas.bot import BotConfig
from neobot_chat import get_model_registry

_DEEPSEEK_KEYS = {
    "DeepSeek_URL": "https://api.deepseek.com",
    "DeepSeek_APIKey": "sk-deepseek-test-1234567890",
}


@pytest.fixture(autouse=True)
def _clean_registry():
    get_model_registry().clear()
    yield
    get_model_registry().clear()


def _clear_platform_env(monkeypatch) -> None:
    for key in (
        "DeepSeek_URL",
        "DeepSeek_APIKey",
        "SiliconFlow_URL",
        "SiliconFlow_APIKey",
        "HuoShan_APIKey",
    ):
        monkeypatch.delenv(key, raising=False)


def _entry(
    model_ref: str,
    *,
    settings: dict[str, Any] | None = None,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "model_ref": model_ref,
        "provider": "DeepSeek",
        "model_name": "deepseek-flash",
    }
    if settings is not None:
        entry["settings"] = settings
    if reasoning_effort is not None:
        entry["reasoning_effort"] = reasoning_effort
    return entry


def _efforts(new: dict[str, Any]) -> dict[str, Any]:
    return {
        entry["model_ref"]: entry.get("reasoning_effort")
        for entry in new["models"]["registry"]
        if isinstance(entry, dict)
    }


# ----------------------------------------------------------------------
# 迁移函数本身
# ----------------------------------------------------------------------


def test_moves_legacy_high_and_max_to_top_level() -> None:
    old = {
        "version": "0.8.0",
        "models": {
            "registry": [
                _entry("a", settings={"deepseek_reasoning_effort": "max"}),
                _entry("b", settings={"deepseek_reasoning_effort": "high"}),
            ]
        },
    }
    new = migrate_v8_to_v9(old)

    assert new["version"] == "0.9.0"
    assert _efforts(new) == {"a": "max", "b": "high"}
    # 旧键必须原样保留（provider 兼容 + 用户没丢设置）
    settings = new["models"]["registry"][0]["settings"]
    assert settings == {"deepseek_reasoning_effort": "max"}


@pytest.mark.parametrize(
    ("legacy", "expected"),
    [
        ("low", "high"),
        ("medium", "high"),
        ("xhigh", "max"),
        (" HIGH ", "high"),
    ],
)
def test_legacy_values_use_deepseek_normalization(legacy, expected) -> None:
    """旧字段的历史归并规则（low/medium->high，xhigh->max）沿用，不搬上去就只是隐藏。"""
    old = {
        "version": "0.8.0",
        "models": {"registry": [_entry("a", settings={"deepseek_reasoning_effort": legacy})]},
    }
    assert _efforts(migrate_v8_to_v9(old))["a"] == expected


@pytest.mark.parametrize("legacy", ["none", "minimal", "ultra", ""])
def test_invalid_legacy_values_are_not_migrated(legacy) -> None:
    """none/minimal 在旧字段里本就无效：搬成 high 会制造「已关闭推理」的假象。"""
    old = {
        "version": "0.8.0",
        "models": {"registry": [_entry("a", settings={"deepseek_reasoning_effort": legacy})]},
    }
    assert "reasoning_effort" not in migrate_v8_to_v9(old)["models"]["registry"][0]


@pytest.mark.parametrize(
    "provider",
    ["OpenAI", "Anthropic", "SiliconFlow", "SiliconFlow-CN", "", "Azure-OpenAI"],
)
def test_non_deepseek_providers_are_not_migrated(provider) -> None:
    """旧版程序给每个模型都写了 deepseek_reasoning_effort 默认值。

    迁移若只看字段存在，会给 OpenAI / Anthropic / 硅基流动条目凭空加一个会被真正
    下发的顶层推理强度（改变行为、甚至 400）。只有 DeepSeek provider 才允许搬迁。
    """
    entry = _entry("foreign", settings={"deepseek_reasoning_effort": "high"})
    entry["provider"] = provider
    migrated = migrate_v8_to_v9({"version": "0.8.0", "models": {"registry": [entry]}})["models"]["registry"][0]
    assert "reasoning_effort" not in migrated
    assert migrated["settings"]["deepseek_reasoning_effort"] == "high"


@pytest.mark.parametrize("provider", ["DeepSeek", "deepseek-offical", "DEEPSEEK_OFFICIAL", " deepseek "])
def test_deepseek_provider_aliases_are_migrated(provider) -> None:
    entry = _entry("ds", settings={"deepseek_reasoning_effort": "max"})
    entry["provider"] = provider
    migrated = migrate_v8_to_v9({"version": "0.8.0", "models": {"registry": [entry]}})["models"]["registry"][0]
    assert migrated["reasoning_effort"] == "max"


def test_migration_is_idempotent() -> None:
    """同一份配置重复迁移（如多次 load/回写）不能改出第二个值。"""
    old = {
        "version": "0.8.0",
        "models": {"registry": [_entry("a", settings={"deepseek_reasoning_effort": "max"})]},
    }
    once = migrate_v8_to_v9(old)
    twice = migrate_v8_to_v9(once)
    assert once == twice


def test_existing_top_level_value_is_not_overwritten() -> None:
    old = {
        "version": "0.8.0",
        "models": {
            "registry": [
                _entry("a", settings={"deepseek_reasoning_effort": "max"}, reasoning_effort="low"),
            ]
        },
    }
    assert _efforts(migrate_v8_to_v9(old))["a"] == "low"


def test_entries_without_legacy_value_stay_untouched() -> None:
    old = {
        "version": "0.8.0",
        "models": {
            "registry": [
                _entry("no-settings"),
                _entry("openai", settings={"temperature": 0.7}),
                _entry("non-dict-settings", settings=[]),
            ]
        },
    }
    new = migrate_v8_to_v9(old)
    assert _efforts(new) == {"no-settings": None, "openai": None, "non-dict-settings": None}


@pytest.mark.parametrize("mode", ["disabled", "DISABLED", "false", "off", "no", "0", False, 0])
def test_entries_with_thinking_disabled_are_not_migrated(mode) -> None:
    """思考已关的条目（出厂 deepseek-flash-off 就是）搬顶层值只显示一个不生效的推理强度。"""
    old = {
        "version": "0.8.0",
        "models": {
            "registry": [
                _entry(
                    "off",
                    settings={
                        "deepseek_thinking_mode": mode,
                        "deepseek_reasoning_effort": "high",
                    },
                )
            ]
        },
    }
    entry = migrate_v8_to_v9(old)["models"]["registry"][0]
    assert "reasoning_effort" not in entry
    # 旧键保留不动，provider 兼容
    assert entry["settings"]["deepseek_reasoning_effort"] == "high"


@pytest.mark.parametrize("mode", ["enabled", "ENABLED", "true", "random", True])
def test_entries_with_thinking_enabled_are_migrated(mode) -> None:
    old = {
        "version": "0.8.0",
        "models": {
            "registry": [
                _entry(
                    "on",
                    settings={
                        "deepseek_thinking_mode": mode,
                        "deepseek_reasoning_effort": "high",
                    },
                )
            ]
        },
    }
    assert _efforts(migrate_v8_to_v9(old))["on"] == "high"


def test_missing_thinking_mode_defaults_to_enabled_and_migrates() -> None:
    old = {
        "version": "0.8.0",
        "models": {"registry": [_entry("a", settings={"deepseek_reasoning_effort": "max"})]},
    }
    assert _efforts(migrate_v8_to_v9(old))["a"] == "max"


@pytest.mark.parametrize("model_type", ["image", "tts", " Image ", "TTS"])
def test_image_and_tts_models_are_not_migrated(model_type) -> None:
    """推理强度对生图 / TTS 模型无意义，搬过去只会在加载时刷告警。"""
    entry = _entry("media", settings={"deepseek_reasoning_effort": "max"})
    entry["model_type"] = model_type
    migrated = migrate_v8_to_v9({"version": "0.8.0", "models": {"registry": [entry]}})["models"]["registry"][0]
    assert "reasoning_effort" not in migrated
    assert migrated["settings"]["deepseek_reasoning_effort"] == "max"


def test_other_sections_and_models_fields_are_preserved() -> None:
    old = {
        "version": "0.8.0",
        "bot": {"account": 10001},
        "models": {
            "registry": [_entry("a", settings={"deepseek_reasoning_effort": "max"})],
            "assignments": {"primary_chat_model": "a"},
            "custom": {"keep": True},
        },
    }
    new = migrate_v8_to_v9(old)

    assert new["bot"] == {"account": 10001}
    assert new["models"]["assignments"] == {"primary_chat_model": "a"}
    assert new["models"]["custom"] == {"keep": True}
    assert new["models"]["registry"][0]["reasoning_effort"] == "max"


def test_non_dict_models_or_non_list_registry_are_kept() -> None:
    assert migrate_v8_to_v9({"version": "0.8.0", "models": "oops"})["models"] == "oops"
    kept = {"registry": "oops", "assignments": {}}
    assert migrate_v8_to_v9({"version": "0.8.0", "models": kept})["models"] == kept
    mixed = {"registry": [{"model_ref": "a"}, "keep-me"]}
    assert migrate_v8_to_v9({"version": "0.8.0", "models": mixed})["models"]["registry"][1] == "keep-me"


def test_missing_models_section_is_fine() -> None:
    assert migrate_v8_to_v9({"version": "0.8.0", "bot": {"account": 1}}) == {
        "version": "0.9.0",
        "bot": {"account": 1},
    }


# ----------------------------------------------------------------------
# Config.load 端到端
# ----------------------------------------------------------------------


def test_load_upgrades_handwritten_v8_config(monkeypatch, tmp_path) -> None:
    _clear_platform_env(monkeypatch)
    for key, value in _DEEPSEEK_KEYS.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr("neobot_app.config.loader.manager.backup_config", lambda *a, **k: None)
    cfg_path = tmp_path / "bot.toml"
    cfg_path.write_text(
        'version = "0.8.0"\n'
        "[bot]\naccount = 10001\n\n"
        "[chat]\n\n"
        "[[models.registry]]\n"
        'model_ref = "flash"\n'
        'provider = "DeepSeek"\n'
        'model_name = "deepseek-flash"\n'
        "[models.registry.settings]\n"
        'deepseek_thinking_mode = "enabled"\n'
        'deepseek_reasoning_effort = "max"\n'
        "\n"
        "[models.assignments]\n"
        'primary_chat_model = "flash"\n'
        'agent_model_1 = "flash"\n'
        'agent_model_2 = "flash"\n'
        'agent_model_3 = "flash"\n'
        'vision_model = ""\n'
        'tts_model = ""\n'
        "creator_image_models = []\n",
        encoding="utf-8",
    )

    config = Config.load(cfg_path, BotConfig)

    assert config.version == "0.9.0"
    definition = config.models.by_ref()["flash"]
    assert definition.reasoning_effort == "max"
    # 旧键保留（provider 兼容，用户不丢设置）
    assert definition.settings.deepseek_reasoning_effort == "max"
    # 注册链也拿到顶层值（面板/请求体两侧同源）
    registered = get_model_registry().get("flash")
    assert registered.settings.reasoning_effort == "max"
    assert registered.settings.reasoning_effort_format == "openai"

    raw = cfg_path.read_text(encoding="utf-8")
    assert 'version = "0.9.0"' in raw
    assert 'reasoning_effort = "max"' in raw
    assert 'deepseek_reasoning_effort = "max"' in raw


def test_chain_from_v3_reaches_v9(monkeypatch, tmp_path) -> None:
    """0.3.0 的旧内联模型配置一路迁到 0.9.0：旧思考强度最终出现在顶层。"""
    _clear_platform_env(monkeypatch)
    for key, value in _DEEPSEEK_KEYS.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr("neobot_app.config.loader.manager.backup_config", lambda *a, **k: None)
    cfg_path = tmp_path / "bot.toml"
    cfg_path.write_text(
        'version = "0.3.0"\n'
        "[bot]\naccount = 10001\n\n"
        "[chat]\n"
        'group_prompt_template = "旧群聊模板"\n'
        "\n"
        "[models.primary_chat_model]\n"
        'provider = "DeepSeek"\n'
        'model_name = "deepseek-v4-pro"\n'
        "[models.primary_chat_model.settings]\n"
        'deepseek_thinking_mode = "enabled"\n'
        'deepseek_reasoning_effort = "max"\n',
        encoding="utf-8",
    )

    config = Config.load(cfg_path, BotConfig)

    assert config.version == "0.9.0"
    assert not hasattr(config.chat, "group_prompt_template")
    # 0.6/0.7 两跳把旧内联模型搬进模型库、并把 deepseek-v4-pro 改名
    definition = config.models.by_ref()["deepseek-flash-max"]
    assert definition.reasoning_effort == "max"
    assert definition.settings.deepseek_reasoning_effort == "max"
