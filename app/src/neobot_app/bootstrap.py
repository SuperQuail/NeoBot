"""Composition Root — 所有对象装配集中在此"""

from __future__ import annotations

from neobot_adapter import OneBotAdapter
from neobot_contracts.ports.clock import SystemClock
from neobot_memory import MemoryService
from neobot_memory.defaults import InMemoryMemoryRepository
from neobot_storage import run_migrations, sqlite_url

from neobot_app.audio import TTSService
from neobot_app.assembly.storage import build_storage
from neobot_app.config.loader.env import load_env
from neobot_app.config.loader.manager import Config
from neobot_app.config.schemas.bot import BotConfig as BotConfigSchema
from neobot_app.core import CONFIG_FILE, DATA_DIR
from neobot_app.database.chatstream import ChatStreamManager
from neobot_app.message.queue import MessageQueue
from neobot_app.observability.logging import LoguruLoggerFactory
from neobot_app.user_profiles import UserProfileService
from neobot_app.runtime.application import NeoBotApplication
from neobot_app.runtime.event_pipeline import EventPipeline
from neobot_app.runtime.inbound_pipeline import InboundPipeline
from neobot_app.willing import WillingService


def _load_config() -> BotConfigSchema:
    load_env()
    return Config.load(CONFIG_FILE, BotConfigSchema)


def create_application() -> NeoBotApplication[OneBotAdapter]:
    logger_factory = LoguruLoggerFactory()
    clock = SystemClock()

    config = _load_config()

    # 自动迁移数据库
    db_url = sqlite_url(DATA_DIR / "neobot.db")
    run_migrations(db_url)

    # Storage (async engine + UoW factory)
    _engine, uow_factory = build_storage(db_url)

    # 消息队列
    timestamp_interval_seconds = getattr(
        config.chat,
        "message_timestamp_interval_seconds",
        300,
    )
    group_message_queue = MessageQueue(
        max_size=config.chat.max_group_chat_observations,
        timestamp_interval_seconds=timestamp_interval_seconds,
    )
    friend_message_queue = MessageQueue(
        max_size=config.chat.max_friend_chat_observations,
        timestamp_interval_seconds=timestamp_interval_seconds,
    )

    # 适配器
    adapter = OneBotAdapter(logger=logger_factory.get_logger("adapter"))

    # Memory
    memory = MemoryService(
        repository=InMemoryMemoryRepository(),
        logger=logger_factory.get_logger("memory"),
        clock=clock,
    )

    # 聊天流（历史消息预热，兼容旧逻辑）
    chat_stream = ChatStreamManager(
        adapter=adapter,
        uow_factory=uow_factory,
        group_message_queue=group_message_queue,
        friend_message_queue=friend_message_queue,
    )

    profile_service = UserProfileService(
        adapter=adapter,
        uow_factory=uow_factory,
        config=config,
        logger=logger_factory.get_logger("app.user_profiles"),
    )

    willing_service = WillingService(
        config=config,
        logger=logger_factory.get_logger("app.willing"),
    )

    # 事件管线（实时消息路由到队列）
    event_pipeline = EventPipeline(
        adapter=adapter,
        group_message_queue=group_message_queue,
        friend_message_queue=friend_message_queue,
        profile_service=profile_service,
        willing_service=willing_service,
        logger=logger_factory.get_logger("app.event_pipeline"),
    )

    # 入站管线（未来替代 EventPipeline）
    _inbound_pipeline = InboundPipeline(
        adapter=adapter,
        memory=memory,
        logger=logger_factory.get_logger("app.inbound_pipeline"),
    )

    tts_service = TTSService(
        config=config.tts,
        logger=logger_factory.get_logger("app.tts"),
    )

    return NeoBotApplication(
        adapter=adapter,
        chat_stream=chat_stream,
        event_pipeline=event_pipeline,
        tts_service=tts_service,
        logger=logger_factory.get_logger("app.runtime"),
        file_server_port=config.file_server.port,
        file_server_host=config.file_server.host,
        file_server_public_url=config.file_server.public_url,
    )
