"""Composition root."""

from __future__ import annotations

from neobot_adapter import OneBotAdapter
from neobot_chat import create_provider
from neobot_contracts.ports.clock import SystemClock
from neobot_memory import MemoryService
from neobot_memory.defaults import InMemoryMemoryRepository
from neobot_storage import run_migrations, sqlite_url

from neobot_app.audio import TTSService
from neobot_app.assembly.agents import build_agent_registry
from neobot_app.assembly.memory import (
    build_archive_memory_service,
    build_image_analysis_service,
)
from neobot_app.assembly.storage import build_storage
from neobot_app.config.loader.env import load_env
from neobot_app.config.loader.manager import Config
from neobot_app.config.schemas.bot import BotConfig as BotConfigSchema
from neobot_app.core import CONFIG_FILE, DATA_DIR
from neobot_app.database.chatstream import ChatStreamManager
from neobot_app.emoji.service import EmojiService
from neobot_app.image import ImageParseService
from neobot_app.message.queue import MessageQueue
from neobot_app.observability.debug import DebugRecorder
from neobot_app.observability.logging import LoguruLoggerFactory
from neobot_app.prompt.builder import PromptBuilder
from neobot_app.reply import ReplyOrchestrator
from neobot_app.runtime.application import NeoBotApplication
from neobot_app.runtime.event_pipeline import EventPipeline
from neobot_app.runtime.inbound_pipeline import InboundPipeline
from neobot_app.user_profiles import UserProfileService
from neobot_app.willing import WillingService


def _load_config() -> BotConfigSchema:
    load_env()
    return Config.load(CONFIG_FILE, BotConfigSchema)


def create_application() -> NeoBotApplication[OneBotAdapter]:
    logger_factory = LoguruLoggerFactory()
    clock = SystemClock()
    config = _load_config()

    debug_recorder = (
        DebugRecorder(DATA_DIR / "debug" / "log")
        if getattr(getattr(config, "debug", None), "enabled", False)
        else None
    )

    db_url = sqlite_url(DATA_DIR / "neobot.db")
    run_migrations(db_url)
    _engine, uow_factory = build_storage(db_url)

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

    adapter = OneBotAdapter(
        logger=logger_factory.get_logger("adapter"),
        packet_callback=debug_recorder.record_packet if debug_recorder is not None else None,
    )

    memory = MemoryService(
        repository=InMemoryMemoryRepository(),
        logger=logger_factory.get_logger("memory"),
        clock=clock,
    )

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

    provider_logger = logger_factory.get_logger("app.provider")
    provider = None
    try:
        provider = create_provider("primary_chat_model")
    except Exception as exc:
        provider_logger.error(f"无法创建主对话 chat provider: {exc}")

    provider_error_message = None
    if provider is None:
        provider_error_message = "当前主回复模型不可用，请检查模型配置与 API Key"
        provider_logger.error(provider_error_message)

    prompt_builder = PromptBuilder(
        config=config,
        profile_service=profile_service,
        logger=logger_factory.get_logger("app.prompt"),
    )

    vision_provider = None
    try:
        vision_provider = create_provider("vision_model")
    except Exception as exc:
        provider_logger.warning(f"无法创建视觉模型 provider: {exc}")

    image_analysis_service = build_image_analysis_service(
        uow_factory=uow_factory,
        logger=logger_factory.get_logger("app.image_analysis"),
    )
    archive_memory_service = build_archive_memory_service(
        uow_factory=uow_factory,
        logger=logger_factory.get_logger("app.archive_memory"),
    )
    agent_registry = build_agent_registry(
        config=config,
        archive_memory_service=archive_memory_service,
        logger=logger_factory.get_logger("app.agent_registry"),
    )

    image_parse_service = ImageParseService(
        vision_provider=vision_provider,
        image_analysis_service=image_analysis_service,
        adapter=adapter,
        logger=logger_factory.get_logger("app.image_parse"),
    )

    emoji_service = EmojiService(
        data_dir=DATA_DIR,
        uow_factory=uow_factory,
        vision_provider=vision_provider,
        logger=logger_factory.get_logger("app.emoji"),
    )

    reply_orchestrator = ReplyOrchestrator(
        adapter=adapter,
        prompt_builder=prompt_builder,
        provider=provider,
        group_message_queue=group_message_queue,
        friend_message_queue=friend_message_queue,
        config=config,
        willing_service=willing_service,
        image_parse_service=image_parse_service,
        emoji_service=emoji_service,
        agent_registry=agent_registry,
        provider_error_message=provider_error_message,
        debug_recorder=debug_recorder,
        logger=logger_factory.get_logger("app.reply"),
    )

    inbound_pipeline = InboundPipeline(
        adapter=adapter,
        memory=memory,
        logger=logger_factory.get_logger("app.inbound_pipeline"),
    )

    event_pipeline = EventPipeline(
        adapter=adapter,
        group_message_queue=group_message_queue,
        friend_message_queue=friend_message_queue,
        profile_service=profile_service,
        willing_service=willing_service,
        reply_orchestrator=reply_orchestrator,
        image_parse_service=image_parse_service,
        inbound_pipeline=inbound_pipeline,
        logger=logger_factory.get_logger("app.event_pipeline"),
    )

    tts_service = TTSService(
        config=config.tts,
        logger=logger_factory.get_logger("app.tts"),
    )

    return NeoBotApplication(
        adapter=adapter,
        chat_stream=chat_stream,
        event_pipeline=event_pipeline,
        reply_orchestrator=reply_orchestrator,
        emoji_service=emoji_service,
        tts_service=tts_service,
        logger=logger_factory.get_logger("app.runtime"),
        file_server_port=config.file_server.port,
        file_server_host=config.file_server.host,
        file_server_public_url=config.file_server.public_url,
    )
