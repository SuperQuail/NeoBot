"""WillingnessSkill 与 WillingService 测试 — 系数钳制/黑名单/异常兜底。"""

from __future__ import annotations

import json
from typing import Any

import pytest

from neobot_adapter.model.message import GroupMessage
from neobot_app.config.schemas.bot import BotConfig
from neobot_app.message.queue import MessageQueue
from neobot_app.skills.willingness_skill import WillingnessSkill
from neobot_app.willing.service import WillingService

GROUP_KEY = "group:456789"


def _make_config() -> BotConfig:
    config = BotConfig()
    config.chat.group_chat_chance = 1.0
    config.chat.reply_mode = "common"
    return config


@pytest.fixture()
def willing_service(tmp_path, monkeypatch) -> WillingService:
    """把数据目录重定向到临时目录后构造真实 WillingService。"""
    monkeypatch.setenv("NEOBOT_DATA_DIR", str(tmp_path / "data"))
    return WillingService(config=_make_config())


def _skill(service: WillingService | None = None) -> WillingnessSkill:
    return WillingnessSkill(willing_service=service)


def _expect_json(payload: str) -> dict[str, Any]:
    """系数/黑名单操作返回文本摘要；未配置分支返回 JSON，两种都容错解析。"""
    try:
        return json.loads(payload)
    except (ValueError, TypeError):
        return {"ok": True, "result": payload}


async def test_set_and_remove_session_coefficient_round_trip(willing_service):
    """正常路径：设置会话系数后 summary 应可见，移除后恢复默认。"""
    skill = _skill(willing_service)

    set_result = _expect_json(await skill.execute("set_session_coefficient", {"value": 0.5}))

    assert set_result["ok"] is True
    assert "0.500" in set_result["result"]
    summary = await skill.execute("get_willingness_status", {})
    assert "会话系数" in summary
    assert "current=0.500" in summary

    remove_result = _expect_json(await skill.execute("remove_session_coefficient", {}))

    assert "已移除会话 current 的临时回复系数" in remove_result["result"]
    after = await skill.execute("get_willingness_status", {})
    assert "会话系数" not in after


async def test_session_coefficient_clamped_to_one(willing_service):
    """边界：value=5 超出上限应被钳制为 1.000。"""
    skill = _skill(willing_service)

    result = _expect_json(await skill.execute("set_session_coefficient", {"value": 5}))

    assert result["ok"] is True
    assert "1.000" in result["result"]


async def test_session_coefficient_clamped_to_zero(willing_service):
    """边界：value=-1 低于下限应被钳制为 0.000。"""
    skill = _skill(willing_service)

    result = _expect_json(await skill.execute("set_session_coefficient", {"value": -1}))

    assert result["ok"] is True
    assert "0.000" in result["result"]


async def test_session_user_coefficient_normalizes_conv_id(willing_service):
    """正常路径：conv_id 带 'kind:' 前缀时应归一化后存储。"""
    skill = _skill(willing_service)

    result = _expect_json(
        await skill.execute("set_session_user_coefficient", {
            "user_id": "10001",
            "value": 0.25,
            "conv_id": GROUP_KEY,
        })
    )

    assert result["ok"] is True
    assert "456789" in result["result"]
    summary = await skill.execute("get_willingness_status", {})
    assert "456789/10001=0.250" in summary


async def test_user_global_coefficient_set_remove_messages(willing_service):
    """正常路径：用户全局系数可设置与移除，重复移除返回提示语。"""
    skill = _skill(willing_service)

    set_result = _expect_json(
        await skill.execute("set_user_global_coefficient", {"user_id": "10001", "value": 0.8})
    )

    assert "0.800" in set_result["result"]

    remove_result = _expect_json(
        await skill.execute("remove_user_global_coefficient", {"user_id": "10001"})
    )

    assert "已移除用户 10001 的全局回复系数" in remove_result["result"]

    again = _expect_json(
        await skill.execute("remove_user_global_coefficient", {"user_id": "10001"})
    )

    assert "没有全局回复系数" in again["result"]


async def test_remove_last_conversation_user_coefficient_cleans_entry(willing_service):
    """边界：移除会话内最后一个用户系数后应清理空的会话条目。"""
    skill = _skill(willing_service)
    await skill.execute("set_session_user_coefficient", {
        "user_id": "10001",
        "value": 0.5,
        "conv_id": GROUP_KEY,
    })

    result = _expect_json(
        await skill.execute("remove_session_user_coefficient", {
            "user_id": "10001",
            "conv_id": GROUP_KEY,
        })
    )

    assert "已移除会话 456789 中用户 10001" in result["result"]
    summary = await skill.execute("get_willingness_status", {})
    assert "会话用户系数" not in summary


async def test_service_blacklist_blocks_and_unblocks_runtime_reply(willing_service):
    """正常路径：service 层加入黑名单后 block_reason 应返回 runtime_blacklisted。"""
    message = GroupMessage(
        message_id=1, user_id=123456, group_id=456789, raw_message="在吗"
    )

    willing_service.add_runtime_blacklist(GROUP_KEY)

    assert (
        willing_service.block_reason_for_message(message=message, queue_key="456789")
        == "runtime_blacklisted"
    )

    willing_service.remove_runtime_blacklist(GROUP_KEY)

    assert willing_service.block_reason_for_message(message=message, queue_key="456789") == ""


