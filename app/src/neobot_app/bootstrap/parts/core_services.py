"""装配核心服务：日志/配置/队列/存储/适配器/插件主机/Provider/浏览器/沙箱。"""

from __future__ import annotations

from neobot_contracts.ports.clock import SystemClock
from neobot_storage import sqlite_url
from neobot_app.bootstrap._pipeline import build_plugin_host
from neobot_app.bootstrap._providers import build_main_provider, build_vision_provider, resolve_vision_model_name
from neobot_app.bootstrap._runtime import build_browser_components, build_creator_image_service, build_drawing_manager, build_image_pool, build_markdown_image_converter, build_notification_hub, build_problem_solver_manager, build_sandbox_components, build_scheduled_task_manager
from neobot_app.bootstrap._services import build_adapter_service, build_context_recorder, build_debug_recorder, build_emoji_service, build_file_server, build_memory_services, build_message_queues
from neobot_app.bootstrap._usage import build_usage_components
from neobot_app.core import DATA_DIR, SRC_DATA_DIR
from neobot_app.observability.logging import LoguruLoggerFactory, configure_loguru
from neobot_app.prompt.store import PromptStore, sync_default_prompts
from neobot_app.runtime.adapter_supervisor import AdapterSupervisor
from neobot_app.runtime.hot_reload_registry import HotReloadRegistry
from neobot_app.utils.data_sync import sync_data_files
from .core_reuse import _build_storage, _load_config_for_reuse, _reuse_or, _run_once, config_load_error
from .maintenance_services import _register_billing_hot_reload_rule, _warmup_billing_scripts
from .state import _BuildState


