"""Composition root — 装配并返回 NeoBotApplication。"""

from __future__ import annotations

from neobot_contracts.ports.clock import SystemClock
from neobot_storage import run_migrations, sqlite_url

from neobot_app.assembly.storage import build_storage
from neobot_app.core import DATA_DIR, SRC_DATA_DIR
from neobot_app.observability.logging import (
    LoguruLoggerFactory,
    configure_loguru,
)
from neobot_app.runtime.application import NeoBotApplication
from neobot_app.utils.data_sync import sync_data_files

from neobot_app.bootstrap._config import build_config
from neobot_app.bootstrap._providers import (
    build_main_provider,
    build_vision_provider,
)
from neobot_app.bootstrap._services import (
    build_adapter_service,
    build_archive_summary_service,
    build_debug_recorder,
    build_emoji_service,
    build_file_server,
    build_image_parse_service,
    build_memory_services,
    build_message_queues,
    build_tts_service,
)
from neobot_app.bootstrap._runtime import (
    build_balance_checker,
    build_browser_components,
    build_creator_image_service,
    build_drawing_manager,
    build_image_pool,
    build_markdown_image_converter,
    build_notification_hub,
    build_problem_solver_manager,
    build_sandbox_components,
    build_scheduled_task_manager,
)
from neobot_app.bootstrap._usage import build_usage_components
from neobot_app.bootstrap._skills import build_plugin_runtime, build_skill_manager
from neobot_app.bootstrap._pipeline import (
    build_pipelines_and_app,
    build_plugin_host,
    build_problem_solver_agent_wiring,
    build_reply_orchestrator,
    register_config_reload_command,
)


