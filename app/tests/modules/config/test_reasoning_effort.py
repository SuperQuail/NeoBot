"""模型库顶层推理强度（reasoning_effort）：契约元数据 / 解析规则 / 加载器下发。

覆盖三块：
- schema 元数据：扁平 options、options_strict、option_labels、option_groups（面板 T2/T3 依赖）；
- resolve_reasoning_effort / describe_reasoning_effort 的各分支；
- register_models：按 provider 归一格式、非法值 / 生图 TTS 忽略告警、旧 DeepSeek 私有键兼容。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import loguru
import pytest

from neobot_app.config.loader.manager import Config
from neobot_app.config.reasoning_effort import (
    CLAUDE_EFFORTS,
    CLAUDE_PREFIX,
    EFFORT_OPTIONS,
    OPENAI_EFFORTS,
    OPTION_GROUPS,
    OPTION_LABELS,
    describe_reasoning_effort,
    resolve_reasoning_effort,
)
from neobot_app.config.schemas.bot import BotConfig, ModelDefinition
from neobot_chat import get_model_registry
from neobot_chat.providers import AnthropicProvider, DeepSeekOfficalProvider, OpenAIProvider

_ENV = {
    "OpenAI_URL": "https://api.openai.com/v1",
    "OpenAI_APIKey": "sk-openai-test",
    "Anthropic_URL": "https://api.anthropic.com",
    "Anthropic_APIKey": "sk-anthropic-test",
    "DeepSeek_URL": "https://api.deepseek.com",
    "DeepSeek_APIKey": "sk-deepseek-test",
}

_CHAT_ASSIGNMENTS = (
    "[models.assignments]\n"
    'primary_chat_model = "chat-a"\n'
    'agent_model_1 = "chat-a"\n'
    'agent_model_2 = "chat-a"\n'
    'agent_model_3 = "chat-a"\n'
)


@pytest.fixture(autouse=True)
def _clean_registry():
    get_model_registry().clear()
    yield
    get_model_registry().clear()


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
    model_type: str = "chat",
    reasoning_effort: str | None = None,
    settings_body: str = "",
) -> str:
    lines = [
        "[[models.registry]]",
        f'model_ref = "{key}"',
        f'model_type = "{model_type}"',
        f'display_name = "测试模型 {key}"',
        f'provider = "{provider}"',
        'model_name = "test-model-1"',
    ]
    if reasoning_effort is not None:
        lines.append(f'reasoning_effort = "{reasoning_effort}"')
    lines.append("[models.registry.settings]")
    return "\n".join(lines) + "\n" + settings_body


def _registered(key: str) -> Any:
    registered = get_model_registry().get(key)
    assert registered is not None, f"模型 {key} 未注册"
    return registered


def _payload(registered: Any) -> dict[str, Any]:
    """用注册出来的 provider 构造请求体（不发网络请求）。"""
    provider = registered.create_provider()
    build = getattr(provider, "_build_payload", None)
    if build is not None:
        return build([{"role": "user", "content": "hi"}], None, stream=False)
    # Anthropic 没有 _build_payload：直接验证 provider 属性由注册链透传
    return {"reasoning_effort": provider.reasoning_effort, "format": provider.reasoning_effort_format}


# ----------------------------------------------------------------------
# schema 元数据（面板契约）
# ----------------------------------------------------------------------


def test_schema_field_defaults_and_position() -> None:
    """顶层字段：默认空串，位置在 model_name 之后、pricing 之前（T2/T3 契约）。"""
    fields = list(ModelDefinition.__dataclass_fields__)
    assert fields.index("reasoning_effort") == fields.index("model_name") + 1
    assert fields.index("reasoning_effort") + 1 == fields.index("pricing")
    assert ModelDefinition.__dataclass_fields__["reasoning_effort"].default == ""


def test_schema_metadata_options_labels_and_groups_are_static() -> None:
    """options / option_labels / option_groups 必须是 describe 能原样透传的 list/dict。"""
    metadata = ModelDefinition.__dataclass_fields__["reasoning_effort"].metadata
    expected_options = [
        "",
        *OPENAI_EFFORTS,
        *(CLAUDE_PREFIX + item for item in CLAUDE_EFFORTS),
    ]
    assert expected_options == EFFORT_OPTIONS
    assert list(metadata["options"]) == EFFORT_OPTIONS
    assert metadata["options_strict"] is True
    assert metadata["description"]

    labels = metadata["option_labels"]
    assert isinstance(labels, dict)
    assert labels == OPTION_LABELS
    assert set(labels) == set(EFFORT_OPTIONS), "每个可选项都必须有中文显示名"
    assert all(isinstance(name, str) and name for name in labels.values())

    groups = metadata["option_groups"]
    assert isinstance(groups, list)
    assert groups == OPTION_GROUPS
    flat = set(EFFORT_OPTIONS)
    for group in groups:
        assert isinstance(group, dict)
        assert isinstance(group["label"], str) and group["label"]
        assert isinstance(group["options"], list)
        assert set(group["options"]) <= flat
    # Claude 系单独成组，且组内取值一律带前缀（面板据此标注）
    claude_group = groups[-1]
    assert all(option.startswith(CLAUDE_PREFIX) for option in claude_group["options"])
    assert [option.split(":", 1)[1] for option in claude_group["options"]] == list(CLAUDE_EFFORTS)
    # 空值不属于任何分组（前端先渲染未分组项，再渲染 optgroup）
    assert all("" not in group["options"] for group in groups)


# ----------------------------------------------------------------------
# resolve / describe
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "provider_kind", "expected"),
    [
        ("", "openai", (None, "openai")),
        ("", "deepseek", (None, "openai")),
        ("", "anthropic", (None, "claude")),
        ("   ", "anthropic", (None, "claude")),
        ("high", "openai", ("high", "openai")),
        ("high", "deepseek", ("high", "openai")),
        ("high", "anthropic", ("high", "claude")),
        ("none", "openai", ("none", "openai")),
        ("minimal", "openai", ("minimal", "openai")),
        # DeepSeek 官方只认 high / max：非 high/max 档位在解析时就归并成真正下发的值
        ("none", "deepseek", ("high", "openai")),
        ("minimal", "deepseek", ("high", "openai")),
        ("low", "deepseek", ("high", "openai")),
        ("medium", "deepseek", ("high", "openai")),
        ("xhigh", "deepseek", ("max", "openai")),
        ("xhigh", "DeepSeek-Offical", ("max", "openai")),
        # Claude 系没有 none / minimal 档位：选了视为无效，由调用方告警
        ("none", "anthropic", (None, "claude")),
        ("minimal", "anthropic", (None, "claude")),
        ("claude:max", "openai", ("max", "claude")),
        ("claude:max", "anthropic", ("max", "claude")),
        # DeepSeek /chat/completions 没有 output_config：Claude 系前缀在 DeepSeek 上无效
        ("claude:low", "deepseek", (None, "openai")),
        ("claude:max", "deepseek", (None, "openai")),
        ("CLAUDE:HIGH", "openai", ("high", "claude")),
        ("claude:none", "openai", (None, "claude")),
        ("claude:", "openai", (None, "claude")),
        (" high ", "openai", ("high", "openai")),
        ("ultra", "openai", (None, "openai")),
        ("ultra", "anthropic", (None, "claude")),
    ],
)
def test_resolve_reasoning_effort(value, provider_kind, expected) -> None:
    assert resolve_reasoning_effort(value, provider_kind=provider_kind) == expected


@pytest.mark.parametrize(
    ("value", "kwargs", "expected"),
    [
        ("", {}, ""),
        ("   ", {}, ""),
        ("high", {}, "high"),
        ("High", {}, "high"),
        ("claude:high", {}, "Claude 系 · high"),
        ("claude:max", {}, "Claude 系 · max"),
        ("claude:", {}, "claude:（无效）"),
        # Anthropic：普通值实际走 output_config.effort，展示时必须标出来
        ("high", {"provider_kind": "anthropic"}, "Claude 系 · high"),
        ("none", {"provider_kind": "anthropic"}, "none（Claude 系不支持）"),
        # DeepSeek：归并档位 / 不支持的 Claude 系 / 思考关闭都要在展示层说清楚
        ("low", {"provider_kind": "deepseek"}, "low（实际下发 high）"),
        ("low", {"provider_kind": "DeepSeek-Offical"}, "low（实际下发 high）"),
        ("xhigh", {"provider_kind": "deepseek"}, "xhigh（实际下发 max）"),
        (
            "claude:max",
            {"provider_kind": "deepseek"},
            "Claude 系 · max（DeepSeek 不支持 Claude 系）",
        ),
        (
            "high",
            {"provider_kind": "deepseek", "thinking_enabled": False},
            "high（思考已关闭，不下发）",
        ),
        # 生图 / TTS 模型上配了也不会下发
        ("max", {"model_type": "image"}, "max（该模型类型不生效）"),
        ("claude:high", {"model_type": "tts"}, "Claude 系 · high（该模型类型不生效）"),
    ],
)
def test_describe_reasoning_effort(value, kwargs, expected) -> None:
    assert describe_reasoning_effort(value, **kwargs) == expected


# ----------------------------------------------------------------------
# 加载器：解析结果进入运行时 settings 并真正下发
# ----------------------------------------------------------------------


def test_loader_passes_openai_effort_to_runtime_settings_and_payload(tmp_path, monkeypatch, loguru_messages) -> None:
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)
    body = _model_block("chat-a", reasoning_effort="high") + _CHAT_ASSIGNMENTS
    Config.load(_write_config(tmp_path, body), BotConfig)

    registered = _registered("chat-a")
    assert registered.settings.reasoning_effort == "high"
    assert registered.settings.reasoning_effort_format == "openai"
    provider = registered.create_provider()
    assert isinstance(provider, OpenAIProvider)
    assert provider.reasoning_effort == "high"
    assert _payload(registered)["reasoning_effort"] == "high"
    # 生效值必须能在启动日志里看到（排查「配了没生效」）
    assert any("推理强度: high" in message for message in loguru_messages)


def test_loader_maps_plain_value_to_claude_format_for_anthropic(tmp_path, monkeypatch) -> None:
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)
    body = _model_block("chat-a", provider="Anthropic", reasoning_effort="high") + _CHAT_ASSIGNMENTS
    Config.load(_write_config(tmp_path, body), BotConfig)

    registered = _registered("chat-a")
    assert registered.settings.reasoning_effort == "high"
    assert registered.settings.reasoning_effort_format == "claude"
    provider = registered.create_provider()
    assert isinstance(provider, AnthropicProvider)
    assert provider.reasoning_effort == "high"


def test_loader_keeps_claude_prefix_on_openai_compatible_provider(tmp_path, monkeypatch) -> None:
    """claude: 前缀与 provider 无关：走 Anthropic 协议的中转站也按 Claude 系下发。"""
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)
    body = _model_block("chat-a", reasoning_effort="claude:max") + _CHAT_ASSIGNMENTS
    Config.load(_write_config(tmp_path, body), BotConfig)

    registered = _registered("chat-a")
    assert registered.settings.reasoning_effort == "max"
    assert registered.settings.reasoning_effort_format == "claude"
    assert _payload(registered)["output_config"] == {"effort": "max"}


def test_loader_empty_effort_is_not_dispatched(tmp_path, monkeypatch, loguru_messages) -> None:
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)
    body = _model_block("chat-a", reasoning_effort="") + _CHAT_ASSIGNMENTS
    Config.load(_write_config(tmp_path, body), BotConfig)

    registered = _registered("chat-a")
    assert registered.settings.reasoning_effort is None
    payload = _payload(registered)
    assert "reasoning_effort" not in payload
    assert "output_config" not in payload
    assert not any("推理强度" in message for message in loguru_messages)


def test_loader_warns_and_ignores_invalid_effort(tmp_path, monkeypatch, loguru_messages) -> None:
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)
    body = _model_block("chat-a", reasoning_effort="ultra") + _CHAT_ASSIGNMENTS
    Config.load(_write_config(tmp_path, body), BotConfig)

    registered = _registered("chat-a")
    assert registered.settings.reasoning_effort is None
    assert "reasoning_effort" not in _payload(registered)
    warnings = [message for message in loguru_messages if "推理强度取值 ultra 无效" in message]
    assert warnings, "非法值必须告警，不能静默忽略"
    assert "chat-a" in warnings[0]


def test_loader_warns_and_ignores_none_on_anthropic(tmp_path, monkeypatch, loguru_messages) -> None:
    """Claude 系不支持 none：格式不匹配同样必须告警。"""
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)
    body = _model_block("chat-a", provider="Anthropic", reasoning_effort="none") + _CHAT_ASSIGNMENTS
    Config.load(_write_config(tmp_path, body), BotConfig)

    registered = _registered("chat-a")
    assert registered.settings.reasoning_effort is None
    assert registered.settings.reasoning_effort_format == "claude"
    warnings = [message for message in loguru_messages if "推理强度取值 none 无效" in message]
    assert warnings and "Claude 系" in warnings[0]


def test_loader_ignores_effort_for_image_and_tts_models(tmp_path, monkeypatch, loguru_messages) -> None:
    """生图 / TTS 模型没有推理强度概念：忽略并告警，不进入运行时 settings。"""
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)
    image_body = (
        _model_block("img-a", model_type="image", reasoning_effort="max")
        + '[agent.creator]\nenabled = true\n[models.assignments]\ncreator_image_models = ["img-a"]\n'
    )
    Config.load(_write_config(tmp_path, image_body), BotConfig)
    assert _registered("img-a").settings.reasoning_effort is None
    assert any("推理强度（max）对 image 模型无意义" in message for message in loguru_messages)

    tts_body = (
        _model_block("tts-a", model_type="tts", reasoning_effort="high")
        + '[tts]\nenabled = true\n[models.assignments]\ntts_model = "tts-a"\n'
    )
    Config.load(_write_config(tmp_path, tts_body), BotConfig)
    assert _registered("tts-a").settings.reasoning_effort is None
    assert any("推理强度（high）对 tts 模型无意义" in message for message in loguru_messages)


def test_loader_legacy_deepseek_private_key_still_works(tmp_path, monkeypatch) -> None:
    """旧 settings.deepseek_reasoning_effort 兼容：顶层留空时仍按原逻辑注入私有键。"""
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)
    body = (
        _model_block(
            "chat-a",
            provider="DeepSeek",
            reasoning_effort="",
            settings_body='deepseek_thinking_mode = "enabled"\ndeepseek_reasoning_effort = "high"\n',
        )
        + _CHAT_ASSIGNMENTS
    )
    Config.load(_write_config(tmp_path, body), BotConfig)

    registered = _registered("chat-a")
    assert registered.settings.reasoning_effort is None
    assert registered.settings.extra_body["__deepseek_reasoning_effort__"] == "high"
    payload = _payload(registered)
    assert payload["reasoning_effort"] == "high"
    assert payload["thinking"] == {"type": "enabled"}


def test_loader_top_level_effort_overrides_legacy_private_key(tmp_path, monkeypatch) -> None:
    """顶层显式值优先于旧私有键（含 DeepSeek 侧档位归并）。"""
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)
    body = (
        _model_block(
            "chat-a",
            provider="DeepSeek",
            reasoning_effort="max",
            settings_body='deepseek_thinking_mode = "enabled"\ndeepseek_reasoning_effort = "high"\n',
        )
        + _CHAT_ASSIGNMENTS
    )
    Config.load(_write_config(tmp_path, body), BotConfig)

    registered = _registered("chat-a")
    assert isinstance(registered.create_provider(), DeepSeekOfficalProvider)
    assert registered.settings.reasoning_effort == "max"
    assert _payload(registered)["reasoning_effort"] == "max"


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("none", "high"),
        ("minimal", "high"),
        ("low", "high"),
        ("medium", "high"),
        ("xhigh", "max"),
    ],
)
def test_loader_normalizes_deepseek_secondary_efforts_with_warning(
    tmp_path, monkeypatch, loguru_messages, configured, expected
) -> None:
    """DeepSeek 只认 high / max：其余档位在解析时归并，运行时 settings / 日志 / 请求体三方一致。"""
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)
    body = (
        _model_block(
            "chat-a",
            provider="DeepSeek",
            reasoning_effort=configured,
            settings_body='deepseek_thinking_mode = "enabled"\n',
        )
        + _CHAT_ASSIGNMENTS
    )
    Config.load(_write_config(tmp_path, body), BotConfig)

    registered = _registered("chat-a")
    # 既然最终只发 high / max，运行时 settings 与启动日志都必须显示真正下发的值
    assert registered.settings.reasoning_effort == expected
    assert _payload(registered)["reasoning_effort"] == expected
    assert any(f"推理强度: {expected}" in message for message in loguru_messages)
    warnings = [
        message for message in loguru_messages if f"推理强度 {configured} 在 DeepSeek 官方只支持 high / max" in message
    ]
    assert warnings, "静默归并会让用户以为所选档位真的生效"


def test_loader_rejects_claude_format_on_deepseek_with_warning(tmp_path, monkeypatch, loguru_messages) -> None:
    """DeepSeek /chat/completions 没有 output_config：Claude 系前缀必须拒绝而不是照发。"""
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)
    body = (
        _model_block(
            "chat-a",
            provider="DeepSeek",
            reasoning_effort="claude:max",
            # 旧键也留空：否则 provider 会继续按旧的默认 high 下发，掩盖「顶层被拒绝」这一点
            settings_body='deepseek_thinking_mode = "enabled"\ndeepseek_reasoning_effort = ""\n',
        )
        + _CHAT_ASSIGNMENTS
    )
    Config.load(_write_config(tmp_path, body), BotConfig)

    registered = _registered("chat-a")
    assert registered.settings.reasoning_effort is None
    payload = _payload(registered)
    assert "reasoning_effort" not in payload
    assert "output_config" not in payload
    warnings = [message for message in loguru_messages if "推理强度取值 claude:max 无效" in message]
    assert warnings and "DeepSeek" in warnings[0]


def test_loader_warns_when_deepseek_thinking_disabled_but_effort_set(tmp_path, monkeypatch, loguru_messages) -> None:
    """思考已关闭时推理强度不会下发，但面板/日志不能装作它在生效。"""
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)
    body = (
        _model_block(
            "chat-a",
            provider="DeepSeek",
            reasoning_effort="max",
            settings_body='deepseek_thinking_mode = "disabled"\n',
        )
        + _CHAT_ASSIGNMENTS
    )
    Config.load(_write_config(tmp_path, body), BotConfig)

    registered = _registered("chat-a")
    assert registered.settings.reasoning_effort == "max"
    payload = _payload(registered)
    assert payload["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in payload
    warnings = [message for message in loguru_messages if "思考模式已关闭" in message and "不会下发" in message]
    assert warnings


def test_default_library_declares_reasoning_effort() -> None:
    """出厂模型库：四个对话模型都显式声明顶层推理强度，语音模型不声明。"""
    from neobot_app.config.schemas.bot import Models

    library = {item.model_ref: item for item in Models().registry}
    assert library["deepseek-flash"].reasoning_effort == "max"
    assert library["deepseek-flash-max"].reasoning_effort == "max"
    assert library["deepseek-flash-high"].reasoning_effort == "high"
    assert library["deepseek-flash-off"].reasoning_effort == ""
    assert library["cosyvoice2"].reasoning_effort == ""
