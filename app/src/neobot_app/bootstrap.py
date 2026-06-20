"""Composition root."""

from __future__ import annotations

from pathlib import Path

from neobot_chat import create_provider
from neobot_modloader import PluginHookBus, PluginHostFacade, PluginRuntime
from neobot_contracts.ports.clock import SystemClock
from neobot_memory import MemoryService
from neobot_memory.defaults import InMemoryMemoryRepository
from neobot_storage import run_migrations, sqlite_url

from neobot_app.audio import TTSService, VolcengineTTSService
from neobot_app.config.schemas.env import EnvConfig
from neobot_app.assembly.agents import resolve_agent_model_name
from neobot_app.assembly.adapter import build_adapter
from neobot_app.bot_detect import BotDetector
from neobot_app.assembly.memory import (
    build_archive_memory_service,
    build_image_analysis_service,
)
from neobot_app.assembly.storage import build_storage
from neobot_app.config.loader.env import load_env
from neobot_app.config.loader.manager import Config
from neobot_app.config.proxy import ConfigProxy
from neobot_app.config.schemas.bot import BotConfig as BotConfigSchema
from neobot_app.core import CONFIG_FILE, DATA_DIR, SRC_DATA_DIR
from neobot_app.utils.data_sync import sync_data_files
from neobot_app.database.chatstream import ChatStreamManager
from neobot_app.emoji.service import EmojiService
from neobot_app.image import ImageParseService
from neobot_app.message.queue import MessageQueue
from neobot_app.observability.debug import DebugRecorder
from neobot_app.observability.logging import (
    LoguruLoggerFactory,
    configure_loguru,
    set_runtime_event_dispatcher,
)
from neobot_app.observability.output import RuntimeOutput
from neobot_app.prompt.builder import PromptBuilder
from neobot_app.statistics.balance import BalanceChecker
from neobot_app.statistics.tracker import UsageTracker, initialize_usage_tracker
from neobot_app.statistics.reporter import UsageReportService
from neobot_app.reply import ReplyOrchestrator
from neobot_app.runtime.archive_memory_summary import ArchiveMemoryAutoSummaryService
from neobot_app.core.file_server import FileServer
from neobot_app.runtime.application import NeoBotApplication
from neobot_app.runtime.event_ingress import EventIngress
from neobot_app.runtime.event_pipeline import EventPipeline
from neobot_app.runtime.event_router import EventRouter
from neobot_app.runtime.inbound_pipeline import InboundPipeline
from neobot_app.runtime.lifecycle_handler import LifecycleHandler
from neobot_app.runtime.message_pipeline import MessagePipeline
from neobot_app.runtime.notice_handler import NoticeHandler
from neobot_app.runtime.notifications import BackgroundNotificationHub
from neobot_app.runtime.onebot_request_handler import OneBotRequestHandler
from neobot_app.runtime.reply_block import ReplyBlockRegistry
from neobot_app.runtime.scheduled_tasks import ScheduledTaskConfig, ScheduledTaskManager
from neobot_app.runtime.temp_cleaner import TempCleaner
from neobot_app.runtime.sandbox_lock import SandboxLock
from neobot_app.runtime.sandbox_service import SandboxService
from neobot_app.runtime.sandbox_maintenance import SandboxMaintenanceManager
from neobot_app.runtime.browser_lifecycle import BrowserLifecycleManager
from neobot_app.browser import BrowserAgentWrapper
from neobot_app.skills import build_all_skills
from neobot_app.user_profiles import UserProfileService
from neobot_app.willing import WillingService


def _load_config() -> BotConfigSchema:
    load_env()
    return Config.load(CONFIG_FILE, BotConfigSchema)


def _create_tts_service(*, config: BotConfigSchema, logger_factory) -> TTSService | VolcengineTTSService | None:
    """根据配置创建对应的 TTS 服务实例。"""
    if not config.tts.enabled:
        return None

    provider = config.tts.tts_provider.strip().casefold()
    tts_logger = logger_factory.get_logger("app.tts")

    if provider == "volcengine":
        api_config = EnvConfig.get_api_platform_config("HuoShan")
        api_key = api_config.api_key
        if not api_key:
            tts_logger.error(
                "火山引擎 TTS 缺少 HuoShan_APIKey 环境变量，TTS 已禁用"
            )
            return None
        app_id = EnvConfig._get_env_value("HuoShan_AppId") or ""
        tts_logger.info(
            f"TTS 提供商: 火山引擎 (Volcengine) - {'旧版控制台鉴权' if app_id else '新版控制台鉴权'}"
        )
        return VolcengineTTSService(
            config=config.tts,
            api_key=api_key,
            app_id=app_id,
            logger=tts_logger,
        )

    # 默认使用硅基流动
    if provider != "siliconflow":
        tts_logger.warning(
            f"未知的 tts_provider '{provider}'，回退到硅基流动 TTS"
        )
    tts_logger.info("TTS 提供商: 硅基流动 (SiliconFlow)")
    return TTSService(
        config=config.tts,
        logger=tts_logger,
    )