def create_application() -> NeoBotApplication:
    configure_loguru(DATA_DIR / "logs", runtime_events=True)
    logger_factory = LoguruLoggerFactory()
    config = build_config()

    sync_data_files(SRC_DATA_DIR, DATA_DIR)

    debug_recorder = build_debug_recorder(
        config=config, logger=logger_factory.get_logger("app.debug")
    )

    db_url = sqlite_url(DATA_DIR / "neobot.db")
    run_migrations(db_url)
    _engine, uow_factory = build_storage(db_url)

    usage = build_usage_components(_engine=_engine, logger_factory=logger_factory)

    group_queue, friend_queue = build_message_queues(config=config)

    adapter = build_adapter_service(
        config=config,
        logger=logger_factory.get_logger("adapter"),
        debug_recorder=debug_recorder,
    )

    # ── 插件主机基础设施 ──
    plugin = build_plugin_host(logger_factory=logger_factory)
    register_config_reload_command(
        host_facade=plugin["host_facade"], config=config
    )

    # ── 记忆 / 用户画像 / 意愿 / 提示词 ──
    memory_svcs = build_memory_services(
        db_url=db_url,
        data_dir=DATA_DIR,
        adapter=adapter,
        config=config,
        logger_factory=logger_factory,
        clock=SystemClock(),
        group_queue=group_queue,
        friend_queue=friend_queue,
        uow_factory=uow_factory,
    )

    provider_logger = logger_factory.get_logger("app.provider")
    provider, provider_error_message = build_main_provider(
        config=config, logger=provider_logger,
    )
    vision_provider = build_vision_provider(logger=provider_logger)

    # ── 表情包 / 文件服务 / 图片暂存池 ──
    emoji_service = build_emoji_service(
        config=config,
        data_dir=DATA_DIR,
        uow_factory=uow_factory,
        vision_provider=vision_provider,
        logger_factory=logger_factory,
    )
    file_server = build_file_server(config=config, data_dir=DATA_DIR)
    image_pool = build_image_pool()

    # ── 运行时组件 ──
    notification_hub = build_notification_hub(logger_factory=logger_factory)
    drawing_manager = build_drawing_manager(
        config=config,
        logger_factory=logger_factory,
        notification_hub=notification_hub,
    )
    scheduled_task_manager = build_scheduled_task_manager(
        config=config,
        uow_factory=uow_factory,
        logger_factory=logger_factory,
        notification_hub=notification_hub,
    )
    problem_solver_manager = build_problem_solver_manager(
        config=config,
        logger_factory=logger_factory,
        notification_hub=notification_hub,
    )

    browser = build_browser_components(
        config=config,
        data_dir=DATA_DIR,
        logger=logger_factory.get_logger("app.browser"),
    )
    markdown_image_converter = build_markdown_image_converter(
        data_dir=DATA_DIR,
        browser_instance=browser["browser_instance"],
        logger_factory=logger_factory,
    )

    creator_image_service = build_creator_image_service(
        uow_factory=uow_factory,
        adapter=adapter,
        config=config,
        emoji_service=emoji_service,
        vision_provider=vision_provider,
        file_server=file_server,
        image_pool=image_pool,
        logger_factory=logger_factory,
    )
    drawing_manager.set_image_service(creator_image_service)

    sandbox = build_sandbox_components(
        config=config,
        data_dir=DATA_DIR,
        notification_hub=notification_hub,
    )
    if sandbox["temp_cleaner"] is not None:
        sandbox["temp_cleaner"].logger = logger_factory.get_logger("app.temp_cleaner")
    if sandbox["sandbox_maintenance_manager"] is not None:
        sandbox["sandbox_maintenance_manager"].logger = (
            logger_factory.get_logger("app.sandbox_maintenance")
        )

    # ── 解题 Agent 装配 ──
    build_problem_solver_agent_wiring(
        config=config,
        problem_solver_manager=problem_solver_manager,
        provider=provider,
        provider_logger=provider_logger,
        sandbox_service=sandbox["sandbox_service"],
        logger_factory=logger_factory,
    )

    # ── Skill 系统 ──
    skill_manager = build_skill_manager(
        config=config,
        adapter=adapter,
        archive_memory_service=memory_svcs["archive_memory_service"],
        profile_service=memory_svcs["profile_service"],
        emoji_service=emoji_service,
        vision_provider=vision_provider,
        file_server=file_server,
        willing_service=memory_svcs["willing_service"],
        drawing_manager=drawing_manager,
        scheduled_task_manager=scheduled_task_manager,
        notification_hub=notification_hub,
        markdown_image_converter=markdown_image_converter,
        creator_image_service=creator_image_service,
        sandbox_lock=sandbox["sandbox_lock"],
        sandbox_service=sandbox["sandbox_service"],
        sandbox_maintenance_manager=sandbox["sandbox_maintenance_manager"],
        browser_instance=browser["browser_instance"],
        browser_lifecycle_manager=browser["browser_lifecycle_manager"],
        problem_solver_manager=problem_solver_manager,
        image_pool=image_pool,
        group_message_queue=group_queue,
        friend_message_queue=friend_queue,
        data_dir=DATA_DIR,
    )
    plugin["host_facade"]._set_skills(skill_manager)

    plugin_runtime = build_plugin_runtime(
        config=config,
        adapter=adapter,
        logger_factory=logger_factory,
        hook_bus=plugin["hook_bus"],
        reply_block_registry=plugin["reply_block_registry"],
        runtime_output=plugin["runtime_output"],
        host_facade=plugin["host_facade"],
        file_server=file_server,
    )

    # ── 图片解析 / 记忆摘要 / TTS / 余额检查 ──
    image_parse_service = build_image_parse_service(
        vision_provider=vision_provider,
        adapter=adapter,
        uow_factory=uow_factory,
        logger_factory=logger_factory,
    )
    archive_summary_service = build_archive_summary_service(
        config=config,
        archive_memory_service=memory_svcs["archive_memory_service"],
        provider=provider,
        fallback_provider=provider,
        logger_factory=logger_factory,
        skill_manager=skill_manager,
    )
    tts_service = build_tts_service(config=config, logger_factory=logger_factory)
    balance_checker = build_balance_checker(
        config=config,
        notification_hub=notification_hub,
        logger_factory=logger_factory,
    )

    # ── 回复编排器 + 交叉注入 ──
    reply_orchestrator = build_reply_orchestrator(
        adapter=adapter,
        prompt_builder=memory_svcs["prompt_builder"],
        provider=provider,
        group_message_queue=group_queue,
        friend_message_queue=friend_queue,
        config=config,
        willing_service=memory_svcs["willing_service"],
        image_parse_service=image_parse_service,
        emoji_service=emoji_service,
        tts_service=tts_service,
        provider_error_message=provider_error_message,
        debug_recorder=debug_recorder,
        logger=logger_factory.get_logger("app.reply"),
        drawing_manager=drawing_manager,
        scheduled_task_manager=scheduled_task_manager,
        problem_solver_manager=problem_solver_manager,
        notification_hub=notification_hub,
        markdown_image_converter=markdown_image_converter,
        reply_block_registry=plugin["reply_block_registry"],
        skill_manager=skill_manager,
        balance_checker=balance_checker,
        hook_bus=plugin["hook_bus"],
        file_server=file_server,
    )
    notification_hub.set_orchestrator(reply_orchestrator)
    drawing_manager.set_orchestrator(reply_orchestrator)
    if scheduled_task_manager is not None:
        scheduled_task_manager.set_orchestrator(reply_orchestrator)
    if problem_solver_manager is not None:
        problem_solver_manager.set_orchestrator(reply_orchestrator)

    # ── 管线 / 网关 / 应用 ──
    return build_pipelines_and_app(
        adapter=adapter,
        memory=memory_svcs["memory"],
        group_message_queue=group_queue,
        friend_message_queue=friend_queue,
        profile_service=memory_svcs["profile_service"],
        willing_service=memory_svcs["willing_service"],
        reply_orchestrator=reply_orchestrator,
        image_parse_service=image_parse_service,
        archive_summary_service=archive_summary_service,
        config=config,
        hook_bus=plugin["hook_bus"],
        reply_block_registry=plugin["reply_block_registry"],
        logger_factory=logger_factory,
        chat_stream=memory_svcs["chat_stream"],
        emoji_service=emoji_service,
        tts_service=tts_service,
        file_server=file_server,
        bot_detector=memory_svcs["bot_detector"],
        scheduled_task_manager=scheduled_task_manager,
        problem_solver_manager=problem_solver_manager,
        markdown_image_converter=markdown_image_converter,
        plugin_runtime=plugin_runtime,
        report_service=usage["report_service"],
        _engine=_engine,
        vision_provider=vision_provider,
        temp_cleaner=sandbox["temp_cleaner"],
        sandbox_maintenance_manager=sandbox["sandbox_maintenance_manager"],
        browser_lifecycle_manager=browser["browser_lifecycle_manager"],
    )
