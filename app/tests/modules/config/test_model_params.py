"""spec(4) Part B：模型注册参数可选化（目录 / scope / 下发规则 / 旧配置迁移）。

覆盖验收 A17-A25 中可单测的部分（后端侧）：
- 参数目录与基础四参数（A17）
- scope 过滤（归一化 provider / model_type，A18）
- 未启用则不下发（A21）
- extra_body 进入聊天 payload、__ 前缀拒绝（A20）
- 生图模型不注入 __deepseek_*__ 内部键、image_api 未启用走 auto（A22/A25）
- 旧配置 enabled_params 推断 + 值不丢（A23）
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import loguru
import pytest

from neobot_app.config.loader.manager import Config, _build_provider_extra_body
from neobot_app.config.model_params import (
    BASE_PARAM_NAMES,
    MODEL_PARAM_CATALOG,
    applicable_catalog,
    apply_model_param_catalog,
    catalog_names,
    clear_inferred,
    extra_body_reserved_keys,
    infer_enabled_params,
    is_inferred,
    resolve_enabled_params,
)
from neobot_app.config.schemas.bot import (
    BotConfig,
    DeepSeekModelSettings,
    normalize_model_type,
)
from neobot_chat import get_model_registry
from neobot_chat.providers import OpenAIProvider

_OPENAI_ENV = {
    "OpenAI_URL": "https://api.openai.com/v1",
    "OpenAI_APIKey": "sk-openai-test",
}
_DEEPSEEK_ENV = {
    "DeepSeek_URL": "https://api.deepseek.com",
    "DeepSeek_APIKey": "sk-deepseek-test",
}


@pytest.fixture(autouse=True)
def _clean_registry():
    get_model_registry().clear()
    clear_inferred()
    yield
    get_model_registry().clear()
    clear_inferred()


@pytest.fixture()
def loguru_messages():
    """收集 loguru 输出（pytest 的 caplog 抓不到 loguru）。"""
    records: list[str] = []
    sink_id = loguru.logger.add(lambda message: records.append(message), format="{message}")
    try:
        yield records
    finally:
        loguru.logger.remove(sink_id)


def _write_config(tmp_path: Path, models_body: str) -> Path:
    path = tmp_path / "bot.toml"
    path.write_text("[bot]\naccount = 10001\n\n[chat]\n\n" + models_body, encoding="utf-8")
    return path


def _model_block(
    key: str,
    *,
    provider: str = "OpenAI",
    settings_body: str = "",
    model_type: str = "chat",
) -> str:
    return (
        "[[models.registry]]\n"
        f'key = "{key}"\n'
        f'model_type = "{model_type}"\n'
        f'description = "测试模型 {key}"\n'
        f'provider = "{provider}"\n'
        'model_name = "test-model-1"\n'
        "[models.registry.settings]\n" + settings_body
    )


def _chat_assignments(key: str = "chat-a") -> str:
    return (
        "[models.assignments]\n"
        f'primary_chat_model = "{key}"\n'
        f'agent_model_1 = "{key}"\n'
        f'agent_model_2 = "{key}"\n'
        f'agent_model_3 = "{key}"\n'
    )

_IMAGE_ASSIGNMENTS = (
    "[agent.creator]\nenabled = true\n"
    "[models.assignments]\ncreator_image_models = [\"img-a\"]\n"
)


def _registered(key: str) -> Any:
    registered = get_model_registry().get(key)
    assert registered is not None, f"模型 {key} 未注册"
    return registered


# ----------------------------------------------------------------------
# A17 / A18：参数目录与 scope
# ----------------------------------------------------------------------

def test_catalog_base_params_are_exactly_four() -> None:
    """A17：基础区恰为 temperature / max_output_tokens / timeout_seconds / top_p。"""
    assert list(BASE_PARAM_NAMES) == [
        "temperature",
        "max_output_tokens",
        "timeout_seconds",
        "top_p",
    ]


def test_catalog_entries_group_type_default_and_scope() -> None:
    """目录项包含 name/group/label/description/type/default/options/scope。"""
    entries = {str(item["name"]): item for item in MODEL_PARAM_CATALOG}
    assert set(entries) == set(catalog_names())
    for item in MODEL_PARAM_CATALOG:
        assert item["group"] in {"openai", "deepseek", "image", "custom"}
        assert item["label"]
        assert item["type"] in {"float", "int", "str", "bool"}
        assert "description" in item and "default" in item and "options" in item

    penalty = entries["frequency_penalty"]
    assert penalty["group"] == "openai"
    assert penalty["scope"] == {"providers": ["openai", "deepseek"]}
    assert penalty["type"] == "float"

    image_api = entries["image_api"]
    assert image_api["group"] == "image"
    assert image_api["scope"] == {"model_types": ["image"]}
    assert image_api["options"] == ["auto", "edits", "generations"]

    thinking = entries["deepseek_thinking_mode"]
    assert thinking["group"] == "deepseek"
    # provider 归一化匹配 + 排除生图 / TTS（R13 / A18）
    assert thinking["scope"] == {
        "providers": ["deepseek"],
        "model_types": ["chat", "vision", "other"],
    }
    assert thinking["default"] == "enabled"
    assert thinking["options"] == ["enabled", "disabled", "random"]

    # 目录项与 schema 字段默认值一致（改 schema 默认值不会让目录漂移）
    schema_fields = DeepSeekModelSettings.__dataclass_fields__
    for name, item in entries.items():
        assert item["default"] == schema_fields[name].default


def test_scope_filtering_normalizes_provider_and_model_type() -> None:
    """A18：候选按 scope 过滤，且 provider / model_type 一律走归一化值。"""
    image_names = {
        item["name"] for item in applicable_catalog(provider="DeepSeek", model_type="image")
    }
    assert "image_api" in image_names
    # R13 / A18：DeepSeek 思考参数不出现在生图模型的可选列表里
    assert "deepseek_thinking_mode" not in image_names
    assert "deepseek_reasoning_effort" not in image_names

    # R13：TTS 模型同样看不到 DeepSeek 思考参数
    tts_deepseek = {
        item["name"] for item in applicable_catalog(provider="DeepSeek", model_type="tts")
    }
    assert "deepseek_thinking_mode" not in tts_deepseek
    assert "frequency_penalty" in tts_deepseek

    tts_names = {item["name"] for item in applicable_catalog(provider="OpenAI", model_type="tts")}
    assert "image_api" not in tts_names
    assert "frequency_penalty" in tts_names

    # 归一化：DeepSeek / deepseek-offical / deepseek_official 命中同一条 scope
    for provider in ("DeepSeek", "deepseek", "deepseek-offical", "deepseek_official"):
        names = {item["name"] for item in applicable_catalog(provider=provider, model_type="chat")}
        assert "deepseek_thinking_mode" in names, provider

    # Anthropic 不接受频率 / 存在惩罚（spec 2.4），因此不出现在候选里
    anthropic_names = {
        item["name"] for item in applicable_catalog(provider="Anthropic", model_type="chat")
    }
    assert "frequency_penalty" not in anthropic_names
    assert "presence_penalty" not in anthropic_names

    # 自定义 model_type（非 image/chat/tts）只显示「全适用」参数
    custom_names = {
        item["name"] for item in applicable_catalog(provider="OpenAI", model_type="MyType")
    }
    assert custom_names == {"frequency_penalty", "presence_penalty"}
    assert normalize_model_type("MyType") == "mytype"


def test_resolve_enabled_params_classifies_unknown_and_inapplicable() -> None:
    applied, unknown, inapplicable = resolve_enabled_params(
        ["frequency_penalty", "image_api", "no_such_param", "deepseek_thinking_mode"],
        provider="OpenAI",
        model_type="chat",
    )
    assert applied == ["frequency_penalty"]
    assert unknown == ["no_such_param"]
    assert inapplicable == ["image_api", "deepseek_thinking_mode"]


# ----------------------------------------------------------------------
# 共享后处理器（两条渲染路径都过它）
# ----------------------------------------------------------------------

def test_apply_model_param_catalog_hides_optionals_and_injects_pseudo() -> None:
    """后处理器：目录内字段置 hidden，settings 组末尾注入 model_params 伪字段。"""
    from neobot_app.builtin_plugins.dashboard.config_manager import describe_dataclass

    fields = apply_model_param_catalog(describe_dataclass(BotConfig, None))
    models_group = next(item for item in fields if item["name"] == "models")
    registry_group = next(item for item in models_group["fields"] if item["name"] == "registry")
    settings_group = next(
        item for item in registry_group["item_fields"] if item["name"] == "settings"
    )

    hidden = {item["name"] for item in settings_group["fields"] if item.get("hidden")}
    assert hidden == set(catalog_names()) | {"enabled_params", "extra_body"}

    pseudo = settings_group["fields"][-1]
    assert pseudo["kind"] == "model_params"
    assert pseudo["name"] == "params"
    assert pseudo["path"][-1] == "params"
    assert pseudo["base_param_names"] == list(BASE_PARAM_NAMES)
    assert {item["name"] for item in pseudo["catalog"]} == set(catalog_names())
    assert pseudo["enabled_params"] == []
    assert pseudo["unknown_params"] == []
    assert pseudo["inapplicable_params"] == []
    assert pseudo["extra_body"] == {}


# ----------------------------------------------------------------------
# A21：未启用则不下发
# ----------------------------------------------------------------------

def test_unenabled_optional_params_never_reach_runtime_settings(tmp_path, monkeypatch) -> None:
    """A21：未列入 enabled_params 的可选参数绝不进入运行时 ModelSettings。"""
    for key, value in _OPENAI_ENV.items():
        monkeypatch.setenv(key, value)
    body = (
        _model_block(
            "chat-a",
            settings_body=(
                "temperature = 0.7\n"
                "max_output_tokens = 4096\n"
                "top_p = 0.9\n"
                "frequency_penalty = 0.5\n"
                "presence_penalty = 0.4\n"
                "enabled_params = []\n"
                "extra_body = {}\n"
            ),
        )
        + _chat_assignments()
    )
    Config.load(_write_config(tmp_path, body), BotConfig)

    settings = _registered("chat-a").settings
    assert settings.temperature == 0.7
    assert settings.max_output_tokens == 4096
    assert settings.top_p == 0.9
    # 未启用：值为 None（不下发），TOML 里的 0.5/0.4 原样保留在配置里
    assert settings.frequency_penalty is None
    assert settings.presence_penalty is None

    provider = _registered("chat-a").create_provider()
    assert isinstance(provider, OpenAIProvider)
    payload = provider._build_payload([{"role": "user", "content": "hi"}], None, stream=False)
    assert "frequency_penalty" not in payload
    assert "presence_penalty" not in payload
    assert payload["temperature"] == 0.7
    assert payload["max_tokens"] == 4096
    assert payload["top_p"] == 0.9

    raw = (tmp_path / "bot.toml").read_text(encoding="utf-8")
    assert "frequency_penalty = 0.5" in raw, "未启用的参数值必须原地保留"


def test_enabled_optional_params_reach_runtime_settings(tmp_path, monkeypatch) -> None:
    """A21 对照：列入 enabled_params 后照常下发。"""
    for key, value in _OPENAI_ENV.items():
        monkeypatch.setenv(key, value)
    body = (
        _model_block(
            "chat-a",
            settings_body=(
                "frequency_penalty = 0.5\n"
                'enabled_params = ["frequency_penalty"]\n'
                "extra_body = {}\n"
            ),
        )
        + _chat_assignments()
    )
    Config.load(_write_config(tmp_path, body), BotConfig)

    assert _registered("chat-a").settings.frequency_penalty == 0.5
    provider = _registered("chat-a").create_provider()
    assert isinstance(provider, OpenAIProvider)
    payload = provider._build_payload([{"role": "user", "content": "hi"}], None, stream=False)
    assert payload["frequency_penalty"] == 0.5


def test_scope_mismatch_is_ignored_at_runtime(tmp_path, monkeypatch) -> None:
    """A18：enabled_params 里不适用当前 scope 的名字被忽略（不下发）。"""
    for key, value in _OPENAI_ENV.items():
        monkeypatch.setenv(key, value)
    body = (
        _model_block(
            "chat-a",
            settings_body=(
                'enabled_params = ["image_api", "deepseek_thinking_mode"]\n'
                'image_api = "generations"\n'
                "extra_body = {}\n"
            ),
        )
        + _chat_assignments()
    )
    Config.load(_write_config(tmp_path, body), BotConfig)

    settings = _registered("chat-a").settings
    # chat 模型：image_api 不适用 -> 回落 auto；deepseek 参数不适用 -> 不合成内部键
    assert settings.image_api == "auto"
    assert "__deepseek_thinking_mode__" not in settings.extra_body


def test_unknown_param_name_is_ignored_with_warning(tmp_path, monkeypatch, loguru_messages) -> None:
    """目录外的名字记 warning 后忽略，不报错、不下发。"""
    for key, value in _OPENAI_ENV.items():
        monkeypatch.setenv(key, value)
    body = (
        _model_block(
            "chat-a",
            settings_body=(
                'enabled_params = ["no_such_param"]\n'
                "frequency_penalty = 0.9\n"
                "extra_body = {}\n"
            ),
        )
        + _chat_assignments()
    )
    Config.load(_write_config(tmp_path, body), BotConfig)

    assert _registered("chat-a").settings.frequency_penalty is None
    assert any("不在参数目录" in message for message in loguru_messages)


# ----------------------------------------------------------------------
# A20：extra_body 进请求体 / __ 前缀拒绝
# ----------------------------------------------------------------------

def test_extra_body_reaches_chat_payload_and_standard_param_wins(tmp_path, monkeypatch) -> None:
    """A20 + 4.6：自定义参数并入聊天请求体；与标准参数重名时标准参数优先。"""
    for key, value in _OPENAI_ENV.items():
        monkeypatch.setenv(key, value)
    body = (
        _model_block(
            "chat-a",
            settings_body=(
                "temperature = 0.7\nextra_body = { top_k = 40, temperature = 0.1 }\n"
            ),
        )
        + _chat_assignments()
    )
    Config.load(_write_config(tmp_path, body), BotConfig)

    settings = _registered("chat-a").settings
    assert settings.extra_body == {"top_k": 40, "temperature": 0.1}
    provider = _registered("chat-a").create_provider()
    assert isinstance(provider, OpenAIProvider)
    payload = provider._build_payload([{"role": "user", "content": "hi"}], None, stream=False)
    assert payload["top_k"] == 40
    assert payload["temperature"] == 0.7  # 标准参数优先（先 update(extra_body) 再设标准参数）


def test_extra_body_reserved_prefix_is_rejected_and_ignored(
    tmp_path, monkeypatch, loguru_messages
) -> None:
    """A20：__ 开头键非法（内部命名空间）；运行时忽略并告警，面板保存被拦下。"""
    from neobot_app.builtin_plugins.dashboard.config_manager import BotConfigManager

    for key, value in _OPENAI_ENV.items():
        monkeypatch.setenv(key, value)
    body = (
        _model_block(
            "chat-a",
            settings_body=(
                'extra_body = { "__deepseek_thinking_mode__" = "false", top_k = 40 }\n'
            ),
        )
        + _chat_assignments()
    )
    config_path = _write_config(tmp_path, body)
    Config.load(config_path, BotConfig)

    settings = _registered("chat-a").settings
    assert "__deepseek_thinking_mode__" not in settings.extra_body
    assert settings.extra_body["top_k"] == 40
    assert any("保留键" in message for message in loguru_messages)

    assert extra_body_reserved_keys({"__x__": 1, "top_k": 2}) == ["__x__"]

    # 面板保存路径：同一条配置必须被校验拦下
    manager = BotConfigManager(config_path=config_path, backup_dir=tmp_path / "backup")
    errors = manager.validate(
        config={
            "models": {
                "registry": [
                    {"key": "chat-a", "settings": {"extra_body": {"__x__": 1}}}
                ]
            }
        }
    )
    assert any("__" in item["message"] for item in errors)


# ----------------------------------------------------------------------
# A22 / A25：生图模型
# ----------------------------------------------------------------------

def test_image_model_has_no_internal_keys_and_defaults_to_auto(tmp_path, monkeypatch) -> None:
    """A25 + A22：provider=DeepSeek 的生图模型不注入内部键；未启用 image_api 走 auto。"""
    for key, value in _DEEPSEEK_ENV.items():
        monkeypatch.setenv(key, value)
    body = (
        _model_block(
            "img-a",
            provider="DeepSeek",
            model_type="image",
            settings_body='extra_body = { n = 1 }\nenabled_params = ["image_api"]\n',
        )
        + _IMAGE_ASSIGNMENTS
    )
    Config.load(_write_config(tmp_path, body), BotConfig)

    settings = _registered("img-a").settings
    assert not any(str(key).startswith("__deepseek") for key in settings.extra_body)
    assert settings.extra_body.get("n") == 1
    assert settings.image_api == "auto"

    # provider 合成函数：生图一律返回空，聊天照旧合成三个内部键
    assert _build_provider_extra_body("DeepSeek", DeepSeekModelSettings(), model_type="image") == {}
    assert "__deepseek_thinking_mode__" in _build_provider_extra_body(
        "DeepSeek", DeepSeekModelSettings(), model_type="chat"
    )


def test_image_api_enabled_value_reaches_runtime(tmp_path, monkeypatch) -> None:
    """A22 对照：启用 image_api 后取配置值。"""
    for key, value in _DEEPSEEK_ENV.items():
        monkeypatch.setenv(key, value)
    body = (
        _model_block(
            "img-a",
            provider="DeepSeek",
            model_type="image",
            settings_body=(
                'image_api = "generations"\nenabled_params = ["image_api"]\nextra_body = {}\n'
            ),
        )
        + _IMAGE_ASSIGNMENTS
    )
    Config.load(_write_config(tmp_path, body), BotConfig)
    assert _registered("img-a").settings.image_api == "generations"


# ----------------------------------------------------------------------
# A23：旧配置迁移
# ----------------------------------------------------------------------

def test_legacy_config_infers_enabled_params_and_keeps_values(tmp_path, monkeypatch) -> None:
    """A23：旧 config.toml（无 enabled_params）→ 按「值 ≠ 默认值」推断并写回，值不丢。"""
    for key, value in _DEEPSEEK_ENV.items():
        monkeypatch.setenv(key, value)
    body = (
        _model_block(
            "ds-a",
            provider="DeepSeek",
            settings_body=(
                # == 默认值 -> 不推断
                'deepseek_thinking_mode = "enabled"\n'
                # != 默认值 -> 推断启用
                'deepseek_reasoning_effort = "max"\n'
                # == 默认值 -> 不推断
                "deepseek_random_thinking_probability = 0.6\n"
                # == 默认值 -> 不推断
                "frequency_penalty = 0.0\n"
                'image_api = "edits"\n'
            ),
        )
        + _chat_assignments("ds-a")
    )
    config_path = _write_config(tmp_path, body)

    config = Config.load(config_path, BotConfig)

    settings_config = config.models.by_key()["ds-a"].settings
    assert settings_config.enabled_params == [
        "image_api",
        "deepseek_reasoning_effort",
    ]
    # 值一律原地保留（含未启用的）
    assert settings_config.deepseek_thinking_mode == "enabled"
    assert settings_config.deepseek_reasoning_effort == "max"
    assert settings_config.deepseek_random_thinking_probability == 0.6
    assert settings_config.frequency_penalty == 0.0

    written = config_path.read_text(encoding="utf-8")
    assert 'enabled_params = ["image_api", "deepseek_reasoning_effort"]' in written

    # R12：DeepSeek 思考参数照旧由 provider 合成（旧配置行为不突变）
    settings = _registered("ds-a").settings
    assert settings.extra_body["__deepseek_reasoning_effort__"] == "max"
    assert settings.extra_body["__deepseek_thinking_mode__"] == "true"
    # image_api 在 chat 模型 scope 外 -> 忽略，回落 auto
    assert settings.image_api == "auto"

    # 推断过的模型被登记（面板据此提示「已按旧配置推断，请复核」）
    assert is_inferred("ds-a") is True


def test_new_config_with_enabled_params_is_not_inferred(tmp_path, monkeypatch) -> None:
    """已有 enabled_params 的新配置：迁移不再推断（以清单为准）。"""
    for key, value in _DEEPSEEK_ENV.items():
        monkeypatch.setenv(key, value)
    body = (
        _model_block(
            "ds-a",
            provider="DeepSeek",
            settings_body='deepseek_reasoning_effort = "max"\nenabled_params = []\nextra_body = {}\n',
        )
        + _chat_assignments("ds-a")
    )
    Config.load(_write_config(tmp_path, body), BotConfig)
    assert is_inferred("ds-a") is False


def test_infer_enabled_params_compares_against_schema_defaults() -> None:
    """推断规则：值 ≠ schema 默认值才视为已启用（顺序即目录顺序）。"""
    assert infer_enabled_params(
        {
            "frequency_penalty": 0.0,
            "presence_penalty": -0.5,
            "image_api": "edits",
            "image_reference_param": "image",
            "deepseek_thinking_mode": "enabled",
            "deepseek_reasoning_effort": "max",
            "deepseek_random_thinking_probability": 0.6,
        }
    ) == ["presence_penalty", "image_api", "deepseek_reasoning_effort"]
    assert infer_enabled_params({}) == []
