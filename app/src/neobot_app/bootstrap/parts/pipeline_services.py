"""装配回复管线服务：图片解析、记忆摘要、TTS、自修复、回复编排器。"""

from __future__ import annotations

from neobot_app.bootstrap._commands import _make_chat_config_update_callback
from neobot_app.bootstrap._pipeline import build_reply_orchestrator
from neobot_app.bootstrap._runtime import build_self_heal_agent_wiring, build_self_heal_manager
from neobot_app.bootstrap._services import build_archive_summary_service, build_image_parse_service, build_tts_service
from neobot_app.core import DATA_DIR
from neobot_app.core.paths import _get_project_root
from neobot_app.observability.logging import register_self_heal_manager
from .core_reuse import _register_flow_task_providers
from .maintenance_services import _build_provider_reload_consumer, _web_search_config_dict
from .state import _BuildState


def _build_pipeline_services(state: _BuildState) -> None:
    """装配回复管线服务：图片解析、记忆摘要、TTS、自修复、回复编排器。"""
    adapter = state.adapter
    balance_checker = state.balance_checker
    bili_runtime = state.bili_runtime
    cache_calculator = state.cache_calculator
    chat_flow_registry = state.chat_flow_registry
    config = state.config
    context_recorder = state.context_recorder
    creator_image_service = state.creator_image_service
    credential_manager = state.credential_manager
    debug_recorder = state.debug_recorder
    drawing_manager = state.drawing_manager
    emoji_service = state.emoji_service
    file_server = state.file_server
    friend_queue = state.friend_queue
    group_queue = state.group_queue
    hot_reload_registry = state.hot_reload_registry
    logger_factory = state.logger_factory
    markdown_image_converter = state.markdown_image_converter
    markdown_skill_registry = state.markdown_skill_registry
    memory_svcs = state.memory_svcs
    notification_hub = state.notification_hub
    plugin = state.plugin
    problem_solver_manager = state.problem_solver_manager
    prompt_store = state.prompt_store
    provider = state.provider
    provider_error_message = state.provider_error_message
    provider_logger = state.provider_logger
    sandbox = state.sandbox
    scheduled_task_manager = state.scheduled_task_manager
    skill_manager = state.skill_manager
    sleep_service = state.sleep_service
    standby_service = state.standby_service
    uow_factory = state.uow_factory
    vision_provider = state.vision_provider

    # ── 图片解析 / 记忆摘要 / TTS / 余额检查 ──
    image_parse_service = build_image_parse_service(
        vision_provider=vision_provider,
        native_vision_provider=provider,
        adapter=adapter,
        uow_factory=uow_factory,
        logger_factory=logger_factory,
    )
    # 「图片已过期」时回显库里留过的描述：登记表按引用摘要查询，落库在解析服务侧
    # （见 app/src/neobot_app/image/unavailable.py）。
    from neobot_app.image.unavailable import install_description_lookup

    install_description_lookup(image_parse_service.description_for_ref)
    archive_summary_service = build_archive_summary_service(
        config=config,
        archive_memory_service=memory_svcs["archive_memory_service"],
        provider=provider,
        fallback_provider=provider,
        logger_factory=logger_factory,
        skill_manager=skill_manager,
        standby_service=standby_service,
    )
    try:
        bili_runtime.set_archive_summary_service(archive_summary_service)
    except Exception:
        pass
    tts_service = build_tts_service(config=config, logger_factory=logger_factory)

    # ── 自修复 Agent 装配 ──
    project_root = _get_project_root()
    source_roots = [project_root / "app", project_root / "packages"]
    log_file_path = DATA_DIR / "logs" / "neobot.log"
    self_heal_manager = build_self_heal_manager(
        config=config,
        logger_factory=logger_factory,
        notification_hub=notification_hub,
        sandbox_service=sandbox["sandbox_service"],
        drawing_manager=drawing_manager,
        creator_image_service=creator_image_service,
        data_dir=DATA_DIR,
        source_roots=source_roots,
        log_file=log_file_path,
        web_search_config=_web_search_config_dict(config),
        vision_provider=vision_provider,
    )
    if self_heal_manager is not None:
        register_self_heal_manager(self_heal_manager)
        build_self_heal_agent_wiring(
            config=config,
            manager=self_heal_manager,
            provider=provider,
            provider_logger=provider_logger,
            sandbox_service=sandbox["sandbox_service"],
            logger_factory=logger_factory,
            data_dir=DATA_DIR,
            source_roots=source_roots,
            log_file=log_file_path,
            vision_provider=vision_provider,
            web_search_config=_web_search_config_dict(config),
            prompt_store=prompt_store,
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
        context_recorder=context_recorder,
        # Bot 自身发言落盘复用同一份 storage 引擎（软重启/冷启动补齐 assistant 块，见 feat(2) §11）
        self_sent_uow_factory=uow_factory,
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
        skills_registry=markdown_skill_registry,
        prompt_store=prompt_store,
        flow_registry=chat_flow_registry,
        cache_calculator=cache_calculator,
        credential_manager=credential_manager,
        config_update_callback=_make_chat_config_update_callback(config),
        sleep_service=sleep_service,
        standby_service=standby_service,
    )
    notification_hub.set_orchestrator(reply_orchestrator)
    drawing_manager.set_orchestrator(reply_orchestrator)
    # cross_chat 的投递要拿住目标聊天的 ReplyEvent 才能取回回复：只有在编排器
    # 可用时才走 start_background_reply，否则退化为 hub 注入（见 cross_chat_skill）。
    _cross_chat_skill = skill_manager.get("cross_chat") if skill_manager is not None else None
    if _cross_chat_skill is not None and callable(getattr(_cross_chat_skill, "set_orchestrator", None)):
        _cross_chat_skill.set_orchestrator(reply_orchestrator)
    # 面板「聊天流」页的后台任务聚合:与 check_background_tasks 工具同源
    _register_flow_task_providers(
        chat_flow_registry,
        drawing_manager=drawing_manager,
        scheduled_task_manager=scheduled_task_manager,
        problem_solver_manager=problem_solver_manager,
        notification_hub=notification_hub,
    )
    if scheduled_task_manager is not None:
        scheduled_task_manager.set_orchestrator(reply_orchestrator)
    if problem_solver_manager is not None:
        problem_solver_manager.set_orchestrator(reply_orchestrator)
    if self_heal_manager is not None:
        self_heal_manager.set_orchestrator(reply_orchestrator)

    # ── provider 热重载：模型名/平台密钥变更后重建并原地替换 ──
    # 挂载点在这里才全部就绪（编排器、图片解析、档案总结），所以消费者在此注册。
    _provider_reload = _build_provider_reload_consumer(
        logger_factory=logger_factory,
        reply_orchestrator=reply_orchestrator,
        image_parse_service=image_parse_service,
        archive_summary_service=archive_summary_service,
        initial_vision_provider=vision_provider,
    )
    # 配置对象在运行期会被 ConfigProxy 原地替换，因此 builder 每次现取。
    # 软重启会重建 provider：先移除指向上一轮对象的消费者，再注册新的
    hot_reload_registry.unregister(getattr(_provider_reload, 'name', 'provider'))
    hot_reload_registry.register(_provider_reload)

    state.archive_summary_service = archive_summary_service
    state.image_parse_service = image_parse_service
    state.log_file_path = log_file_path
    state.reply_orchestrator = reply_orchestrator
    state.self_heal_manager = self_heal_manager
    state.source_roots = source_roots
    state.tts_service = tts_service
