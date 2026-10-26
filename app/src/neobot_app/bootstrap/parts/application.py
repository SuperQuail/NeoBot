"""组合根主入口：分阶段装配并返回 NeoBotApplication。"""

from __future__ import annotations

from neobot_app.bootstrap._pipeline import build_pipelines_and_app, register_host_services
from neobot_app.bootstrap._skills import build_plugin_runtime
from neobot_app.runtime.application import NeoBotApplication
from neobot_app.runtime.process_restart import ProcessRestartSignal
from neobot_app.runtime.process_stop import ProcessStopSignal

from .agent_services import _build_agent_services
from .bilibili_services import _build_bilibili_services
from .core_reuse import _reuse_enabled, _reuse_or
from .core_services import _build_core_services
from .hot_reload_services import _build_hot_reload_services
from .pipeline_services import _build_pipeline_services
from .prompt_analysis import _build_prompt_analysis
from .state import _BuildState


def create_application(*, owns_plugins: bool = True) -> NeoBotApplication:
    state = _BuildState()
    _build_core_services(state)
    _build_agent_services(state)
    _build_bilibili_services(state)

    adapter = state.adapter
    agent_registry = state.agent_registry
    browser = state.browser
    command_service = state.command_service
    config = state.config
    file_server = state.file_server
    logger_factory = state.logger_factory
    markdown_skill_registry = state.markdown_skill_registry
    plugin = state.plugin

    plugin_runtime = _reuse_or(
        "plugin_runtime",
        lambda: build_plugin_runtime(
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
    ),
    )

    # 插件运行时是核心对象：软重启会重建 agent/skill 注册表与截图端口，必须显式
    # 绑定新代际，否则插件注册会落在上一代对象上（插件 Agent/Skill 静默消失）。
    plugin_runtime.bind_generation(
        agent_registry=agent_registry,
        skills_registry=markdown_skill_registry,
        screenshots=browser["screenshots"],
    )

    _build_pipeline_services(state)
    _build_hot_reload_services(state)
    _build_prompt_analysis(state)

    # 核心对象清单（软重启复用，实际构建见 parts/core_services.py / core_reuse.py）：
    # "logger_factory" / "config" / "prompt_store" / "sleep_service" / "standby_service" /
    # "avatar_store" / "debug_recorder" / "storage" / "usage" / "adapter" /
    # "hot_reload_registry" / "plugin" / "file_server" / "command_service" /
    # "plugin_runtime"。

    _engine = state._engine
    archive_summary_service = state.archive_summary_service
    asr_service = state.asr_service
    avatar_store = state.avatar_store
    bili_runtime = state.bili_runtime
    cache_calculator = state.cache_calculator
    chat_flow_registry = state.chat_flow_registry
    context_recorder = state.context_recorder
    creator_image_service = state.creator_image_service
    credential_manager = state.credential_manager
    drawing_manager = state.drawing_manager
    emoji_service = state.emoji_service
    friend_queue = state.friend_queue
    group_queue = state.group_queue
    image_parse_service = state.image_parse_service
    image_pool = state.image_pool
    maintenance_coros = state.maintenance_coros
    markdown_image_converter = state.markdown_image_converter
    memory_svcs = state.memory_svcs
    notification_hub = state.notification_hub
    problem_solver_manager = state.problem_solver_manager
    prompt_analyzer = state.prompt_analyzer
    prompt_store = state.prompt_store
    provider = state.provider
    reply_orchestrator = state.reply_orchestrator
    sandbox = state.sandbox
    scheduled_task_manager = state.scheduled_task_manager
    self_heal_manager = state.self_heal_manager
    skill_manager = state.skill_manager
    sleep_service = state.sleep_service
    standby_service = state.standby_service
    tts_service = state.tts_service
    usage = state.usage
    vision_detect_service = state.vision_detect_service
    vision_provider = state.vision_provider

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
            "bilibili_service": (
                bili_runtime.service if bili_runtime is not None else None,
                "B站服务（登录/动态/轮询）",
            ),
            "asr_service": (asr_service, "外部 ASR 服务（硅基流动）"),
            "command_service": (command_service, "命令服务"),
            "credential_manager": (credential_manager, "凭据管理器"),
            "sleep_service": (sleep_service, "睡眠服务"),
            "avatar_store": (
                avatar_store,
                "用户头像本地存储与惰性刷新（spec(5) §4.9）",
            ),
            "standby_service": (standby_service, "待机服务（只保留核心服务 / 软重启运行）"),
            "prompt_analyzer": (prompt_analyzer, "提示词分析（面板分析页）"),
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
            "billing_service": (usage.get("billing"), "消耗计费脚本服务（spec(4) Part A）"),
            "archive_memory_service": (memory_svcs["archive_memory_service"], "档案记忆服务"),
            "archive_summary_service": (
                archive_summary_service,
                "档案自动总结服务（实现 agent_prompt_parts，供分析页自动收集）",
            ),
            "profile_service": (memory_svcs["profile_service"], "用户画像服务"),
            "willing_service": (memory_svcs["willing_service"], "回复意愿服务"),
            "chat_stream": (memory_svcs["chat_stream"], "聊天流管理器"),
            "bot_detector": (memory_svcs["bot_detector"], "官方 Bot 检测器"),
            "sandbox_service": (sandbox["sandbox_service"], "沙箱服务"),
            "prompt_store": (prompt_store, "提示词存储"),
            "chat_flow_registry": (chat_flow_registry, "聊天流快照登记处（面板只读）"),
            "context_recorder": (
                context_recorder,
                "完整提示词历史记录器（面板按需读取；纯内存 + 逐份 diff，保留最近 N 份）",
            ),
            "plugin_runtime": (plugin_runtime, "插件运行时"),
        },
    )

    # 自动收集所有实现 agent_prompt_parts() 的宿主服务：新增 Agent 只要实现规范并注册服务，
    # 分析页就会出现，**不需要**再改这里的来源列表。
    discovered = prompt_analyzer.catalog.discover(plugin["host_facade"].services)
    logger_factory.get_logger("app.analysis").info(
        f"提示词分析自动收集到 {discovered} 个 Agent"
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
        standby_service=standby_service,
        avatar_store=avatar_store,
        owns_plugins=owns_plugins,
    )

    # 面板等服务需要读取 application（重启入口）
    register_host_services(plugin["host_facade"], {"application": (application, "应用运行时")})

    # Only core-reuse mode has a process-level watcher. Standalone applications
    # keep the legacy application.request_restart path rather than a dead flag.
    if _reuse_enabled():
        restart_signal = _reuse_or("process_restart", ProcessRestartSignal)
        # 优雅停机信号与重启信号并列：面板的退出端点也走核心信号，
        # 这样才能在待机态 / 切换中收到停机请求（那一代 Application 可能已经不在）
        stop_signal = _reuse_or("process_stop", ProcessStopSignal)
        register_host_services(
            plugin["host_facade"],
            {
                "process_restart": (restart_signal, "进程重启信号（核心持有）"),
                "process_stop": (stop_signal, "优雅停机信号（核心持有）"),
            },
        )

    # 命令 /reboot:绑定应用重启回调
    if command_service is not None:
        restart = getattr(application, "request_restart", None)
        if callable(restart):
            command_service.set_restart_callback(restart)

    return application
