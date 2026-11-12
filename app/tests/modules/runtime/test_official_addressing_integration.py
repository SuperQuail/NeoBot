"""官方 @ 事件 → 生产消费路径集成验收（用户真实事件 JSON）。

完整链路：EventMapper.from_dispatch → safe_parse_model(GroupMessage) →
CommandService.handle_message（群命令触发）/ WillingService.is_at_mentioned（被@必回）。
复现用户线上状态：机器人 QQ 号未解析（self_id=0、config.bot.account=0）、content 已去
@ 前缀（例如 " /今日天气 "）；同时覆盖群全量消息的 @ 变体与同 msg_id 的 AT+FULL 去重。
"""

from __future__ import annotations

import asyncio
import itertools
from types import SimpleNamespace
from typing import Any

import pytest

from neobot_adapter.model.message import GroupMessage
from neobot_adapter.official.events import EventMapper
from neobot_adapter.official.identity import MessageIdMap
from neobot_adapter.utils.parse import safe_parse_model
from neobot_app.commands.service import CommandService
from neobot_app.config.schemas.bot import BotConfig
from neobot_app.message.addressing import is_addressed_to_bot
from neobot_app.message.queue import MessageQueue
from neobot_app.runtime.event_pipeline import EventPipeline
from neobot_app.willing.service import WillingService
from neobot_contracts.ports.logging import NullLogger

_EVENT_SEQ = itertools.count(1)


def _dispatch(
    event_type: str,
    data: dict[str, Any],
    *,
    event_id: str | None = None,
    seq: int = 1,
) -> dict[str, Any]:
    return {
        "op": 0,
        "t": event_type,
        "id": event_id or f"evt-{next(_EVENT_SEQ)}",
        "s": seq,
        "d": data,
    }


def _user_group_at_payload(
    content: str = " /今日天气 ",
    *,
    message_id: str = "ROBOT1.0_user-example",
) -> dict[str, Any]:
    """用户提供的 GROUP_AT_MESSAGE_CREATE 示例：content 无 @ 前缀、无 mentions。"""
    return _dispatch(
        "GROUP_AT_MESSAGE_CREATE",
        {
            "id": message_id,
            "content": content,
            "timestamp": "2026-11-12T12:00:00+08:00",
            "group_openid": "group-openid-1",
            "author": {
                "id": "member-openid-1",
                "member_openid": "member-openid-1",
                "union_openid": "union-openid-1",
            },
            "message_scene": {"source": "default", "ext": []},
        },
    )


def _full_group_payload(
    content: str,
    *,
    message_id: str = "ROBOT1.0_group-msg",
    mentions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": message_id,
        "content": content,
        "timestamp": "2026-11-12T12:00:00+08:00",
        "group_openid": "group-openid-1",
        "author": {"id": "member-openid-1", "member_openid": "member-openid-1"},
    }
    if mentions is not None:
        data["mentions"] = mentions
    return _dispatch("GROUP_MESSAGE_CREATE", data)


def _map_message(
    payload: dict[str, Any],
    mapper: EventMapper,
) -> GroupMessage:
    """事件字典 → 消息模型；补上双通道门面 publish 时注入的 neobot_channel。"""
    event = mapper.from_dispatch(payload)
    assert event is not None, "事件映射不应返回 None"
    return safe_parse_model({**event, "neobot_channel": "official"}, GroupMessage)


def _mapper(*, self_id: int = 0, bot_openid: str = "") -> EventMapper:
    mapper = EventMapper(message_ids=MessageIdMap(), logger=NullLogger(), self_id=self_id)
    mapper.bot_openid = bot_openid
    return mapper


async def _send(*_args: Any, **_kwargs: Any) -> None:
    return None


def _command_service() -> CommandService:
    """与生产一致的内置命令表；uin 未解析时 config.bot.account=0。"""
    config = SimpleNamespace(
        chat=SimpleNamespace(admin_accounts=[], sub_admin_accounts=[]),
        bot=SimpleNamespace(account=0),
    )
    return CommandService(
        config=config,
        adapter=SimpleNamespace(send=lambda _conversation, _message: None),
        send_callback=_send,
        register_builtins=True,
    )


def _willing_service() -> WillingService:
    config = BotConfig()
    config.bot.account = 0
    config.chat.at_mention_guaranteed_reply = True
    return WillingService(config)


def _event_pipeline() -> EventPipeline:
    return EventPipeline(
        adapter=SimpleNamespace(connected_channels=("official",)),
        group_message_queue=MessageQueue(),
        friend_message_queue=MessageQueue(),
        config=BotConfig(),
    )


