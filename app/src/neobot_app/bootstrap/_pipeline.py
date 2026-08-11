"""插件主机、回复编排器、事件管线、网关与应用组装"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from neobot_modloader import PluginHookBus, PluginHostFacade

from neobot_app.observability.logging import set_runtime_event_dispatcher
from neobot_app.observability.output import RuntimeOutput
from neobot_app.reply import ReplyOrchestrator
from neobot_app.runtime.application import NeoBotApplication

if TYPE_CHECKING:
    from neobot_contracts.ports.screenshot import ScreenshotPort
from neobot_app.runtime.event_pipeline import EventPipeline
from neobot_app.runtime.gateway import EventGateway
from neobot_app.runtime.inbound_pipeline import InboundPipeline
from neobot_app.runtime.lifecycle_handler import LifecycleHandler
from neobot_app.runtime.notice_handler import NoticeHandler
from neobot_app.runtime.onebot_request_handler import OneBotRequestHandler
from neobot_app.runtime.reply_block import ReplyBlockRegistry
from neobot_app.config.schemas.bot import BotConfig as BotConfigSchema
from neobot_app.core import DATA_DIR, SRC_DATA_DIR
from neobot_app.prompt.store import sync_default_prompts
from neobot_app.utils.data_sync import sync_data_files
from neobot_app.utils.logger import get_module_logger

from neobot_app.bootstrap._providers import build_optional_agent_provider

logger = get_module_logger("bootstrap.pipeline")


def build_plugin_host(
    *,
    logger_factory: Any,
) -> dict[str, Any]:
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

    return {
        "reply_block_registry": reply_block_registry,
        "runtime_output": runtime_output,
        "hook_bus": hook_bus,
        "host_facade": host_facade,
    }


def register_config_reload_command(
    *,
    host_facade: Any,
    config: Any,
) -> None:
    from neobot_app.bootstrap._config import _load_config
    from neobot_app.config.loader.manager import ConfigLoadError

    async def _reload_config(**kwargs: Any) -> dict[str, Any]:
        try:
            new_config = _load_config()
        except ConfigLoadError as exc:
            message = f"配置重载失败，保持旧配置生效：{exc}"
            logger.error(message)
            return {"status": "error", "message": message}
        config.reload(new_config)
        sync_data_files(SRC_DATA_DIR, DATA_DIR)
        sync_default_prompts(DATA_DIR, logger=logger)
        await host_facade.lifecycle.fire("config.changed")
        return {
            "status": "ok",
            "message": (
                "配置已重载（部分生效）。"
                "已生效：运行时按需读取的配置（提示词模板文件、概率系数、冷却时间、"
                "名单等，含模型注册表——新建的 Provider 请求将使用新值）。"
                "需重启 NeoBot 后生效：运行中的 LLM Provider（模型名/API Key/"
                "base_url 已固化在现有实例中）、关键词规则（KeywordReactionBuilder "
                "持有构建时快照）、TTS/表情包等构建期组件、缓存计算器参数"
                "（缓存保留时间/命中差价）。成本管线开关与阈值、提示词模板文件实时生效。"
            ),
        }

    host_facade.commands.register(
        "config.reload",
        "重新加载配置文件并通知所有已订阅 lifecycle 的插件",
        _reload_config,
    )


def build_problem_solver_agent_wiring(
    *,
    config: BotConfigSchema,
    problem_solver_manager: Any,
    provider: Any,
    provider_logger: Any,
    sandbox_service: Any,
    logger_factory: Any,
    vision_provider: Any = None,
    prompt_store: Any = None,
) -> None:
    if problem_solver_manager is None:
        return

    from neobot_app.agents.problem_solver import (
        ProblemSolverAgentConfig,
        build_problem_solver_agent,
    )

    problem_solver_config = ProblemSolverAgentConfig.from_schema(
        getattr(config.agent, "problem_solver", None)
    )
    ps_provider = build_optional_agent_provider(
        config=config,
        agent_name="problem_solver",
        fallback_provider=provider,
        logger=provider_logger,
    )
    build_problem_solver_agent(
        ps_provider,
        config=problem_solver_config,
        logger=logger_factory.get_logger("app.problem_solver"),
        manager=problem_solver_manager,
        sandbox_service=sandbox_service,
        vision_provider=vision_provider,
        prompt_store=prompt_store,
    )


def build_reply_orchestrator(
    *,
    adapter: Any,
    prompt_builder: Any,
    provider: Any,
    group_message_queue: Any,
    friend_message_queue: Any,
    config: Any,
    willing_service: Any,
    image_parse_service: Any,
    emoji_service: Any,
    tts_service: Any,
    provider_error_message: str | None,
    debug_recorder: Any,
    logger: Any,
    drawing_manager: Any,
    scheduled_task_manager: Any,
    problem_solver_manager: Any,
    notification_hub: Any,
    markdown_image_converter: Any,
    reply_block_registry: Any,
    skill_manager: Any,
    balance_checker: Any,
    hook_bus: Any,
    file_server: Any,
    skills_registry: Any = None,
    prompt_store: Any = None,
    cache_calculator: Any = None,
) -> ReplyOrchestrator:
    bind_send = getattr(emoji_service, "bind_send_dependencies", None)
    if callable(bind_send):
        bind_send(adapter, file_server)
    return ReplyOrchestrator(
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
        logger=logger,
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
        skills_registry=skills_registry,
        prompt_store=prompt_store,
        cache_calculator=cache_calculator,
    )


def build_pipelines_and_app(
    *,
    adapter: Any,
    memory: Any,
    group_message_queue: Any,
    friend_message_queue: Any,
    profile_service: Any,
    willing_service: Any,
    reply_orchestrator: ReplyOrchestrator,
    image_parse_service: Any,
    archive_summary_service: Any,
    config: Any,
    hook_bus: Any,
    reply_block_registry: Any,
    logger_factory: Any,
    chat_stream: Any,
    emoji_service: Any,
    tts_service: Any,
    file_server: Any,
    bot_detector: Any,
    scheduled_task_manager: Any,
    problem_solver_manager: Any,
    markdown_image_converter: Any,
    plugin_runtime: Any,
    report_service: Any,
    _engine: Any,
    vision_provider: Any,
    browser_lifecycle_manager: Any,
    browser_instance: Any = None,
    screenshots: "ScreenshotPort | None" = None,
    creator_image_service: Any = None,
    drawing_manager: Any = None,
    background_coros: list | None = None,
    self_heal_manager: Any = None,
    console_service: Any = None,
    command_service: Any = None,
    credential_manager: Any = None,
) -> NeoBotApplication:
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
        command_service=command_service,
        credential_manager=credential_manager,
    )

    notice_handler = NoticeHandler(legacy_pipeline=legacy_event_pipeline)
    request_handler = OneBotRequestHandler(
        logger=logger_factory.get_logger("app.onebot_request")
    )
    lifecycle_handler = LifecycleHandler(
        logger=logger_factory.get_logger("app.lifecycle")
    )

    event_gateway = EventGateway(
        event_source=adapter,
        hook_bus=hook_bus,
        legacy_pipeline=legacy_event_pipeline,
        notice_handler=notice_handler,
        request_handler=request_handler,
        lifecycle_handler=lifecycle_handler,
        logger=logger_factory.get_logger("app.event_gateway"),
    )

    return NeoBotApplication(
        adapter=adapter,
        chat_stream=chat_stream,
        event_ingress=event_gateway,
        message_pipeline=event_gateway,
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
        browser_lifecycle_manager=browser_lifecycle_manager,
        browser_instance=browser_instance,
        screenshots=screenshots,
        creator_image_service=creator_image_service,
        drawing_manager=drawing_manager,
        background_coros=background_coros,
        self_heal_manager=self_heal_manager,
        console_service=console_service,
    )
