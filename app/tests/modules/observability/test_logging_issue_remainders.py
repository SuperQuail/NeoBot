"""覆盖配置重复告警、历史批次与兼容 API 的实际行为。"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from neobot_app.agents.self_heal import SelfHealAgentConfig, SelfHealManager
from neobot_app.database.chatstream import ChatStreamManager
from neobot_app.prompt.store import PromptStore
from neobot_contracts.ports.logging import NullLogger


def test_prompt_warnings_are_once_per_field_and_configuration_version(tmp_path):
    logger = Mock(spec=NullLogger)
    store = PromptStore(tmp_path, logger=logger)
    store.custom_file.parent.mkdir(parents=True)
    store.custom_file.write_text('[group_chat]\ntemplate = 12\nenabled = ["invalid"]\n')
    for _ in range(20):
        assert store.get("group_chat", "template", "fallback") == "fallback"
        assert store.enabled("group_chat", default=False) is False
    assert logger.warning.call_count == 2
    store.custom_file.write_text('[group_chat]\ntemplate = "fixed"\nenabled = true\n')
    assert store.get("group_chat", "template") == "fixed"
    assert store.enabled("group_chat") is True
    assert logger.warning.call_count == 2
    store.custom_file.write_text("[group_chat]\ntemplate = 34\n")
    assert store.get("group_chat", "template", "fallback") == "fallback"
    assert logger.warning.call_count == 3


async def test_self_heal_rejection_logs_only_when_state_changes():
    logger = Mock(spec=NullLogger)
    config = SelfHealAgentConfig(enabled=True, daily_limit=2, admin_account="")
    manager = SelfHealManager(config=config, logger=logger)
    for _ in range(20):
        assert not await manager._dispatch(reason="errors")
    assert logger.info.call_count == 1
    manager._daily_trigger_count()
    manager._trigger_count_today = 2
    for _ in range(20):
        assert not await manager._dispatch(reason="errors")
    assert logger.info.call_count == 2
    logger.warning.assert_not_called()
    logger.error.assert_not_called()


@pytest.mark.parametrize("injected", [False, True])
async def test_chatstream_default_startup_summary_does_not_require_friend_history(monkeypatch, caplog, injected):
    from neobot_app.config.schemas.bot import BotConfig

    config = BotConfig()
    assert config.chat.enable_friend_startup_history_warmup is False
    load_config = Mock(return_value=config)
    monkeypatch.setattr("neobot_app.config.instance.load_bot_config", load_config)
    adapter = SimpleNamespace(get_group_list=AsyncMock(return_value=SimpleNamespace(data=[])))
    manager = ChatStreamManager(adapter=adapter, uow_factory=Mock(), bot_config=config if injected else None)
    with caplog.at_level(logging.INFO, logger="neobot_app.database.chatstream"):
        await manager.initialize()
        await manager.initialize()
    assert manager._initialized
    summaries = [record for record in caplog.records if record.getMessage() == "聊天流初始化完成"]
    assert len(summaries) == 1
    assert summaries[0].friend_history_count == 0
    assert summaries[0].group_count == 0
    adapter.get_group_list.assert_awaited_once()
    assert load_config.call_count == (0 if injected else 1)


@pytest.mark.parametrize("kind", ["private", "group"])
async def test_history_invalid_messages_are_one_batch_warning_without_content(kind, caplog):
    history = SimpleNamespace(data=SimpleNamespace(messages=[("PRIVATE_MESSAGE_CONTENT",)] * 100))
    adapter = SimpleNamespace(
        get_friend_msg_history=AsyncMock(return_value=history),
        get_group_msg_history=AsyncMock(return_value=history),
    )
    manager = ChatStreamManager(adapter=adapter, uow_factory=Mock())
    manager._merge_self_sent_history = AsyncMock()
    with caplog.at_level(logging.DEBUG, logger="neobot_app.database.chatstream"):
        if kind == "private":
            await manager._process_friend_history(SimpleNamespace(user_id=42), 100)
        else:
            await manager._process_group_history(SimpleNamespace(group_id=42), 100)
    warnings = [record for record in caplog.records if record.levelno >= logging.WARNING]
    assert len(warnings) == 1
    assert warnings[0].chat_flow_id == f"{kind}:42"
    assert warnings[0].skipped_tuples == 100
    assert warnings[0].processed == 0
    assert "PRIVATE_MESSAGE_CONTENT" not in caplog.text
    manager._merge_self_sent_history.assert_awaited_once()


async def test_legacy_group_cache_remains_callable_without_progress_logs(monkeypatch):
    from neobot_adapter.request import group

    logger = Mock()
    monkeypatch.setattr(group, "logger", logger)
    monkeypatch.setattr(group, "_group_name_cache", {})
    monkeypatch.setattr(group, "_group_cache_initialized", False)
    fetch = AsyncMock(return_value=SimpleNamespace(data=[SimpleNamespace(group_id=42, group_name="test")]))
    monkeypatch.setattr(group, "get_group_list", fetch)
    assert await group.get_group_name(42) == "test"
    assert await group.get_group_name(42) == "test"
    assert group.get_all_group_names() == {42: "test"}
    fetch.assert_awaited_once()
    group.clear_group_name_cache()
    assert group.get_all_group_names() == {}
    logger.info.assert_not_called()
    logger.warning.assert_not_called()
    logger.error.assert_not_called()
