"""暴露给主回复代理的回复相关工具。"""

from __future__ import annotations

from typing import Any

from neobot_chat.schema.protocol import ToolExecutor
from neobot_chat.schema.types import ToolAccessPolicy
from neobot_chat.tools.toolset import ToolSpec, Toolset
from neobot_contracts.ports.logging import Logger

from neobot_app.reply.tool_parts.common import BASIC_REPLY_TOOLS, _default_resolver
from neobot_app.reply.tool_parts.core import _CoreMixin
from neobot_app.reply.tool_parts.dispatch import _DispatchMixin
from neobot_app.reply.tool_parts.session_tools import _SessionToolsMixin
from neobot_app.reply.tool_parts.session_runtime import _SessionRuntimeMixin
from neobot_app.reply.tool_parts.reply_tools import _ReplyToolsMixin
from neobot_app.reply.tool_parts.long_reply_tools import _LongReplyToolsMixin
from neobot_app.reply.tool_parts.misc_tools import _MiscToolsMixin
from neobot_app.reply.tool_parts.willingness_tools import _WillingnessToolsMixin
from neobot_app.reply.tool_parts.emoji_tools import _EmojiToolsMixin
from neobot_app.reply.tool_parts.background_tools import _BackgroundToolsMixin
from neobot_app.reply.tool_parts.skill_tools import _SkillToolsMixin

__all__ = ["BASIC_REPLY_TOOLS", "ReplyToolExecutor", "build_reply_toolset"]


class ReplyToolExecutor(
    _CoreMixin,
    _DispatchMixin,
    _SessionToolsMixin,
    _SessionRuntimeMixin,
    _ReplyToolsMixin,
    _LongReplyToolsMixin,
    _MiscToolsMixin,
    _WillingnessToolsMixin,
    _EmojiToolsMixin,
    _BackgroundToolsMixin,
    _SkillToolsMixin,
    ToolExecutor,
):
    """回复模式工具的执行器。"""

    async def __aenter__(self) -> ReplyToolExecutor:
        if self._closed:
            raise RuntimeError("ReplyToolExecutor is closed")
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.close()


def build_reply_toolset(
    *,
    send_reply_handler: Any = None,
    willing_service: Any = None,
    numbering: Any = None,
    send_emoji_handler: Any = None,
    emoji_service: Any = None,
    wait_handler: Any = None,
    react_emoji_handler: Any = None,
    search_emoji_handler: Any = None,
    cancel_handler: Any = None,
    tts_service: Any = None,
    speak_handler: Any = None,
    poke_user_handler: Any = None,
    drawing_manager: Any = None,
    scheduled_task_manager: Any = None,
    problem_solver_manager: Any = None,
    notification_hub: Any = None,
    markdown_image_converter: Any = None,
    send_long_reply_handler: Any = None,
    skill_manager: Any = None,
    skills_registry: Any = None,
    allowed_tools: set[str] | None = None,
    chat_context: str | None = None,
    conv_kind: str = "",
    conv_id: str = "",
    current_user_id: int | None = None,
    human_request: bool = False,
    agent_history: list[dict] | None = None,
    wait_cooldown_seconds: int = 60,
    ai_reply_check: bool = False,
    ai_reply_check_lightweight: bool = True,
    bot_name: str = "Bot",
    long_reply_fallback_template: str = "{bot_name}懒得和你说道理，你不配听",
    long_reply_max_length: int = 300,
    long_reply_max_sentence_count: int = 12,
    enable_ai_reply_regenerate: bool = True,
    logger: Logger | None = None,
    policy: ToolAccessPolicy | None = None,
    credential_manager: Any = None,
    config: Any = None,
    config_update_callback: Any = None,
    native_vision_provider: Any = None,
    reviewer: Any = None,
    auto_review: bool = True,
    review_timeout_seconds: float = 30.0,
) -> Toolset:
    executor = ReplyToolExecutor(
        send_reply_handler=send_reply_handler,
        willing_service=willing_service,
        numbering=numbering,
        send_emoji_handler=send_emoji_handler,
        emoji_service=emoji_service,
        wait_handler=wait_handler,
        react_emoji_handler=react_emoji_handler,
        search_emoji_handler=search_emoji_handler,
        cancel_handler=cancel_handler,
        tts_service=tts_service,
        speak_handler=speak_handler,
        poke_user_handler=poke_user_handler,
        drawing_manager=drawing_manager,
        scheduled_task_manager=scheduled_task_manager,
        problem_solver_manager=problem_solver_manager,
        notification_hub=notification_hub,
        markdown_image_converter=markdown_image_converter,
        send_long_reply_handler=send_long_reply_handler,
        skill_manager=skill_manager,
        skills_registry=skills_registry,
        allowed_tools=allowed_tools,
        chat_context=chat_context,
        conv_kind=conv_kind,
        conv_id=conv_id,
        current_user_id=current_user_id,
        human_request=human_request,
        agent_history=agent_history,
        wait_cooldown_seconds=wait_cooldown_seconds,
        ai_reply_check=ai_reply_check,
        ai_reply_check_lightweight=ai_reply_check_lightweight,
        bot_name=bot_name,
        long_reply_fallback_template=long_reply_fallback_template,
        long_reply_max_length=long_reply_max_length,
        long_reply_max_sentence_count=long_reply_max_sentence_count,
        enable_ai_reply_regenerate=enable_ai_reply_regenerate,
        logger=logger,
        credential_manager=credential_manager,
        config=config,
        config_update_callback=config_update_callback,
        native_vision_provider=native_vision_provider,
        reviewer=reviewer,
        auto_review=auto_review,
        review_timeout_seconds=review_timeout_seconds,
    )
    definitions = executor.definitions()
    specs = [
        ToolSpec(definition=definition, access_resolver=_default_resolver)
        for definition in definitions
    ]
    return Toolset(executor=executor, specs=specs, policy=policy or ToolAccessPolicy())
