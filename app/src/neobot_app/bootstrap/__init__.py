"""Composition root — 装配并返回 NeoBotApplication。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

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


def _make_maintenance_coro(
    *,
    provider: Any,
    skill_manager: Any,
    sandbox_components: dict[str, Any],
    data_dir: Path,
    admin_id: str,
    logger: Any,
):
    """创建沙箱维护 AI Agent 后台循环协程。不经过聊天流，直接调用 AI。"""
    from dataclasses import dataclass

    from neobot_chat.runtime.agent import Agent
    from neobot_chat.tools.toolset import ToolSpec, Toolset
    from neobot_chat.schema.types import ToolAccessRule

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
            try:
                logger.info("沙箱维护 Agent 开始执行")
                agent = Agent(
                    provider=provider,
                    toolset=toolset,
                    system_prompt=_MAINTENANCE_SYSTEM_PROMPT,
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
        vision_provider=vision_provider,
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
        temp_cleaner=sandbox["temp_cleaner"],
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

    # ── 沙箱维护 Agent（独立 AI 循环，不经过聊天流）──
    admin_accounts = getattr(getattr(config, "chat", None), "admin_accounts", None) or []
    maintenance_coros = []
    if sandbox["sandbox_service"] is not None and admin_accounts:
        maintenance_coros.append(
            _make_maintenance_coro(
                provider=provider,
                skill_manager=skill_manager,
                sandbox_components=sandbox,
                data_dir=DATA_DIR,
                admin_id=admin_accounts[0],
                logger=logger_factory.get_logger("app.sandbox_maintenance_agent"),
            )
        )

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
        browser_lifecycle_manager=browser["browser_lifecycle_manager"],
        background_coros=maintenance_coros,
    )