# ── 用户真实 @ 事件：命令 + 必回 ────────────────────────────────────


@pytest.mark.parametrize("content", ["/reboot", " /reboot "])
async def test_user_group_at_event_is_consumed_by_command_service(content: str) -> None:
    """self_id=0、无 mentions 的 @ 事件也必须触发已注册命令（consumed=True）。"""
    message = _map_message(_user_group_at_payload(content), _mapper(self_id=0))

    result = await _command_service().handle_message(
        message, kind="group", queue_key="group-openid-1"
    )

    assert message.mentioned_self is True
    assert result.consumed is True
    assert _willing_service().is_at_mentioned(message) is True


async def test_user_group_at_plain_text_triggers_guaranteed_reply() -> None:
    """用户示例 " /今日天气 " 不是内置命令：命令不消费，但必回必须触发。"""
    message = _map_message(_user_group_at_payload(" /今日天气 "), _mapper(self_id=0))
    service = _command_service()

    result = await service.handle_message(message, kind="group", queue_key="group-openid-1")

    assert result.consumed is False
    assert is_addressed_to_bot(message) is True
    assert _willing_service().is_at_mentioned(message) is True


# ── 群全量消息（GROUP_MESSAGE_CREATE） ──────────────────────────────


async def test_full_group_message_without_mention_does_not_trigger() -> None:
    """群全量消息没有 @ 机器人：命令与必回都不触发。"""
    message = _map_message(
        _full_group_payload("随便聊聊"), _mapper(bot_openid="bot-openid")
    )

    result = await _command_service().handle_message(
        message, kind="group", queue_key="group-openid-1"
    )

    assert message.mentioned_self is False
    assert result.consumed is False
    assert _willing_service().is_at_mentioned(message) is False


async def test_full_group_message_content_marker_triggers_command_and_reply() -> None:
    """content 含 <@!bot_openid>：命令与必回都触发。"""
    message = _map_message(
        _full_group_payload("<@!bot-openid> /reboot"),
        _mapper(bot_openid="bot-openid"),
    )

    result = await _command_service().handle_message(
        message, kind="group", queue_key="group-openid-1"
    )

    assert message.mentioned_self is True
    assert result.consumed is True
    assert _willing_service().is_at_mentioned(message) is True


async def test_full_group_message_mentions_bot_triggers_command_and_reply() -> None:
    """mentions 含 bot=True 且 id==bot_openid：命令与必回都触发。"""
    message = _map_message(
        _full_group_payload(
            "/reboot",
            mentions=[{"id": "bot-openid", "username": "机器人", "bot": True}],
        ),
        _mapper(bot_openid="bot-openid"),
    )

    result = await _command_service().handle_message(
        message, kind="group", queue_key="group-openid-1"
    )

    assert message.mentioned_self is True
    assert result.consumed is True
    assert _willing_service().is_at_mentioned(message) is True


# ── 同 msg_id 的 AT+FULL 双事件去重 ─────────────────────────────────


async def test_duplicate_at_then_full_events_keep_addressed_result() -> None:
    """先到 AT、后到 FULL 同 msg_id：运行期去重丢 FULL，保留的 AT 仍是被 @。"""
    mapper = _mapper(bot_openid="bot-openid")
    at_message = _map_message(
        _user_group_at_payload(" /reboot ", message_id="ROBOT1.0_same-msg"), mapper
    )
    full_message = _map_message(
        _full_group_payload(" /reboot ", message_id="ROBOT1.0_same-msg"), mapper
    )
    pipeline = _event_pipeline()

    assert at_message.message_id == full_message.message_id
    assert await pipeline._is_duplicate_message(at_message) is False
    assert await pipeline._is_duplicate_message(full_message) is True

    kept = at_message
    assert is_addressed_to_bot(kept) is True
    assert _willing_service().is_at_mentioned(kept) is True
    result = await _command_service().handle_message(
        kept, kind="group", queue_key="group-openid-1"
    )
    assert result.consumed is True


async def test_duplicate_full_then_at_events_keep_addressed_result() -> None:
    """FULL 先到（content 标记可识别机器人）、AT 后到：去重丢 AT 后仍是被 @。"""
    mapper = _mapper(bot_openid="bot-openid")
    full_message = _map_message(
        _full_group_payload("<@!bot-openid> /reboot", message_id="ROBOT1.0_same-msg"),
        mapper,
    )
    at_message = _map_message(
        _user_group_at_payload(" /reboot ", message_id="ROBOT1.0_same-msg"), mapper
    )
    pipeline = _event_pipeline()

    assert full_message.message_id == at_message.message_id
    assert await pipeline._is_duplicate_message(full_message) is False
    assert await pipeline._is_duplicate_message(at_message) is True

    kept = full_message
    assert kept.mentioned_self is True
    assert is_addressed_to_bot(kept) is True
    assert _willing_service().is_at_mentioned(kept) is True
    result = await _command_service().handle_message(
        kept, kind="group", queue_key="group-openid-1"
    )
    assert result.consumed is True


