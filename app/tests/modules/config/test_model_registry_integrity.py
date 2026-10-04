"""模型库引用名完整性：合法引用不得误报，缺失/重复的引用名必须可见。

对应两条 issue：
- #68 所有合法分配被误报「引用了模型库中不存在的引用名」（改名时漏改 by_key -> by_ref，
  又用 hasattr 静默兜底，导致校验实际失效）；
- #69 引用名缺失（by_ref 跳过）或重复（字典推导后写覆盖）的条目被静默丢弃。

注意：`[models.assignments]` 是**逐键与默认值合并**的，只写一个角色时其余角色会保留
默认引用名。所以这里的 fixture 必须显式写满所有角色，否则会混进默认引用造成的噪音。
"""

from __future__ import annotations

from pathlib import Path

import loguru
import pytest

from neobot_app.config.loader.manager import Config
from neobot_app.config.schemas.bot import BotConfig

MISSING_REF_MARKER = "引用了模型库中不存在的引用名"
NO_BY_REF_MARKER = "没有 by_ref()"

#: 与 ModelAssignments 的字段一致；测试里统一全量覆盖，避免默认值混入
ROLES = (
    "primary_chat_model",
    "agent_model_1",
    "agent_model_2",
    "agent_model_3",
    "vision_model",
    "tts_model",
)


@pytest.fixture()
def loguru_messages():
    """收集 loguru 输出（pytest 的 caplog 抓不到 loguru）。"""
    records: list[str] = []
    sink_id = loguru.logger.add(lambda message: records.append(message), format="{message}")
    try:
        yield records
    finally:
        loguru.logger.remove(sink_id)


def _assignments_block(default_ref: str, **overrides: str) -> str:
    lines = ["[models.assignments]"]
    for role in ROLES:
        lines.append(f'{role} = "{overrides.get(role, default_ref)}"')
    image_ref = overrides.get("creator_image_models", default_ref)
    lines.append(f'creator_image_models = ["{image_ref}"]')
    return "\n".join(lines) + "\n"


def _write_config(tmp_path: Path, registry: str, assignments: str) -> Path:
    cfg_path = tmp_path / "bot.toml"
    cfg_path.write_text(
        "[bot]\naccount = 10001\n\n[chat]\n\n" + registry + "\n" + assignments,
        encoding="utf-8",
    )
    return cfg_path


def _entry(model_ref: str | None, model_name: str, provider: str = "DeepSeek") -> str:
    parts = ["[[models.registry]]"]
    if model_ref is not None:
        parts.append(f'model_ref = "{model_ref}"')
    parts.append(f'provider = "{provider}"')
    parts.append(f'model_name = "{model_name}"')
    return "\n".join(parts) + "\n"


def _messages_containing(messages: list[str], marker: str) -> list[str]:
    """按**去重后**的文案返回：`Config.load` 内部已注册一轮，显式再调 `register_models`
    会产生一轮完全相同的告警，这里关心的是「有没有把问题说清楚」，不是说了几遍。"""
    unique: list[str] = []
    for message in messages:
        if marker in message and message not in unique:
            unique.append(message)
    return unique


# ---------------------------------------------------------------- #68


def test_valid_assignments_are_never_reported_as_missing(tmp_path, loguru_messages):
    """合法引用不得被误报为「不存在」——这是 #68 的直接回归守卫。"""
    # Arrange：库里两个条目（同名不同配置），分配分别指向它们
    cfg_path = _write_config(
        tmp_path,
        _entry("flash", "deepseek-flash") + "\n" + _entry("flash-max", "deepseek-flash"),
        _assignments_block("flash", agent_model_1="flash-max"),
    )

    # Act
    config_obj = Config.load(cfg_path, BotConfig)
    Config.register_models(config_obj)

    # Assert
    assert _messages_containing(loguru_messages, MISSING_REF_MARKER) == []
    assert _messages_containing(loguru_messages, NO_BY_REF_MARKER) == []
    assert set(config_obj.models.by_ref()) == {"flash", "flash-max"}


def test_truly_missing_reference_is_reported_once(tmp_path, loguru_messages):
    """真的写了库里没有的引用名时，必须恰好报出那一个。"""
    cfg_path = _write_config(
        tmp_path,
        _entry("flash", "deepseek-flash"),
        _assignments_block("flash", agent_model_1="typo-does-not-exist"),
    )

    config_obj = Config.load(cfg_path, BotConfig)
    Config.register_models(config_obj)

    reported = _messages_containing(loguru_messages, MISSING_REF_MARKER)
    assert len(reported) == 1
    assert "typo-does-not-exist" in reported[0]
    assert "primary_chat_model" not in reported[0]


# ---------------------------------------------------------------- #69


def test_entry_without_model_ref_is_reported_not_silently_dropped(tmp_path, loguru_messages):
    """缺引用名的条目会被 by_ref() 跳过；必须告警说清是第几个条目（#69 情况一）。"""
    cfg_path = _write_config(
        tmp_path,
        _entry("flash", "deepseek-flash") + "\n" + _entry(None, "deepseek-v4-pro"),
        _assignments_block("flash"),
    )

    config_obj = Config.load(cfg_path, BotConfig)
    Config.register_models(config_obj)

    warnings = _messages_containing(loguru_messages, "缺少引用名")
    assert len(warnings) == 1
    assert "第 2 个条目" in warnings[0]
    assert "deepseek-v4-pro" in warnings[0]
    # 既有行为保持不变：该条目不进 by_ref()
    assert set(config_obj.models.by_ref()) == {"flash"}


def test_duplicate_model_ref_is_reported(tmp_path, loguru_messages):
    """重复引用名会后者覆盖前者；必须告警，不然先写的条目静默失效（#69 情况二）。"""
    cfg_path = _write_config(
        tmp_path,
        _entry("flash", "deepseek-flash") + "\n" + _entry("flash", "deepseek-v4-pro"),
        _assignments_block("flash"),
    )

    config_obj = Config.load(cfg_path, BotConfig)
    Config.register_models(config_obj)

    warnings = _messages_containing(loguru_messages, "重复引用名")
    assert len(warnings) == 1
    assert "flash" in warnings[0]
    assert "第 1 个" in warnings[0] and "第 2 个" in warnings[0]
    # 记录既有行为：后者生效
    assert config_obj.models.by_ref()["flash"].model_name == "deepseek-v4-pro"


def test_healthy_registry_produces_no_integrity_warning(tmp_path, loguru_messages):
    """正常模型库不该产生任何自检告警（避免把真问题淹没在噪音里）。"""
    cfg_path = _write_config(
        tmp_path,
        _entry("flash", "deepseek-flash") + "\n" + _entry("flash-2", "deepseek-flash"),
        _assignments_block("flash", agent_model_1="flash-2"),
    )

    Config.load(cfg_path, BotConfig)
    Config.register_models(Config.load(cfg_path, BotConfig))

    assert _messages_containing(loguru_messages, "缺少引用名") == []
    assert _messages_containing(loguru_messages, "重复引用名") == []
    assert _messages_containing(loguru_messages, MISSING_REF_MARKER) == []
