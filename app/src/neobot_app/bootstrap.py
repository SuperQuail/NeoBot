"""Composition Root — 所有对象装配集中在此"""

from __future__ import annotations

from neobot_adapter import OneBotAdapter
from neobot_adapter.gateway import OneBotGateway

from neobot_contracts.ports.clock import SystemClock

from neobot_app.config.loader.env import load_env
from neobot_app.config.loader.manager import Config
from neobot_app.config.schemas.bot import BotConfig as BotConfigSchema
from neobot_app.core import CONFIG_FILE
from neobot_app.database.chatstream import ChatStreamManager
from neobot_app.message.queue import MessageQueue
from neobot_app.observability.logging import LoguruLoggerFactory
from neobot_app.runtime.application import NeoBotApplication
from neobot_app.runtime.event_pipeline import EventPipeline
from neobot_app.runtime.inbound_pipeline import InboundPipeline
from neobot_app.runtime.history_warmup import HistoryWarmupService

from neobot_memory import MemoryService
from neobot_memory.defaults import InMemoryMemoryRepository


def _load_config() -> BotConfigSchema:
    load_env()
    return Config.load(CONFIG_FILE, BotConfigSchema)


def create_application() -> NeoBotApplication[OneBotAdapter]:
    logger_factory = LoguruLoggerFactory()
    clock = SystemClock()

    config = _load_config()

    # 消息队列
    group_message_queue = MessageQueue(max_size=config.chat.max_group_chat_observations)
    friend_message_queue = MessageQueue(max_size=config.chat.max_friend_chat_observations)

    # 适配器
    adapter = OneBotAdapter(logger=logger_factory.get_logger("adapter"))

    # Gateway
    gateway = OneBotGateway(adapter)

    # Memory
    memory = MemoryService(
        repository=InMemoryMemoryRepository(),
        logger=logger_factory.get_logger("memory"),
        clock=clock,
    )

    # 聊天流（历史消息预热，兼容旧逻辑）
    chat_stream = ChatStreamManager(
        adapter=adapter,
        group_message_queue=group_message_queue,
        friend_message_queue=friend_message_queue,
    )

    # 事件管线（实时消息路由到队列）
    event_pipeline = EventPipeline(
        adapter=adapter,
        group_message_queue=group_message_queue,
        friend_message_queue=friend_message_queue,
        logger=logger_factory.get_logger("app.event_pipeline"),
    )

    # 入站管线（未来替代 EventPipeline）
    _inbound_pipeline = InboundPipeline(
        gateway=gateway,
        memory=memory,
        logger=logger_factory.get_logger("app.inbound_pipeline"),
    )

    return NeoBotApplication(
        adapter=adapter,
        chat_stream=chat_stream,
        event_pipeline=event_pipeline,
        logger=logger_factory.get_logger("app.runtime"),
    )