async def test_duplicate_full_without_bot_info_then_at_upgrades_to_addressed() -> None:
    """FULL 先到但没拿到 bot 信息（mentioned_self=False）占住 msg_id，AT 后到必须放行。"""
    mapper = _mapper(bot_openid="")
    full_message = _map_message(_full_group_payload("/reboot", message_id="ROBOT1.0_late-at"), mapper)
    at_message = _map_message(_user_group_at_payload(" /reboot ", message_id="ROBOT1.0_late-at"), mapper)
    pipeline = _event_pipeline()

    assert full_message.message_id == at_message.message_id
    assert full_message.mentioned_self is False
    assert at_message.mentioned_self is True
    assert await pipeline._is_duplicate_message(full_message) is False
    assert await pipeline._is_duplicate_message(at_message) is False  # 未 @ → 被 @ 升级放行
    assert await pipeline._is_duplicate_message(at_message) is True  # 只升级一次

    result = await _command_service().handle_message(at_message, kind="group", queue_key="group-openid-1")
    assert result.consumed is True
    assert _willing_service().is_at_mentioned(at_message) is True


# ── FULL→AT 升级后的队列与副作用（e2e） ─────────────────────────────


class _ArchiveSummarySpy:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def record_message(self, **kwargs: Any) -> None:
        self.records.append(kwargs)


class _ReplyOrchestratorSpy:
    def __init__(self) -> None:
        self.starts: list[dict[str, Any]] = []

    def start_reply(self, **kwargs: Any) -> object:
        self.starts.append(kwargs)
        return object()


class _CommandServiceSpy:
    def __init__(self, delegate: CommandService) -> None:
        self._delegate = delegate
        self.consumed = 0

    @property
    def registry(self):
        return self._delegate.registry

    @staticmethod
    def _message_text(message: Any) -> str:
        return CommandService._message_text(message)

    async def handle_message(self, message: Any, *, kind: str, queue_key: str):
        result = await self._delegate.handle_message(message, kind=kind, queue_key=queue_key)
        if result is not None and result.consumed:
            self.consumed += 1
        return result


def _e2e_willing_config(
    *,
    group_chat_chance: float = 0.0,
    willing_global_coefficient: float = 1.0,
) -> BotConfig:
    config = BotConfig()
    config.bot.account = 0
    config.chat.at_mention_guaranteed_reply = True
    config.chat.group_chat_chance = group_chat_chance
    config.chat.willing_global_coefficient = willing_global_coefficient
    config.chat.at_mention_reply_delay_seconds = 0.0
    return config


def _pipeline_event(payload: dict[str, Any], mapper: EventMapper) -> dict[str, Any]:
    event = mapper.from_dispatch(payload)
    assert event is not None, "事件映射不应返回 None"
    return {**event, "neobot_channel": "official"}


def _wired_pipeline(
    *,
    archive: _ArchiveSummarySpy | None = None,
    orchestrator: _ReplyOrchestratorSpy | None = None,
    command_service: Any = None,
    group_chat_chance: float = 0.0,
    willing_global_coefficient: float = 1.0,
) -> EventPipeline:
    config = _e2e_willing_config(
        group_chat_chance=group_chat_chance,
        willing_global_coefficient=willing_global_coefficient,
    )
    return EventPipeline(
        adapter=SimpleNamespace(connected_channels=("official",)),
        group_message_queue=MessageQueue(),
        friend_message_queue=MessageQueue(),
        willing_service=WillingService(config),
        reply_orchestrator=orchestrator,
        archive_summary_service=archive,
        command_service=command_service,
        config=config,
        logger=NullLogger(),
    )


