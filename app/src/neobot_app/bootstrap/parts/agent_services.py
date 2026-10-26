"""装配 Agent 侧服务：解题去线、注册表、命令服务、凭据、Skill 管理器。"""

from __future__ import annotations

import inspect
from typing import Any
from neobot_app.bootstrap._commands import build_command_service, build_credential_manager
from neobot_app.bootstrap._pipeline import build_problem_solver_agent_wiring, register_config_reload_command
from neobot_app.bootstrap._runtime import build_balance_checker
from neobot_app.bootstrap._services import build_vision_detect_service
from neobot_app.bootstrap._skills import build_skill_manager
from neobot_app.core import DATA_DIR
from neobot_app.skills.balance_guide import sync_balance_query_skill
from .core_reuse import _reuse_or
from .maintenance_services import _web_search_config_dict
from .state import _BuildState


def _build_agent_services(state: _BuildState) -> None:
    """装配 Agent 侧服务：解题去线、注册表、命令服务、凭据、Skill 管理器。"""
    adapter = state.adapter
    avatar_store = state.avatar_store
    browser = state.browser
    config = state.config
    creator_image_service = state.creator_image_service
    drawing_manager = state.drawing_manager
    emoji_service = state.emoji_service
    file_server = state.file_server
    friend_queue = state.friend_queue
    group_queue = state.group_queue
    hot_reload_registry = state.hot_reload_registry
    image_pool = state.image_pool
    logger_factory = state.logger_factory
    markdown_image_converter = state.markdown_image_converter
    memory_svcs = state.memory_svcs
    notification_hub = state.notification_hub
    plugin = state.plugin
    problem_solver_manager = state.problem_solver_manager
    prompt_store = state.prompt_store
    provider = state.provider
    provider_logger = state.provider_logger
    sandbox = state.sandbox
    scheduled_task_manager = state.scheduled_task_manager
    sleep_service = state.sleep_service
    standby_service = state.standby_service
    uow_factory = state.uow_factory
    vision_provider = state.vision_provider

    # ── 解题 Agent 装配 ──
    build_problem_solver_agent_wiring(
        config=config,
        problem_solver_manager=problem_solver_manager,
        provider=provider,
        provider_logger=provider_logger,
        sandbox_service=sandbox["sandbox_service"],
        logger_factory=logger_factory,
        vision_provider=vision_provider,
        prompt_store=prompt_store,
    )

    # ── Skill 系统（balance_checker 先构建供 skill 条件注册使用） ──
    from neobot_chat.skills import SkillRegistry
    from neobot_chat.tools import AgentRegistry

    agent_registry = AgentRegistry()
    # discover() 加载 data/skills 目录下所有 SKILL.md（目录不存在时内部安全返回），
    # 否则该目录是死配置；discover 以裸 name 为 key，插件技能经 register_many
    # 以 owner:name 为 key，二者互不冲突（同名裸名与限定名也不会撞）
    markdown_skill_registry = SkillRegistry(root=DATA_DIR / "skills").discover()
    sync_balance_query_skill(
        registry=markdown_skill_registry,
        data_dir=DATA_DIR,
        config=config,
        logger=logger_factory.get_logger("app.skills"),
    )
    register_config_reload_command(
        host_facade=plugin["host_facade"],
        config=config,
        on_reload=lambda: sync_balance_query_skill(
            registry=markdown_skill_registry,
            data_dir=DATA_DIR,
            config=config,
            logger=logger_factory.get_logger("app.skills"),
        ),
        hot_reload=hot_reload_registry,
    )
    balance_checker = build_balance_checker(
        config=config,
        notification_hub=notification_hub,
        logger_factory=logger_factory,
    )
    # ── 本地视觉检测(ONNX/YOLO):启动时扫描模型目录并维护 models.toml 索引 ──
    vision_detect_service = build_vision_detect_service(
        config=config,
        data_dir=DATA_DIR,
        logger_factory=logger_factory,
    )

    # ── 命令系统(被@触发、/ 前缀、权限树;先于 skill/插件构建,供其注入) ──
    async def _reload_config_from_command() -> Any:
        """QQ /reload 命令 -> 宿主 config.reload 命令（与面板按钮同一入口）。"""
        commands = getattr(plugin["host_facade"], "commands", None)
        caller = getattr(commands, "call", None)
        if not callable(caller):
            return None
        result = caller("config.reload")
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, dict):
            return None
        return {
            "ok": str(result.get("status") or "").lower() == "ok",
            "message": str(result.get("message") or ""),
            "changes": result.get("changes"),
        }

    command_service = _reuse_or(
        "command_service",
        lambda: build_command_service(
        config=config,
        adapter=adapter,
        logger_factory=logger_factory,
        markdown_image_converter=markdown_image_converter,
        file_server=file_server,
        sleep_service=sleep_service,
        standby_service=standby_service,
        config_reload_callback=_reload_config_from_command,
        screenshots=browser["screenshots"],
    ),
    )
    if command_service is not None:
        # 软重启会重建浏览器实例：截图端口必须跟着换，否则 /help 会打到旧实例
        command_service.set_screenshots(browser["screenshots"])
    # 管理员卡片只画头像、不列 QQ 号：把 AvatarStore 接进命令服务（issue #85）
    command_service.set_avatar_store(avatar_store)

    # ── 凭据管理器(风险操作授权:踢人/退群需超级管理员凭据) ──
    credential_manager = build_credential_manager(
        permissions=command_service.permissions if command_service is not None else None,
    )
    if vision_detect_service is not None:
        from neobot_app.indexer import build_init_runner

        init_runner = build_init_runner(vision_detect_service=vision_detect_service)
        for task_report in init_runner.run_sync(force=False):
            if task_report.get("skipped"):
                continue
            report = task_report.get("report")
            if report is None:
                continue
            summary = getattr(report, "summary", lambda: str(report))
            if report.added or report.missing or report.errors or report.unconfigured:
                logger_factory.get_logger("app.init").warning(
                    f"[init] {task_report['task']}: {summary()}"
                )
    skill_manager = build_skill_manager(
        config=config,
        adapter=adapter,
        archive_memory_service=memory_svcs["archive_memory_service"],
        profile_service=memory_svcs["profile_service"],
        uow_factory=uow_factory,
        emoji_service=emoji_service,
        vision_provider=vision_provider,
        file_server=file_server,
        willing_service=memory_svcs["willing_service"],
        drawing_manager=drawing_manager,
        scheduled_task_manager=scheduled_task_manager,
        notification_hub=notification_hub,
        markdown_image_converter=markdown_image_converter,
        creator_image_service=creator_image_service,
        sandbox_service=sandbox["sandbox_service"],
        sandbox_maintenance_manager=sandbox["sandbox_maintenance_manager"],
        temp_cleaner=sandbox["temp_cleaner"],
        browser_instance=browser["browser_instance"],
        browser_lifecycle_manager=browser["browser_lifecycle_manager"],
        problem_solver_manager=problem_solver_manager,
        image_pool=image_pool,
        group_message_queue=group_queue,
        friend_message_queue=friend_queue,
        data_dir=DATA_DIR,
        balance_checker=balance_checker,
        agent_registry=agent_registry,
        vision_detect_service=vision_detect_service,
        credential_manager=credential_manager,
        sleep_service=sleep_service,
        agent_provider=provider,
        web_search_config=_web_search_config_dict(config),
    )
    plugin["host_facade"]._set_skills(skill_manager)

    state.agent_registry = agent_registry
    state.balance_checker = balance_checker
    state.command_service = command_service
    state.credential_manager = credential_manager
    state.markdown_skill_registry = markdown_skill_registry
    state.skill_manager = skill_manager
    state.vision_detect_service = vision_detect_service
