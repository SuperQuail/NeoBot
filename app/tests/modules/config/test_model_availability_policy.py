"""模型可用性判定策略测试。

判定是纯函数：输入缺失清单，输出致命/降级两组。这里锁死三件事：
1. 默认策略「除登记的可降级角色外，一律致命」—— 保守，新增角色不会被误放行；
2. ``DegradeEverythingPolicy`` 只降级、绝不致命 —— 「先把界面起来」的运行模式；
3. 两种策略的文案都完整包含角色、key 与缺失原因（否则「能启动但不回复」无法定位）。
"""

from __future__ import annotations

import pytest

from neobot_app.config.availability import (
    DEFAULT_DEGRADABLE_ROLES,
    AvailabilityReport,
    DegradeEverythingPolicy,
    FindingSeverity,
    ModelAvailabilityPolicy,
    ModelFinding,
)


def _finding(role: str, key: str = "some-model", missing: tuple[str, ...] = ("平台 X_APIKey 配置",)):
    return ModelFinding(role=role, key=key, missing=missing)


# ── 默认策略：保守 ──────────────────────────────────────────────────


def test_default_policy_keeps_required_roles_fatal() -> None:
    report = ModelAvailabilityPolicy().classify(
        [_finding("primary_chat_model"), _finding("agent_model_1")]
    )

    assert report.has_fatal is True
    assert {item.role for item in report.fatal} == {"primary_chat_model", "agent_model_1"}
    assert report.has_degraded is False


@pytest.mark.parametrize("role", sorted(DEFAULT_DEGRADABLE_ROLES))
def test_default_policy_degrades_registered_roles(role: str) -> None:
    report = ModelAvailabilityPolicy().classify([_finding(role)])

    assert report.has_fatal is False
    assert [item.role for item in report.degraded] == [role]


def test_default_policy_unknown_role_is_fatal_not_silently_allowed() -> None:
    """未登记的新角色默认致命：不能让新增角色被无意放行。"""
    report = ModelAvailabilityPolicy().classify([_finding("brand_new_role")])

    assert report.has_fatal is True


def test_degradable_roles_can_be_narrowed() -> None:
    policy = ModelAvailabilityPolicy(degradable_roles=())

    report = policy.classify([_finding("vision_model")])

    assert report.has_fatal is True


# ── 降级策略：绝不致命 ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "role",
    ["primary_chat_model", "agent_model_1", "vision_model", "tts_model", "brand_new_role"],
)
def test_degrade_everything_never_fatal(role: str) -> None:
    report = DegradeEverythingPolicy().classify([_finding(role)])

    assert report.has_fatal is False
    assert report.has_degraded is True


def test_degrade_everything_preserves_all_findings() -> None:
    findings = [_finding("primary_chat_model", key="a"), _finding("tts_model", key="b")]

    report = DegradeEverythingPolicy().classify(findings)

    assert [item.key for item in report.degraded] == ["a", "b"]


# ── 文案 ────────────────────────────────────────────────────────────


def test_fatal_message_lists_every_finding() -> None:
    report = ModelAvailabilityPolicy().classify(
        [
            _finding("primary_chat_model", key="deepseek-v4-pro", missing=("平台 DeepSeek_APIKey 配置",)),
            _finding("agent_model_1", key="deepseek-v4-flash", missing=("provider 配置", "model_name 配置")),
        ]
    )

    message = report.fatal_message()

    assert "配置校验失败" in message
    assert "模型 deepseek-v4-pro（primary_chat_model）缺少: 平台 DeepSeek_APIKey 配置" in message
    assert "模型 deepseek-v4-flash（agent_model_1）缺少: provider 配置、model_name 配置" in message


def test_fatal_message_is_empty_without_fatal_findings() -> None:
    assert AvailabilityReport(fatal=()).fatal_message() == ""


def test_degraded_messages_are_per_finding() -> None:
    report = ModelAvailabilityPolicy().classify(
        [_finding("vision_model", key="qwen3-vl"), _finding("tts_model", key="cosyvoice2")]
    )

    messages = report.degraded_messages()

    assert len(messages) == 2
    assert messages[0].startswith("模型 qwen3-vl（vision_model）缺少: ")
    assert messages[1].startswith("模型 cosyvoice2（tts_model）缺少: ")


def test_finding_without_key_describes_role_only() -> None:
    """引用缺失 key 的场景没有具体模型 key，文案不能出现空的「模型 （role）」。"""
    text = ModelFinding(
        role="primary_chat_model",
        key="",
        missing=("引用的模型缺少 key（模型库条目的 key 不能为空）",),
    ).describe()

    assert "模型 （" not in text
    assert text.startswith("primary_chat_model: ")


def test_severity_enum_values() -> None:
    assert FindingSeverity.FATAL == "fatal"
    assert FindingSeverity.DEGRADED == "degraded"
