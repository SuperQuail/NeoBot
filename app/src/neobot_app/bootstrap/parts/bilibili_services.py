"""装配可选外部集成：B站运行时与 ASR（失败只告警，不影响启动）。"""

from __future__ import annotations

from typing import Any
from .state import _BuildState


def _build_bilibili_services(state: _BuildState) -> None:
    """装配可选外部集成：B站运行时与 ASR（失败只告警，不影响启动）。"""
    adapter = state.adapter
    chat_flow_registry = state.chat_flow_registry
    command_service = state.command_service
    config = state.config
    hot_reload_registry = state.hot_reload_registry
    logger_factory = state.logger_factory
    memory_svcs = state.memory_svcs
    notification_hub = state.notification_hub
    prompt_store = state.prompt_store
    provider = state.provider
    skill_manager = state.skill_manager
    uow_factory = state.uow_factory
    vision_provider = state.vision_provider

    # ── B站 + 外部 ASR（默认开启；B站无登录态时服务休眠，等同关闭）──
    asr_service = None
    bili_runtime = None
    try:
        from neobot_app.audio.asr import build_asr_service
        from neobot_app.bilibili.runtime import (
            BilibiliRuntime,
            BilibiliRuntimeConfigConsumer,
            build_bilibili_skills,
        )

        asr_service = build_asr_service(
            config, logger=logger_factory.get_logger("app.asr")
        )
        async def _notify_live_event(event: Any) -> None:
            """把直播事件按配置推送到 QQ；失败不打断监听。"""
            try:
                section = getattr(config, "bilibili", None)
                targets = list(getattr(section, "live_event_notify_targets", None) or [])
                kinds = set(
                    getattr(section, "live_event_notify_kinds", None)
                    or ["gift", "super_chat", "guard"]
                )
                kind = str(getattr(event, "kind", "") or "")
                if not targets or kind not in kinds or adapter is None:
                    return
                name = str(getattr(event, "name", "") or "观众")
                value = int(getattr(event, "value", 0) or 0)
                text = str(getattr(event, "text", "") or "")
                if kind == "gift":
                    message = f"🎁 {name} 送出 {value} 瓜子"
                elif kind == "super_chat":
                    message = f"💬 SC ¥{value} {name}：{text}"
                elif kind == "guard":
                    message = f"🚢 {name} 上舰（{value}）"
                elif kind == "enter":
                    message = f"👋 {name} 进入直播间"
                else:
                    message = f"[{kind}] {name} {text}".strip()
                from neobot_contracts.models import ConversationRef

                for target in targets:
                    raw = str(target or "").strip()
                    if ":" not in raw:
                        continue
                    conv_kind, conv_id = raw.split(":", 1)
                    if conv_kind not in {"group", "private"} or not conv_id:
                        continue
                    try:
                        await adapter.send(
                            ConversationRef(kind=conv_kind, id=conv_id),
                            [{"type": "text", "data": {"text": message}}],
                            wait_response=False,
                        )
                    except Exception:
                        continue
            except Exception:
                return

        bili_runtime = BilibiliRuntime(
            config=config,
            provider=provider,
            archive_service=memory_svcs["archive_memory_service"],
            uow_factory=uow_factory,
            command_service=command_service,
            asr_service=asr_service,
            vision_provider=vision_provider,
            on_live_event=_notify_live_event,
            willing_service=memory_svcs["willing_service"],
            flow_registry=chat_flow_registry,
            notification_hub=notification_hub,
            logger=logger_factory.get_logger("app.bilibili"),
            bot_name=config.bot.nick_name,
            bot_data=config.bot.bot_data,
            prompt_store=prompt_store,
        )
        if command_service is not None:
            bili_runtime.register_commands(command_service)
        hot_reload_registry.unregister("bilibili")
        hot_reload_registry.register(BilibiliRuntimeConfigConsumer(bili_runtime))
        for _skill in build_bilibili_skills(
            archive_service=memory_svcs["archive_memory_service"],
            uow_factory=uow_factory,
            runtime=bili_runtime,
        ):
            try:
                skill_manager.register(_skill)
            except Exception:
                logger_factory.get_logger("app.bilibili").exception(
                    f"B站技能注册失败：{getattr(_skill, 'name', _skill)}"
                )
        _agent_tools_owner = skill_manager.get("agent_tools")
        if _agent_tools_owner is not None and hasattr(_agent_tools_owner, "runtime"):
            _agent_tools_owner.runtime.set_bilibili_tasks(bili_runtime.video_task_manager)

        _cross_chat = skill_manager.get("cross_chat")
        if _cross_chat is not None and callable(
            getattr(_cross_chat, "set_bilibili_channel", None)
        ):
            _cross_chat.set_bilibili_channel(bili_runtime.channel)
    except Exception:
        logger_factory.get_logger("app.bilibili").exception(
            "B站/ASR 装配失败，相关功能降级为关闭"
        )

    state.asr_service = asr_service
    state.bili_runtime = bili_runtime
