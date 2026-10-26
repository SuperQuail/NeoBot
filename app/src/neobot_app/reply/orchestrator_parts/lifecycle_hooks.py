"""钩子注册、服务装配与管线状态查询。"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from neobot_app.reply.event import ReplyEvent
from ._runtime import asyncio

class LifecycleHooksMixin:
    def register_pre_reply_hook(
        self, hook: Callable[[ReplyEvent], Awaitable[str | None]]
    ) -> None:
        """注册预回复钩子。返回非 None 字符串时将短路跳过 AI 生成。"""
        self._pre_reply_hooks.append(hook)
    def register_post_reply_hook(
        self, hook: Callable[[ReplyEvent, str | None], Awaitable[str | None]]
    ) -> None:
        """注册后回复钩子。返回非 None 字符串时将替换回复文本。"""
        self._post_reply_hooks.append(hook)
    async def _apply_pre_reply_hooks(self, event: ReplyEvent) -> str | None:
        for hook in self._pre_reply_hooks:
            try:
                result = await hook(event)
                if result is not None:
                    return result
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # 钩子是插件扩展点：失败必须留痕，否则「钩子没生效」与
                # 「钩子抛异常被吞」从外部完全无法区分。
                self._logger.warning(
                    "pre_reply hook 执行失败，已跳过",
                    event_id=event.event_id,
                    hook=_hook_name(hook),
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
        return None
    async def _apply_post_reply_hooks(
        self, event: ReplyEvent, text: str | None
    ) -> str | None:
        for hook in self._post_reply_hooks:
            try:
                modified = await hook(event, text)
                if modified is not None:
                    text = modified
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._logger.warning(
                    "post_reply hook 执行失败，已跳过",
                    event_id=event.event_id,
                    hook=_hook_name(hook),
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
        return text
    async def handle_agent_tool_input(self, message: Any, *, kind: str, queue_key: str) -> str | None:
        """Called only by real-message ingress, never by a model-facing tool."""
        from neobot_app.agent_tools.invocation import CURRENT_HUMAN_MESSAGE
        from neobot_app.agent_tools.contracts import ToolContext
        from neobot_app.skills.agent_tools_skill import AgentToolsSkill
        if not CURRENT_HUMAN_MESSAGE.get() or self._skill_manager is None:
            return None
        shared = self._skill_manager.get("agent_tools")
        if not isinstance(shared, AgentToolsSkill):
            return None
        user_id, message_id = getattr(message, "user_id", None), getattr(message, "message_id", None)
        if user_id is None or message_id is None or not str(queue_key).isdigit():
            return None
        flow = f"{kind}:{queue_key}"
        context = ToolContext(owner=f"{flow}:main", chat_flow_id=flow, user_id=int(user_id), human_request=True)
        from neobot_app.message.process import event_message__to_text
        text = await event_message__to_text(message)
        return await shared.runtime.accept_human_input(context, text, str(message_id))
    def is_pipeline_active(self, kind: str, conversation_id: str) -> bool:
        pipeline_key = f"{kind}:{conversation_id}"
        task = self._active_pipelines.get(pipeline_key)
        if task is not None and task.done():
            self._active_pipelines.pop(pipeline_key, None)
            return False
        return task is not None
    def is_pipeline_key_active(self, pipeline_key: str) -> bool:
        task = self._active_pipelines.get(pipeline_key)
        if task is not None and task.done():
            self._active_pipelines.pop(pipeline_key, None)
            return False
        return task is not None
    def install_tts_service(self, service: Any) -> Any:
        """换用新的 TTS 服务，返回被替换下来的旧服务。

        与 `install_provider` 同一模式：TTS 服务在构造时就把模型条目
        （api_key / base_url / 音色）固化了，改配置后必须重建才能生效。
        同样只换引用，不负责关闭旧服务。

        为什么需要它：TTS 此前在启动期一次性装配，模型没注册就直接不建服务
        —— 于是「先在面板里补好平台 Key，再重载」这条路走不通，必须重启进程。
        """
        previous = self._tts_service
        self._tts_service = service
        self._logger.info(
            "TTS 服务已更新",
            model=getattr(getattr(service, "_model", None), "model_name", "") or "",
            enabled=service is not None,
        )
        return previous
    def install_provider(self, provider: Any, error_message: str | None = None) -> Any:
        """换用新的回复 provider，返回被替换下来的旧 provider。

        供配置热重载使用：模型名 / API Key 变化后必须重建 provider，而 provider
        是编排器在构造时固化的。这里只做「换引用」，**不负责关闭旧 provider**
        —— 由调用方在确认替换成功后统一清理，避免替换失败时旧 provider 已被关闭
        导致服务不可用。
        """
        previous = self._provider
        self._provider = provider
        self._provider_error_message = error_message
        self._logger.info(
            "回复 provider 已更新",
            model=getattr(provider, "model", "") or "",
        )
        return previous
    @property
    def provider(self) -> Any:
        """当前回复 provider（只读，便于状态展示与测试断言）。"""
        return self._provider

def _hook_name(hook: object) -> str:
    """钩子的可读标识（用于日志）。"""
    return str(
        getattr(hook, "__qualname__", None)
        or getattr(hook, "__name__", None)
        or type(hook).__name__
    )
