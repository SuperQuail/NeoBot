"""执行器构造、生命周期与工具表编排（由 reply/tools.py 拆分）。"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

from neobot_app.reply.postprocess import ReplySplitPreview
from neobot_app.skills.activation import SkillToolActivation
from neobot_chat.schema.types import ToolDefinition
from neobot_contracts.ports.logging import Logger, NullLogger


class _CoreMixin:
    def __init__(
        self,
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
        credential_manager: Any = None,
        config: Any = None,
        config_update_callback: Any = None,
        native_vision_provider: Any = None,
        reviewer: Any = None,
        auto_review: bool = True,
        review_timeout_seconds: float = 30.0,
    ) -> None:
        self._native_vision_provider = native_vision_provider
        self._reviewer = reviewer
        self._auto_review = bool(auto_review)
        self._review_timeout = max(1.0, float(review_timeout_seconds or 30.0))
        self._send_reply = send_reply_handler
        self._willing = willing_service
        self._numbering = numbering
        self._send_emoji = send_emoji_handler
        self._emoji = emoji_service
        self._wait = wait_handler
        self._react_emoji = react_emoji_handler
        self._search_emoji = search_emoji_handler
        self._cancel = cancel_handler
        self._tts_service = tts_service
        self._speak_handler = speak_handler
        self._poke_user = poke_user_handler
        self._drawing_manager = drawing_manager
        self._scheduled_task_manager = scheduled_task_manager
        self._problem_solver_manager = problem_solver_manager
        self._notification_hub = notification_hub
        self._markdown_image_converter = markdown_image_converter
        self._send_long_reply = send_long_reply_handler
        self._skill_manager = skill_manager
        self._skills_registry = skills_registry
        self._allowed_tools = allowed_tools
        self._chat_context = chat_context
        self._conv_kind = conv_kind
        self._conv_id = conv_id
        self._current_user_id = current_user_id
        self._human_request = human_request
        self._agent_history = agent_history if agent_history is not None else []
        self._ai_reply_check = ai_reply_check
        self._ai_reply_check_lightweight = ai_reply_check_lightweight
        self._ai_check_pending = False
        self._split_previews: deque[ReplySplitPreview] = deque(maxlen=8)
        self._bot_name = bot_name
        self._long_reply_fallback_template = long_reply_fallback_template
        self._long_reply_max_length = long_reply_max_length
        self._long_reply_max_sentence_count = long_reply_max_sentence_count
        self._enable_ai_reply_regenerate = enable_ai_reply_regenerate
        self._wait_cooldown_seconds = wait_cooldown_seconds
        self._credential_manager = credential_manager
        self._config = config
        self._config_update_callback = config_update_callback
        self._last_wait_time = 0.0
        self._session_tasks: set[asyncio.Task] = set()
        self._session_task_info: dict[int, dict] = {}
        self._session_task_queue: dict[str, dict] = {}
        self._session_completed: dict[str, list[dict]] = {}
        #: 已发布完成通知的 task_id；保证任务级一次性通知（重试/清理不重复发）。
        self._session_notified: set[str] = set()
        self._closed = False
        self._close_task: asyncio.Task[None] | None = None
        self._logger = logger or NullLogger()
        self._skill_tokens: dict[str, Any] = {}
        # 本管线已按需加载的技能工具；管线结束时随执行器一起销毁。
        # 惰性构建：允许测试/插件在构造之后替换 skill_manager。
        self._activation_cache: SkillToolActivation | None = None
        self._activation_manager: Any = None

    @property
    def ai_check_pending(self) -> bool:
        """A send_reply review still awaits an explicit reply/cancel decision."""
        return self._ai_check_pending

    @property
    def closed(self) -> bool:
        """Whether close has begun and new session work is rejected."""
        return self._closed

    @property
    def _activation(self) -> SkillToolActivation | None:
        """当前 skill_manager 对应的按需加载状态；管理器被替换时自动重建。"""
        manager = self._skill_manager
        if manager is None:
            return None
        if self._activation_cache is None or self._activation_manager is not manager:
            self._activation_cache = SkillToolActivation(
                manager, authorize=self.is_tool_authorized
            )
            self._activation_manager = manager
        return self._activation_cache

    def preactivate_skills(self, names: Any) -> list[str]:
        """本轮预激活技能包（插件消息意图入口用）；返回实际已激活的技能名。

        在构建本轮工具表之前调用即可让这些技能的工具 schema 立刻生效；
        未知 / 已常驻 / 不可见的技能名会被 SkillToolActivation 自行忽略。
        """
        activation = self._activation
        if activation is None:
            return []
        requested = [str(item) for item in (names or ()) if str(item)]
        if not requested:
            return []
        activation.load({"skills": requested})
        return activation.activated_names()

    def definitions(self) -> list[ToolDefinition]:
        tools: list[ToolDefinition] = []
        self._define_skill_tools(tools)
        self._define_reply_tools(tools)
        self._define_long_reply_tool(tools)
        self._define_wait_tool(tools)
        self._define_willingness_tools(tools)
        self._define_emoji_tools(tools)
        self._define_speak_tool(tools)
        self._define_poke_tool(tools)
        self._define_background_tools(tools)
        self._merge_skill_tool_defs(tools)
        return self._filter_tool_defs(tools)

    async def drain_sessions(self) -> None:
        """等待在途会话工具任务自然结束，不取消它们。

        回复管线结束时调用。会话工具的契约是活过本轮回复（模型可继续聊天/做其他事，
        完成后由通知中心唤醒下一次回复），所以这里只等它们跑完，好让执行器连同完整
        对话历史一起释放；只有进程关停才用 close() 取消。
        """
        while self._session_tasks:
            tasks = tuple(self._session_tasks)
            await asyncio.gather(*tasks, return_exceptions=True)
            self._session_tasks.difference_update(tasks)

    async def close(self) -> None:
        """Idempotently reject new session work, cancel active work, and wait for it."""
        if self._close_task is None:
            self._closed = True
            self._session_task_queue.clear()
            self._close_task = asyncio.create_task(self._finish_close())
        await asyncio.shield(self._close_task)

    async def _finish_close(self) -> None:
        while self._session_tasks:
            tasks = tuple(self._session_tasks)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self._session_tasks.difference_update(tasks)
        self._session_task_queue.clear()
        self._session_task_info.clear()
        self._session_completed.clear()
        self._session_notified.clear()
