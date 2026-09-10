"""Composition root — 装配并返回 NeoBotApplication。"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from typing import Any

from neobot_contracts.ports.clock import SystemClock
from neobot_storage import backup_sqlite_database, run_migrations, sqlite_url

from neobot_app.assembly.storage import build_storage
from neobot_app.core import DATA_DIR, SRC_DATA_DIR
from neobot_app.core.paths import _get_project_root
from neobot_app.observability.logging import (
    LoguruLoggerFactory,
    configure_loguru,
    register_self_heal_manager,
)
from neobot_app.runtime.application import NeoBotApplication
from neobot_app.utils.data_sync import sync_data_files

from neobot_app.bootstrap._config import build_config
from neobot_app.bootstrap._commands import (
    build_command_service,
    build_credential_manager,
    _make_chat_config_update_callback,
)
from neobot_app.bootstrap._providers import (
    build_main_provider,
    build_vision_provider,
    resolve_vision_model_name,
)
from neobot_app.bootstrap._services import (
    build_adapter_service,
    build_archive_summary_service,
    build_context_recorder,
    build_debug_recorder,
    build_emoji_service,
    build_file_server,
    build_image_parse_service,
    build_memory_services,
    build_message_queues,
    build_tts_service,
    build_vision_detect_service,
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
    build_self_heal_agent_wiring,
    build_self_heal_manager,
)
from neobot_app.bootstrap._usage import build_usage_components
from neobot_app.bootstrap._skills import build_plugin_runtime, build_skill_manager
from neobot_app.bootstrap._pipeline import (
    build_pipelines_and_app,
    build_plugin_host,
    build_problem_solver_agent_wiring,
    build_reply_orchestrator,
    register_config_reload_command,
    register_host_services,
)
from neobot_app.prompt.store import PromptStore, sync_default_prompts
from neobot_app.runtime.adapter_supervisor import AdapterSupervisor
from neobot_app.runtime.hot_reload_registry import HotReloadRegistry
from neobot_app.runtime.provider_reload import ProviderReloadConsumer
from neobot_app.skills.balance_guide import sync_balance_query_skill


_MAINTENANCE_SYSTEM_PROMPT = (
    "你是一个沙箱文件维护助手，负责检查和清理沙箱中的文件。\n\n"
    "## 核心规则\n"
    "1. **清理前必须先阅读 sandbox/文件存储.md 了解当前存储规范**\n"
    "2. 如文件存储.md 不存在，先检查 sandbox/ 目录结构，按默认规范创建文件存储.md\n"
    "3. 清理完成后必须调用 file_storage__update_storage_doc 更新索引\n\n"
    "## 默认存储规范（文件存储.md 不存在时参考）\n"
    "- tools/ — 可复用的工具脚本、程序\n"
    "- docs/ — 文档、参考资料、说明文件\n"
    "- assets/ — 静态资源（图片、字体、模板等）\n"
    "- temp/ — 临时文件，按 chat_flow_id 分子目录，可随时清理\n"
    "- gift/ — 礼物文件，由 gift skill 管理，勿手动编辑\n"
    "- 文件命名统一使用 snake_case，中文名保留原样\n"
    "- 根目录只保留 文件存储.md、TODO.md 和持久化目录\n\n"
    "## 维护流程\n"
    "1. 先调用 sandbox_maintenance__check_capacity 了解容量\n"
    "2. 调用 sandbox_maintenance__scan_temp_files 检查临时文件\n"
    "3. 调用 sandbox_maintenance__get_maintenance_status 查看状态\n"
    "4. 阅读 sandbox/文件存储.md 了解当前规范\n"
    "5. 根据需要清理过期临时文件、垃圾文件、错放文件\n"
    "6. 调用 sandbox_maintenance__trigger_maintenance 整理持久化文件\n"
    "7. 完成后调用 file_storage__update_storage_doc 更新索引\n\n"
    "## 注意\n"
    "- 只做文件清理和整理，不实现新工具，不处理 TODO\n"
    "- 输出简洁明了，完成每步后汇报结果"
)


def _build_provider_reload_consumer(
    *,
    logger_factory: Any,
    reply_orchestrator: Any,
    image_parse_service: Any,
    archive_summary_service: Any,
    initial_vision_provider: Any,
) -> ProviderReloadConsumer:
    """装配 provider 重建消费者：构建 + 各挂载点的换引用与清理。

    这里集中表达「provider 被谁持有」这一事实，避免该知识散落在多个模块里。
    """
    from neobot_app.bootstrap._providers import (
        build_main_provider,
        build_vision_provider,
        resolve_vision_model_name,
    )
    from neobot_app.runtime.provider_reload import (
        ProviderBundle,
        ProviderReloadConsumer,
    )

    provider_logger = logger_factory.get_logger("app.provider")

    def _build(config: Any) -> ProviderBundle:
        vision = build_vision_provider(
            logger=provider_logger,
            model_name=resolve_vision_model_name(config),
        )
        main, main_error = build_main_provider(
            config=config, logger=provider_logger, vision_provider=vision
        )
        return ProviderBundle(main=main, main_error=main_error, vision=vision)

    def _install_reply(bundle: ProviderBundle) -> Any:
        return reply_orchestrator.install_provider(bundle.main, bundle.main_error)

    def _install_images(bundle: ProviderBundle) -> Any:
        return image_parse_service.install_providers(
            vision_provider=bundle.vision,
            native_vision_provider=bundle.main,
        )

    def _install_archive(bundle: ProviderBundle) -> Any:
        return archive_summary_service.install_provider(bundle.main)

    async def _dispose_provider(previous: Any) -> None:
        closer = getattr(previous, "close", None)
        if callable(closer):
            result = closer()
            if inspect.isawaitable(result):
                await result

    def _dispose_images(previous: Any) -> None:
        """图片解析持有 (vision, native) 两个 provider：只关前者。

        native 与回复 provider 是同一个对象，由回复挂载点负责关闭，重复关闭
        会触发 provider 内部的重复释放。
        """
        vision = previous[0] if isinstance(previous, tuple) else previous
        return _dispose_provider(vision)

    return ProviderReloadConsumer(
        builder=_build,
        installers={
            "reply": (_install_reply, _dispose_provider),
            "image_parse": (_install_images, _dispose_images),
            "archive_summary": (_install_archive, lambda _previous: None),
        },
        logger=logger_factory.get_logger("app.provider_reload"),
    )


def _make_maintenance_coro(
    *,
    provider: Any,
    skill_manager: Any,
    sandbox_components: dict[str, Any],
    data_dir: Path,
    admin_id: str,
    logger: Any,
    prompt_store: Any = None,
):
    """创建沙箱维护 AI Agent 后台循环协程。不经过聊天流，直接调用 AI。"""
    from dataclasses import dataclass

    from neobot_chat.runtime.agent import Agent
    from neobot_chat.tools.toolset import ToolSpec, Toolset
    from neobot_chat.schema.types import ToolAccessRule

    maintenance_prompt = _MAINTENANCE_SYSTEM_PROMPT
    if prompt_store is not None:
        maintenance_prompt = prompt_store.get(
            "maintenance", "system_prompt", default=_MAINTENANCE_SYSTEM_PROMPT
        )

    @dataclass(frozen=True)
    class _SkillToolExecutor:
        _mgr: Any = skill_manager

        def definitions(self):
            return self._mgr.get_tools()

        async def execute(self, name: str, args: dict) -> str:
            return await self._mgr.execute(name, args)

        async def close(self) -> None:
            pass

    def _always_allow(_args: dict, _ctx: Any, _policy: Any) -> ToolAccessRule:
        return ToolAccessRule(action="allow")

    tool_defs = skill_manager.get_tools()
    specs = [ToolSpec(definition=d, access_resolver=_always_allow) for d in tool_defs]
    toolset = Toolset(executor=_SkillToolExecutor(), specs=specs)

    async def _loop() -> None:
        await asyncio.sleep(60)
        while True:
            agent: Agent | None = None
            try:
                logger.info("沙箱维护 Agent 开始执行")
                agent = Agent(
                    provider=provider,
                    toolset=toolset,
                    system_prompt=maintenance_prompt,
                    max_iterations=30,
                    command_timeout=120,
                )
                state = {
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                "请执行一次完整的沙箱维护清理。\n"
                                "按系统提示中的维护流程逐步操作，完成每步后汇报结果。"
                            ),
                        },
                    ],
                }
                result = await agent.invoke(state)
                msgs = result.get("messages", [])
                tool_count = sum(1 for m in msgs if m.get("role") == "tool")
                assist_msgs = [m for m in msgs if m.get("role") == "assistant" and m.get("content")]
                last_content = assist_msgs[-1].get("content", "")[:200] if assist_msgs else "(无文本输出)"
                logger.info(
                    f"沙箱维护完成: {tool_count} 次工具调用, "
                    f"最后输出: {last_content}"
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(f"沙箱维护 Agent 异常: {exc}")
            finally:
                if agent is not None:
                    try:
                        await agent.close()
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.warning(f"沙箱维护 Agent 关闭异常: {exc}")
            try:
                await asyncio.sleep(10800)  # 3 小时
            except asyncio.CancelledError:
                raise

    return _loop()


def create_application() -> NeoBotApplication:
    configure_loguru(DATA_DIR / "logs", runtime_events=True)
    logger_factory = LoguruLoggerFactory()
    config = build_config()

    sync_data_files(SRC_DATA_DIR, DATA_DIR)
    sync_default_prompts(DATA_DIR, logger=logger_factory.get_logger("app.prompt"))
    prompt_store = PromptStore(DATA_DIR, logger=logger_factory.get_logger("app.prompt"))

    # ── 睡眠服务(/sleep /awake 命令、睡眠 skill、事件管线共用) ──
    from neobot_app.runtime.sleep_service import SleepService

    sleep_service = SleepService(
        prompt_store=prompt_store,
        logger=logger_factory.get_logger("app.sleep"),
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

    debug_recorder = build_debug_recorder(
        config=config, logger=logger_factory.get_logger("app.debug")
    )

    # 聊天上下文记录器(debug 模式):每次模型调用的完整上下文,保留最近 100 轮
    context_recorder = build_context_recorder(
        config=config, logger=logger_factory.get_logger("app.context")
    )

    # 迁移前先留一份可回滚快照：alembic 迁移里存在不可逆操作
    # （如 0021 的去重 DELETE），失败时没有备份就只能人工恢复。
    db_path = DATA_DIR / "neobot.db"
    db_url = sqlite_url(db_path)
    db_backup_logger = logger_factory.get_logger("app.db_backup")
    backup_path = backup_sqlite_database(
        db_path, DATA_DIR / "db_backup", logger=db_backup_logger
    )
    if backup_path is not None:
        db_backup_logger.info(f"迁移前已备份数据库: {backup_path}")
    run_migrations(db_url)
    _engine, uow_factory = build_storage(db_url)

    usage = build_usage_components(_engine=_engine, logger_factory=logger_factory)

    group_queue, friend_queue = build_message_queues(config=config)

    adapter = build_adapter_service(
        config=config,
        logger=logger_factory.get_logger("adapter"),
        debug_recorder=debug_recorder,
    )

    # ── 配置热重载编排：组件自己声明关心哪些配置项并负责生效 ──
    # 装配顺序即生效顺序：适配器先恢复连接，其余组件再按新配置重建。
    hot_reload_registry = HotReloadRegistry(
        [AdapterSupervisor(adapter, logger=logger_factory.get_logger("app.adapter_reload"))],
        logger=logger_factory.get_logger("app.hot_reload"),
    )

    # ── 插件主机基础设施 ──
    plugin = build_plugin_host(logger_factory=logger_factory)

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

    command_service = build_command_service(
        config=config,
        adapter=adapter,
        logger_factory=logger_factory,
        markdown_image_converter=markdown_image_converter,
        file_server=file_server,
        sleep_service=sleep_service,
        config_reload_callback=_reload_config_from_command,
    )

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
        sandbox_lock=sandbox["sandbox_lock"],
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
        agent_registry=agent_registry,
        skills_registry=markdown_skill_registry,
        screenshots=browser["screenshots"],
        command_registry=command_service.registry if command_service is not None else None,
    )

    # ── 图片解析 / 记忆摘要 / TTS / 余额检查 ──
    image_parse_service = build_image_parse_service(
        vision_provider=vision_provider,
        native_vision_provider=provider,
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
        web_search_config={},
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
            web_search_config={},
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
        cache_calculator=cache_calculator,
        credential_manager=credential_manager,
        config_update_callback=_make_chat_config_update_callback(config),
        sleep_service=sleep_service,
    )
    notification_hub.set_orchestrator(reply_orchestrator)
    drawing_manager.set_orchestrator(reply_orchestrator)
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
    hot_reload_registry.register(_provider_reload)

    # ── 沙箱维护 Agent（独立 AI 循环，不经过聊天流）──
    admin_accounts = getattr(getattr(config, "chat", None), "admin_accounts", None) or []
    maintenance_coros = []
    # 睡眠剩余时间播报：睡眠期间每分钟打印剩余时间（仅日志，不回复）
    maintenance_coros.append(sleep_service.ticker())
    if (
        sandbox["sandbox_service"] is not None
        and admin_accounts
        and provider is not None
    ):
        maintenance_coros.append(
            _make_maintenance_coro(
                provider=provider,
                skill_manager=skill_manager,
                sandbox_components=sandbox,
                data_dir=DATA_DIR,
                admin_id=admin_accounts[0],
                logger=logger_factory.get_logger("app.sandbox_maintenance_agent"),
                prompt_store=prompt_store,
            )
        )

    # ── 宿主服务注册（官方/第三方插件通过 ctx.plugin_host.services 读取）──
    register_host_services(
        plugin["host_facade"],
        {
            "config": (config, "配置代理（运行时可重载）"),
            "adapter": (adapter, "OneBot 适配器"),
            "logger_factory": (logger_factory, "日志工厂"),
            "host_commands": (plugin["host_facade"].commands, "宿主命令注册表"),
            "group_queue": (group_queue, "群消息队列"),
            "friend_queue": (friend_queue, "好友消息队列"),
            "reply_orchestrator": (reply_orchestrator, "回复编排器"),
            "emoji_service": (emoji_service, "表情包服务"),
            "tts_service": (tts_service, "语音合成服务"),
            "file_server": (file_server, "文件服务器"),
            "image_pool": (image_pool, "图片暂存池"),
            "drawing_manager": (drawing_manager, "后台绘图管理器"),
            "creator_image_service": (creator_image_service, "生图服务"),
            "scheduled_task_manager": (scheduled_task_manager, "定时任务管理器"),
            "problem_solver_manager": (problem_solver_manager, "解题 Agent 管理器"),
            "notification_hub": (notification_hub, "后台通知中心"),
            "self_heal_manager": (self_heal_manager, "自修复管理器"),
            "browser_lifecycle_manager": (browser["browser_lifecycle_manager"], "浏览器生命周期管理器"),
            "vision_detect_service": (vision_detect_service, "本地视觉检测服务"),
            "vision_provider": (vision_provider, "视觉模型 Provider"),
            "provider": (provider, "主模型 Provider"),
            "command_service": (command_service, "命令服务"),
            "credential_manager": (credential_manager, "凭据管理器"),
            "sleep_service": (sleep_service, "睡眠服务"),
            "cache_calculator": (cache_calculator, "缓存命中计算器"),
            "skill_manager": (skill_manager, "Skill 管理器"),
            "markdown_skill_registry": (markdown_skill_registry, "Markdown Skill 注册表"),
            "agent_registry": (agent_registry, "Agent 注册表"),
            "usage_tracker": (usage["tracker"], "模型用量追踪器"),
            "usage_session_factory": (
                getattr(usage["tracker"], "_session_factory", None),
                "用量数据库会话工厂",
            ),
            "report_service": (usage["report_service"], "用量报告服务"),
            "archive_memory_service": (memory_svcs["archive_memory_service"], "档案记忆服务"),
            "profile_service": (memory_svcs["profile_service"], "用户画像服务"),
            "willing_service": (memory_svcs["willing_service"], "回复意愿服务"),
            "chat_stream": (memory_svcs["chat_stream"], "聊天流管理器"),
            "bot_detector": (memory_svcs["bot_detector"], "官方 Bot 检测器"),
            "sandbox_service": (sandbox["sandbox_service"], "沙箱服务"),
            "prompt_store": (prompt_store, "提示词存储"),
            "plugin_runtime": (plugin_runtime, "插件运行时"),
        },
    )

    # ── 管线 / 网关 / 应用 ──
    application = build_pipelines_and_app(
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
        browser_lifecycle_manager=browser["browser_lifecycle_manager"],
        browser_instance=browser["browser_instance"],
        screenshots=browser["screenshots"],
        creator_image_service=creator_image_service,
        drawing_manager=drawing_manager,
        background_coros=maintenance_coros,
        self_heal_manager=self_heal_manager,
        command_service=command_service,
        credential_manager=credential_manager,
        sleep_service=sleep_service,
    )

    # 面板等服务需要读取 application（重启入口）
    register_host_services(plugin["host_facade"], {"application": (application, "应用运行时")})

    # 命令 /reboot:绑定应用重启回调
    if command_service is not None:
        restart = getattr(application, "request_restart", None)
        if callable(restart):
            command_service.set_restart_callback(restart)

    return application