async def _flush_background(pipeline: EventPipeline) -> None:
    tasks = [task for task in pipeline._background_tasks if not task.done()]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def test_full_then_at_upgrade_keeps_one_entry_one_summary_one_reply() -> None:
    """FULL(未@)先处理已入队/已总结；同 msg_id 的 AT 升级后队列仍 1 条、总结一次、必回一次。"""
    mapper = _mapper(bot_openid="")
    archive = _ArchiveSummarySpy()
    orchestrator = _ReplyOrchestratorSpy()
    pipeline = _wired_pipeline(archive=archive, orchestrator=orchestrator)
    full_event = _pipeline_event(_full_group_payload(" /今日天气 ", message_id="ROBOT1.0_e2e-reply"), mapper)
    at_event = _pipeline_event(_user_group_at_payload(" /今日天气 ", message_id="ROBOT1.0_e2e-reply"), mapper)

    await pipeline.handle_group_message_event(full_event)
    await pipeline.handle_group_message_event(at_event)
    await _flush_background(pipeline)

    assert pipeline._group_queue.size("group-openid-1") == 1
    kept = pipeline._group_queue.get("group-openid-1")
    assert kept is not None
    assert kept.mentioned_self is True
    assert len(archive.records) == 1
    assert len(orchestrator.starts) == 1
    assert orchestrator.starts[0]["message"].mentioned_self is True


async def test_full_then_at_upgrade_triggers_command_once() -> None:
    """FULL 先到未触发命令；同 msg_id 的 AT 升级后命令只触发一次，归档总结仍只有一次。"""
    mapper = _mapper(bot_openid="")
    archive = _ArchiveSummarySpy()
    command = _CommandServiceSpy(_command_service())
    pipeline = _wired_pipeline(archive=archive, command_service=command)
    full_event = _pipeline_event(_full_group_payload("/reboot", message_id="ROBOT1.0_e2e-cmd"), mapper)
    at_event = _pipeline_event(_user_group_at_payload(" /reboot ", message_id="ROBOT1.0_e2e-cmd"), mapper)

    await pipeline.handle_group_message_event(full_event)
    await pipeline.handle_group_message_event(at_event)
    await _flush_background(pipeline)

    assert pipeline._group_queue.size("group-openid-1") == 1
    assert command.consumed == 1
    assert len(archive.records) == 1


async def test_full_probability_reply_then_at_upgrade_replies_once(monkeypatch) -> None:
    """FULL(未@) 被意愿概率命中先回复；AT 升级只补 @ 语义，不再第二次回复。"""
    from neobot_app.willing import builtin as willing_builtin

    monkeypatch.setattr(willing_builtin.random, "random", lambda: 0.0)
    mapper = _mapper(bot_openid="")
    archive = _ArchiveSummarySpy()
    orchestrator = _ReplyOrchestratorSpy()
    pipeline = _wired_pipeline(
        archive=archive,
        orchestrator=orchestrator,
        group_chat_chance=1.0,
    )
    full_event = _pipeline_event(
        _full_group_payload("随便聊聊", message_id="ROBOT1.0_e2e-reply-once"), mapper
    )
    at_event = _pipeline_event(
        _user_group_at_payload(" 随便聊聊", message_id="ROBOT1.0_e2e-reply-once"), mapper
    )

    await pipeline.handle_group_message_event(full_event)
    assert len(orchestrator.starts) == 1  # FULL 概率命中，已经启动回复

    await pipeline.handle_group_message_event(at_event)
    await _flush_background(pipeline)

    assert len(orchestrator.starts) == 1  # 同 msg_id 的 AT 升级不再重复触发
    assert pipeline._group_queue.size("group-openid-1") == 1
    assert len(archive.records) == 1


async def test_full_command_then_at_upgrade_does_not_chat_reply_first(monkeypatch) -> None:
    """FULL 命令文本未 @ 时不先当闲聊回复；AT 后命令只执行一次。"""
    from neobot_app.willing import builtin as willing_builtin

    monkeypatch.setattr(willing_builtin.random, "random", lambda: 0.0)
    mapper = _mapper(bot_openid="")
    archive = _ArchiveSummarySpy()
    orchestrator = _ReplyOrchestratorSpy()
    command = _CommandServiceSpy(_command_service())
    pipeline = _wired_pipeline(
        archive=archive,
        orchestrator=orchestrator,
        command_service=command,
        group_chat_chance=1.0,
    )
    full_event = _pipeline_event(
        _full_group_payload("/reboot", message_id="ROBOT1.0_e2e-cmd-once"), mapper
    )
    at_event = _pipeline_event(
        _user_group_at_payload(" /reboot ", message_id="ROBOT1.0_e2e-cmd-once"), mapper
    )

    await pipeline.handle_group_message_event(full_event)
    assert len(orchestrator.starts) == 0  # 命令文本不先当闲聊回一句

    await pipeline.handle_group_message_event(at_event)
    await _flush_background(pipeline)

    assert command.consumed == 1
    assert len(orchestrator.starts) == 0
    assert pipeline._group_queue.size("group-openid-1") == 1
    assert len(archive.records) == 1
