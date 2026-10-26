"""装配热重载重建回调、模型消费者与后台维护协程。"""

from __future__ import annotations

from typing import Any
from neobot_app.bootstrap._pipeline import build_problem_solver_agent_wiring
from neobot_app.bootstrap._providers import build_vision_provider, resolve_vision_model_name
from neobot_app.bootstrap._runtime import build_creator_image_service, build_self_heal_agent_wiring
from neobot_app.bootstrap._services import build_tts_service
from neobot_app.core import DATA_DIR
from neobot_app.runtime.provider_reload import ModelConsumerReload
from .maintenance_agent import _make_maintenance_coro
from .maintenance_schedule import DEFAULT_MAINTENANCE_INTERVAL_SECONDS
from .maintenance_services import _web_search_config_dict
from .state import _BuildState


def _build_hot_reload_services(state: _BuildState) -> None:
    """装配热重载重建回调、模型消费者与后台维护协程。"""
    _engine = state._engine
    adapter = state.adapter
    bili_runtime = state.bili_runtime
    browser = state.browser
    command_service = state.command_service
    config = state.config
    drawing_manager = state.drawing_manager
    emoji_service = state.emoji_service
    file_server = state.file_server
    hot_reload_registry = state.hot_reload_registry
    image_pool = state.image_pool
    log_file_path = state.log_file_path
    logger_factory = state.logger_factory
    problem_solver_manager = state.problem_solver_manager
    prompt_store = state.prompt_store
    provider = state.provider
    provider_logger = state.provider_logger
    reply_orchestrator = state.reply_orchestrator
    sandbox = state.sandbox
    self_heal_manager = state.self_heal_manager
    skill_manager = state.skill_manager
    sleep_service = state.sleep_service
    source_roots = state.source_roots
    uow_factory = state.uow_factory
    vision_provider = state.vision_provider

    # ── 其余「持有模型产物」的组件：同样跟着 models/env 变更重建 ──
    # 每个组件是独立消费者：注册表逐个隔离失败（见 runtime/hot_reload_registry.apply），
    # 所以 TTS 建不起来不会拖垮 provider 的重建，报告里也能逐个看到成败。
    def _rebuild_tts(new_config: Any) -> None:
        """重建 TTS 服务并换装。

        启动期这个服务是「模型没注册就直接不建」的（build_tts_service 里那道闸门）：
        不重建的话，用户先在面板里补好平台 Key、再点重载也依然要重启进程 ——
        这正是 issue #74 里「覆盖不到」的那一半。
        `build_tts_service` 返回 None 表示当前配置下 TTS 仍不可用，这里如实换装成
        停用状态（而不是留着旧服务继续用旧凭据）。
        """
        service = build_tts_service(config=new_config, logger_factory=logger_factory)
        reply_orchestrator.install_tts_service(service)

    def _current_vision_provider(new_config: Any) -> Any:
        """重建时**现取**视觉 provider。

        装配闭包里的 `vision_provider` 是**启动期**那一个：直接把它再注入一遍，
        等于「重建了但装的还是旧视觉模型」—— 比不重建更隐蔽（issue #75）。
        这里按新配置重建；建不出来时回退到旧的，总比塞个 None 好。
        """
        return (
            build_vision_provider(
                logger=provider_logger, model_name=resolve_vision_model_name(new_config)
            )
            or vision_provider
        )

    def _rebuild_emoji(new_config: Any) -> None:
        """表情包的图片解析用的视觉 provider 也要换（issue #75）。

        `EmojiService._vision_provider` 在构造期固化，且真的用在解析表情包图片上 ——
        不换装的话，换了视觉模型之后表情包识别仍走旧模型。
        """
        emoji_service.install_vision_provider(_current_vision_provider(new_config))

    def _rebuild_skills(new_config: Any) -> None:
        """把新视觉 provider 推给所有声明了换装入口的技能（issue #75）。

        技能在启动期由 `build_all_skills` 建好并注册，内部持有视觉 provider 且**真的在用**
        （drawing_skill 看参考图、image_parse_skill 解析图片）。这里按
        「谁实现了 `install_vision_provider` 就推给谁」扫描，而不是写死技能名：
        以后新增会看图的技能，实现同一入口即可自动跟上。
        """
        provider = _current_vision_provider(new_config)
        # all_skills 是 property，不是方法（写成 all_skills() 会抛 TypeError）
        for skill in skill_manager.all_skills:
            installer = getattr(skill, "install_vision_provider", None)
            if callable(installer):
                installer(provider)

    def _rebuild_creator_image(new_config: Any) -> None:
        """重建生图服务并换装（生图服务在构造时固化默认模型与平台凭据）。

        仅覆盖「本来就启用」的情况：`agent.creator.enabled` 是装配期开关，
        从关闭改为启用属于结构性变更，仍按需重启（consumer 的 reason 里写明）。
        """
        creator_cfg = getattr(getattr(new_config, "agent", None), "creator", None)
        if creator_cfg is None or not getattr(creator_cfg, "enabled", False):
            return
        service = build_creator_image_service(
            uow_factory=uow_factory,
            adapter=adapter,
            config=new_config,
            emoji_service=emoji_service,
            vision_provider=_current_vision_provider(new_config),
            file_server=file_server,
            image_pool=image_pool,
            logger_factory=logger_factory,
        )
        drawing_manager.set_image_service(service)

    def _rebuild_problem_solver(new_config: Any) -> None:
        """重建解题 Agent 并换绑到 manager。

        provider 在装配时被 Agent 经闭包捕获，所以只能重跑装配来换。
        `provider=` 传的是**当前**主 provider（provider 消费者先注册、先执行），
        它同时也是解题模型不可用时的回退目标。
        """
        before = getattr(problem_solver_manager, "_agent", None)
        build_problem_solver_agent_wiring(
            config=new_config,
            problem_solver_manager=problem_solver_manager,
            provider=reply_orchestrator.provider,
            provider_logger=provider_logger,
            sandbox_service=sandbox["sandbox_service"],
            logger_factory=logger_factory,
            vision_provider=_current_vision_provider(new_config),
            prompt_store=prompt_store,
        )
        # 装配函数在 provider 不可用时直接 return、不动 manager：那样旧 Agent 会继续
        # 用旧凭据跑，比「功能停用」更危险。这里显式摘掉。
        if getattr(problem_solver_manager, "_agent", None) is before and before is not None:
            problem_solver_manager.set_agent(None)

    def _rebuild_self_heal(new_config: Any) -> None:
        """重建自修复 Agent 并换绑（同样：provider 被 Agent 捕获，只能重跑装配）。"""
        agent = build_self_heal_agent_wiring(
            config=new_config,
            manager=self_heal_manager,
            provider=reply_orchestrator.provider,
            provider_logger=provider_logger,
            sandbox_service=sandbox["sandbox_service"],
            logger_factory=logger_factory,
            data_dir=DATA_DIR,
            source_roots=source_roots,
            log_file=log_file_path,
            vision_provider=_current_vision_provider(new_config),
            web_search_config=_web_search_config_dict(new_config),
            prompt_store=prompt_store,
        )
        if agent is None:
            # provider 不可用 -> 装配跳过；显式停用，不留旧 Agent。
            self_heal_manager.set_agent(None)

    for _consumer in (
        ModelConsumerReload(
            name="tts",
            rebuild=_rebuild_tts,
            reason="TTS 服务持有模型（音色与平台密钥），凭据变更后重建",
        ),
        ModelConsumerReload(
            name="creator_image",
            rebuild=_rebuild_creator_image,
            reason="生图服务持有默认模型与平台凭据，变更后重建（启用开关变更仍需重启）",
        ),
        ModelConsumerReload(
            name="emoji",
            rebuild=_rebuild_emoji,
            reason="表情包图片解析持有视觉 provider（真的在用），模型变更后换装",
        ),
        ModelConsumerReload(
            name="skills",
            rebuild=_rebuild_skills,
            reason="技能（绘图看参考图 / 图片解析）持有视觉 provider，模型变更后推送新实例",
        ),
        ModelConsumerReload(
            name="problem_solver",
            rebuild=_rebuild_problem_solver,
            reason="解题 Agent 经闭包捕获 provider，模型/凭据变更后重跑装配",
        ),
        ModelConsumerReload(
            name="self_heal",
            rebuild=_rebuild_self_heal,
            reason="自修复 Agent 经闭包捕获 provider，模型/凭据变更后重跑装配",
        ),
    ):
        hot_reload_registry.unregister(_consumer.name)
        hot_reload_registry.register(_consumer)

    # ── 沙箱维护 Agent（独立 AI 循环，不经过聊天流）──
    admin_accounts = getattr(getattr(config, "chat", None), "admin_accounts", None) or []
    maintenance_coros = []
    if bili_runtime is not None:
        maintenance_coros.append(bili_runtime.run())
    # 睡眠剩余时间播报：睡眠期间每分钟打印剩余时间（仅日志，不回复）
    maintenance_coros.append(sleep_service.ticker())
    # /help 预渲染缓存（spec(5) §4.2 / R9）：后台异步、不阻塞启动；
    # 软重启时运行时工厂会重新执行本函数，因此同样会再跑一次。
    # commands 传可调用对象：协程真正运行时才读命令表，插件命令此时已注册。
    if command_service is not None:
        from neobot_app.runtime import help_cache

        maintenance_coros.append(
            help_cache.make_prerender_coro(
                commands=command_service.registry.commands,
                screenshots=browser["screenshots"],
                log=logger_factory.get_logger("app.commands"),
            )
        )
    if (
        sandbox["sandbox_service"] is not None
        and admin_accounts
        and provider is not None
    ):
        _sandbox_cfg = getattr(config.agent, "sandbox", None)
        _maintenance_cfg = getattr(_sandbox_cfg, "maintenance", None)
        maintenance_interval = int(
            getattr(_maintenance_cfg, "interval_seconds", None)
            or DEFAULT_MAINTENANCE_INTERVAL_SECONDS
        )
        maintenance_coros.append(
            _make_maintenance_coro(
                provider=provider,
                skill_manager=skill_manager,
                sandbox_components=sandbox,
                data_dir=DATA_DIR,
                admin_id=admin_accounts[0],
                logger=logger_factory.get_logger("app.sandbox_maintenance_agent"),
                prompt_store=prompt_store,
                engine=_engine,
                interval_seconds=maintenance_interval,
            )
        )

    state.maintenance_coros = maintenance_coros