def _build_core_services(state: _BuildState) -> None:
    """装配核心服务：日志/配置/队列/存储/适配器/插件主机/Provider/浏览器/沙箱。"""

    _run_once("loguru", lambda: configure_loguru(DATA_DIR / "logs", runtime_events=True))
    logger_factory = _reuse_or("logger_factory", LoguruLoggerFactory)
    config = _load_config_for_reuse()

    sync_data_files(SRC_DATA_DIR, DATA_DIR)
    sync_default_prompts(DATA_DIR, logger=logger_factory.get_logger("app.prompt"))
    prompt_store = _reuse_or(
        "prompt_store",
        lambda: PromptStore(DATA_DIR, logger=logger_factory.get_logger("app.prompt")),
    )

    # ── 聊天流快照登记处(网页面板「聊天流」页只读视图) ──
    from neobot_app.reply.flow_registry import ChatFlowRegistry

    chat_flow_registry = _reuse_or(
        "chat_flow_registry",
        lambda: ChatFlowRegistry(logger=logger_factory.get_logger("app.reply")),
    )

    # ── 睡眠服务(/sleep /awake 命令、睡眠 skill、事件管线共用) ──
    from neobot_app.runtime.sleep_service import SleepService

    sleep_service = _reuse_or(
        "sleep_service",
        lambda: SleepService(
            prompt_store=prompt_store,
            logger=logger_factory.get_logger("app.sleep"),
        ),
    )

    # ── 待机服务(面板待机按钮、/standby /reboot 共用的状态机) ──
    # 待机 = 停掉 bot 运行时、只留面板与命令；运行时的停/启由装配层通过回调注入。
    from neobot_app.runtime.standby_service import (
        DEFAULT_RESUME_TIMEOUT_SECONDS,
        DEFAULT_SHUTDOWN_TIMEOUT_SECONDS,
        StandbyService,
    )

    standby_cfg = getattr(config, "standby", None)
    standby_service = _reuse_or(
        "standby_service",
        lambda: StandbyService(
            logger=logger_factory.get_logger("app.standby"),
            state_path=DATA_DIR / "standby.json",
            connect_onebot=bool(getattr(standby_cfg, "connect_onebot", True)),
            # 配置缺失时强制「启动即待机」：用默认配置把面板拉起来修配置
            start_in_standby=bool(config_load_error())
            or bool(getattr(standby_cfg, "start_in_standby", False)),
            # 关闭/软重启的观察窗口：关闭要跑记忆总结这类分钟级收尾，窗口必须装得下。
            shutdown_timeout=float(
                getattr(standby_cfg, "shutdown_timeout_seconds", None)
                or DEFAULT_SHUTDOWN_TIMEOUT_SECONDS
            ),
            resume_timeout=float(
                getattr(standby_cfg, "resume_timeout_seconds", None)
                or DEFAULT_RESUME_TIMEOUT_SECONDS
            ),
            # 进入待机同样是「停掉整个 bot 运行时」，与关闭共用同一个窗口。
            enter_timeout=float(
                getattr(standby_cfg, "shutdown_timeout_seconds", None)
                or DEFAULT_SHUTDOWN_TIMEOUT_SECONDS
            ),
        ),
    )
    if config_load_error():
        standby_service.set_startup_reason(
            f"配置缺失，已进入待机等待修复：{config_load_error()}"
        )

    # ── 字符级缓存命中计算器(成本管线;仅聊天管线接入) ──
    from neobot_app.cache import CacheCalculator

    cache_calculator = CacheCalculator(
        retention_seconds=(
            getattr(getattr(config, "chat", None), "cache_retention_seconds", None) or 1800
        ),
        price_difference=(
            getattr(getattr(config, "chat", None), "cache_hit_price_difference", None) or 120
        ),
        logger=logger_factory.get_logger("app.cache"),
    )

    debug_recorder = _reuse_or(
        "debug_recorder",
        lambda: build_debug_recorder(
            config=config, logger=logger_factory.get_logger("app.debug")
        ),
    )

    # 完整提示词历史记录器:每次模型调用的完整上下文,纯内存 + 逐份 diff 保留最近
    # N 份(默认 100),重启即清空。由 [chat].chat_flow_prompt_history_enabled 控制,
    # 与 debug 开关解耦 —— 面板的「聊天流 → 完整提示词」不依赖 debug.enabled。
    context_recorder = build_context_recorder(
        config=config, logger=logger_factory.get_logger("app.context")
    )

    # 迁移前先留一份可回滚快照：alembic 迁移里存在不可逆操作
    # （如 0021 的去重 DELETE），失败时没有备份就只能人工恢复。
    db_path = DATA_DIR / "neobot.db"
    db_url = sqlite_url(db_path)
    _engine, uow_factory = _reuse_or(
        "storage", lambda: _build_storage(db_path, db_url, logger_factory)
    )

    usage = _reuse_or(
        "usage",
        lambda: build_usage_components(
            _engine=_engine,
            logger_factory=logger_factory,
            config=config,
        ),
    )

    # ── 本体级头像存储（spec(5) §4.9 / R33–R37）──
    # 复用同一份 storage 引擎：头像三列就在 user_data 上，所以「有 user_data 行
    # = 认识该用户」自动覆盖「聊过天的人」。软重启时复用实例（内存缓存与在途
    # 下载不重建），配置项在构造期读取。
    from neobot_app.runtime.avatar_store import AvatarStore

    avatar_store = _reuse_or(
        "avatar_store",
        lambda: AvatarStore(
            uow_factory=uow_factory,
            config=config,
            logger=logger_factory.get_logger("app.avatar_store"),
        ),
    )

    # 计费脚本按需加载：登记热重载规则，面板/文件变更后无需重启进程（spec(4) §4.4 / Q13）。
    # 放在 _reuse_or 之外，保证软重启复用组件时规则依然登记在案。
    _register_billing_hot_reload_rule()
    _warmup_billing_scripts(usage.get("billing"))

    group_queue, friend_queue = build_message_queues(config=config)

    adapter = _reuse_or(
        "adapter",
        lambda: build_adapter_service(
            config=config,
            logger=logger_factory.get_logger("adapter"),
            debug_recorder=debug_recorder,
        ),
    )

    # ── 配置热重载编排：组件自己声明关心哪些配置项并负责生效 ──
    # 装配顺序即生效顺序：适配器先恢复连接，其余组件再按新配置重建。
    hot_reload_registry = _reuse_or(
        "hot_reload_registry",
        lambda: HotReloadRegistry(
            [
                AdapterSupervisor(
                    adapter, logger=logger_factory.get_logger("app.adapter_reload")
                )
            ],
            logger=logger_factory.get_logger("app.hot_reload"),
        ),
    )

    # ── 插件主机基础设施 ──
    plugin = _reuse_or("plugin", lambda: build_plugin_host(logger_factory=logger_factory))
    adapter.core.speaking_policy = plugin["speaking_policy"]

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
        prompt_store=prompt_store,
    )

    provider_logger = logger_factory.get_logger("app.provider")
    # 视觉模型先创建：既用于图片解析，也作为主模型不可用时的自动回退路由。
    vision_provider = build_vision_provider(
        logger=provider_logger, model_name=resolve_vision_model_name(config)
    )
    provider, provider_error_message = build_main_provider(
        config=config, logger=provider_logger, vision_provider=vision_provider,
    )

    # ── 表情包 / 文件服务 / 图片暂存池 ──
    emoji_service = build_emoji_service(
        config=config,
        data_dir=DATA_DIR,
        uow_factory=uow_factory,
        vision_provider=vision_provider,
        logger_factory=logger_factory,
    )
    file_server = _reuse_or(
        "file_server", lambda: build_file_server(config=config, data_dir=DATA_DIR)
    )
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
        screenshots=browser["screenshots"],
        logger_factory=logger_factory,
    )

    if getattr(config.agent.creator, "enabled", False):
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
    else:
        creator_image_service = None

    sandbox = build_sandbox_components(
        config=config,
        data_dir=DATA_DIR,
    )
    if sandbox["temp_cleaner"] is not None:
        # 两个类的字段名是 _logger：写成 .logger 只是往实例上挂了个死属性，
        # 生产里它们始终用构造时的 NullLogger，所有清理失败都不可见。
        sandbox["temp_cleaner"]._logger = logger_factory.get_logger("app.temp_cleaner")
    if sandbox["sandbox_maintenance_manager"] is not None:
        sandbox["sandbox_maintenance_manager"]._logger = logger_factory.get_logger(
            "app.sandbox_maintenance"
        )

    state._engine = _engine
    state.adapter = adapter
    state.avatar_store = avatar_store
    state.browser = browser
    state.cache_calculator = cache_calculator
    state.chat_flow_registry = chat_flow_registry
    state.config = config
    state.context_recorder = context_recorder
    state.creator_image_service = creator_image_service
    state.debug_recorder = debug_recorder
    state.drawing_manager = drawing_manager
    state.emoji_service = emoji_service
    state.file_server = file_server
    state.friend_queue = friend_queue
    state.group_queue = group_queue
    state.hot_reload_registry = hot_reload_registry
    state.image_pool = image_pool
    state.logger_factory = logger_factory
    state.markdown_image_converter = markdown_image_converter
    state.memory_svcs = memory_svcs
    state.notification_hub = notification_hub
    state.plugin = plugin
    state.problem_solver_manager = problem_solver_manager
    state.prompt_store = prompt_store
    state.provider = provider
    state.provider_error_message = provider_error_message
    state.provider_logger = provider_logger
    state.sandbox = sandbox
    state.scheduled_task_manager = scheduled_task_manager
    state.sleep_service = sleep_service
    state.standby_service = standby_service
    state.uow_factory = uow_factory
    state.usage = usage
    state.vision_provider = vision_provider
