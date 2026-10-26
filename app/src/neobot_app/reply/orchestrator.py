"""ReplyOrchestrator — 管理回复事件的创建与异步执行，支持 common/agent 两种模式"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TYPE_CHECKING
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_app.reply.debug import DebugHelper
from neobot_app.reply.event import ReplyEvent
from neobot_app.reply.sender import ReplySender

if TYPE_CHECKING:
    from neobot_adapter import OneBotAdapter
    from neobot_app.cache import CacheCalculator
    from neobot_app.config.schemas.bot import BotConfig
    from neobot_app.core.file_server import FileServer
    from neobot_app.emoji.service import EmojiService
    from neobot_app.image import ImageParseService
    from neobot_app.message.queue import MessageQueue
    from neobot_app.observability.debug import DebugRecorder
    from neobot_app.prompt.builder import PromptBuilder
    from neobot_app.prompt.store import PromptStore
    from neobot_app.willing.service import WillingService
    from neobot_chat.providers.base import Provider

import asyncio as asyncio
from neobot_app.time_context import monotonic_seconds as monotonic_seconds

from neobot_app.reply.orchestrator_parts.lifecycle_hooks import LifecycleHooksMixin
from neobot_app.reply.orchestrator_parts.lifecycle_start import LifecycleStartMixin
from neobot_app.reply.orchestrator_parts.lifecycle_shutdown import LifecycleShutdownMixin
from neobot_app.reply.orchestrator_parts.modes import ModesMixin
from neobot_app.reply.orchestrator_parts.agent_loop import AgentLoopMixin
from neobot_app.reply.orchestrator_parts.agent_prompt import AgentPromptMixin
from neobot_app.reply.orchestrator_parts.agent_toolset import AgentToolsetMixin
from neobot_app.reply.orchestrator_parts.agent_handlers import AgentHandlersMixin
from neobot_app.reply.orchestrator_parts.agent_model_call import AgentModelCallMixin
from neobot_app.reply.orchestrator_parts.agent_tool_exec import AgentToolExecMixin
from neobot_app.reply.orchestrator_parts.agent_pipeline import AgentPipelineMixin
from neobot_app.reply.orchestrator_parts.settings import SettingsMixin
from neobot_app.reply.orchestrator_parts.observability import ObservabilityMixin
from neobot_app.reply.orchestrator_parts.prompt_blocks import PromptBlocksMixin
from neobot_app.reply.orchestrator_parts.prompt_build import PromptBuildMixin
from neobot_app.reply.orchestrator_parts.prompt_context import PromptContextMixin
from neobot_app.reply.orchestrator_parts.tool_results import ToolResultsMixin
from neobot_app.reply.orchestrator_parts.empty_turn import EmptyTurnMixin
from neobot_app.reply.orchestrator_parts.sending import SendingMixin
from neobot_app.reply.orchestrator_parts.queue_entries import QueueEntriesMixin
from neobot_app.reply.orchestrator_parts.generate import GenerateMixin
from neobot_app.reply.orchestrator_parts.suspend_private import SuspendPrivateMixin
from neobot_app.reply.orchestrator_parts.suspend_group import SuspendGroupMixin

from neobot_app.reply.orchestrator_parts.empty_turn import (
    EMPTY_TURN_NO_OUTPUT as EMPTY_TURN_NO_OUTPUT,
    EMPTY_TURN_TRUNCATED as EMPTY_TURN_TRUNCATED,
    _classify_empty_turn as _classify_empty_turn,
    _extract_finish_reason as _extract_finish_reason,
    _extract_usage_summary as _extract_usage_summary,
)
from neobot_app.reply.orchestrator_parts.lifecycle_hooks import _hook_name as _hook_name
from neobot_app.reply.orchestrator_parts.prompt_blocks import (
    _AT_MENTION_PRIORITY_BLOCK as _AT_MENTION_PRIORITY_BLOCK,
    _NO_TOOL_CALL_REMINDER as _NO_TOOL_CALL_REMINDER,
    _SILENT_NUDGE_TEXT as _SILENT_NUDGE_TEXT,
    _xml_escape as _xml_escape,
)
from neobot_app.reply.orchestrator_parts.sending import _segment_file_hint as _segment_file_hint
from neobot_app.reply.orchestrator_parts.settings import _CHAT_FIELD_DEFAULTS as _CHAT_FIELD_DEFAULTS, _chat_default as _chat_default, _safe_int as _safe_int
from neobot_app.reply.orchestrator_parts.tool_text import (
    _BARE_SECRET_KEY_RE as _BARE_SECRET_KEY_RE,
    _INTERNAL_TOOL_KEYS as _INTERNAL_TOOL_KEYS,
    _MAX_TOOL_LOG_CHARS as _MAX_TOOL_LOG_CHARS,
    _MAX_TOOL_REDACTION_CHARS as _MAX_TOOL_REDACTION_CHARS,
    _MAX_TOOL_REDACTION_ITEMS as _MAX_TOOL_REDACTION_ITEMS,
    _MAX_TOOL_TEXT_CHARS as _MAX_TOOL_TEXT_CHARS,
    _SECRET_VALUE_RE as _SECRET_VALUE_RE,
    _SENSITIVE_TOOL_KEYS as _SENSITIVE_TOOL_KEYS,
    _SENSITIVE_TOOL_KEY_SUFFIXES as _SENSITIVE_TOOL_KEY_SUFFIXES,
    _TOOL_FAILURE_HINT_AFTER as _TOOL_FAILURE_HINT_AFTER,
    _URL_USERINFO_RE as _URL_USERINFO_RE,
    _bounded_tool_text as _bounded_tool_text,
    _clip_tool_summary as _clip_tool_summary,
    _is_sensitive_tool_key as _is_sensitive_tool_key,
    _normalize_tool_key as _normalize_tool_key,
    _parse_tool_args as _parse_tool_args,
    _redact_tool_value as _redact_tool_value,
    _redacted_tool_text as _redacted_tool_text,
    _render_tool_package_index as _render_tool_package_index,
    _render_tool_result_template as _render_tool_result_template,
    _safe_tool_args as _safe_tool_args,
    _scrub_secret_values as _scrub_secret_values,
)


class ReplyOrchestrator(LifecycleHooksMixin, LifecycleStartMixin, LifecycleShutdownMixin, ModesMixin, AgentLoopMixin, AgentPromptMixin, AgentToolsetMixin, AgentHandlersMixin, AgentModelCallMixin, AgentToolExecMixin, AgentPipelineMixin, SettingsMixin, ObservabilityMixin, PromptBlocksMixin, PromptBuildMixin, PromptContextMixin, ToolResultsMixin, EmptyTurnMixin, SendingMixin, QueueEntriesMixin, GenerateMixin, SuspendPrivateMixin, SuspendGroupMixin):
    def __init__(
        self,
        *,
        adapter: OneBotAdapter,
        prompt_builder: PromptBuilder,
        provider: Provider | None = None,
        group_message_queue: MessageQueue | None = None,
        friend_message_queue: MessageQueue | None = None,
        config: BotConfig | None = None,
        willing_service: WillingService | None = None,
        image_parse_service: ImageParseService | None = None,
        emoji_service: EmojiService | None = None,
        tts_service: Any = None,
        provider_error_message: str | None = None,
        debug_recorder: DebugRecorder | None = None,
        context_recorder: Any = None,
        self_sent_uow_factory: Any = None,
        logger: Logger | None = None,
        drawing_manager: Any = None,
        scheduled_task_manager: Any = None,
        problem_solver_manager: Any = None,
        notification_hub: Any = None,
        markdown_image_converter: Any = None,
        reply_block_registry: Any = None,
        skill_manager: Any = None,
        balance_checker: Any = None,
        runtime_events: Any = None,
        file_server: FileServer | None = None,
        skills_registry: Any = None,
        prompt_store: PromptStore | None = None,
        flow_registry: Any = None,
        cache_calculator: CacheCalculator | None = None,
        credential_manager: Any = None,
        config_update_callback: Any = None,
        sleep_service: Any = None,
        standby_service: Any = None,
    ) -> None:
        self._adapter = adapter
        self._sleep_service = sleep_service
        self._standby_service = standby_service
        self._prompt_builder = prompt_builder
        self._prompt_store = prompt_store
        #: 聊天流快照登记处（面板只读视图）；None 时全部记录调用直接跳过
        self._flow_registry = flow_registry
        self._cache_calculator = cache_calculator
        self._provider = provider
        self._group_queue = group_message_queue
        self._friend_queue = friend_message_queue
        self._config = config
        self._willing_service = willing_service
        self._image_parse_service = image_parse_service
        self._emoji_service = emoji_service
        self._tts_service = tts_service
        self._provider_error_message = (
            provider_error_message or "当前主回复模型不可用，请检查模型配置"
        )
        self._debug_recorder = debug_recorder
        self._context_recorder = context_recorder
        self._logger = logger or NullLogger()
        self._drawing_manager = drawing_manager
        self._scheduled_task_manager = scheduled_task_manager
        self._problem_solver_manager = problem_solver_manager
        self._markdown_image_converter = markdown_image_converter
        self._reply_block_registry = reply_block_registry
        self._skill_manager = skill_manager
        self._markdown_skills = skills_registry
        self._balance_checker = balance_checker
        self._runtime_events = runtime_events
        self._file_server = file_server
        self._credential_manager = credential_manager
        self._config_update_callback = config_update_callback
        self._tasks: set[asyncio.Task[None]] = set()
        self._callback_tasks: set[asyncio.Task[None]] = set()
        #: 事件 ID -> 该次回复创建的工具执行器。
        #: 必须按事件索引并在回复结束时释放：旧实现只 add 不 remove，
        #: 每个 agent 模式回复都会永久留下一个持有完整对话历史的执行器。
        self._tool_executors: dict[str, Any] = {}
        self._agent_tool_turns: dict[str, tuple[Any, Any, list[dict]]] = {}
        self._active_pipelines: dict[str, asyncio.Task[None]] = {}
        self._last_reply_time: dict[str, float] = {}
        self._last_sentence_time: dict[str, float] = {}
        self._closed = False
        self._notification_hub = notification_hub
        self._pre_reply_hooks: list[Callable[[ReplyEvent], Awaitable[str | None]]] = []
        self._post_reply_hooks: list[
            Callable[[ReplyEvent, str | None], Awaitable[str | None]]
        ] = []
        self._debug_helper = DebugHelper(
            debug_recorder=debug_recorder,
            runtime_events=runtime_events,
            logger=self._logger,
        )
        image_registrar = self._resolve_image_registrar(drawing_manager)
        self._sender = ReplySender(
            adapter=adapter,
            file_server=file_server,
            config=config,
            # Bot 自身发言的落盘复用宿主共享的 storage 引擎（缺省时 sender 自己惰性打开同一份库）
            self_sent_uow_factory=self_sent_uow_factory,
            # Bot 自发图片登记进 temp 图库（tmp_xxx），供 agent 之后再次取回查看
            image_registrar=image_registrar,
            bot_name=self._get_bot_name(),
            emoji_service=emoji_service,
            markdown_image_converter=markdown_image_converter,
            debug_helper=self._debug_helper,
            runtime_events=runtime_events,
            io_timeout_seconds=self._get_io_timeout_seconds(),
            sentence_cooldown_seconds=self._get_sentence_cooldown_seconds(),
            private_chat_sentence_cooldown_seconds=self._get_private_chat_sentence_cooldown_seconds(),
            long_reply_max_length=self._get_long_reply_max_length(),
            long_reply_max_sentence_count=self._get_long_reply_max_sentence_count(),
            long_reply_fallback_template=self._get_long_reply_fallback_template(),
            enable_ai_reply_regenerate=self._get_enable_ai_reply_regenerate(),
            provider=provider,
            balance_checker=balance_checker,
            logger=self._logger,
        )