@pytest.mark.xfail(
    reason="BUG-0004 add_session_blacklist 忽略 pipeline_key 参数，硬编码 'current'，无法屏蔽真实会话",
    strict=False,
)
async def test_add_session_blacklist_should_block_given_pipeline_key(willing_service):
    """异常路径：带 pipeline_key 调用 add_session_blacklist 后该会话应被屏蔽。"""
    skill = _skill(willing_service)
    message = GroupMessage(
        message_id=1, user_id=123456, group_id=456789, raw_message="在吗"
    )

    await skill.execute("add_session_blacklist", {"pipeline_key": GROUP_KEY})

    assert (
        willing_service.block_reason_for_message(message=message, queue_key=GROUP_KEY)
        == "runtime_blacklisted"
    )


@pytest.mark.xfail(
    reason="BUG-0005 黑名单/系数存储时剥离 kind: 前缀，但 block_reason 与 evaluate 用未归一化的 queue_key 比对，前缀键永不命中",
    strict=False,
)
async def test_blacklist_with_prefixed_key_should_block_conversation(willing_service):
    """异常路径：以 group:xxx 前缀键加入黑名单后，该会话消息应被完全屏蔽。"""
    queue = MessageQueue()
    message = GroupMessage(
        message_id=3, user_id=123456, group_id=456789, raw_message="你好"
    )
    queue.push(GROUP_KEY, message)
    willing_service.add_runtime_blacklist(GROUP_KEY)

    assert (
        willing_service.block_reason_for_message(message=message, queue_key=GROUP_KEY)
        == "runtime_blacklisted"
    )
    decision = willing_service.evaluate(
        message=message, queue=queue, queue_key=GROUP_KEY
    )
    assert decision.should_reply is False


async def test_runtime_blacklist_zeroes_group_probability(willing_service):
    """正常路径：黑名单会话的群消息 evaluate 应完全屏蔽回复。"""
    queue = MessageQueue()
    message = GroupMessage(
        message_id=2, user_id=123456, group_id=456789, raw_message="你好"
    )
    queue.push("456789", message)
    willing_service.add_runtime_blacklist(GROUP_KEY)

    decision = willing_service.evaluate(
        message=message, queue=queue, queue_key="456789"
    )

    assert decision.should_reply is False
    assert decision.probability == 0.0
    assert any("runtime_blacklist" in r for r in decision.reasons)


async def test_get_status_summary_contains_all_sections(willing_service):
    """正常路径：设置各类系数后 summary 应包含全部五个分区。"""
    skill = _skill(willing_service)
    await skill.execute("set_session_coefficient", {"value": 0.9})
    await skill.execute("set_user_global_coefficient", {"user_id": "10001", "value": 0.7})
    await skill.execute("set_session_user_coefficient", {
        "user_id": "10002",
        "value": 0.4,
        "conv_id": GROUP_KEY,
    })
    await skill.execute("add_session_blacklist", {})

    summary = await skill.execute("get_willingness_status", {})

    assert "全局系数: 1.000" in summary
    assert "会话系数" in summary
    assert "用户全局系数" in summary
    assert "会话用户系数" in summary
    assert "临时黑名单" in summary


@pytest.mark.xfail(
    reason="BUG-0001 空 user_id 时 ValueError 直接上抛而非返回 ok=False 的 JSON",
    strict=False,
)
async def test_empty_user_id_should_return_json_error_not_raise(willing_service):
    """异常路径：user_id 为空时应返回 JSON 错误，而不是向调用方抛出 ValueError。"""
    skill = _skill(willing_service)

    result = json.loads(
        await skill.execute("set_user_global_coefficient", {"user_id": "", "value": 0.5})
    )

    assert result["ok"] is False


@pytest.mark.xfail(
    reason="BUG-0002 非数字 value 时 float() 转换异常直接上抛而非返回 JSON 错误",
    strict=False,
)
async def test_non_numeric_value_should_return_json_error_not_raise(willing_service):
    """异常路径：value 非数字时应返回 JSON 错误，而不是向调用方抛出 ValueError。"""
    skill = _skill(willing_service)

    result = json.loads(
        await skill.execute("set_session_coefficient", {"value": "abc"})
    )

    assert result["ok"] is False


async def test_unconfigured_service_returns_mock_notes():
    """边界：未注入 willing_service 时应以模拟响应工作而不是报错。"""
    skill = _skill(None)

    status = json.loads(await skill.execute("get_willingness_status", {}))

    assert status["ok"] is True
    assert "未配置" in status["note"]

    add = json.loads(await skill.execute("add_session_blacklist", {}))

    assert add["ok"] is True
    assert "模拟" in add["note"]

    set_result = json.loads(await skill.execute("set_session_coefficient", {"value": 0.5}))

    assert set_result["ok"] is False
    assert "willing_service 未配置" in set_result["error"]


async def test_unknown_tool_rejected(willing_service):
    """异常路径：未知工具名应返回 unknown willingness tool 错误。"""
    skill = _skill(willing_service)

    result = json.loads(await skill.execute("no_such_tool", {}))

    assert result["ok"] is False
    assert "unknown willingness tool" in result["error"]


def test_service_requires_nonempty_ids(willing_service):
    """异常路径：直接调用 service 时空 user_id/conv_id 应抛出 ValueError。"""
    with pytest.raises(ValueError):
        willing_service.set_runtime_user_global_coefficient("", 0.5)
    with pytest.raises(ValueError):
        willing_service.set_runtime_conversation_coefficient("", 0.5)