def _create_optional_agent_provider(
    *,
    config: BotConfigSchema,
    agent_name: str,
    fallback_provider,
    provider_logger,
):
    model_name = resolve_agent_model_name(config, agent_name, default_index=1)
    try:
        return create_provider(model_name)
    except Exception as exc:
        provider_logger.warning(
            f"无法创建 {agent_name} provider({model_name})，回退到主回复 provider: {exc}"
        )
        return fallback_provider


def _auto_install_chromium() -> bool:
    """尝试通过 Playwright 自动下载 Chromium。"""
    logger = LoguruLoggerFactory().get_logger("app.bootstrap")
    try:
        from playwright._impl._driver import compute_driver_executable, get_driver_dir

        import subprocess
        driver_path = get_driver_dir()
        driver_exe = compute_driver_executable()
        cli = Path(driver_path) / driver_exe
        logger.info("未检测到浏览器，正在自动下载 Chromium（约 150MB）…")
        result = subprocess.run(
            [str(cli), "install", "chromium"],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            logger.info("Chromium 自动下载完成")
            return True
        logger.warning(f"Chromium 自动下载失败: {result.stderr.strip()}")
        return False
    except ImportError:
        logger.info("playwright 未安装，跳过自动下载。"
                     "如需浏览器功能请: pip install playwright && playwright install chromium")
        return False
    except Exception as exc:
        logger.warning(f"Chromium 自动下载异常: {exc}")
        return False


def create_application() -> NeoBotApplication:
    configure_loguru(DATA_DIR / "logs", runtime_events=True)
    logger_factory = LoguruLoggerFactory()
    clock = SystemClock()
    config = ConfigProxy(_load_config())

    sync_data_files(SRC_DATA_DIR, DATA_DIR)

    debug_recorder = (
        DebugRecorder(
            DATA_DIR / "debug" / "log",
            logger=logger_factory.get_logger("app.debug"),
        )
        if getattr(getattr(config, "debug", None), "enabled", False)
        else None
    )

    db_url = sqlite_url(DATA_DIR / "neobot.db")
    run_migrations(db_url)
    _engine, uow_factory = build_storage(db_url)

    from sqlalchemy.ext.asyncio import async_sessionmaker
    usage_session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    usage_tracker = UsageTracker(
        usage_session_factory,
        logger=logger_factory.get_logger("app.usage"),
    )
    initialize_usage_tracker(usage_tracker)
    report_service = UsageReportService(
        usage_session_factory,
        logger=logger_factory.get_logger("app.usage_report"),
    )

    timestamp_interval_seconds = getattr(
        config.chat,
        "message_timestamp_interval_seconds",
        300,
    )
    poke_weight = getattr(config.chat, "poke_weight", 0.2)
    reaction_weight = getattr(config.chat, "reaction_weight", 0.2)
    forward_weight = getattr(config.chat, "forward_message_queue_weight", 2)
    bot_account = config.bot.account
    reply_blacklist = set(config.chat.reply_blacklist or [])
    group_message_queue = MessageQueue(
        max_size=config.chat.max_group_chat_observations,
        timestamp_interval_seconds=timestamp_interval_seconds,
        poke_weight=poke_weight,
        reaction_weight=reaction_weight,
        forward_weight=forward_weight,
        bot_account=bot_account,
        reply_blacklist=reply_blacklist,
    )
    friend_message_queue = MessageQueue(
        max_size=config.chat.max_friend_chat_observations,
        timestamp_interval_seconds=timestamp_interval_seconds,
        poke_weight=poke_weight,
        reaction_weight=reaction_weight,
        forward_weight=forward_weight,
        bot_account=bot_account,
        reply_blacklist=reply_blacklist,
    )

    adapter = build_adapter(
        config=config,
        logger=logger_factory.get_logger("adapter"),
        packet_callback=debug_recorder.record_packet if debug_recorder is not None else None,
    )

    plugin_runtime = None
    reply_block_registry = ReplyBlockRegistry()
    runtime_output = RuntimeOutput(logger=logger_factory.get_logger("app.output"))
    hook_bus = PluginHookBus(
        logger=logger_factory.get_logger("modloader.hooks"),
        record_ai_reply_block=reply_block_registry.block_event,
        output=runtime_output,
    )
    runtime_output.set_runtime_events(hook_bus)
    set_runtime_event_dispatcher(hook_bus.dispatch_envelope)

    host_facade = PluginHostFacade(events=hook_bus, output=runtime_output)

    # 注册动态配置重载命令
    async def _reload_config(**kwargs: Any) -> dict[str, Any]:
        new_config = _load_config()
        config.reload(new_config)
        sync_data_files(SRC_DATA_DIR, DATA_DIR)
        await host_facade.lifecycle.fire("config.changed")
        return {"status": "ok", "message": "配置已重载，所有服务下次访问配置时将看到新值"}

    host_facade.commands.register("config.reload", "重新加载配置文件并通知所有已订阅 lifecycle 的插件", _reload_config)

    bot_detector = BotDetector(adapter)

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

    archive_memory_service = build_archive_memory_service(
        uow_factory=uow_factory,
        logger=logger_factory.get_logger("app.archive_memory"),
    )

    profile_service = UserProfileService(
        adapter=adapter,
        uow_factory=uow_factory,
        config=config,
        logger=logger_factory.get_logger("app.user_profiles"),
        archive_memory_service=archive_memory_service,
    )

    willing_service = WillingService(
        config=config,
        logger=logger_factory.get_logger("app.willing"),
        bot_detector=bot_detector,
    )

    provider_logger = logger_factory.get_logger("app.provider")
    provider = None
    main_model_name = resolve_agent_model_name(config, "main_agent", default_index=0)
    try:
        provider = create_provider(main_model_name)
    except Exception as exc:
        provider_logger.error(f"无法创建主对话 chat provider({main_model_name}): {exc}")

    provider_error_message = None
    if provider is None:
        provider_error_message = "当前主回复模型不可用，请检查模型配置与 API Key"
        provider_logger.error(provider_error_message)

    adaptive_prompt_enabled = (
        getattr(getattr(config.agent, "memory", None), "adaptive_prompt_enabled", True)
    )
    prompt_builder = PromptBuilder(
        config=config,
        profile_service=profile_service,
        logger=logger_factory.get_logger("app.prompt"),
        archive_memory_service=archive_memory_service,
        adaptive_prompt_path=(
            DATA_DIR / "自适应提示词.txt" if adaptive_prompt_enabled else None
        ),
        uow_factory=uow_factory,
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
    emoji_page_size = getattr(getattr(config, "chat", None), "emoji_page_size", 50) or 50
    emoji_service = EmojiService(
        data_dir=DATA_DIR,
        uow_factory=uow_factory,
        vision_provider=vision_provider,
        page_size=emoji_page_size,
        logger=logger_factory.get_logger("app.emoji"),
    )

    # 创建后台绘图管理器
    from neobot_app.agents.creator import BackgroundDrawingManager, CreatorAgentConfig
    from neobot_app.agents.problem_solver import (
        ProblemSolverManager,
        ProblemSolverAgentConfig,
        build_problem_solver_agent,
    )
    from neobot_app.reply.markdown_image import MarkdownImageConverter

    notification_hub = BackgroundNotificationHub(
        logger=logger_factory.get_logger("app.background_notifications"),
    )

    creator_config = CreatorAgentConfig.from_schema(config.agent.creator)
    drawing_manager = BackgroundDrawingManager(
        config=creator_config,
        logger=logger_factory.get_logger("app.drawing"),
        notification_hub=notification_hub,
    )

    scheduled_task_config = ScheduledTaskConfig.from_schema(config.scheduled_task)
    scheduled_task_manager = (
        ScheduledTaskManager(
            uow_factory=uow_factory,
            config=scheduled_task_config,
            logger=logger_factory.get_logger("app.scheduled_task"),
            notification_hub=notification_hub,
        )
        if scheduled_task_config.enabled
        else None
    )

    problem_solver_config = ProblemSolverAgentConfig.from_schema(
        getattr(config.agent, "problem_solver", None)
    )
    problem_solver_manager = (
        ProblemSolverManager(
            config=problem_solver_config,
            logger=logger_factory.get_logger("app.problem_solver"),
            notification_hub=notification_hub,
        )
        if problem_solver_config.enabled
        else None
    )

    # ── Phase 1: Skill 系统基础设施 ──
    sandbox_lock = SandboxLock()

    browser_cfg = getattr(config.agent, "browser", None)
    browser_instance: Any = None
    browser_lifecycle_manager: Any = None

    if browser_cfg and browser_cfg.enabled:
        # 尝试查找浏览器，找不到则自动下载
        from neobot_app.browser.agent_browser.manager import _find_chrome_binary
        if not _find_chrome_binary():
            _auto_install_chromium()

        if _find_chrome_binary():
            idle_timeout = int(getattr(browser_cfg, "auto_close_idle_seconds", 600)) // 60
            browser_lifecycle_manager = BrowserLifecycleManager(
                idle_timeout_minutes=max(idle_timeout, 1),
                hold_max_minutes=browser_cfg.hold_max_minutes,
            )
            browser_instance = BrowserAgentWrapper(
                data_dir=DATA_DIR / "browser",
                headless=getattr(browser_cfg, "headless", True),
                port=getattr(browser_cfg, "port", 0),
                browser_path=getattr(browser_cfg, "browser_path", ""),
                lifecycle_manager=browser_lifecycle_manager,
            )
            browser_lifecycle_manager.set_browser_instance(browser_instance)

            # 设置关闭回调：当聊天流闲置超时，关闭其标签页
            async def _close_flow_tabs(chat_flow_id: str, tab_ids: set) -> None:
                if browser_instance is None:
                    return
                tabs_result = await browser_instance.list_tabs()
                if isinstance(tabs_result, list):
                    tabs = tabs_result
                elif isinstance(tabs_result, dict):
                    tabs = tabs_result.get("tabs", [])
                else:
                    return
                id_to_index = {t["tab_id"]: t["index"] for t in tabs if "tab_id" in t and "index" in t}
                indices = sorted(
                    (id_to_index[tid] for tid in tab_ids if tid in id_to_index),
                    reverse=True,
                )
                for idx in indices:
                    try:
                        await browser_instance.close_tab(idx)
                    except Exception:
                        pass

            browser_lifecycle_manager.set_close_callback(_close_flow_tabs)
        else:
            logger.warning("浏览器已启用但未能找到或下载 Chromium，浏览器功能不可用")

    markdown_image_converter = MarkdownImageConverter(
        output_dir=DATA_DIR / "markdown_images",
        browser_instance=browser_instance,
        logger=logger_factory.get_logger("app.markdown_image"),
    )

    file_server = FileServer(
        DATA_DIR,
        port=config.file_server.port,
        host=config.file_server.host,
        public_url=config.file_server.public_url,
        enabled=config.file_server.enabled,
    )

    sandbox_cfg = getattr(config.agent, "sandbox", None)
    sandbox_service = (
        SandboxService(
            sandbox_root=DATA_DIR / "sandbox",
            lock=sandbox_lock,
            allowed_read_dirs=[
                DATA_DIR / "emoji",
                DATA_DIR / "creator" / "gallery",
            ],
        )
        if sandbox_cfg and sandbox_cfg.enabled
        else None
    )

    temp_cleaner = (
        TempCleaner(
            temp_dir=DATA_DIR / "sandbox" / "temp",
            max_age_seconds=sandbox_cfg.temp_max_age_seconds,
            scan_interval_seconds=sandbox_cfg.scan_interval_seconds,
            logger=logger_factory.get_logger("app.temp_cleaner"),
        )
        if sandbox_cfg and sandbox_cfg.enabled
        else None
    )

    sandbox_maintenance_manager = (
        SandboxMaintenanceManager(
            sandbox_root=DATA_DIR / "sandbox",
            interval_seconds=(
                sandbox_cfg.maintenance.interval_seconds
                if sandbox_cfg else 43200
            ),
            enabled=(
                sandbox_cfg.maintenance.enabled
                if sandbox_cfg else True
            ),
            notification_hub=notification_hub,
            logger=logger_factory.get_logger("app.sandbox_maintenance"),
        )
        if sandbox_cfg and sandbox_cfg.enabled
        else None
    )

    if problem_solver_manager is not None:
        ps_provider = _create_optional_agent_provider(
            config=config,
            agent_name="problem_solver",
            fallback_provider=provider,
            provider_logger=provider_logger,
        )
        build_problem_solver_agent(
            ps_provider,
            config=problem_solver_config,
            logger=logger_factory.get_logger("app.problem_solver"),
            manager=problem_solver_manager,
            sandbox_service=sandbox_service,
        )

    skill_manager = build_all_skills(
        disabled_skills=getattr(getattr(config.agent, "skill", None), "disabled_skills", None),
        config=config,
        adapter=adapter,
        archive_memory_service=archive_memory_service,
        profile_service=profile_service,
        emoji_service=emoji_service,
        vision_provider=vision_provider,
        file_server=file_server,
        willing_service=willing_service,
        drawing_manager=drawing_manager,
        scheduled_task_manager=scheduled_task_manager,
        notification_hub=notification_hub,
        markdown_image_converter=markdown_image_converter,
        sandbox_lock=sandbox_lock,
        sandbox_service=sandbox_service,
        sandbox_maintenance_manager=sandbox_maintenance_manager,
        browser_instance=browser_instance,
        browser_lifecycle_manager=browser_lifecycle_manager,
        problem_solver_manager=problem_solver_manager,
        data_dir=DATA_DIR,
    )

    # 将 SkillManager 注入 PluginHostFacade（供插件 register_skill 使用）
    host_facade._set_skills(skill_manager)

    if config.plugins.enabled:
        plugin_dir = Path(config.plugins.dir)
        if not plugin_dir.is_absolute():
            plugin_dir = DATA_DIR / plugin_dir

        # MediaSender wrapper — binds file_server so plugins never import neobot_app
        from neobot_app.utils import media_sender as _media_sender_module

        class _MediaSenderWrapper:
            """Wraps neobot_app.utils.media_sender for injection via MediaSender protocol."""

            def __init__(self, fs: Any) -> None:
                self._fs = fs

            async def send_image(
                self,
                adapter: Any,
                conversation: Any,
                *,
                path: Path | None = None,
                data: bytes | None = None,
                filename: str | None = None,
            ) -> Any:
                if path is not None:
                    return await _media_sender_module.send_image(self._fs, adapter, conversation, path)
                if data is not None:
                    raise NotImplementedError("send_image with raw data is handled by the plugin runtime context")
                raise ValueError("Must provide path or data+filename")

            async def send_audio(self, adapter: Any, conversation: Any, *, path: Path) -> Any:
                return await _media_sender_module.send_audio(self._fs, adapter, conversation, path)

            def prepare_image_segment(self, file_server: Any, file_path: Path) -> dict:
                return _media_sender_module.prepare_image_segment(file_server, file_path)

            def prepare_audio_segment(self, file_server: Any, file_path: Path) -> dict:
                return _media_sender_module.prepare_audio_segment(file_server, file_path)

        media_sender = _MediaSenderWrapper(file_server)

        plugin_runtime = PluginRuntime(
            plugin_dir=plugin_dir,
            data_dir=DATA_DIR / "plugins_data",
            adapter=adapter,
            logger_factory=logger_factory,
            hook_bus=hook_bus,
            record_ai_reply_block=reply_block_registry.block_event,
            output=runtime_output,
            host=host_facade,
            file_server=file_server,
            media_sender=media_sender,
            auto_install_dependencies=True,
        )
        plugin_runtime.load_all()

    image_parse_service = ImageParseService(
        vision_provider=vision_provider,
        image_analysis_service=image_analysis_service,
        adapter=adapter,
        logger=logger_factory.get_logger("app.image_parse"),
    )

    adaptive_prompt_skill = skill_manager.get("adaptive_prompt")
    summary_tool_defs = adaptive_prompt_skill.get_tools() if adaptive_prompt_skill else []

    async def _summary_tool_executor(tool_name: str, args: dict) -> str:
        return await skill_manager.execute(tool_name, args)

    archive_summary_service = ArchiveMemoryAutoSummaryService(
        archive_memory_service=archive_memory_service,
        provider=_create_optional_agent_provider(
            config=config,
            agent_name="archive_summary",
            fallback_provider=provider,
            provider_logger=provider_logger,
        ),
        config=config,
        item_archive_config=getattr(
            getattr(getattr(config, "agent", None), "memory", None), "item_archive", None
        ),
        logger=logger_factory.get_logger("app.archive_summary"),
        tool_definitions=summary_tool_defs,
        tool_executor=_summary_tool_executor,
    )

    tts_service = _create_tts_service(
        config=config,
        logger_factory=logger_factory,
    )

    chat_cfg = config.chat
    balance_checker = None
    if getattr(chat_cfg, "enable_balance_check", False):
        primary_provider = getattr(
            getattr(config.models, "primary_chat_model", None), "provider", ""
        )
        if primary_provider.strip().casefold() in {"deepseek", "deepseek_offical", "deepseek_official"}:
            ds_config = EnvConfig.get_api_platform_config("DeepSeek")
            if ds_config.api_key and getattr(chat_cfg, "admin_accounts", None):
                balance_checker = BalanceChecker(
                    api_key=ds_config.api_key,
                    base_url=ds_config.url or "https://api.deepseek.com",
                    notification_hub=notification_hub,
                    admin_accounts=list(chat_cfg.admin_accounts),
                    balance_threshold=getattr(chat_cfg, "balance_threshold", 1.0),
                    cooldown_seconds=getattr(chat_cfg, "balance_check_cooldown_seconds", 300),
                    logger=logger_factory.get_logger("app.balance"),
                )
                provider_logger.info("余额检查已启用")
            else:
                provider_logger.warning(
                    "余额检查已启用但缺少 DeepSeek API Key 或管理员账户，自动禁用"
                )
        else:
            provider_logger.info(
                "主模型非 DeepSeek，余额检查自动禁用"
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
        tts_service=tts_service,
        provider_error_message=provider_error_message,
        debug_recorder=debug_recorder,
        logger=logger_factory.get_logger("app.reply"),
        drawing_manager=drawing_manager,
        scheduled_task_manager=scheduled_task_manager,
        problem_solver_manager=problem_solver_manager,
        notification_hub=notification_hub,
        markdown_image_converter=markdown_image_converter,
        reply_block_registry=reply_block_registry,
        skill_manager=skill_manager,
        balance_checker=balance_checker,
        runtime_events=hook_bus,
        file_server=file_server,
    )
    notification_hub.set_orchestrator(reply_orchestrator)
    drawing_manager.set_orchestrator(reply_orchestrator)
    if scheduled_task_manager is not None:
        scheduled_task_manager.set_orchestrator(reply_orchestrator)
    if problem_solver_manager is not None:
        problem_solver_manager.set_orchestrator(reply_orchestrator)

    inbound_pipeline = InboundPipeline(
        adapter=adapter,
        memory=memory,
        logger=logger_factory.get_logger("app.inbound_pipeline"),
    )

    legacy_event_pipeline = EventPipeline(
        adapter=adapter,
        group_message_queue=group_message_queue,
        friend_message_queue=friend_message_queue,
        profile_service=profile_service,
        willing_service=willing_service,
        reply_orchestrator=reply_orchestrator,
        image_parse_service=image_parse_service,
        inbound_pipeline=inbound_pipeline,
        archive_summary_service=archive_summary_service,
        config=config,
        logger=logger_factory.get_logger("app.event_pipeline"),
        reply_block_registry=reply_block_registry,
    )
    message_pipeline = MessagePipeline(
        legacy_pipeline=legacy_event_pipeline,
        logger=logger_factory.get_logger("app.message_pipeline"),
    )
    notice_handler = NoticeHandler(legacy_pipeline=legacy_event_pipeline)
    request_handler = OneBotRequestHandler(logger=logger_factory.get_logger("app.onebot_request"))
    lifecycle_handler = LifecycleHandler(logger=logger_factory.get_logger("app.lifecycle"))
    event_router = EventRouter(
        message_pipeline=message_pipeline,
        notice_handler=notice_handler,
        request_handler=request_handler,
        lifecycle_handler=lifecycle_handler,
        logger=logger_factory.get_logger("app.event_router"),
    )
    event_ingress = EventIngress(
        event_source=adapter,
        hook_bus=hook_bus,
        router=event_router,
        logger=logger_factory.get_logger("app.event_ingress"),
    )

    return NeoBotApplication(
        adapter=adapter,
        chat_stream=chat_stream,
        event_ingress=event_ingress,
        message_pipeline=message_pipeline,
        reply_orchestrator=reply_orchestrator,
        emoji_service=emoji_service,
        tts_service=tts_service,
        logger=logger_factory.get_logger("app.runtime"),
        file_server=file_server,
        bot_detector=bot_detector,
        scheduled_task_manager=scheduled_task_manager,
        problem_solver_manager=problem_solver_manager,
        markdown_image_converter=markdown_image_converter,
        plugin_runtime=plugin_runtime,
        report_service=report_service,
        engine=_engine,
        vision_provider=vision_provider,
        archive_summary_service=archive_summary_service,
        temp_cleaner=temp_cleaner,
        sandbox_maintenance_manager=sandbox_maintenance_manager,
        browser_lifecycle_manager=browser_lifecycle_manager,
    )
