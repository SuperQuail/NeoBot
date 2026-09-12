"""ReplyOrchestrator — 管理回复事件的创建与异步执行，支持 common/agent 两种模式"""

from __future__ import annotations

import asyncio
import inspect
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.runtime_event import RuntimeEnvelope

from neobot_app.prompt.render import render_template
from neobot_app.prompt.store import get_template_value
from neobot_app.reply._utils import entry_fingerprint
from neobot_app.reply.debug import DebugHelper
from neobot_app.reply.event import ReplyEvent, ReplyState
from neobot_app.reply.postprocess import process_reply_text
from neobot_app.reply.sender import ReplySender
from neobot_app.reply.vision_context import (
    ReplyVisionContext,
    append_image_context,
    labelled_tool_images,
    visible_content_length,
)
from neobot_app.statistics.tracker import get_usage_tracker
from neobot_chat.runtime.agent import SILENT_HEARTBEAT
from neobot_app.utils.media_sender import prepare_image_segment, send_image
from neobot_app.time_context import get_current_time_values, monotonic_seconds


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _safe_int(value: object) -> int:
    """把配置值安全解析为 int；非数字/None/空串一律返回 0。

    避免畸形配置（如 bot.account 填了 "your_qq"）在 int() 处抛 ValueError，
    导致每次 agent 回复管线崩溃。
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


#: 同一个工具 + 同一组参数连续失败到这个次数后，在工具结果里附一句软提示。
#: 刻意只提示、不短路：部署者修好环境（例如换对 QQ 版本）之后继续调用必须
#: 真实执行，否则工具会永久不可用。
_TOOL_FAILURE_HINT_AFTER = 3

_MAX_TOOL_TEXT_CHARS = 16 * 1024
_MAX_TOOL_LOG_CHARS = 2 * 1024
_MAX_TOOL_REDACTION_CHARS = 1024 * 1024
_MAX_TOOL_REDACTION_ITEMS = 256
_SENSITIVE_TOOL_KEYS = frozenset(
    {
        "secret",
        "password",
        "passwd",
        "pwd",
        "token",
        "api_key",
        "apikey",
        "api-key",
        "authorization",
        "auth",
        "cookie",
        "credential",
        "access_key",
        "private_key",
        "bearer",
        "client_secret",
        "access_token",
        "refresh_token",
    }
)
_SENSITIVE_TOOL_KEY_SUFFIXES = (
    "_secret",
    "_password",
    "_passwd",
    "_pwd",
    "_token",
    "_credential",
    "_authorization",
    "_cookie",
    "_api_key",
    "_access_key",
    "_private_key",
)
_INTERNAL_TOOL_KEYS = frozenset({"_delegate_context"})


def _normalize_tool_key(key: object) -> str:
    text = str(key)
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", text)
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    return re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").casefold()


def _is_sensitive_tool_key(key: object) -> bool:
    normalized = _normalize_tool_key(key)
    if normalized in _SENSITIVE_TOOL_KEYS:
        return True
    return any(normalized.endswith(suffix) for suffix in _SENSITIVE_TOOL_KEY_SUFFIXES)


def _bounded_tool_text(value: object, limit: int = _MAX_TOOL_TEXT_CHARS) -> str:
    if isinstance(value, str):
        text = value[: limit + 1]
    elif isinstance(value, (dict, list, tuple)):
        try:
            text = json.dumps(value, ensure_ascii=False, default=lambda _: "<object>")[
                : limit + 1
            ]
        except (TypeError, ValueError, RecursionError):
            text = f"<{type(value).__name__}>"
    else:
        try:
            text = str(value)[: limit + 1]
        except Exception:
            text = f"<{type(value).__name__}>"
    return text if len(text) <= limit else text[:limit] + "\n...[truncated]"


def _clip_tool_summary(text: str, limit: int) -> str:
    """压缩工具输出时保留的摘要:优先在换行处截断,避免半截 JSON 误导模型。"""
    cleaned = text.strip()
    if limit <= 0 or len(cleaned) <= limit:
        return cleaned
    head = cleaned[:limit]
    newline = head.rfind("\n")
    if newline >= limit // 2:
        head = head[:newline]
    return head.rstrip() + "..."


def _render_tool_result_template(
    template: str,
    *,
    tool_name: str,
    summary: str,
    original_chars: int,
) -> str:
    """渲染工具输出压缩模板(占位符与转义规则与其它提示词一致)。"""
    return render_template(
        template,
        {
            "tool_name": tool_name or "未知工具",
            "summary": summary,
            "original_chars": original_chars,
        },
    )


def _redact_tool_value(
    value: object,
    _depth: int = 0,
    *,
    drop_internal: bool = False,
) -> object:
    """递归替换敏感键的值；深/宽超限时整体折叠，避免无界展开。"""
    if _depth > 8:
        return "<truncated>"
    if isinstance(value, dict):
        redacted: dict[str, object] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= _MAX_TOOL_REDACTION_ITEMS:
                redacted["..."] = "<truncated>"
                break
            key_text = str(key)
            if key_text in _INTERNAL_TOOL_KEYS:
                if not drop_internal:
                    redacted[key_text] = "<redacted>"
                continue
            safe_key = _scrub_secret_values(key_text)
            redacted[safe_key] = (
                "<redacted>"
                if _is_sensitive_tool_key(key)
                else _redact_tool_value(
                    item,
                    _depth + 1,
                    drop_internal=drop_internal,
                )
            )
        return redacted
    if isinstance(value, (list, tuple)):
        items = list(value[:_MAX_TOOL_REDACTION_ITEMS])
        redacted_items = [
            _redact_tool_value(
                item,
                _depth + 1,
                drop_internal=drop_internal,
            )
            for item in items
        ]
        if len(value) > _MAX_TOOL_REDACTION_ITEMS:
            redacted_items.append("<truncated>")
        return redacted_items
    if isinstance(value, str):
        return _scrub_secret_values(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return "<object>"


_SECRET_VALUE_RE = re.compile(
    r"(?i)(bearer\s+|"
    r"[\"']?(?:authorization|api[_-]?key|apikey|access[_-]?token|access[_-]?key|"
    r"auth[_-]?token|client[_-]?secret|private[_-]?key|"
    r"secret|token|passwd|password|credential|pwd)"
    r"[\"']?\s*[:=]\s*[\"']?)"
    r"(?:bearer\s+)?[^\s,;\"']+"
)

#: 没有键名的裸密钥形态（``sk-proj-...``）：上面那条正则要求 ``key=value``
#: 或 ``Bearer``，异常文本里直接出现的 key 会整条漏给模型。
_BARE_SECRET_KEY_RE = re.compile(r"sk-[A-Za-z0-9_-]{8,}")
#: URL 内嵌凭据：``https://user:password@host``。
_URL_USERINFO_RE = re.compile(r"(?i)([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@")


def _scrub_secret_values(text: str) -> str:
    """把字符串值内嵌的常见密钥形态（Bearer <token>、token=xxx 等）替换为占位符。"""
    if not isinstance(text, str):
        return text
    scrubbed = _SECRET_VALUE_RE.sub(lambda match: match.group(1) + "<redacted>", text)
    scrubbed = _BARE_SECRET_KEY_RE.sub("<redacted>", scrubbed)
    return _URL_USERINFO_RE.sub(r"\1<redacted>@", scrubbed)


def _redacted_tool_text(value: object, limit: int = _MAX_TOOL_LOG_CHARS) -> str:
    """日志/调试用文本：先解析完整的有界对象并脱敏，最后才截断。"""
    if isinstance(value, str):
        parsed: object | None = None
        should_parse = len(value) <= _MAX_TOOL_REDACTION_CHARS
        if should_parse:
            try:
                parsed = json.loads(value)
            except (json.JSONDecodeError, TypeError, ValueError, RecursionError):
                parsed = None
        if parsed is not None or value.strip() == "null":
            text = _bounded_tool_text(
                _redact_tool_value(parsed),
                _MAX_TOOL_REDACTION_CHARS,
            )
        else:
            # Only the prefix can reach the bounded log output. Scrub it before
            # truncating so oversized or malformed JSON cannot bypass redaction.
            scan_limit = max(_MAX_TOOL_TEXT_CHARS, limit * 2)
            text = _scrub_secret_values(value[:scan_limit])
    else:
        try:
            text = json.dumps(
                _redact_tool_value(value),
                ensure_ascii=False,
                default=lambda _: "<object>",
            )
        except (TypeError, ValueError, RecursionError):
            text = f"<{type(value).__name__}>"
    return _bounded_tool_text(_scrub_secret_values(text), limit)


def _safe_tool_args(args: object) -> str:
    redacted = _redact_tool_value(args, drop_internal=True)
    return _redacted_tool_text(redacted, _MAX_TOOL_LOG_CHARS)


def _parse_tool_args(value: object) -> dict[str, Any]:
    """Normalize provider tool arguments to the dictionary executor contract."""
    if isinstance(value, dict):
        return dict(value)
    if value is None:
        return {}
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError, ValueError, RecursionError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


#: 空轮次成因：输出预算被思维链吃光（finish_reason=length）。
EMPTY_TURN_TRUNCATED = "truncated"
#: 空轮次成因：模型没给正文也没调工具，且不是长度截断。
EMPTY_TURN_NO_OUTPUT = "empty"


def _extract_finish_reason(response: object) -> str:
    """读取 provider 透出的结束原因（缺失时返回空串）。"""
    if not isinstance(response, dict):
        return ""
    extensions = response.get("extensions")
    if not isinstance(extensions, dict):
        return ""
    value = extensions.get("finish_reason")
    return value.strip() if isinstance(value, str) else ""


def _extract_usage_summary(response: object) -> dict[str, object]:
    """取出这一轮的 output / reasoning token 数（缺失时为 None）。

    空轮次判定与日志观测共用同一套取值，避免两处口径漂移。
    """
    extensions = response.get("extensions") if isinstance(response, dict) else None
    usage = extensions.get("usage") if isinstance(extensions, dict) else None
    usage = usage if isinstance(usage, dict) else {}
    details = usage.get("completion_tokens_details")
    details = details if isinstance(details, dict) else {}
    return {
        "output_tokens": usage.get("output_tokens"),
        "reasoning_tokens": details.get("reasoning_tokens"),
    }


def _classify_empty_turn(response: object) -> str:
    """给「正文为空且没有工具调用」的一轮定性。

    两种情况都会导致回复丢失，必须区分记录：
    - EMPTY_TURN_TRUNCATED：finish_reason=length，输出预算被思维链吃光；
    - EMPTY_TURN_NO_OUTPUT：其它原因的空输出。
    """
    if _extract_finish_reason(response).casefold() == "length":
        return EMPTY_TURN_TRUNCATED
    return EMPTY_TURN_NO_OUTPUT


if TYPE_CHECKING:
    from neobot_adapter import OneBotAdapter
    from neobot_adapter.model.message import GroupMessage, PrivateMessage
    from neobot_chat.providers.base import Provider
    from neobot_app.config.schemas.bot import BotConfig
    from neobot_app.emoji.service import EmojiService
    from neobot_app.observability.debug import DebugRecorder
    from neobot_app.message.numbering import MessageNumbering
    from neobot_app.message.queue import MessageQueue
    from neobot_app.cache import CacheCalculator
    from neobot_app.prompt.builder import PromptBuilder
    from neobot_app.prompt.store import PromptStore
    from neobot_app.willing.models import WillingDecision
    from neobot_app.willing.service import WillingService
    from neobot_app.image import ImageParseService
    from neobot_app.core.file_server import FileServer


def _hook_name(hook: object) -> str:
    """钩子的可读标识（用于日志）。"""
    return str(
        getattr(hook, "__qualname__", None)
        or getattr(hook, "__name__", None)
        or type(hook).__name__
    )


class ReplyOrchestrator:
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
        self._sender = ReplySender(
            adapter=adapter,
            file_server=file_server,
            config=config,
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

    def start_reply(
        self,
        *,
        message: PrivateMessage | GroupMessage,
        queue: MessageQueue,
        queue_key: str,
        decision: WillingDecision,
        pre_reply_message_id: int | None = None,
        on_reply_done: Callable[[], Awaitable[None]] | None = None,
        skip_cooldown: bool = False,
        background_content: str | None = None,
    ) -> ReplyEvent | None:
        if self._closed:
            self._logger.warning("ReplyOrchestrator 已关闭，拒绝创建回复管线")
            return None
        mode = self._resolve_mode()
        conversation_ref = self._build_conversation_ref(message, queue_key)
        from neobot_app.agent_tools.invocation import CURRENT_HUMAN_MESSAGE
        event = ReplyEvent(
            mode=mode,
            human_request=CURRENT_HUMAN_MESSAGE.get() and background_content is None,
            message=message,
            willing_decision=decision,
            conversation_ref=conversation_ref,
            pre_reply_message_id=pre_reply_message_id,
            background_content=background_content,
        )

        # 按 kind:queue_key 组合键去重，避免群号与 QQ 号相同时互相阻塞
        pipeline_key = f"{conversation_ref.kind}:{queue_key}"
        existing = self._active_pipelines.get(pipeline_key)
        if existing is not None and existing.done():
            self._active_pipelines.pop(pipeline_key, None)
            existing = None
        if existing is not None and not existing.done():
            self._logger.debug(
                "回复管线已在运行，跳过创建",
                event_id=event.event_id,
                pipeline_key=pipeline_key,
            )
            self._record_debug(
                "skipped_pipeline_overlap",
                event,
                queue_key=queue_key,
                pipeline_key=pipeline_key,
            )
            return None

        # 冷却检查：距上次回复结束不足冷却时间则跳过（后台通知可绕过）
        if not skip_cooldown:
            cooldown = self._get_cooldown_seconds()
            last_time = self._last_reply_time.get(pipeline_key, 0.0)
            elapsed = monotonic_seconds() - last_time
            if elapsed < cooldown:
                self._logger.debug(
                    "冷却中，跳过创建回复",
                    event_id=event.event_id,
                    pipeline_key=pipeline_key,
                    elapsed=f"{elapsed:.1f}s",
                    cooldown=f"{cooldown}s",
                )
                self._record_debug(
                    "skipped_cooldown",
                    event,
                    queue_key=queue_key,
                    pipeline_key=pipeline_key,
                    elapsed_seconds=elapsed,
                    cooldown_seconds=cooldown,
                )
                return None

        self._logger.info(
            "创建回复事件",
            event_id=event.event_id,
            conversation_id=queue_key,
            conversation_kind=getattr(event.conversation_ref, "kind", ""),
            probability=f"{decision.probability:.3f}",
            mode=mode,
        )
        self._record_debug(
            "created",
            event,
            queue_key=queue_key,
            decision={
                "manager_name": decision.manager_name,
                "probability": decision.probability,
                "should_reply": decision.should_reply,
                "reasons": list(decision.reasons),
            },
        )

        def _cleanup(task: asyncio.Task[None]) -> None:
            self._tasks.discard(task)
            if self._active_pipelines.get(pipeline_key) is task:
                self._active_pipelines.pop(pipeline_key, None)
            shared_turn = self._agent_tool_turns.pop(event.event_id, None)
            if shared_turn is not None:
                runtime, context, history = shared_turn
                try:
                    runtime.finish_turn(context, history, cancelled=event.state in {ReplyState.CANCELLED, ReplyState.FAILED})
                except Exception as exc:
                    self._logger.warning("agent 目标续跑未能调度", error=str(exc))
            self._release_executor(event.event_id)
            if on_reply_done is not None:
                callback_task = asyncio.ensure_future(on_reply_done())
                self._callback_tasks.add(callback_task)

                def _callback_done(done_task: asyncio.Future[None]) -> None:
                    self._callback_tasks.discard(callback_task)
                    try:
                        done_task.result()
                    except asyncio.CancelledError:
                        pass
                    except Exception as exc:
                        self._logger.warning(
                            "回复完成回调失败",
                            event_id=event.event_id,
                            pipeline_key=pipeline_key,
                            error=str(exc),
                        )

                callback_task.add_done_callback(_callback_done)

        task = asyncio.create_task(self._run(event, queue, queue_key))
        self._tasks.add(task)
        self._active_pipelines[pipeline_key] = task
        task.add_done_callback(_cleanup)
        return event

    def _release_executor(self, event_id: str) -> None:
        """释放某次回复创建的工具执行器。

        执行器持有该轮完整对话历史与技能 token，必须随管线结束释放；但不能直接
        ``close()``：close() 会取消在途的会话工具（download__url / parse_image
        等），而它们的契约是活过本轮回复、完成后由通知中心唤醒下一次回复。
        所以先等在途会话任务自然结束，再关闭执行器——内存依然会被释放，只是
        释放时机推迟到后台工作完成。关闭失败只记日志，不能影响管线收尾。
        """
        executor = self._tool_executors.pop(event_id, None)
        if executor is None:
            return

        async def _drain_and_close() -> None:
            drain = getattr(executor, "drain_sessions", None)
            if callable(drain):
                await drain()
            await executor.close()

        close_task: asyncio.Future[None]
        try:
            close_task = asyncio.ensure_future(_drain_and_close())
        except Exception as exc:
            # 同步异常绝不能冒泡到 done 回调：那会连带跳过 on_reply_done，
            # 让「回复中」标记永久残留。
            self._logger.warning(
                "回复工具执行器释放失败", event_id=event_id, error=str(exc)
            )
            return
        self._callback_tasks.add(close_task)

        def _done(done_task: asyncio.Future[None]) -> None:
            self._callback_tasks.discard(close_task)
            try:
                done_task.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                self._logger.warning(
                    "回复工具执行器释放失败",
                    event_id=event_id,
                    error=str(exc),
                )

        close_task.add_done_callback(_done)

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

    def start_background_reply(
        self,
        *,
        kind: str,
        conversation_id: str,
        content: str,
        manager_name: str = "background_drawing",
        reasons: list[str] | None = None,
    ) -> Any | None:
        """程序化启动回复管线，用于后台绘图等系统通知。

        当绘图完成但对应聊天流无活跃管线时，由 BackgroundDrawingManager 调用。
        """
        if self._closed:
            self._logger.warning("ReplyOrchestrator 已关闭，拒绝创建后台回复管线")
            return None
        from neobot_app.willing.models import WillingDecision

        queue_key = str(conversation_id)
        pipeline_key = f"{kind}:{queue_key}"

        if not kind or not conversation_id:
            self._logger.error(
                "start_background_reply: 无效的会话参数",
                kind=kind,
                conversation_id=conversation_id,
                manager_name=manager_name,
            )
            return None

        existing = self._active_pipelines.get(pipeline_key)
        if existing is not None and existing.done():
            self._active_pipelines.pop(pipeline_key, None)
            existing = None
        if existing is not None and not existing.done():
            self._logger.debug(
                "后台回复管线已在运行，跳过创建",
                pipeline_key=pipeline_key,
            )
            return None

        queue = self._group_queue if kind == "group" else self._friend_queue
        if queue is None:
            self._logger.error(
                "无法启动后台回复：消息队列未配置",
                kind=kind,
                conversation_id=conversation_id,
            )
            return None

        # 将通知内容推入消息队列作为触发消息
        @dataclass
        class _SyntheticSender:
            card: str = ""
            nickname: str = "系统"

        @dataclass
        class _SyntheticMessage:
            time: int = 0
            self_id: int = 0
            post_type: str = "message"
            message_type: str = kind
            sub_type: str = "normal"
            message_id: int = 0
            user_id: int = 0
            group_id: int = (
                int(conversation_id)
                if kind == "group" and conversation_id.isdigit()
                else 0
            )
            message: list = field(
                default_factory=lambda: [{"type": "text", "data": {"text": content}}]
            )
            raw_message: str = ""
            font: int = 0
            sender: Any = field(default_factory=_SyntheticSender)
            message_seq: int = 0
            target_id: int = 0
            temp_source: int = 0

        synthetic_msg = _SyntheticMessage()

        decision = WillingDecision(
            manager_name=manager_name,
            probability=1.0,
            should_reply=True,
            reasons=tuple(reasons) if reasons else ("后台绘图任务完成通知",),
        )

        self._logger.info(
            "启动后台回复管线",
            pipeline_key=pipeline_key,
            kind=kind,
            conversation_id=conversation_id,
        )
        return self.start_reply(
            message=synthetic_msg,
            queue=queue,
            queue_key=queue_key,
            decision=decision,
            skip_cooldown=True,
            background_content=content,
        )

    async def shutdown(self) -> None:
        self._closed = True
        deferred: BaseException | None = None

        async def _run_step(label: str, action: Callable[[], Any]) -> None:
            nonlocal deferred
            deferred_cancel: asyncio.CancelledError | None = None
            cleanup_task: asyncio.Future[Any] | None = None
            try:
                result = action()
                if inspect.isawaitable(result):
                    cleanup_task = asyncio.ensure_future(result)
                    while not cleanup_task.done():
                        try:
                            await asyncio.shield(cleanup_task)
                        except asyncio.CancelledError as exc:
                            current = asyncio.current_task()
                            if current is not None and current.cancelling():
                                deferred_cancel = deferred_cancel or exc
                                continue
                            raise
                    cleanup_task.result()
            except BaseException as exc:
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    self._logger.error(
                        f"{label} 在关闭编排器时被中断",
                        error_type=type(exc).__name__,
                        error=str(exc),
                    )
                    deferred = exc
                elif isinstance(exc, asyncio.CancelledError):
                    self._logger.warning(
                        f"{label} 在关闭编排器时被取消"
                    )
                    current = asyncio.current_task()
                    if deferred_cancel is not None:
                        deferred = deferred or deferred_cancel
                    elif current is not None and current.cancelling():
                        deferred = deferred or exc
                else:
                    self._logger.warning(
                        f"{label} 在关闭编排器时失败",
                        error_type=type(exc).__name__,
                        error=str(exc),
                    )
            if deferred_cancel is not None:
                deferred = deferred or deferred_cancel

        async def _cancel_tasks(tasks: set[asyncio.Task[None]]) -> None:
            pending = list(tasks)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

        async def _close_executors() -> None:
            executors = list(self._tool_executors.values())
            if not executors:
                return
            fatal: BaseException | None = None
            results = await asyncio.gather(
                *(executor.close() for executor in executors),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, BaseException):
                    self._logger.warning(
                        "回复工具执行器关闭失败",
                        error_type=type(result).__name__,
                        error=str(result),
                    )
                    if isinstance(result, (KeyboardInterrupt, SystemExit)):
                        fatal = result
            if fatal is not None:
                raise fatal

        await _run_step("reply pipelines", lambda: _cancel_tasks(self._tasks))
        await _run_step(
            "reply completion callbacks", lambda: _cancel_tasks(self._callback_tasks)
        )
        await _run_step("reply tool executors", _close_executors)
        if self._skill_manager is not None:
            shared_tools = self._skill_manager.get("agent_tools")
            if shared_tools is not None:
                await _run_step("shared agent tools", shared_tools.close)
        if self._drawing_manager is not None:
            await _run_step("drawing manager", self._drawing_manager.shutdown)
        if self._scheduled_task_manager is not None:
            await _run_step(
                "scheduled task manager", self._scheduled_task_manager.shutdown
            )
        if self._notification_hub is not None:
            await _run_step("notification hub", self._notification_hub.clear)
        if self._provider is not None:
            await _run_step("reply provider", self._provider.close)

        self._tool_executors.clear()
        self._active_pipelines.clear()
        self._tasks.clear()
        self._callback_tasks.clear()
        self._last_reply_time.clear()
        self._last_sentence_time.clear()
        self._logger.info("ReplyOrchestrator 已关闭")
        if deferred is not None:
            raise deferred

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

    def _resolve_mode(self) -> str:
        # 回退值必须与 config.schemas.bot.Chat.reply_mode 的默认值一致（agent），
        # 否则「字段缺失」时会静默降级成 common（只有基础回复能力）。
        if self._config is not None:
            mode = getattr(self._config.chat, "reply_mode", "agent") or "agent"
            if mode in ("common", "agent"):
                return mode
        return "agent"

    def _get_cooldown_seconds(self) -> int:
        if self._config is not None:
            val = getattr(self._config.chat, "reply_cooldown_seconds", None)
            if isinstance(val, int):
                return val
        return 2

    def _get_wait_cooldown_seconds(self) -> int:
        if self._config is not None:
            val = getattr(self._config.chat, "wait_cooldown_seconds", None)
            if isinstance(val, int):
                return val
        return 60

    def _get_sentence_cooldown_seconds(self) -> float:
        if self._config is not None:
            val = getattr(self._config.chat, "reply_sentence_cooldown_seconds", None)
            if isinstance(val, (int, float)):
                return float(val)
        return 2.0

    def _get_private_chat_sentence_cooldown_seconds(self) -> float:
        if self._config is not None:
            val = getattr(
                self._config.chat, "private_chat_sentence_cooldown_seconds", None
            )
            if isinstance(val, (int, float)):
                return float(val)
        return 2.0

    def _get_max_wait_seconds(self) -> int:
        if self._config is not None:
            val = getattr(self._config.chat, "agent_wait_max_seconds", None)
            if isinstance(val, int) and val > 0:
                return val
        return 60

    def _get_private_chat_suspend_wait_seconds(self) -> int:
        if self._config is not None:
            val = getattr(self._config.chat, "private_chat_suspend_wait_seconds", None)
            if isinstance(val, int) and val > 0:
                return val
        return 300

    def _get_agent_max_iterations(self) -> int:
        if self._config is not None:
            val = getattr(self._config.chat, "agent_max_iterations", None)
            if isinstance(val, int) and val > 0:
                return val
        return 200

    def _get_group_agent_silent_timeout_seconds(self) -> float:
        if self._config is not None:
            val = getattr(self._config.chat, "group_agent_silent_timeout_seconds", None)
            if isinstance(val, (int, float)):
                return max(0.0, float(val))
        return 120.0

    def _get_io_timeout_seconds(self) -> float:
        return 30.0

    def _get_dependency_timeout_seconds(self) -> float:
        return 10.0

    def _get_private_image_wait_timeout_seconds(self) -> float:
        # 视觉模型单次调用上限 60s；图片解析可能含下载(≤30s)+推理(≤60s)，
        # 取 90s 作为私聊回复等待图片解析的上限，避免无限阻塞。
        return 90.0

    def _get_prompt_timeout_seconds(self) -> float:
        return 30.0

    def _get_model_response_timeout_seconds(self, event: ReplyEvent) -> float:
        if (
            event.conversation_ref is not None
            and event.conversation_ref.kind == "group"
        ):
            timeout = self._get_group_agent_silent_timeout_seconds()
            if timeout > 0:
                return timeout
        return 120.0

    async def _send_with_timeout(
        self, conversation_ref: ConversationRef, payload: object
    ) -> Any:
        return await self._sender.send_with_timeout(conversation_ref, payload)

    async def _call_api_with_timeout(self, action: str, params: dict[str, Any]) -> Any:
        return await self._sender.call_api_with_timeout(action, params)

    def _get_private_chat_max_tokens(self) -> int:
        if self._config is not None:
            val = getattr(self._config.chat, "private_chat_max_tokens", None)
            if isinstance(val, int) and val > 0:
                return val
        return 50000

    def _get_private_chat_new_message_collect_seconds(self) -> float:
        if self._config is not None:
            val = getattr(
                self._config.chat, "private_chat_new_message_collect_seconds", None
            )
            if isinstance(val, (int, float)) and val > 0:
                return float(val)
        return 5.0

    def _get_native_vision_default_image_count(self) -> int:
        value = getattr(getattr(self._config, "chat", None), "native_vision_default_image_count", 4)
        return value if type(value) is int and value >= 0 else 4

    @staticmethod
    def _estimate_tokens(messages: list[dict]) -> int:
        total_chars = sum(
            len(str({key: value for key, value in m.items() if key != "content"}))
            + visible_content_length(m.get("content"))
            for m in messages
        )
        # 中文为主：1 字符 ≈ 1.3-1.5 token；用 /0.75 做偏保守估计
        return int(total_chars / 0.75)

    def _get_ai_reply_check(self) -> bool:
        if self._config is None:
            return False
        chat = getattr(self._config, "chat", None)
        value = getattr(chat, "ai_reply_check", False)
        return value if isinstance(value, bool) else False

    def _get_ai_reply_check_lightweight(self) -> bool:
        """轻量检查仅在完整检查关闭时生效。"""
        if self._get_ai_reply_check():
            return False
        if self._config is None:
            return True
        chat = getattr(self._config, "chat", None)
        value = getattr(chat, "ai_reply_check_lightweight", True)
        return value if isinstance(value, bool) else True

    def _get_bot_name(self) -> str:
        if self._config is None:
            return "Bot"
        bot = getattr(self._config, "bot", None)
        value = getattr(bot, "nick_name", "Bot")
        return value.strip() if isinstance(value, str) and value.strip() else "Bot"

    def _get_bot_account(self) -> int:
        if self._config is None:
            return 0
        bot = getattr(self._config, "bot", None)
        value = getattr(bot, "account", 0) or 0
        return value

    def _show_boundary_markers(self) -> bool:
        if self._config is None:
            return False
        chat = getattr(self._config, "chat", None)
        return bool(getattr(chat, "show_last_reply_markers", False))

    def _inject_member_archives(self) -> bool:
        """群聊是否注入群员个人档案（默认 False，由 agent 按需读取）。"""
        if self._config is None:
            return False
        chat = getattr(self._config, "chat", None)
        return bool(getattr(chat, "inject_member_archives", False))

    # ── 成本计算管线(字符级缓存命中计算) ──

    def _cost_pipeline_enabled(self) -> bool:
        if self._config is None:
            return False
        chat = getattr(self._config, "chat", None)
        return bool(getattr(chat, "cost_pipeline_enabled", True)) and self._cache_calculator is not None

    def _get_cost_pipeline_threshold(self) -> int:
        if self._config is not None:
            chat = getattr(self._config, "chat", None)
            val = getattr(chat, "cost_pipeline_threshold", None)
            if isinstance(val, int) and val >= 0:
                return val
        return 20

    def _provider_cache_key(self) -> str:
        if self._provider is not None:
            model = getattr(self._provider, "model", None)
            if model:
                return str(model)
        return "chat"

    def _record_cache_request(self, messages: list[dict], response: dict) -> None:
        """记录一次聊天管线模型调用(构建缓存前缀单元)。

        仅聊天管线接入;记忆总结/子Agent/非聊天模型不调用本方法。
        成本管线关闭时不启用,不占用性能。
        """
        if not self._cost_pipeline_enabled():
            return
        calculator = self._cache_calculator
        if calculator is None:
            return
        try:
            from neobot_app.cache import serialize_messages, serialize_response_text

            calculator.record(
                self._provider_cache_key(),
                serialize_messages(messages),
                serialize_response_text(response),
            )
        except Exception:
            self._logger.debug(
                "缓存计算记录失败(忽略)", exc_info=True,
            )

    def _cache_continue_cheaper_than_restart(
        self,
        messages: list[dict],
        system_prompt: str = "",
        queue: MessageQueue | None = None,
        queue_key: str = "",
        numbering: Any = None,
    ) -> bool:
        """成本续用决策:计算缓存命中后的继续成本是否低于重启管线的输入成本。

        - 继续成本:当前消息列表按缓存命中计价(命中前缀部分按 1/差价)
        - 重启成本:重新构建的 [system + 角色消息] 全量输入按未命中计价
          (即"重启一个聊天管线的输入成本")
        - 存在有效命中时继续更便宜才续用
        """
        if not self._cost_pipeline_enabled():
            return False
        # The character-prefix calculator collapses multimodal blocks to one
        # placeholder. Do not extend a pipeline based on that false cost saving.
        if any(
            isinstance(message.get("content"), list) and any(
                isinstance(part, dict) and part.get("type") in {"image_url", "image", "file"}
                for part in message["content"]
            )
            for message in messages
        ):
            return False
        calculator = self._cache_calculator
        if calculator is None:
            return False
        try:
            from neobot_app.cache import serialize_messages

            continue_text = serialize_messages(messages)
            if not continue_text:
                return False
            continue_estimate = calculator.estimate_cost(
                self._provider_cache_key(), continue_text
            )
            # 前置:必须存在有效缓存命中(否则"继续更便宜"无从谈起,
            # 纯长度比较会受消息渲染差异干扰)
            if not continue_estimate.cheaper_than_full_miss():
                return False
            continue_cost = continue_estimate.cost

            # 重启管线的输入:system + 从队列重新构建的角色消息
            restart_text = continue_text
            if system_prompt and queue is not None and queue_key:
                from neobot_app.prompt.role_messages import build_role_messages

                fresh_roles = build_role_messages(
                    queue,
                    queue_key,
                    numbering=numbering,
                    bot_account=self._get_bot_account(),
                    include_boundary_markers=self._show_boundary_markers(),
                )
                restart_text = serialize_messages(
                    [{"role": "system", "content": system_prompt}] + fresh_roles
                )
            if not restart_text:
                return False
            restart_cost = float(len(restart_text))
            return continue_cost < restart_cost
        except Exception:
            return False

    def _get_long_reply_fallback_template(self) -> str:
        default = "{bot_name}懒得和你说道理，你不配听"
        if self._prompt_store is not None:
            value = self._prompt_store.template("long_reply_fallback", default=default)
            if value and value.strip():
                return value
        return default

    # ── 聊天流快照(网页面板只读视图) ──

    def _flow_key(self, event: ReplyEvent, queue_key: str) -> str:
        ref = event.conversation_ref
        kind = getattr(ref, "kind", "") if ref is not None else ""
        return f"{kind}:{queue_key}" if kind else ""

    @staticmethod
    def _flow_queue_key(event: ReplyEvent) -> str:
        """从事件推导队列键(common 模式的 _generate_reply 拿不到 queue_key)。"""
        ref = event.conversation_ref
        if ref is None:
            return ""
        return str(getattr(ref, "id", "") or "")

    def _flow_conversation(self, event: ReplyEvent, queue_key: str) -> tuple[str, str]:
        ref = event.conversation_ref
        kind = getattr(ref, "kind", "") if ref is not None else ""
        return str(kind or ""), str(queue_key or "")

    def _current_model_name(self) -> str:
        return str(getattr(self._provider, "model", "") or "")

    def _record_flow_prompt(self, event: ReplyEvent, queue_key: str, prompt: str) -> None:
        """登记本轮 system 提示词;未接入面板时零开销。"""
        registry = self._flow_registry
        if registry is None:
            return
        key = self._flow_key(event, queue_key)
        if not key:
            return
        kind, conv_id = self._flow_conversation(event, queue_key)
        try:
            registry.record_prompt(
                key,
                system_prompt=prompt,
                model=self._current_model_name(),
                conversation_kind=kind,
                conversation_id=conv_id,
            )
        except Exception:
            self._logger.debug("登记聊天流提示词失败(忽略)", pipeline_key=key)

    def _record_flow_request(
        self,
        event: ReplyEvent,
        queue_key: str,
        messages: list[dict],
        *,
        iteration: int = 0,
    ) -> None:
        """登记最近一次模型请求的消息列表。"""
        registry = self._flow_registry
        if registry is None:
            return
        key = self._flow_key(event, queue_key)
        if not key:
            return
        try:
            registry.record_request(
                key,
                messages=messages,
                model=self._current_model_name(),
                iteration=iteration,
            )
        except Exception:
            self._logger.debug("登记聊天流请求失败(忽略)", pipeline_key=key)

    def _set_flow_active(self, event: ReplyEvent, queue_key: str, active: bool) -> None:
        registry = self._flow_registry
        if registry is None:
            return
        key = self._flow_key(event, queue_key)
        if not key:
            return
        try:
            registry.set_active(key, active)
        except Exception:
            self._logger.debug("登记聊天流状态失败(忽略)", pipeline_key=key)

    # ── 提示词分区(统一从 prompts.toml 读取,缺失时用内置兜底) ──

    def _prompt_template(self, key: str, sub: str = "template") -> str:
        """读取提示词分区模板:文件(自定义覆盖默认) -> 内置兜底。"""
        return get_template_value(self._prompt_store, key, sub)

    def _prompt_section_enabled(self, key: str, default: bool = True) -> bool:
        if self._prompt_store is None:
            return default
        return self._prompt_store.enabled(key, default=default)

    def _native_vision_note(self) -> str:
        """原生视觉说明([native_vision] 模板);分区关闭或模板为空时返回空串。

        这段说明是**稳定内容**,因此追加在 system 提示词里而不是对话末尾:
        系统提示词在各条管线之间逐字节相同,能持续命中上下文缓存;
        追加在历史之后的位置随历史长度变化,永远无法进入可复用前缀。
        """
        if not self._prompt_section_enabled("native_vision"):
            return ""
        return render_template(self._prompt_template("native_vision"), {})

    def _build_current_time_message(self) -> dict[str, str] | None:
        """渲染"回复前"追加的 <当前时间> user 块;关闭或为空时返回 None。"""
        builder = self._prompt_builder
        render = getattr(builder, "build_current_time_message", None)
        if callable(render):
            return render()
        if not self._prompt_section_enabled("current_time"):
            return None
        text = render_template(
            self._prompt_template("current_time"), get_current_time_values()
        )
        if not text:
            return None
        return {"role": "user", "content": text}

    # ── 工具输出压缩 ──

    def _get_tool_result_full_keep(self) -> int:
        """重新构建提示词后保留完整内容的最近工具返回条数。"""
        if self._config is None:
            return 10
        value = getattr(self._config.chat, "tool_result_full_keep", 10)
        return value if isinstance(value, int) and value >= 0 else 10

    def _get_tool_result_summary_chars(self) -> int:
        """非基础工具压缩后保留的结果摘要字符数。"""
        if self._config is None:
            return 200
        value = getattr(self._config.chat, "tool_result_summary_chars", 200)
        return value if isinstance(value, int) and value > 0 else 200

    def _render_compressed_tool_result(
        self, tool_name: str, content: object, summary_chars: int
    ) -> str:
        """把一条工具返回渲染成压缩形式。"""
        from neobot_app.reply.tools import BASIC_REPLY_TOOLS

        original = "" if content is None else str(content)
        summary = _clip_tool_summary(original, summary_chars)
        if tool_name in BASIC_REPLY_TOOLS:
            text = _render_tool_result_template(
                self._prompt_template("tool_result_compressed"),
                tool_name=tool_name,
                summary=summary,
                original_chars=len(original),
            )
            return text or f"[已压缩] 工具 {tool_name or '未知工具'} 调用成功。"
        text = _render_tool_result_template(
            self._prompt_template("tool_result_compressed_detail"),
            tool_name=tool_name,
            summary=summary,
            original_chars=len(original),
        )
        return text or summary

    def _compress_stale_tool_results(
        self,
        messages: list[dict],
        compressed_call_ids: set[str],
        tool_names: dict[str, str],
        *,
        event: ReplyEvent | None = None,
        queue_key: str = "",
    ) -> int:
        """压缩较早的工具返回:只保留最近 N 条完整内容,其余压缩。

        在"重新构建/续用提示词"的新一轮开始时调用;已压缩过的条目按
        tool_call_id 去重,不会重复处理。压缩只改写内容,不动消息顺序,
        也不会让 assistant 的 tool_calls 与结果消息失配。
        """
        keep = self._get_tool_result_full_keep()
        indices = [
            index
            for index, message in enumerate(messages)
            if isinstance(message, dict) and message.get("role") == "tool"
        ]
        if keep >= 0 and len(indices) <= keep:
            return 0
        stale = list(indices) if keep <= 0 else indices[:-keep]
        stale = [
            index
            for index in stale
            if str(messages[index].get("tool_call_id", "")) not in compressed_call_ids
        ]
        if not stale:
            return 0
        summary_chars = self._get_tool_result_summary_chars()
        for index in stale:
            message = messages[index]
            call_id = str(message.get("tool_call_id", ""))
            message["content"] = self._render_compressed_tool_result(
                tool_names.get(call_id, ""), message.get("content"), summary_chars
            )
            if call_id:
                compressed_call_ids.add(call_id)
        if event is not None:
            self._record_debug(
                "tool_results_compressed",
                event,
                queue_key=queue_key,
                compressed_count=len(stale),
                kept_full=len(indices) - len(stale),
            )
        return len(stale)

    def _get_long_reply_max_length(self) -> int:
        if self._config is None:
            return 300
        chat = getattr(self._config, "chat", None)
        value = getattr(chat, "long_reply_max_length", 300)
        return value if isinstance(value, int) and value > 0 else 300

    def _get_long_reply_max_sentence_count(self) -> int:
        if self._config is None:
            return 12
        chat = getattr(self._config, "chat", None)
        value = getattr(chat, "long_reply_max_sentence_count", 12)
        return value if isinstance(value, int) and value > 0 else 12

    def _get_enable_ai_reply_regenerate(self) -> bool:
        if self._config is None:
            return True
        chat = getattr(self._config, "chat", None)
        value = getattr(chat, "enable_ai_reply_regenerate_on_length_limit", True)
        return bool(value)

    def _get_group_chat_reply_lifespan(self) -> int:
        if self._config is not None:
            val = getattr(self._config.chat, "group_chat_reply_lifespan", None)
            if isinstance(val, int) and val >= 0:
                return val
        return 5

    def _get_group_chat_suspend_wait_seconds(self) -> int:
        if self._config is not None:
            val = getattr(self._config.chat, "group_chat_suspend_wait_seconds", None)
            if isinstance(val, int) and val > 0:
                return val
        return 3600

    def _get_at_mention_reply_delay_seconds(self) -> float:
        if self._config is not None:
            val = getattr(self._config.chat, "at_mention_reply_delay_seconds", None)
            if isinstance(val, (int, float)) and val >= 0:
                return float(val)
        return 5.0

    def _record_debug(self, stage: str, event: ReplyEvent, **extra: object) -> None:
        self._debug_helper.record(stage, event, **extra)

    async def _record_context(
        self,
        event: ReplyEvent,
        messages: list[dict],
        *,
        iteration: int,
        stage: str,
        response: dict | None = None,
    ) -> None:
        """记录一轮模型调用的完整上下文与输出(debug 模式,滚动保留最近 100 轮)。

        用于事后分析 token 构成:每轮迭代/每次模型调用一个文件,
        内容为发送给模型的完整 messages(含 system prompt)、模型输出(response)
        以及数据包中的 usage/缓存命中率。
        """
        recorder = self._context_recorder
        if recorder is None:
            return
        try:
            total_chars = 0
            for message in messages:
                if not isinstance(message, dict):
                    continue
                content = message.get("content")
                if content is not None:
                    total_chars += len(str(content))

            # 模型输出与 usage(与 usage tracker 同一来源:extensions.usage)
            output_text = ""
            usage: dict | None = None
            if isinstance(response, dict):
                output_content = response.get("content")
                if output_content is not None:
                    output_text = str(output_content)
                extensions = response.get("extensions")
                if isinstance(extensions, dict):
                    candidate = extensions.get("usage")
                    if isinstance(candidate, dict):
                        usage = candidate
            cache_hit_rate: float | None = None
            if usage is not None:
                hit = usage.get("cache_hit_tokens", 0) or 0
                miss = usage.get("cache_miss_tokens", 0) or 0
                total = hit + miss
                if total > 0:
                    cache_hit_rate = round(hit / total, 4)

            conv_ref = event.conversation_ref
            from datetime import datetime, timezone

            payload = {
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "stage": stage,
                "event_id": event.event_id,
                "mode": event.mode,
                "conversation_kind": getattr(conv_ref, "kind", "") if conv_ref else "",
                "conversation_id": getattr(conv_ref, "id", "") if conv_ref else "",
                "iteration": iteration,
                "messages_count": len(messages),
                "total_chars": total_chars,
                "estimated_tokens": self._estimate_tokens(messages),
                "output_chars": len(output_text),
                "output_estimated_tokens": int(len(output_text) / 0.75),
                "usage": usage,
                "cache_hit_tokens": (
                    usage.get("cache_hit_tokens", 0) if usage else None
                ),
                "cache_miss_tokens": (
                    usage.get("cache_miss_tokens", 0) if usage else None
                ),
                "cache_hit_rate": cache_hit_rate,
                "messages": messages,
                "response": response,
            }
            await asyncio.to_thread(recorder.record_context, payload)
        except Exception as exc:
            self._logger.debug(
                "聊天上下文记录失败",
                event_id=event.event_id,
                error=str(exc),
            )

    async def _emit_runtime_event(
        self, stage: str, event: ReplyEvent, **payload: object
    ) -> RuntimeEnvelope:
        return await self._debug_helper.emit_runtime_event(stage, event, **payload)

    async def _handle_runtime_failure(self, event: ReplyEvent, exc: Exception) -> None:
        return await self._debug_helper.handle_runtime_failure(
            event,
            exc,
            provider_error_message=self._provider_error_message,
            send_with_timeout=self._send_with_timeout,
        )

    async def _run(
        self,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_key: str,
    ) -> None:
        started_at = monotonic_seconds()
        try:
            before_decide = await self._emit_runtime_event(
                "reply.decide.before", event, queue_key=queue_key
            )
            if before_decide.consumed:
                event.error = "reply lifecycle consumed before decision"
                event.transition(ReplyState.CANCELLED)
                await self._emit_runtime_event(
                    "reply.cancel", event, queue_key=queue_key
                )
                return
            start_envelope = await self._emit_runtime_event(
                "reply.decide.after", event, queue_key=queue_key
            )
            if start_envelope.consumed:
                event.error = "reply lifecycle consumed before run"
                event.transition(ReplyState.CANCELLED)
                await self._emit_runtime_event(
                    "reply.cancel", event, queue_key=queue_key
                )
                return
            self._set_flow_active(event, queue_key, True)
            if event.mode == "agent":
                await self._run_agent_mode(event, queue, queue_key)
            else:
                await self._run_common_mode(event, queue, queue_key)
            self._set_flow_active(event, queue_key, False)
            if event.state == ReplyState.CANCELLED:
                self._record_debug("cancelled", event, queue_key=queue_key)
                await self._emit_runtime_event(
                    "reply.cancel", event, queue_key=queue_key
                )
                return
            if event.state == ReplyState.FAILED:
                # 管线内部判定失败（例如模型空轮次）。必须走失败收尾：旧实现
                # 一路记成 completed，日志里看不出「这条消息根本没回复」。
                self._logger.warning(
                    "回复事件失败（管线内部判定）",
                    event_id=event.event_id,
                    mode=event.mode,
                    error=event.error,
                )
                self._record_debug("failed", event, queue_key=queue_key)
                await self._emit_runtime_event(
                    "reply.fail", event, queue_key=queue_key, error=event.error
                )
                return
            # 记录完成时间用于冷却
            if event.conversation_ref is not None:
                pipeline_key = f"{event.conversation_ref.kind}:{queue_key}"
                self._last_reply_time[pipeline_key] = monotonic_seconds()
            # 记录上次回复位置
            enable_tracking = (
                getattr(
                    getattr(self._config, "chat", None),
                    "enable_last_reply_tracking",
                    True,
                )
                if self._config
                else True
            )
            if enable_tracking:
                queue.set_last_reply_position(
                    queue_key,
                    before_message_id=event.pre_reply_message_id,
                )
            elapsed = monotonic_seconds() - started_at
            self._logger.info(
                "回复事件结束",
                event_id=event.event_id,
                mode=event.mode,
                state=event.state.name,
                duration=f"{elapsed:.1f}s",
                reply_preview=event.generated_text[:80] if event.generated_text else "",
            )
            self._record_debug("completed", event, queue_key=queue_key)
            await self._emit_runtime_event(
                "reply.complete", event, queue_key=queue_key, duration_seconds=elapsed
            )
        except asyncio.CancelledError:
            self._set_flow_active(event, queue_key, False)
            event.error = "cancelled"
            if not event.is_terminal:
                try:
                    event.transition(ReplyState.CANCELLED)
                except RuntimeError:
                    pass
            self._logger.warning("回复事件被取消", event_id=event.event_id)
            self._record_debug("cancelled", event, queue_key=queue_key)
            await self._emit_runtime_event("reply.cancel", event, queue_key=queue_key)
            raise
        except Exception as exc:
            self._set_flow_active(event, queue_key, False)
            try:
                event.transition(ReplyState.FAILED)
            except RuntimeError:
                pass
            event.error = f"{type(exc).__name__}: {exc}"
            self._logger.error(
                "回复事件失败",
                event_id=event.event_id,
                mode=event.mode,
                error=event.error,
            )
            self._record_debug("failed", event, queue_key=queue_key)
            await self._emit_runtime_event(
                "reply.fail", event, queue_key=queue_key, error=event.error
            )
            await self._handle_runtime_failure(event, exc)

    # ── Common 模式 ──

    async def _run_common_mode(
        self,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_key: str,
    ) -> None:
        await self._maybe_trigger_sticker(queue, queue_key, event)

        last_reply_message_id, all_new = self._resolve_last_reply(queue, queue_key)
        role_messages = await self._build_role_messages(
            event,
            queue,
            queue_key,
            last_reply_message_id=last_reply_message_id,
            all_new=all_new,
        )
        context_messages: list[dict[str, str]] = []
        prompt = await self._build_prompt(
            event,
            queue,
            queue_key,
            last_reply_message_id=last_reply_message_id,
            all_new=all_new,
            context_blocks=context_messages,
        )
        self._record_flow_prompt(event, queue_key, prompt)
        self._record_debug(
            "base_prompt_built", event, queue_key=queue_key, prompt=prompt
        )

        # pre-reply hooks：可短路跳过 AI 生成
        reply_text = await self._apply_pre_reply_hooks(event)
        if reply_text is None:
            reply_text = await self._generate_reply(
                event, prompt, role_messages, context_messages
            )

        self._record_debug(
            "reply_generated", event, queue_key=queue_key, reply_text=reply_text
        )

        await self._send_reply(event, reply_text)

    async def _maybe_trigger_sticker(
        self,
        queue: MessageQueue,
        queue_key: str,
        event: ReplyEvent | None = None,
    ) -> None:
        """按配置概率随机发送一张表情包到当前会话。

        后台通知（绘图完成、定时任务等）触发的管线不适用——没有用户交互上下文。
        """
        import random

        if event is not None and event.willing_decision is not None:
            mgr = event.willing_decision.manager_name
            if mgr in ("background_drawing", "scheduled_task"):
                return

        prob = (
            getattr(self._config.chat, "random_sticker_probability", 0.1)
            if self._config
            else 0.1
        )
        try:
            prob = float(prob)
        except (TypeError, ValueError):
            prob = 0.1
        prob = max(0.0, min(1.0, prob))
        if random.random() >= prob:
            return
        if self._emoji_service is None or self._emoji_service.emoji_count == 0:
            return
        if event is None or event.conversation_ref is None:
            return

        number = random.randint(1, self._emoji_service.emoji_count)
        entry = self._emoji_service.get_entry(number)
        if entry is None:
            return

        try:
            await send_image(
                self._file_server,
                self._adapter,
                event.conversation_ref,
                entry.file_path,
                wait_response=False,
            )
            # 记录表情包使用次数
            await self._emoji_service.record_usage(number)
            self._logger.debug(
                "已随机发送表情包",
                event_id=event.event_id,
                number=number,
                file=entry.file_name,
            )
        except Exception as exc:
            self._logger.debug(
                "随机表情包发送失败",
                event_id=event.event_id,
                error=str(exc),
            )

    # ── Agent 模式 ──

    def _match_markdown_skills(self, queue: MessageQueue, queue_key: str) -> list[Any]:
        query = self._last_user_text(queue, queue_key)
        if not query:
            return []
        return (
            self._markdown_skills.match(query, limit=3) if self._markdown_skills else []
        )

    def _last_user_text(self, queue: MessageQueue, queue_key: str) -> str:
        from neobot_app.message.queue import QueueEntryType as _QET

        # 只取「最后一条用户消息」的全部文本段作为技能匹配查询文本：
        # - 从队列末尾逆序遍历，避免把 bot 自己发送的消息（语音/图片等会自推入队列）
        #   或更早的旧话题文本算进去，导致旧技能被错误激活
        # - 优先使用 MessageQueue 注入的 bot_account（bootstrap 已按配置传入），
        #   其次回退到 config.bot.account 解析；两者都为 0/None 时不过滤（保持旧行为）
        bot_account = _safe_int(getattr(queue, "bot_account", None))
        if not bot_account and self._config is not None:
            bot_cfg = getattr(self._config, "bot", None)
            if bot_cfg is not None:
                bot_account = _safe_int(getattr(bot_cfg, "account", 0) or 0)
        for entry in reversed(queue.entries(queue_key)):
            if entry.kind != _QET.MESSAGE or entry.message is None:
                continue
            if bot_account:
                user_id = getattr(entry.message, "user_id", None)
                # 防御性解析：user_id 理论经 pydantic 校验为 int 不可达，
                # 但非数字时按 0 处理（与 bot_account 不等，消息保留），避免崩溃
                if user_id is not None and _safe_int(user_id) == bot_account:
                    continue
            parts: list[str] = []
            segments = getattr(entry.message, "message", None) or []
            for segment in segments:
                if getattr(segment, "type", None) != "text":
                    continue
                text = (segment.data or {}).get("text")
                if text:
                    parts.append(str(text))
            return " ".join(parts).strip()
        return ""

    @staticmethod
    def _render_skills(skills: list[Any]) -> str:
        lines = [
            "当用户请求与以下技能相关的事情时，先调用 skills__read_manifest 读取对应技能说明，"
            "再按说明逐步操作（如需要，可用 skills__read_resource 读取技能目录内的参考资料）。"
        ]
        for skill in skills:
            skill_id = getattr(skill, "qualified_name", None) or skill.name
            description = getattr(skill, "description", "") or ""
            lines.append(
                f'<skill id="{_xml_escape(str(skill_id))}" description="{_xml_escape(str(description))}" />'
            )
        return "\n".join(lines)

    async def _run_agent_mode(
        self,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_key: str,
    ) -> None:
        is_group = (
            event.conversation_ref is not None
            and event.conversation_ref.kind == "group"
        )
        silent_timeout = (
            self._get_group_agent_silent_timeout_seconds() if is_group else 0.0
        )
        silent_deadline = (
            monotonic_seconds() + silent_timeout if silent_timeout > 0 else 0.0
        )

        def reset_silent_deadline(extra_seconds: float = 0.0) -> None:
            nonlocal silent_deadline
            if silent_timeout <= 0:
                return
            silent_deadline = (
                monotonic_seconds() + silent_timeout + max(0.0, extra_seconds)
            )

        def silent_remaining() -> float | None:
            if silent_timeout <= 0:
                return None
            return silent_deadline - monotonic_seconds()

        def cancel_for_silence(phase: str) -> None:
            event.error = (
                f"群聊 agent 管线静默超过 {silent_timeout:.0f} 秒，"
                f"已强制关闭（阶段：{phase}）"
            )
            if not event.is_terminal:
                event.transition(ReplyState.CANCELLED)
            self._logger.warning(
                "群聊 agent 管线静默超时，强制关闭",
                event_id=event.event_id,
                queue_key=queue_key,
                phase=phase,
                timeout_seconds=silent_timeout,
            )
            self._record_debug(
                "group_agent_silent_timeout",
                event,
                queue_key=queue_key,
                phase=phase,
                timeout_seconds=silent_timeout,
            )

        heartbeat_token = SILENT_HEARTBEAT.set(reset_silent_deadline)
        try:
            await self._run_agent_mode_inner(
                event,
                queue,
                queue_key,
                silent_timeout=silent_timeout,
                reset_silent_deadline=reset_silent_deadline,
                silent_remaining=silent_remaining,
                cancel_for_silence=cancel_for_silence,
            )
        finally:
            SILENT_HEARTBEAT.reset(heartbeat_token)

    async def _run_agent_mode_inner(
        self,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_key: str,
        *,
        silent_timeout: float,
        reset_silent_deadline: Callable[[float], None],
        silent_remaining: Callable[[], float | None],
        cancel_for_silence: Callable[[str], None],
    ) -> None:
        from neobot_app.message.numbering import MessageNumbering
        from neobot_app.reply.tools import build_reply_toolset

        # 随机触发表情包发送
        await self._maybe_trigger_sticker(queue, queue_key, event)

        numbering = MessageNumbering()

        # 1. 克隆消息队列
        queue_copy = queue.clone(queue_key)

        # 2. 构建角色消息(聊天记录拆分为真实 user/assistant 消息,先于 system
        #    构建以填充消息编号映射)与 system 提示词(不含聊天记录)。
        #    每轮会变的上下文(群友信息/对方档案/印象)由 builder 渲染成 user 块,
        #    追加在 system 之后、聊天记录之前,而不是塞进 system。
        last_reply_message_id, all_new = self._resolve_last_reply(queue, queue_key)
        role_messages = await self._build_role_messages(
            event,
            queue_copy,
            queue_key,
            numbering=numbering,
            last_reply_message_id=last_reply_message_id,
            all_new=all_new,
        )
        context_messages: list[dict[str, str]] = []
        prompt = await self._build_prompt(
            event,
            queue_copy,
            queue_key,
            numbering=numbering,
            last_reply_message_id=last_reply_message_id,
            all_new=all_new,
            context_blocks=context_messages,
        )
        self._record_flow_prompt(event, queue_key, prompt)
        self._record_debug("prompt_built", event, queue_key=queue_key, prompt=prompt)

        # 注入匹配的 Markdown 技能（插件 SKILL.md）：先完成匹配与 allowed-tools 判定，
        # 供后续表情包搜索提示引用（限制激活时 search_custom_emoji 已被过滤）
        matched_skills: list[Any] = []
        if self._markdown_skills is not None:
            matched = self._match_markdown_skills(queue_copy, queue_key)
            if matched:
                matched_skills = list(matched)

        # allowed-tools 白名单：仅当本轮所有命中技能都声明了非空 allowed-tools 时才限制
        # 工具集，限制集为这些声明的并集；任一命中技能未声明（或声明为空）则不限制
        # （传 None，避免未声明技能的工具被其他技能的声明误伤）
        allowed_tools: set[str] | None = None
        if matched_skills:
            declared = [
                set(getattr(skill, "allowed_tools", None) or ())
                for skill in matched_skills
            ]
            if all(declared):
                union: set[str] = set()
                for tools in declared:
                    union.update(tools)
                allowed_tools = union

        # 表情包列表不再注入提示词:它按使用次数排序且带"已用N次",每次发出表情包都会
        # 改变 system 前缀,让整段缓存失效。改为按需工具 list_emojis / search_custom_emoji。

        # 注入 Skill 操作说明(一行摘要;完整说明用 skills__view_instructions 按需查看)
        if self._skill_manager is not None:
            skill_instructions = self._skill_manager.get_instructions()
            hidden_skill = (
                "image_parse" if getattr(self._provider, "native_vision", False) is True
                else "image_context"
            )
            skill_instructions = "\n".join(
                line for line in skill_instructions.splitlines()
                if not line.startswith(f"- {hidden_skill}:")
            )
            if skill_instructions:
                prompt += (
                    "\n\n<Skill 操作说明>\n"
                    f"{skill_instructions}\n"
                    "需要某个技能的具体操作说明、参数细节或注意事项时,"
                    "调用 skills__view_instructions 查看完整内容。"
                    "\n未直接列出调用工具的技能,其工具定义尚未加载以节省每次调用的开销;"
                    "需要使用时先调用 skills__load_tools 加载(一次可加载多个),"
                    "加载后本轮即可直接调用。"
                    "\n</Skill 操作说明>"
                )

        # 注入匹配的 Markdown 技能（插件 SKILL.md）
        if matched_skills:
            prompt += (
                "\n\n<可用技能>\n"
                + self._render_skills(matched_skills)
                + "\n</可用技能>"
            )

        # 限制说明（保持与 <可用技能> 相邻追加）
        if allowed_tools is not None:
            prompt += (
                "\n注意：当前激活技能限制了可用工具，仅允许："
                f"{', '.join(sorted(allowed_tools))}"
                "（以及始终可用的基础回复工具与技能读取工具）。"
            )

        # 原生视觉说明属于稳定内容:放进 system 提示词(跨管线逐字节相同、可缓存),
        # 不再作为对话末尾的 user 消息(那个位置随历史长度变化,永远命中不了缓存)
        native_vision_active = getattr(self._provider, "native_vision", False) is True
        if native_vision_active:
            vision_note = self._native_vision_note()
            if vision_note:
                prompt += f"\n\n{vision_note}"

        self._record_debug("prompt_built", event, queue_key=queue_key, prompt=prompt)

        # 3. 准备消息列表(system + 上下文块 + 角色消息 + 后台通知)
        event.transition(ReplyState.GENERATING)
        messages: list[dict] = [{"role": "system", "content": prompt}]
        messages.extend(context_messages)
        messages.extend(role_messages)
        if context_messages:
            self._record_debug(
                "chat_context_injected",
                event,
                queue_key=queue_key,
                injected_count=len(context_messages),
            )
        if event.background_content:
            messages.append({"role": "user", "content": event.background_content})
            _bg_kind = event.conversation_ref.kind if event.conversation_ref else ""
            _bg_id = event.conversation_ref.id if event.conversation_ref else ""
            self._logger.info(
                "orchestrator 注入后台通知（新管线初始消息）",
                event_id=event.event_id,
                pipeline_key=f"{_bg_kind}:{_bg_id}",
                notification_preview=event.background_content[:120],
            )
            self._record_debug(
                "background_notification_injected_initial",
                event,
                queue_key=queue_key,
                notification=event.background_content[:200],
            )

        # 4. 构建工具集
        reply_sent = False
        cancelled = False

        async def cancel_handler(reason: str | None = None) -> None:
            nonlocal cancelled
            cancelled = True
            event.error = reason or "agent 主动取消回复"
            if not event.is_terminal:
                event.transition(ReplyState.CANCELLED)
            self._logger.debug(
                "Agent主动取消回复",
                event_id=event.event_id,
                reason=reason,
            )

        async def send_reply_handler(
            text: str,
            reply_to: int | None = None,
            mention: list[int] | None = None,
            segments: list[str] | None = None,
            send_original: bool = False,
            images: list[int] | None = None,
            merge_text_with_image: bool = False,
        ) -> None:
            nonlocal reply_sent
            reply_sent = True
            event.generated_text = text
            if reply_to is not None:
                event.reply_to_number = reply_to
                msg_id = numbering.get_message_id(reply_to)
                await self._send_reply(
                    event,
                    text,
                    reply_to_message_id=msg_id,
                    mention_user_ids=mention,
                    segments=segments,
                    send_original=send_original,
                    images=images,
                    merge_text_with_image=merge_text_with_image,
                )
            else:
                await self._send_reply(
                    event,
                    text,
                    mention_user_ids=mention,
                    segments=segments,
                    send_original=send_original,
                    images=images,
                    merge_text_with_image=merge_text_with_image,
                )

        async def send_emoji_handler(number: int, text: str = "") -> None:
            if self._emoji_service is None:
                return
            entry = self._emoji_service.get_entry(number)
            if entry is None:
                return
            # 构建消息段：可选文字 + 图片
            segments: list[dict] = []
            if text.strip():
                segments.append({"type": "text", "data": {"text": text.strip()}})
            segments.append(prepare_image_segment(self._file_server, entry.file_path))
            await self._send_with_timeout(event.conversation_ref, segments)
            # 记录表情包使用次数
            await self._emoji_service.record_usage(number)

        async def wait_handler(seconds: int = 20) -> str:
            max_wait = self._get_max_wait_seconds()
            wait_time = max(1, min(seconds, max_wait))
            await asyncio.sleep(wait_time)
            new_entries = self._collect_new_entries(queue, queue_copy, queue_key)
            if new_entries:
                # 睡眠拦截:睡眠中被@则唤醒并注入唤醒提示词,其余消息忽略
                if self._sleeping():
                    if self._entries_have_at_mention(new_entries, queue_key=queue_key):
                        wake_prompt = self._wake_from_sleep() or ""
                        self._logger.info(
                            "睡眠中 wait 工具被@唤醒",
                            queue_key=queue_key,
                        )
                        return (
                            f"等待了 {wait_time} 秒,期间被@叫醒了。"
                            f"{wake_prompt}"
                        )
                    self._logger.info(
                        "睡眠中 wait 工具忽略新消息",
                        queue_key=queue_key,
                        count=len(new_entries),
                    )
                    return (
                        f"等待了 {wait_time} 秒,期间收到新消息,"
                        "但 Bot 正在睡觉,暂不处理。"
                    )
                # 刷新对比基准,避免多次 wait 的重复名提示基于过期快照
                nonlocal previous_entries
                previous_entries = queue_copy.entries(queue_key)
                new_text = numbering.apply_new(
                    new_entries,
                    queue_copy,
                    context_entries=queue_copy.entries(queue_key),
                    previous_entries=previous_entries,
                )
                if new_text:
                    # wait 期间首次出现的群成员:档案一并注入工具结果
                    # (登记到 rendered_user_ids 前必须真正渲染过,否则档案永远丢失)
                    if is_group:
                        from neobot_app.message.queue import QueueEntryType as _QET_W

                        new_user_ids: list[str] = []
                        for entry in new_entries:
                            if (
                                entry.kind == _QET_W.MESSAGE
                                and entry.message is not None
                            ):
                                uid = getattr(entry.message, "user_id", None)
                                if uid is not None:
                                    uid_str = str(uid)
                                    if uid_str not in rendered_user_ids:
                                        rendered_user_ids.add(uid_str)
                                        new_user_ids.append(uid_str)
                        if new_user_ids:
                            profile_service = getattr(
                                self._prompt_builder, "_profile_service", None
                            )
                            if profile_service is not None:
                                try:
                                    member_profiles = (
                                        await profile_service.render_specific_members(
                                            new_user_ids,
                                            include_archives=self._inject_member_archives(),
                                        )
                                    )
                                except Exception:
                                    member_profiles = ""
                                if member_profiles:
                                    new_text += (
                                        f"\n\n[新出现的群友档案]\n{member_profiles}"
                                    )
                    return f"等待了 {wait_time} 秒，期间收到新消息：\n{new_text}"
            return f"等待了 {wait_time} 秒，期间没有收到新消息。"

        async def react_emoji_handler(message_number: int, emoji_id: int) -> str:
            from neobot_adapter.request.message import set_msg_emoji_like
            from neobot_app.message.queue import ReactionEntry

            msg_id = numbering.get_message_id(message_number)
            if msg_id is None:
                return f"错误：消息编号 {message_number} 不存在于当前上下文中"

            await asyncio.wait_for(
                set_msg_emoji_like(message_id=msg_id, emoji_id=emoji_id),
                timeout=self._get_io_timeout_seconds(),
            )

            # 获取操作者名称（bot 自身）
            bot_name = (
                getattr(self._config.bot, "nick_name", "Bot") if self._config else "Bot"
            )

            reaction = ReactionEntry(
                target_message_id=msg_id,
                emoji_id=emoji_id,
                operator_user_id=getattr(self._config.bot, "account", 0)
                if self._config
                else 0,
                operator_name=bot_name,
            )
            # 同时推送到源队列和快照队列
            queue.push_reaction(queue_key, reaction)
            queue_copy.push_reaction(queue_key, reaction)

            from neobot_app.emoji.mapping import lookup_emoji

            emoji_info = lookup_emoji(emoji_id)
            emoji_label = emoji_info[0] if emoji_info else f"#{emoji_id}"
            return f"已对消息{message_number}做出表情回应:{emoji_label}"

        def search_emoji_handler(keyword: str) -> str:
            from neobot_app.emoji.mapping import search_emoji

            results = search_emoji(keyword)
            if not results:
                return f"未找到与「{keyword}」相关的QQ表情"
            lines = [f"搜索「{keyword}」的结果："]
            for item in results:
                lines.append(f"  ID {item['id']}: {item['name']} ({item['hint']})")
            return "\n".join(lines)

        async def speak_handler(text: str) -> str:
            if self._tts_service is None:
                return "错误：TTS 服务未配置"
            segment = await asyncio.wait_for(
                self._tts_service.synthesize_segment(text),
                timeout=self._get_io_timeout_seconds(),
            )
            await self._send_with_timeout(event.conversation_ref, [segment])
            # 记录 bot 自身发送的语音消息到队列
            self._push_self_sent_message(
                queue=queue,
                queue_copy=queue_copy,
                queue_key=queue_key,
                conv_ref=event.conversation_ref,
                text=f"[语音消息:{text}]",
            )
            return f"已发送语音消息，内容：{text[:50]}{'...' if len(text) > 50 else ''}"

        async def poke_user_handler(user_id: int) -> str:
            if conv_kind == "group":
                result = await self._call_api_with_timeout(
                    "group_poke",
                    {
                        "group_id": int(conv_id),
                        "user_id": user_id,
                    },
                )
                return (
                    f"已在群{conv_id}中戳一戳 QQ:{user_id}"
                    if self._api_succeeded(result)
                    else f"群戳一戳失败: {result}"
                )
            else:
                result = await self._call_api_with_timeout(
                    "friend_poke",
                    {
                        "user_id": user_id,
                    },
                )
                return (
                    f"已戳一戳好友 QQ:{user_id}"
                    if self._api_succeeded(result)
                    else f"好友戳一戳失败: {result}"
                )

        async def send_long_reply_handler(
            image_path: str,
            caption: str = "",
            reply_to: int | None = None,
            mention: list[int] | None = None,
            markdown: str = "",
        ) -> None:
            nonlocal reply_sent
            reply_sent = True
            conv_ref = event.conversation_ref
            # 解析消息编号 -> 实际 message_id
            reply_to_message_id = None
            if reply_to is not None:
                reply_to_message_id = numbering.get_message_id(reply_to)
            # 发送说明文字（如果有）
            if caption.strip():
                caption_segs = self._build_reply_segments(
                    text=caption.strip(),
                    conversation_kind=conv_ref.kind if conv_ref else "",
                    reply_to_message_id=reply_to_message_id,
                    mention_user_ids=mention,
                )
                await self._send_with_timeout(conv_ref, caption_segs)
            # 发送图片（不附带引用，图片单独发送）
            await send_image(
                self._file_server, self._adapter, conv_ref, Path(image_path),
                wait_response=False,
            )
            # 记录 bot 自身发送的 Markdown 图片消息到队列（仅记录 md 文本，不调用视觉模型）
            if markdown.strip():
                self._push_self_sent_message(
                    queue=queue,
                    queue_copy=queue_copy,
                    queue_key=queue_key,
                    conv_ref=conv_ref,
                    text=f"[图片信息:md内容{markdown.strip()}]",
                )

        conv_kind = event.conversation_ref.kind if event.conversation_ref else ""
        conv_id = event.conversation_ref.id if event.conversation_ref else ""
        current_user_id = None
        try:
            raw_user = getattr(event.message, "user_id", None)
            if raw_user is not None:
                current_user_id = int(raw_user)
        except (TypeError, ValueError):
            current_user_id = None
        reply_toolset = build_reply_toolset(
            send_reply_handler=send_reply_handler,
            willing_service=self._willing_service,
            numbering=numbering,
            send_emoji_handler=send_emoji_handler,
            emoji_service=self._emoji_service,
            wait_handler=wait_handler,
            react_emoji_handler=react_emoji_handler,
            search_emoji_handler=search_emoji_handler,
            cancel_handler=cancel_handler,
            tts_service=self._tts_service,
            speak_handler=speak_handler,
            poke_user_handler=poke_user_handler,
            drawing_manager=self._drawing_manager,
            scheduled_task_manager=self._scheduled_task_manager,
            problem_solver_manager=self._problem_solver_manager,
            skill_manager=self._skill_manager,
            notification_hub=self._notification_hub,
            markdown_image_converter=self._markdown_image_converter,
            send_long_reply_handler=send_long_reply_handler,
            chat_context=prompt,
            conv_kind=conv_kind,
            conv_id=conv_id,
            current_user_id=current_user_id,
            human_request=event.human_request,
            agent_history=messages,
            skills_registry=self._markdown_skills,
            allowed_tools=allowed_tools,
            wait_cooldown_seconds=self._get_wait_cooldown_seconds(),
            ai_reply_check=self._get_ai_reply_check(),            ai_reply_check_lightweight=self._get_ai_reply_check_lightweight(),
            bot_name=self._get_bot_name(),
            long_reply_fallback_template=self._get_long_reply_fallback_template(),
            long_reply_max_length=self._get_long_reply_max_length(),
            long_reply_max_sentence_count=self._get_long_reply_max_sentence_count(),
            enable_ai_reply_regenerate=self._get_enable_ai_reply_regenerate(),
            logger=self._logger,
            credential_manager=self._credential_manager,
            config=self._config,
            config_update_callback=self._config_update_callback,
            native_vision_provider=self._provider,
        )
        self._tool_executors[event.event_id] = reply_toolset.executor
        if self._skill_manager is not None and conv_kind in {"group", "private"} and str(conv_id).isdigit():
            from neobot_app.skills.agent_tools_skill import AgentToolsSkill
            from neobot_app.agent_tools.contracts import ToolContext
            shared_tools = self._skill_manager.get("agent_tools")
            if isinstance(shared_tools, AgentToolsSkill):
                flow = f"{conv_kind}:{conv_id}"
                allowed = reply_toolset.executor.agent_tool_capabilities()
                context = ToolContext(owner=f"{flow}:main", chat_flow_id=flow, user_id=current_user_id,
                                      human_request=event.human_request, allowed_tools=allowed)
                self._agent_tool_turns[event.event_id] = (shared_tools.runtime, context, messages)

        tools = reply_toolset.definitions()
        vision_context = ReplyVisionContext()
        from neobot_app.skills.image_context_skill import ImageContextSkill

        default_image_loader = ImageContextSkill(
            adapter=self._adapter,
            group_message_queue=queue_copy if conv_kind == "group" else None,
            friend_message_queue=queue_copy if conv_kind != "group" else None,
        )

        # 5. Agent 循环（外层 while 支持私聊连续会话）
        max_iterations = self._get_agent_max_iterations()
        ai_check_prompted = False
        is_private = (
            event.conversation_ref is not None
            and event.conversation_ref.kind == "private"
        )
        is_group = (
            event.conversation_ref is not None
            and event.conversation_ref.kind == "group"
        )
        group_lifespan = self._get_group_chat_reply_lifespan() if is_group else 0
        # 成本管线续用预算:基础寿命(默认5)耗尽后,若缓存命中后的继续成本
        # 低于重启管线的输入成本,可额外续用(默认20次),总寿命不超过 5+20
        cost_pipeline_extension_budget = (
            self._get_cost_pipeline_threshold()
            if is_group and group_lifespan > 0 and self._cost_pipeline_enabled()
            else 0
        )

        # 记录已渲染的群成员用户ID，用于挂起恢复时补充新成员档案
        rendered_user_ids: set[str] = set()
        if is_group:
            from neobot_app.message.queue import QueueEntryType as _QET

            for entry in queue_copy.entries(queue_key):
                if entry.kind == _QET.MESSAGE and entry.message is not None:
                    uid = getattr(entry.message, "user_id", None)
                    if uid is not None:
                        rendered_user_ids.add(str(uid))

        # pre-reply hooks：可短路跳过 Agent 循环，直接用返回文本发送
        pre_hook_text = await self._apply_pre_reply_hooks(event)
        if pre_hook_text is not None:
            event.generated_text = pre_hook_text
            self._record_debug(
                "reply_generated", event, queue_key=queue_key, reply_text=pre_hook_text
            )
            await self._send_reply(event, pre_hook_text)
            return

        # 工具输出压缩状态:已压缩的 tool_call_id 与调用名映射(压缩只改内容,
        # 不动消息顺序,assistant.tool_calls 与结果消息始终配对)
        compressed_tool_call_ids: set[str] = set()
        tool_name_by_call_id: dict[str, str] = {}
        #: 工具失败指纹 -> 连续失败次数；成功一次即清零。
        tool_failure_streak: dict[str, int] = {}

        # 回复前追加的 <当前时间> user 块:每次调用模型前追加一条最新时间,
        # 已追加的时间块保留在对话历史里(不清理),让模型能看到时间推进。
        def append_current_time_block() -> None:
            block = self._build_current_time_message()
            if block is not None:
                messages.append(block)

        previous_entries = queue_copy.entries(queue_key)
        round_index = 0
        while True:
            # 需要重新构建/续用提示词的新一轮:把较早的工具返回压缩,
            # 只保留最近 N 条完整内容,控制上下文成本
            if round_index > 0:
                self._compress_stale_tool_results(
                    messages,
                    compressed_tool_call_ids,
                    tool_name_by_call_id,
                    event=event,
                    queue_key=queue_key,
                )
            round_index += 1
            reply_sent = False
            cancelled = False
            ai_check_prompted = False

            vision_fallback_bonus = False
            for iteration in range(max_iterations + 1):
                if iteration >= max_iterations and not vision_fallback_bonus:
                    break
                # 待机熔断：进入待机后已启动的管线必须立刻停火，
                # 否则一次风暴期间仍然会把排队中的模型调用全部跑完。
                if self.is_standby():
                    self._logger.warning(
                        "Bot 已进入待机，回复管线提前结束",
                        event_id=event.event_id,
                        queue_key=queue_key,
                        iteration=iteration + 1,
                    )
                    try:
                        event.transition(ReplyState.CANCELLED)
                    except RuntimeError:
                        pass
                    return
                if self._provider is None:
                    raise RuntimeError("未配置 chat provider，无法生成回复")

                current_vision = getattr(self._provider, "native_vision", False) is True
                if current_vision != native_vision_active:
                    native_vision_active = current_vision
                    tools = reply_toolset.executor.definitions()
                    messages.append({"role": "user", "content": "[视觉能力变更] 原生视觉已关闭，图片未发送；外部图片解析工具已恢复，请按需重新解析。"})

                pipeline_key = f"{conv_kind}:{conv_id}"
                notification_text = await self._poll_background_notifications(
                    pipeline_key
                )
                if notification_text:
                    messages.append({"role": "user", "content": notification_text})
                    self._logger.info(
                        "orchestrator 注入通知到消息列表",
                        event_id=event.event_id,
                        pipeline_key=pipeline_key,
                        iteration=iteration,
                        notification_preview=notification_text[:120],
                    )
                    self._record_debug(
                        "background_notification_injected",
                        event,
                        queue_key=queue_key,
                        notification=notification_text[:200],
                    )

                if native_vision_active:
                    try:
                        await asyncio.wait_for(
                            vision_context.refresh_defaults(
                                queue=queue_copy, queue_key=queue_key, numbering=numbering,
                                loader=default_image_loader, pipeline_key=pipeline_key,
                                max_images=self._get_native_vision_default_image_count(),
                            ),
                            timeout=max(0.1, silent_remaining() or self._get_dependency_timeout_seconds()),
                        )
                    except asyncio.TimeoutError:
                        self._logger.warning("默认原生视觉图片加载超时", queue_key=queue_key)
                # 回复前:追加独立的 <当前时间> user 块(始终是最后一条消息)
                append_current_time_block()
                request_messages = (
                    vision_context.request_messages(messages) if native_vision_active else list(messages)
                )
                self._record_flow_request(
                    event, queue_key, request_messages, iteration=iteration + 1
                )
                remaining = silent_remaining()
                if remaining is not None and remaining <= 0:
                    cancel_for_silence("before_model")
                    return
                try:
                    model_timeout = (
                        max(0.1, remaining)
                        if remaining is not None
                        else self._get_model_response_timeout_seconds(event)
                    )
                    before_model = await self._emit_runtime_event(
                        "model.call.before",
                        event,
                        queue_key=queue_key,
                        iteration=iteration + 1,
                        messages=request_messages,
                        tools=tools if tools else None,
                        timeout_seconds=model_timeout,
                    )
                    if before_model.consumed and isinstance(before_model.result, dict):
                        response = before_model.result
                    else:
                        request_messages = before_model.payload.get("messages", request_messages)
                        tools = before_model.payload.get("tools", tools)
                        response = await asyncio.wait_for(
                            self._provider.chat(
                                request_messages, tools=tools if tools else None
                            ),
                            timeout=model_timeout,
                        )
                    after_model = await self._emit_runtime_event(
                        "model.call.after",
                        event,
                        queue_key=queue_key,
                        iteration=iteration + 1,
                        messages=request_messages,
                        response=response,
                    )
                    response = after_model.payload.get("response", response)
                except asyncio.TimeoutError:
                    if remaining is not None:
                        cancel_for_silence("model")
                        return
                    event.error = "AI response timed out"
                    try:
                        event.transition(ReplyState.CANCELLED)
                    except RuntimeError:
                        pass
                    self._logger.warning(
                        "agent 模式模型调用超时",
                        event_id=event.event_id,
                        queue_key=queue_key,
                        timeout_seconds=self._get_model_response_timeout_seconds(event),
                    )
                    return
                reset_silent_deadline()

                self._record_cache_request(request_messages, response)

                await self._record_context(
                    event,
                    request_messages,
                    iteration=iteration + 1,
                    stage="agent_model_call",
                    response=response,
                )

                usage = (response.get("extensions") or {}).get("usage")
                if isinstance(usage, dict) and hasattr(self._provider, "model"):
                    try:
                        conv_ref = event.conversation_ref
                        await get_usage_tracker().record(
                            module="reply_agent",
                            model_name=self._provider.model,
                            input_tokens=usage["input_tokens"],
                            output_tokens=usage["output_tokens"],
                            cache_hit_tokens=usage.get("cache_hit_tokens", 0),
                            cache_miss_tokens=usage.get("cache_miss_tokens", 0),
                            conversation_kind=conv_ref.kind if conv_ref else "",
                            conversation_id=conv_ref.id if conv_ref else "",
                        )
                        if self._balance_checker is not None:
                            await self._balance_checker.check_and_notify()
                    except Exception:
                        pass

                # 规范化：把「这一轮为什么结束」与「预算用在哪」提升为一级字段，
                # 排查截断时不必再挖 response.extensions 的嵌套结构。
                iteration_counters = _extract_usage_summary(response)
                self._record_debug(
                    "agent_iteration",
                    event,
                    queue_key=queue_key,
                    iteration=iteration + 1,
                    response=response,
                    finish_reason=_extract_finish_reason(response) or None,
                    max_tokens=getattr(self._provider, "max_tokens", None),
                    output_tokens=iteration_counters["output_tokens"],
                    reasoning_tokens=iteration_counters["reasoning_tokens"],
                )
                messages.append(response)

                vision_just_disabled = native_vision_active and (
                    getattr(self._provider, "native_vision", False) is not True
                )
                if vision_just_disabled:
                    native_vision_active = False
                    tools = reply_toolset.executor.definitions()
                    self._record_debug(
                        "native_vision_fallback", event, queue_key=queue_key,
                        degradation=getattr(self._provider, "vision_degradation", None),
                    )
                tool_calls = response.get("tool_calls")
                if not tool_calls and vision_just_disabled:
                    vision_fallback_bonus = True
                    # Retry once with the restored parser tools rather than sending
                    # an answer produced without either images or a parser.
                    messages.append({"role": "user", "content": "[原生视觉回退] 图片无法发送，非视觉模型及图片解析工具已恢复。请按需调用 image_parse__parse_image，不能声称已经看到图片。"})
                    continue
                if not tool_calls:
                    if not reply_sent:
                        content = response.get("content", "")
                        text = (
                            content.strip()
                            if isinstance(content, str)
                            else str(content)
                        )
                        if text:
                            full_check = self._get_ai_reply_check()
                            light_check = self._get_ai_reply_check_lightweight()
                            need_check = full_check
                            if not need_check and light_check:
                                pre_check = process_reply_text(
                                    text,
                                    bot_name=self._get_bot_name(),
                                    fallback_template=self._get_long_reply_fallback_template(),
                                    max_length=self._get_long_reply_max_length(),
                                    max_sentence_count=self._get_long_reply_max_sentence_count(),
                                )
                                need_check = pre_check.fallback_used
                            if need_check and not ai_check_prompted:
                                ai_check_prompted = True
                                check_prompt = self._build_ai_reply_check_prompt(text)
                                messages.append(
                                    {"role": "user", "content": check_prompt}
                                )
                                self._record_debug(
                                    "ai_reply_check_requested",
                                    event,
                                    queue_key=queue_key,
                                    reply_text=text,
                                    check_prompt=check_prompt,
                                    check_mode="full" if full_check else "lightweight",
                                )
                                continue
                            event.generated_text = text
                            self._record_debug(
                                "reply_generated",
                                event,
                                queue_key=queue_key,
                                reply_text=text,
                            )
                            await self._send_reply(event, text)
                            reply_sent = True
                        else:
                            # 空轮次：正文为空且没有工具调用。旧实现在这里直接
                            # break，事件以 COMPLETED/err=None 收尾，回复丢失且
                            # 完全不可观测；现在必须显式记录并置为 FAILED。
                            self._handle_empty_turn(
                                event,
                                response,
                                queue_key=queue_key,
                                iteration=iteration + 1,
                            )
                    break

                image_parts: list[dict] = []
                for tc in tool_calls:
                    function = tc.get("function", {}) if isinstance(tc, dict) else {}
                    if not isinstance(function, dict):
                        function = {}
                    name = str(function.get("name", ""))
                    args = _parse_tool_args(function.get("arguments"))
                    safe_args = _safe_tool_args(args)
                    self._logger.info(
                        f"工具调用: {name}",
                        event_id=event.event_id,
                        tool=name,
                        args=safe_args,
                    )
                    self._record_debug(
                        "tool_called",
                        event,
                        queue_key=queue_key,
                        iteration=iteration + 1,
                        tool_name=name,
                        tool_args=safe_args,
                    )
                    wait_extra_seconds = 0.0
                    if name == "wait":
                        raw_seconds = args.get("seconds", 20)
                        try:
                            parsed_seconds = int(raw_seconds)
                        except (ValueError, TypeError):
                            parsed_seconds = 20
                        wait_extra_seconds = float(
                            max(1, min(parsed_seconds, self._get_max_wait_seconds()))
                        )
                    reset_silent_deadline(wait_extra_seconds)
                    result: object | None = None
                    safe_result: str | None = None
                    tool_error: str | None = None
                    remaining: float | None = None
                    tool_failure_key = self._tool_failure_key(name, args)
                    try:
                        remaining = silent_remaining()
                        tool_timeout = (
                            max(0.1, remaining)
                            if remaining is not None
                            else max(
                                self._get_model_response_timeout_seconds(event),
                                wait_extra_seconds
                                + self._get_dependency_timeout_seconds(),
                            )
                        )
                        if not reply_toolset.executor.is_tool_authorized(name):
                            result = reply_toolset.executor.authorization_error(name)
                        else:
                            before_tool = await self._emit_runtime_event(
                                "tool.call.before",
                                event,
                                queue_key=queue_key,
                                iteration=iteration + 1,
                                tool_name=name,
                                # 保持可变原始参数供 before 钩子注入/改写工具调用
                                tool_args=args,
                                timeout_seconds=tool_timeout,
                            )
                            name = str(before_tool.payload.get("tool_name", name))
                            args = _parse_tool_args(
                                before_tool.payload.get("tool_args", args)
                            )
                            safe_args = _safe_tool_args(args)

                            # A hook may rewrite both tool and arguments. Recompute
                            # wait allowance and authorization from the final call.
                            wait_extra_seconds = 0.0
                            if name == "wait":
                                raw_seconds = args.get("seconds", 20)
                                try:
                                    parsed_seconds = int(raw_seconds)
                                except (ValueError, TypeError):
                                    parsed_seconds = 20
                                wait_extra_seconds = float(
                                    max(
                                        1,
                                        min(
                                            parsed_seconds,
                                            self._get_max_wait_seconds(),
                                        ),
                                    )
                                )
                            reset_silent_deadline(wait_extra_seconds)
                            remaining = silent_remaining()
                            tool_timeout = (
                                max(0.1, remaining)
                                if remaining is not None
                                else max(
                                    self._get_model_response_timeout_seconds(event),
                                    wait_extra_seconds
                                    + self._get_dependency_timeout_seconds(),
                                )
                            )
                            tool_failure_key = self._tool_failure_key(name, args)
                            if not reply_toolset.executor.is_tool_authorized(name):
                                result = reply_toolset.executor.authorization_error(
                                    name
                                )
                            elif before_tool.consumed:
                                result = before_tool.result
                            else:
                                result = await asyncio.wait_for(
                                    reply_toolset.executor.execute(name, args),
                                    timeout=tool_timeout,
                                )
                        after_tool = await self._emit_runtime_event(
                            "tool.call.after",
                            event,
                            queue_key=queue_key,
                            iteration=iteration + 1,
                            tool_name=name,
                            # after 事件不再携带原始参数，使用脱敏后的参数文本
                            tool_args=safe_args,
                            tool_result=result,
                        )
                        result = after_tool.payload.get("tool_result", result)
                        if getattr(self._provider, "native_vision", False) is True:
                            from neobot_app.skills.image_context_skill import ImageContextResult

                            if isinstance(result, ImageContextResult):
                                image_parts.extend(labelled_tool_images(result, tool_call_id=str(tc.get("id", ""))))
                        safe_result = _redacted_tool_text(result, _MAX_TOOL_LOG_CHARS)
                        result = _bounded_tool_text(result)
                    except asyncio.TimeoutError:
                        tool_error = f"工具 {name} 执行超时"
                        self._logger.warning(
                            "agent 工具调用超时",
                            event_id=event.event_id,
                            queue_key=queue_key,
                            tool=name,
                        )
                        await self._emit_runtime_event(
                            "tool.call.after",
                            event,
                            queue_key=queue_key,
                            iteration=iteration + 1,
                            tool_name=name,
                            tool_args=safe_args,
                            tool_error=tool_error,
                            timed_out=True,
                        )
                        if remaining is not None:
                            cancel_for_silence(f"tool:{name}")
                            return
                    except Exception as tool_exc:
                        # 保留失败原因：只记 error_type 的话，日志与模型都拿不到
                        # 真实原因（旧实现连 str(exc) 都没保留）。回给模型的文案
                        # 先脱敏，避免异常信息里的密钥进入 LLM 上下文。
                        raw_detail = f"{type(tool_exc).__name__}: {tool_exc}".strip()
                        detail = _scrub_secret_values(raw_detail)[:300]
                        tool_error = f"工具 {name} 执行失败：{detail}"
                        self._logger.warning(
                            f"工具调用失败: {name}",
                            event_id=event.event_id,
                            tool=name,
                            error=detail,
                        )
                        await self._emit_runtime_event(
                            "tool.call.after",
                            event,
                            queue_key=queue_key,
                            iteration=iteration + 1,
                            tool_name=name,
                            tool_args=safe_args,
                            tool_error=tool_error,
                        )
                    tool_call_id = (
                        str(tc.get("id", "")) if isinstance(tc, dict) else ""
                    )
                    if tool_call_id:
                        tool_name_by_call_id[tool_call_id] = name
                    if tool_error is not None:
                        tool_failure_streak[tool_failure_key] = (
                            tool_failure_streak.get(tool_failure_key, 0) + 1
                        )
                        failures = tool_failure_streak[tool_failure_key]
                        hint = ""
                        if failures >= _TOOL_FAILURE_HINT_AFTER:
                            # 软限制：只提示不短路。同工具同参数连续失败说明大概率是
                            # 环境/权限问题，再重试只会把推理链拖长（截断的放大器）；
                            # 但调用依旧真实执行，修复环境后立刻就能继续用。
                            hint = "\n" + self._tool_repeat_failure_hint(name, failures)
                            self._logger.warning(
                                f"工具连续失败，已附加软提示: {name}",
                                event_id=event.event_id,
                                tool=name,
                                failures=failures,
                            )
                            self._record_debug(
                                "tool_repeat_failure_hint",
                                event,
                                queue_key=queue_key,
                                iteration=iteration + 1,
                                tool_name=name,
                                tool_args=safe_args,
                                failures=failures,
                                tool_error=tool_error,
                            )
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call_id,
                                "content": f"工具调用失败：{tool_error}{hint}",
                            }
                        )
                        self._record_debug(
                            "tool_failed",
                            event,
                            queue_key=queue_key,
                            iteration=iteration + 1,
                            tool_name=name,
                            tool_args=safe_args,
                            tool_error=tool_error,
                        )
                    else:
                        tool_failure_streak.pop(tool_failure_key, None)
                        self._logger.info(
                            f"工具返回: {name}",
                            event_id=event.event_id,
                            tool=name,
                            result=safe_result,
                        )
                        self._record_debug(
                            "tool_returned",
                            event,
                            queue_key=queue_key,
                            iteration=iteration + 1,
                            tool_name=name,
                            tool_args=safe_args,
                            tool_result=safe_result,
                        )
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call_id,
                                "content": str(result),
                            }
                        )

                # 技能按需加载：模型调用 skills__load_tools 后，新工具立即补进下一轮的
                # tools 列表，不必等到下一次回复管线。
                if reply_toolset.executor.consume_tools_dirty():
                    tools = reply_toolset.executor.definitions()
                    self._logger.info(
                        "技能工具已按需加载",
                        event_id=event.event_id,
                        skills=reply_toolset.executor.activated_skill_names(),
                        tools_count=len(tools),
                    )

                # Keep history textual; all automatic/manual images are assembled
                # into a labelled user appendix at the END of every model request.
                vision_context.manual_parts.extend(image_parts)
                if vision_just_disabled:
                    messages.append({"role": "user", "content": "[原生视觉回退] 图片未发送；非视觉模型和外部图片解析工具已恢复。"})

                if reply_sent or cancelled:
                    break

                # 注入此期间的新消息
                new_entries = self._collect_new_entries(queue, queue_copy, queue_key)
                if new_entries:
                    from neobot_app.message.queue import QueueEntryType as _QET3
                    from neobot_app.prompt.role_messages import (
                        build_role_messages_from_entries,
                    )

                    new_role_messages = build_role_messages_from_entries(
                        new_entries,
                        queue_copy,
                        queue_key,
                        numbering=numbering,
                        bot_account=self._get_bot_account(),
                        include_boundary_markers=self._show_boundary_markers(),
                    )
                    if new_role_messages:
                        messages.extend(new_role_messages)
                        self._record_debug(
                            "agent_new_messages_injected",
                            event,
                            queue_key=queue_key,
                            injected_count=len(new_role_messages),
                        )
                    # 登记新消息中的用户ID,避免后续挂起恢复时重复渲染其档案
                    if is_group:
                        for entry in new_entries:
                            if (
                                entry.kind == _QET3.MESSAGE
                                and entry.message is not None
                            ):
                                uid = getattr(entry.message, "user_id", None)
                                if uid is not None:
                                    rendered_user_ids.add(str(uid))

            # 保存编号映射（每轮更新）
            event.message_number_map = numbering.mapping

            # CANCELLED 是终态；不得通过群聊寿命循环把它直接改回 GENERATING。
            if cancelled or event.state == ReplyState.CANCELLED:
                break

            # 未回复且非取消 → 异常，结束
            if not reply_sent and not cancelled:
                break

            # ── 群聊寿命机制 ──
            if is_group:
                if group_lifespan > 0:
                    group_lifespan -= 1
                    action = "cancel消耗寿命" if cancelled else "回复消耗寿命"
                    self._logger.info(
                        f"群聊回复管线{action}",
                        event_id=event.event_id,
                        queue_key=queue_key,
                        remaining_lifespan=group_lifespan,
                        cancelled=cancelled,
                    )
                    if group_lifespan <= 0:
                        # 基础寿命耗尽:成本管线续用判断(缓存命中后继续成本
                        # 低于重启管线输入成本时,额外续用,受阈值上限约束)
                        if cost_pipeline_extension_budget > 0 and self._cache_continue_cheaper_than_restart(
                            vision_context.request_messages(messages) if native_vision_active else messages,
                            prompt, queue, queue_key, numbering
                        ):
                            cost_pipeline_extension_budget -= 1
                            group_lifespan = 1
                            self._logger.info(
                                "群聊回复管线成本续用(缓存命中后继续成本低于重启管线)",
                                event_id=event.event_id,
                                queue_key=queue_key,
                                remaining_extension_budget=cost_pipeline_extension_budget,
                            )
                            self._record_debug(
                                "group_pipeline_cost_extended",
                                event,
                                queue_key=queue_key,
                                remaining_extension_budget=cost_pipeline_extension_budget,
                            )
                        else:
                            self._logger.info(
                                "群聊回复管线寿命归零，结束管线",
                                event_id=event.event_id,
                                queue_key=queue_key,
                            )
                            break

                    # 群聊挂起，等待新消息或后台通知
                    self._logger.debug(
                        "群聊管线挂起等待新消息或通知",
                        event_id=event.event_id,
                        queue_key=queue_key,
                        remaining_lifespan=group_lifespan,
                    )
                    new_entries, notification_text, wake_prompt = (
                        await self._suspend_group_chat(queue, queue_copy, queue_key)
                    )
                    if not new_entries and not notification_text:
                        self._logger.debug(
                            "群聊挂起超时，结束管线",
                            event_id=event.event_id,
                            queue_key=queue_key,
                        )
                        break

                    # 注入后台通知
                    if notification_text:
                        messages.append({"role": "user", "content": notification_text})
                        self._logger.info(
                            "注入后台通知（群聊挂起期间）",
                            event_id=event.event_id,
                            queue_key=queue_key,
                        )
                        self._record_debug(
                            "background_notification_injected_during_group_suspend",
                            event,
                            queue_key=queue_key,
                            notification=notification_text[:200],
                        )

                    # 注入睡眠唤醒提示词(挂起期间被@唤醒)
                    if wake_prompt:
                        messages.append(
                            {"role": "user", "content": f"[系统状态]{wake_prompt}"}
                        )
                        self._logger.info(
                            "注入睡眠唤醒提示词(挂起期间被@唤醒)",
                            event_id=event.event_id,
                            queue_key=queue_key,
                        )

                    # 构建增量提示并注入（角色消息 + 新成员档案说明）
                    if new_entries:
                        resume_messages = await self._build_group_chat_resume_messages(
                            new_entries,
                            queue_key,
                            rendered_user_ids,
                            numbering,
                            queue_copy,
                        )
                        # 更新已渲染用户ID集合
                        from neobot_app.message.queue import QueueEntryType as _QET2

                        for entry in new_entries:
                            if (
                                entry.kind == _QET2.MESSAGE
                                and entry.message is not None
                            ):
                                uid = getattr(entry.message, "user_id", None)
                                if uid is not None:
                                    rendered_user_ids.add(str(uid))
                        for resume_message in resume_messages:
                            messages.append(resume_message)
                        if resume_messages:
                            self._record_debug(
                                "group_chat_resume_content_injected",
                                event,
                                queue_key=queue_key,
                                injected_messages=[
                                    {
                                        "role": m.get("role"),
                                        "content": (m.get("content") or "")[:200],
                                    }
                                    for m in resume_messages
                                ],
                            )

                    # 重置静默超时计时器，避免挂起耗时触发超时保护
                    reset_silent_deadline()
                    # 重置事件状态，允许下一轮回复
                    event.state = ReplyState.GENERATING
                    event.completed_at = None
                    continue  # 继续外层 while 循环，重新进入 agent 回复流程

                # 寿命为 0（禁用寿命机制），正常结束管线
                break

            # 非私聊 → 结束（兜底）
            if not is_private:
                break

            # Count the image appendix too; the automatic image budget must not
            # bypass the existing total-context lifetime guard.
            estimated_tokens = self._estimate_tokens(
                vision_context.request_messages(messages) if native_vision_active else messages
            )
            # Token 超限 → 结束（下次消息触发管线重启）
            if estimated_tokens >= self._get_private_chat_max_tokens():
                self._logger.info(
                    "私聊token超限，结束当前会话",
                    event_id=event.event_id,
                    queue_key=queue_key,
                    estimated_tokens=estimated_tokens,
                )
                break

            # 私聊挂起，等待新消息或后台通知
            self._logger.debug(
                "私聊会话挂起等待新消息或通知",
                event_id=event.event_id,
                queue_key=queue_key,
            )
            new_entries, notification_text = await self._suspend_private_chat(
                queue, queue_copy, queue_key
            )
            if not new_entries and not notification_text:
                self._logger.debug(
                    "私聊挂起超时，结束会话",
                    event_id=event.event_id,
                    queue_key=queue_key,
                )
                break

            # 注入后台通知（视作新消息，结束挂起状态）
            if notification_text:
                messages.append({"role": "user", "content": notification_text})
                self._logger.info(
                    "注入后台通知（挂起期间）",
                    event_id=event.event_id,
                    queue_key=queue_key,
                )
                self._record_debug(
                    "background_notification_injected_during_suspend",
                    event,
                    queue_key=queue_key,
                    notification=notification_text[:200],
                )

            # 注入新消息(按发送者拆分为角色消息),继续下一轮 agent 循环
            if new_entries:
                from neobot_app.prompt.role_messages import (
                    build_role_messages_from_entries,
                )

                new_role_messages = build_role_messages_from_entries(
                    new_entries,
                    queue_copy,
                    queue_key,
                    numbering=numbering,
                    bot_account=self._get_bot_account(),
                    include_boundary_markers=self._show_boundary_markers(),
                )
                if new_role_messages:
                    messages.extend(new_role_messages)
                    self._record_debug(
                        "private_chat_new_messages_injected",
                        event,
                        queue_key=queue_key,
                        injected_count=len(new_role_messages),
                    )

        if event.state == ReplyState.GENERATING and not event.is_terminal:
            try:
                event.transition(ReplyState.COMPLETED)
            except RuntimeError:
                pass

    # ── 空轮次(模型没给正文也没调工具) ──

    @staticmethod
    def _tool_failure_key(name: str, args: object) -> str:
        """同工具 + 同参数的失败指纹（参数不可序列化时退化为 repr）。"""
        try:
            payload = json.dumps(
                args, ensure_ascii=False, sort_keys=True, default=str
            )
        except (TypeError, ValueError, RecursionError):
            payload = repr(args)
        return f"{name}|{payload}"

    @staticmethod
    def _tool_repeat_failure_hint(name: str, failures: int) -> str:
        """软提示：说明重复失败，但仍允许继续调用（工具不会被永久摘除）。"""
        return (
            f"注意：{name} 用相同参数已连续失败 {failures} 次。"
            "若判断是环境或权限问题，请不要再重复尝试，改用其它工具或直接向用户说明；"
            "如果确认问题已经修复，可以继续调用。"
        )

    @staticmethod
    def _build_empty_turn_error(
        reason: str, finish_reason: str, output_tokens: object
    ) -> str:
        if reason == EMPTY_TURN_TRUNCATED:
            return (
                "模型输出被输出上限截断：本轮没有正文也没有工具调用"
                f"（finish_reason=length, output_tokens={output_tokens}）"
            )
        return (
            "模型返回空输出：本轮没有正文也没有工具调用"
            f"（finish_reason={finish_reason or '未提供'}）"
        )

    def _handle_empty_turn(
        self,
        event: ReplyEvent,
        response: object,
        *,
        queue_key: str,
        iteration: int,
    ) -> None:
        """空轮次不再静默结束：区分成因、留痕，并把事件置为 FAILED。

        这里刻意不做重试：实测重试大概率拿不到有效输出，只会再多烧一轮
        input token。也不发兜底回复（避免群聊刷屏）。要保证的只有一件事——
        「模型没产出导致回复丢失」一定留下可检索的记录，而不是 COMPLETED。
        """
        finish_reason = _extract_finish_reason(response)
        reason = _classify_empty_turn(response)
        counters = _extract_usage_summary(response)
        output_tokens = counters["output_tokens"]
        reasoning_tokens = counters["reasoning_tokens"]

        event.error = self._build_empty_turn_error(
            reason, finish_reason, output_tokens
        )
        if not event.is_terminal:
            try:
                event.transition(ReplyState.FAILED)
            except RuntimeError:
                pass

        self._logger.warning(
            "模型空轮次：该轮没有正文也没有工具调用，回复未发出",
            event_id=event.event_id,
            queue_key=queue_key,
            iteration=iteration,
            reason=reason,
            finish_reason=finish_reason or None,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
        )
        self._record_debug(
            "empty_turn_detected",
            event,
            queue_key=queue_key,
            iteration=iteration,
            reason=reason,
            finish_reason=finish_reason or None,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
        )
        if reason == EMPTY_TURN_TRUNCATED:
            # 超限截断是成本问题，单独留一条便于直接检索/统计。
            self._record_debug(
                "empty_turn_truncated",
                event,
                queue_key=queue_key,
                iteration=iteration,
                finish_reason=finish_reason,
                output_tokens=output_tokens,
                reasoning_tokens=reasoning_tokens,
            )

    # ── 待机熔断(只保留核心服务,已启动管线立即停火) ──

    def is_standby(self) -> bool:
        """Bot 是否处于待机状态。"""
        service = getattr(self, "_standby_service", None)
        return bool(service is not None and service.is_standby())

    # ── 睡眠拦截(挂起循环 / wait 工具共用) ──

    def _sleeping(self) -> bool:
        """是否处于睡眠中(群聊不触发回复;私聊不睡眠)。"""
        service = getattr(self, "_sleep_service", None)
        return service is not None and service.is_sleeping()

    def _wake_from_sleep(self) -> str | None:
        """结束睡眠并返回唤醒提示词;未在睡眠时返回 None。"""
        service = getattr(self, "_sleep_service", None)
        if service is None or not service.is_sleeping():
            return None
        service.wake(reason="at_mention_pipeline")
        return service.wake_prompt()

    def _entries_have_at_mention(self, entries: list, *, queue_key: str) -> bool:
        """检查是否有未被硬性屏蔽的 @bot 消息(与睡眠事件入口一致)。"""
        from neobot_app.message.queue import QueueEntryType as _QET

        if self._willing_service is None:
            return False
        for entry in entries:
            if entry.kind != _QET.MESSAGE or entry.message is None:
                continue
            if self._willing_service.is_at_mentioned(entry.message):
                block_reason = self._willing_service.block_reason_for_message(
                    message=entry.message, queue_key=queue_key
                )
                if not block_reason:
                    return True
        return False

    def _collect_new_entries(
        self,
        source: MessageQueue,
        snapshot: MessageQueue,
        queue_key: str,
    ) -> list:
        """收集源队列中比快照新的条目并更新快照。

        使用指纹集合比对，而非位置分割：
        - 指纹在 snapshot 中已存在 → 不是新条目（即使推送顺序与 message_id 顺序不一致）
        - 指纹不在 snapshot 中 → 新条目（支持队列驱逐后的安全回退）
        - 已被命令系统消费的消息（mark_command_consumed）不返回，但仍加入快照，
          避免挂起循环反复拾取；命令回复已由事件入口发出，挂起管线不应再回复
        """
        from neobot_app.message.queue import QueueEntryType

        source_entries = source.entries(queue_key)
        if not source_entries:
            return []

        snapshot_entries = snapshot.entries(queue_key)

        # 收集 snapshot 中所有条目的指纹
        snapshot_fingerprints: set[str] = set()
        for entry in snapshot_entries:
            fp = entry_fingerprint(entry)
            if fp:
                snapshot_fingerprints.add(fp)

        # 在 source 中找出指纹不在 snapshot 中的新条目
        new_entries: list = []
        skipped_consumed: list = []
        for entry in source_entries:
            fp = entry_fingerprint(entry)
            if fp and fp in snapshot_fingerprints:
                continue  # 已存在于快照中
            # 命令系统已消费的消息：跳过注入（仍加入快照，避免反复收集）
            if (
                entry.kind == QueueEntryType.MESSAGE
                and entry.message is not None
                and source.is_command_consumed(queue_key, entry.message.message_id)
            ):
                skipped_consumed.append(entry)
                self._logger.debug(
                    "挂起管线跳过命令已消费消息",
                    queue_key=queue_key,
                    message_id=entry.message.message_id,
                )
                continue
            new_entries.append(entry)

        snapshot.append_entries(queue_key, new_entries + skipped_consumed)

        # 返回全部可渲染的新条目:消息 + 表情回应/戳一戳/撤回(时间戳除外)。
        # 全量构建(role_messages)会渲染这些非消息条目,增量注入必须保持一致,
        # 否则挂起/等待期间到达的回应/戳一戳/撤回会对模型"凭空消失"。
        return [
            entry
            for entry in new_entries
            if entry.kind != QueueEntryType.TIMESTAMP
        ]

    def _consume_ai_reply_blocked_entries(self, entries: list) -> list:
        if self._reply_block_registry is None:
            return entries
        consume = getattr(self._reply_block_registry, "consume_message", None)
        if not callable(consume):
            return entries
        kept = []
        for entry in entries:
            message = getattr(entry, "message", None)
            if message is not None and consume(message):
                self._logger.info("插件监听器已阻止挂起期间私聊消息触发 AI 回复")
                continue
            kept.append(entry)
        return kept

    async def _poll_background_notifications(self, pipeline_key: str) -> str | None:
        """轮询所有后台通知源，返回通知文本或 None。"""
        try:
            if self._notification_hub is not None:
                notification = await asyncio.wait_for(
                    self._notification_hub.poll(pipeline_key),
                    timeout=self._get_dependency_timeout_seconds(),
                )
                if notification:
                    self._logger.info(
                        "orchestrator._poll_background_notifications 轮询到通知",
                        pipeline_key=pipeline_key,
                        source=notification.source,
                        preview=notification.content[:120],
                    )
                    return notification.content
                return None

            # 向后兼容：未迁移到统一通知中心的后台管理器
            if self._drawing_manager is not None:
                notification = await asyncio.wait_for(
                    self._drawing_manager.poll_notification(pipeline_key),
                    timeout=self._get_dependency_timeout_seconds(),
                )
                if notification:
                    return notification

            if self._scheduled_task_manager is not None:
                notification = await asyncio.wait_for(
                    self._scheduled_task_manager.poll_notification(pipeline_key),
                    timeout=self._get_dependency_timeout_seconds(),
                )
                if notification:
                    return notification

            if self._problem_solver_manager is not None:
                notification = await asyncio.wait_for(
                    self._problem_solver_manager.poll_notification(pipeline_key),
                    timeout=self._get_dependency_timeout_seconds(),
                )
                if notification:
                    return notification
        except asyncio.TimeoutError:
            self._logger.warning(
                "后台通知轮询超时",
                pipeline_key=pipeline_key,
                timeout_seconds=self._get_dependency_timeout_seconds(),
            )

        return None

    async def _suspend_private_chat(
        self,
        source: MessageQueue,
        snapshot: MessageQueue,
        queue_key: str,
    ) -> tuple[list, str | None]:
        """挂起等待私聊新消息或后台通知。

        首条消息后额外收集一段时间；后台通知会立即中断挂起。
        返回 (新消息条目列表, 通知文本或None)。
        """
        suspend_secs = self._get_private_chat_suspend_wait_seconds()
        collect_secs = self._get_private_chat_new_message_collect_seconds()
        deadline = monotonic_seconds() + suspend_secs
        first_new_time = 0.0
        all_new_entries: list = []
        notification_text: str | None = None

        self._logger.debug(
            "私聊挂起循环开始轮询",
            queue_key=queue_key,
            suspend_secs=suspend_secs,
            collect_secs=collect_secs,
        )
        pipeline_key = f"private:{queue_key}"

        while monotonic_seconds() < deadline:
            await asyncio.sleep(1.0)
            current_new: list = []
            try:
                current_new = self._collect_new_entries(source, snapshot, queue_key)
            except Exception as exc:
                self._logger.debug(
                    "私聊挂起收集新消息异常",
                    queue_key=queue_key,
                    error=str(exc),
                )
                continue
            if current_new:
                current_new = self._consume_ai_reply_blocked_entries(current_new)
            if current_new:
                if not all_new_entries:
                    first_new_time = monotonic_seconds()
                    self._logger.debug(
                        "私聊挂起检测到首条新消息",
                        queue_key=queue_key,
                        count=len(current_new),
                    )
                all_new_entries.extend(current_new)

            # 轮询后台通知，有通知立即中断挂起
            if notification_text is None:
                notification_text = await self._poll_background_notifications(
                    pipeline_key
                )

            if notification_text:
                self._logger.debug(
                    "私聊挂起检测到后台通知，结束挂起",
                    queue_key=queue_key,
                )
                break

            if all_new_entries:
                elapsed_since_first = monotonic_seconds() - first_new_time
                if elapsed_since_first >= collect_secs:
                    self._logger.debug(
                        "私聊挂起收集窗口结束",
                        queue_key=queue_key,
                        total_new=len(all_new_entries),
                        elapsed=f"{elapsed_since_first:.1f}s",
                    )
                    break

        if all_new_entries:
            self._logger.debug(
                "私聊挂起收集到新消息",
                queue_key=queue_key,
                count=len(all_new_entries),
            )
        elif notification_text:
            self._logger.debug(
                "私聊挂起收到后台通知",
                queue_key=queue_key,
            )
        else:
            self._logger.debug(
                "私聊挂起超时未收到新消息或通知",
                queue_key=queue_key,
            )
        return all_new_entries, notification_text

    def _evaluate_single_message_willing(
        self,
        *,
        message: Any,
        queue: Any,
        queue_key: str,
    ) -> bool:
        """评估单条消息的回复意愿，与正常回复流程使用完全相同的判断逻辑。

        返回 True 表示应该回复。
        """
        if self._willing_service is None:
            return True

        sender_id = str(getattr(message, "user_id", "?"))

        # @提及 → 检查屏蔽后直接通过
        if self._willing_service.is_at_mentioned(message):
            block_reason = self._willing_service.block_reason_for_message(
                message=message, queue_key=queue_key
            )
            if block_reason:
                self._logger.info(
                    "挂起意愿判断：@提及消息被屏蔽",
                    queue_key=queue_key,
                    sender_id=sender_id,
                    reason=block_reason,
                )
                return False
            self._logger.info(
                "挂起意愿判断：@提及，直接触发回复",
                queue_key=queue_key,
                sender_id=sender_id,
            )
            return True

        # 正常意愿评估
        try:
            decision = self._willing_service.evaluate(
                message=message, queue=queue, queue_key=queue_key
            )
            self._logger.info(
                "挂起意愿判断",
                queue_key=queue_key,
                sender_id=sender_id,
                probability=f"{decision.probability:.3f}",
                should_reply=decision.should_reply,
                reasons=list(decision.reasons),
            )
            return decision.should_reply
        except Exception as exc:
            self._logger.info(
                "挂起意愿判断异常，跳过",
                queue_key=queue_key,
                sender_id=sender_id,
                error=str(exc),
            )
            return False

    async def _suspend_group_chat(
        self,
        source: MessageQueue,
        snapshot: MessageQueue,
        queue_key: str,
    ) -> tuple[list, str | None, str | None]:
        """挂起等待群聊新消息或后台通知。

        新消息需通过回复意愿判断（@提及或概率命中）才结束挂起。
        - @提及：等待 at_mention_reply_delay_seconds 收集上下文后结束挂起
        - 普通意愿命中：立即结束挂起
        - 后台通知：立即中断挂起
        - 睡眠中：非@消息忽略（不触发回复），@提及唤醒并注入唤醒提示词
        返回 (新消息条目列表, 通知文本或None, 唤醒提示词或None)；
        返回空列表且无通知表示超时。
        """
        from neobot_app.message.queue import QueueEntryType as _QET

        suspend_secs = self._get_group_chat_suspend_wait_seconds()
        at_delay = self._get_at_mention_reply_delay_seconds()
        deadline = monotonic_seconds() + suspend_secs
        all_new_entries: list = []
        notification_text: str | None = None
        wake_prompt: str | None = None
        has_willing = False
        at_mention_deadline = 0.0

        self._logger.debug(
            "群聊挂起循环开始轮询",
            queue_key=queue_key,
            suspend_secs=suspend_secs,
            at_delay=at_delay,
        )
        pipeline_key = f"group:{queue_key}"

        def _has_at_mention(entries: list) -> bool:
            """检查条目列表中是否有@提及消息。"""
            if self._willing_service is None:
                return False
            for entry in entries:
                if entry.kind != _QET.MESSAGE or entry.message is None:
                    continue
                if self._willing_service.is_at_mentioned(entry.message):
                    return True
            return False

        def _check_willing(entries: list) -> bool:
            """检查条目列表中是否有任何消息通过回复意愿判断。

            复用 _evaluate_single_message_willing，与正常回复流程使用同一套判断逻辑。
            """
            for entry in entries:
                if entry.kind != _QET.MESSAGE or entry.message is None:
                    continue
                if self._evaluate_single_message_willing(
                    message=entry.message,
                    queue=source,
                    queue_key=queue_key,
                ):
                    return True
            return False

        while monotonic_seconds() < deadline:
            await asyncio.sleep(1.0)
            current_new: list = []
            try:
                current_new = self._collect_new_entries(source, snapshot, queue_key)
            except Exception as exc:
                self._logger.debug(
                    "群聊挂起收集新消息异常",
                    queue_key=queue_key,
                    error=str(exc),
                )
                continue
            if current_new:
                current_new = self._consume_ai_reply_blocked_entries(current_new)
            if current_new:
                # 睡眠拦截:睡眠中非@消息忽略(已入快照,不会反复拾取),
                # @提及唤醒并注入唤醒提示词,与事件入口语义一致
                if self._sleeping():
                    if not self._entries_have_at_mention(
                        current_new, queue_key=queue_key
                    ):
                        self._logger.info(
                            "睡眠中,挂起管线忽略新消息",
                            queue_key=queue_key,
                            count=len(current_new),
                        )
                        continue
                    wake_prompt = self._wake_from_sleep() or ""
                    self._logger.info(
                        "睡眠中,挂起管线被@唤醒",
                        queue_key=queue_key,
                    )
                    all_new_entries.extend(current_new)
                    has_willing = True
                    at_mention_deadline = monotonic_seconds() + at_delay
                    continue
                all_new_entries.extend(current_new)
                if not has_willing:
                    if _check_willing(current_new):
                        has_willing = True
                        if _has_at_mention(current_new):
                            # @提及：启动延迟收集窗口，不立即break
                            at_mention_deadline = monotonic_seconds() + at_delay
                        else:
                            # 普通意愿命中：立即结束
                            self._logger.debug(
                                "群聊挂起普通意愿命中，立即结束挂起",
                                queue_key=queue_key,
                                count=len(all_new_entries),
                            )
                            break

            # 轮询后台通知，有通知立即中断挂起
            if notification_text is None:
                notification_text = await self._poll_background_notifications(
                    pipeline_key
                )

            if notification_text:
                self._logger.debug(
                    "群聊挂起检测到后台通知，结束挂起",
                    queue_key=queue_key,
                )
                break

            # @提及延迟窗口到期
            if at_mention_deadline > 0 and monotonic_seconds() >= at_mention_deadline:
                self._logger.debug(
                    "群聊挂起@提及收集窗口到期",
                    queue_key=queue_key,
                    total_new=len(all_new_entries),
                )
                break

        if all_new_entries:
            self._logger.debug(
                "群聊挂起收集到新消息",
                queue_key=queue_key,
                count=len(all_new_entries),
            )
        elif notification_text:
            self._logger.debug(
                "群聊挂起收到后台通知",
                queue_key=queue_key,
            )
        else:
            self._logger.debug(
                "群聊挂起超时未收到新消息或通知",
                queue_key=queue_key,
            )

        # 通知存在 → 总是返回（通知本身就是触发理由）
        if notification_text:
            return all_new_entries, notification_text, wake_prompt

        # 有意愿消息 → 返回
        if has_willing:
            return all_new_entries, None, wake_prompt

        # 超时且无意愿消息 → 不触发回复
        self._logger.debug(
            "群聊挂起超时，未收到有意愿消息或通知",
            queue_key=queue_key,
            collected_count=len(all_new_entries),
        )
        return [], None, None

    async def _build_group_chat_resume_messages(
        self,
        new_entries: list,
        queue_key: str,
        rendered_user_ids: set[str],
        numbering: Any,
        queue_copy: MessageQueue,
    ) -> list[dict[str, str]]:
        """为群聊挂起恢复构建增量消息列表。

        新消息按发送者拆分为 user/assistant 角色消息;
        新成员档案与当前时间渲染为一条 user 说明消息,附在新消息之前。
        """
        from neobot_app.message.queue import QueueEntryType
        from neobot_app.prompt.role_messages import build_role_messages_from_entries

        # 收集新消息中的用户ID
        new_user_ids: list[str] = []
        seen: set[str] = set()
        for entry in new_entries:
            if entry.kind == QueueEntryType.MESSAGE and entry.message is not None:
                uid = getattr(entry.message, "user_id", None)
                if uid is not None:
                    uid_str = str(uid)
                    if uid_str not in seen:
                        seen.add(uid_str)
                        if uid_str not in rendered_user_ids:
                            new_user_ids.append(uid_str)

        # 新消息 -> 角色消息
        role_messages = build_role_messages_from_entries(
            new_entries,
            queue_copy,
            queue_key,
            numbering=numbering,
            bot_account=self._get_bot_account(),
            include_boundary_markers=self._show_boundary_markers(),
        )

        # 新成员档案(user 块内容,不插入 system 提示词)
        new_member_text = ""
        group_name = ""
        if new_user_ids and self._prompt_builder is not None:
            profile_service = getattr(self._prompt_builder, "_profile_service", None)
            if profile_service is not None:
                member_profiles = await profile_service.render_specific_members(
                    new_user_ids,
                    include_archives=self._inject_member_archives(),
                )
                if member_profiles:
                    try:
                        group_name = await profile_service.get_group_name(queue_key)
                    except Exception:
                        group_name = ""
                    render_profiles = getattr(
                        self._prompt_builder, "build_new_member_profiles_text", None
                    )
                    if callable(render_profiles):
                        new_member_text = render_profiles(
                            member_profiles,
                            group_name=group_name,
                            group_id=queue_key,
                        )
                    else:
                        new_member_text = member_profiles

        resume_messages: list[dict[str, str]] = []

        # 说明消息(新成员档案 + 续接说明),位于新消息之前。
        # 当前时间由回复前的独立 <当前时间> user 块提供,这里不再重复。
        if new_member_text or role_messages:
            context_text = self._render_resume_context(new_member_text)
            if context_text:
                resume_messages.append({"role": "user", "content": context_text})

        resume_messages.extend(role_messages)
        return resume_messages

    def _render_resume_context(self, new_member_text: str) -> str:
        """渲染群聊挂起恢复的说明文本(模板来自 [group_chat_resume])。"""
        builder = self._prompt_builder
        render = getattr(builder, "build_group_chat_resume_text", None)
        if callable(render):
            return render(new_member_profiles=new_member_text)
        template = self._prompt_template("group_chat_resume")
        values = get_current_time_values()
        values["new_member_profiles"] = new_member_text
        return render_template(template, values)

    # ── Prompt 构建 ──

    async def _build_prompt(
        self,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_key: str,
        numbering: MessageNumbering | None = None,
        last_reply_message_id: int | None = None,
        all_new: bool = False,
        context_blocks: list[dict[str, str]] | None = None,
    ) -> str:
        # 等待该队列所有待处理的图片解析完成
        if self._image_parse_service is not None:
            image_wait_timeout: float | None = None
            if (
                event.conversation_ref is not None
                and event.conversation_ref.kind == "group"
            ):
                image_wait_timeout = self._get_group_agent_silent_timeout_seconds()
            else:
                # 私聊不能无限等：视觉模型慢/抖动时会把整条私聊回复卡在 prompt
                # 构建阶段。给一个有限上限（与视觉模型调用超时 60s 对齐并留余量），
                # 超时后未替换的图片段按原始“图片 [url]”占位进 prompt 即可。
                image_wait_timeout = self._get_private_image_wait_timeout_seconds()
            await self._image_parse_service.wait_for_queue(
                queue_key,
                timeout=image_wait_timeout,
            )

        before_prompt = await self._emit_runtime_event(
            "prompt.build.before", event, queue_key=queue_key
        )
        if before_prompt.consumed:
            return str(before_prompt.result or before_prompt.payload.get("prompt", ""))
        event.transition(ReplyState.BUILDING_PROMPT)
        if event.conversation_ref is None:
            raise ValueError("ReplyEvent.conversation_ref is None")

        if event.conversation_ref.kind == "group":
            try:
                prompt = await asyncio.wait_for(
                    self._prompt_builder.build_group_chat_prompt(
                        group_id=int(queue_key),
                        message_queue=queue,
                        numbering=numbering,
                        last_reply_message_id=last_reply_message_id,
                        all_new=all_new,
                        context_blocks=context_blocks,
                    ),
                    timeout=self._get_prompt_timeout_seconds(),
                )
                after_prompt = await self._emit_runtime_event(
                    "prompt.build.after", event, queue_key=queue_key, prompt=prompt
                )
                return str(after_prompt.payload.get("prompt", prompt))
            except asyncio.TimeoutError:
                self._logger.warning(
                    "群聊提示词构建超时",
                    event_id=event.event_id,
                    queue_key=queue_key,
                    timeout_seconds=self._get_prompt_timeout_seconds(),
                )
                raise

        try:
            prompt = await asyncio.wait_for(
                self._prompt_builder.build_friend_chat_prompt(
                    user_id=int(queue_key),
                    message_queue=queue,
                    numbering=numbering,
                    last_reply_message_id=last_reply_message_id,
                    all_new=all_new,
                    context_blocks=context_blocks,
                ),
                timeout=self._get_prompt_timeout_seconds(),
            )
            after_prompt = await self._emit_runtime_event(
                "prompt.build.after", event, queue_key=queue_key, prompt=prompt
            )
            return str(after_prompt.payload.get("prompt", prompt))
        except asyncio.TimeoutError:
            self._logger.warning(
                "私聊提示词构建超时",
                event_id=event.event_id,
                queue_key=queue_key,
                timeout_seconds=self._get_prompt_timeout_seconds(),
            )
            raise

    # ── LLM 生成 ──

    async def _build_role_messages(
        self,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_key: str,
        *,
        numbering: MessageNumbering | None = None,
        last_reply_message_id: int | None = None,
        all_new: bool = False,
    ) -> list[dict[str, str]]:
        """构建聊天记录的角色消息列表(user/assistant)。

        必须优先于 system 提示词构建(消息编号在构建过程中填充,
        system 中的 [聊天消息编号映射] 依赖这些编号)。
        """
        if self._prompt_builder is None:
            return []
        if event.conversation_ref is not None and event.conversation_ref.kind == "group":
            return await self._prompt_builder.build_group_chat_messages(
                group_id=int(queue_key),
                message_queue=queue,
                numbering=numbering,
                last_reply_message_id=last_reply_message_id,
                all_new=all_new,
            )
        return await self._prompt_builder.build_friend_chat_messages(
            user_id=int(queue_key),
            message_queue=queue,
            numbering=numbering,
            last_reply_message_id=last_reply_message_id,
            all_new=all_new,
        )

    def _resolve_last_reply(
        self,
        queue: MessageQueue,
        queue_key: str,
    ) -> tuple[int | None, bool]:
        """返回指定队列键对应的 (last_reply_message_id, all_new)。

        跟踪被禁用时返回 (None, False)。
        跟踪启用但尚未记录位置时返回 (None, True)。
        已存在最后回复位置时返回 (message_id, False)。
        """
        enable_tracking = (
            getattr(
                getattr(self._config, "chat", None), "enable_last_reply_tracking", True
            )
            if self._config
            else True
        )
        if not enable_tracking:
            return None, False
        last_msg_id = queue.get_last_reply_position(queue_key)
        if last_msg_id is None:
            return None, True
        return last_msg_id, False

    async def _generate_reply(
        self,
        event: ReplyEvent,
        prompt: str,
        role_messages: list[dict[str, str]] | None = None,
        context_messages: list[dict[str, str]] | None = None,
    ) -> str:
        event.transition(ReplyState.GENERATING)
        if self._provider is None:
            raise RuntimeError("未配置 chat provider，无法生成回复")

        messages: list[dict] = [
            {"role": "system", "content": prompt},
        ]
        if context_messages:
            messages.extend(context_messages)
        if role_messages:
            messages.extend(role_messages)
        common_image_parts: list[dict] = []
        if getattr(self._provider, "native_vision", False) is True:
            from neobot_app.skills.image_context_skill import ImageContextSkill

            loader = ImageContextSkill(adapter=self._adapter)
            loaded = await loader.load_message(
                event.message, max_images=self._get_native_vision_default_image_count(),
            )
            common_image_parts = labelled_tool_images(loaded, tool_call_id="当前消息默认图片", automatic=True)
            if not json.loads(loaded).get("ok"):
                self._logger.warning("原生视觉图片加载失败", result=str(loaded))
                messages.append({"role": "user", "content": f"[图片未加载，不能声称看过图片] {loaded}"})
        if event.background_content:
            messages.append({"role": "user", "content": event.background_content})
            self._record_debug(
                "background_notification_injected_initial",
                event,
                notification=event.background_content[:200],
            )
        # 回复前追加独立的 <当前时间> user 块
        time_block = self._build_current_time_message()
        if time_block is not None:
            messages.append(time_block)
        append_image_context(messages, common_image_parts)
        self._record_flow_request(event, self._flow_queue_key(event), messages)
        timeout = self._get_model_response_timeout_seconds(event)
        before_model = await self._emit_runtime_event(
            "model.call.before", event, messages=messages, timeout_seconds=timeout
        )
        if before_model.consumed and isinstance(before_model.result, dict):
            response = before_model.result
        else:
            messages = before_model.payload.get("messages", messages)
            try:
                response = await asyncio.wait_for(
                    self._provider.chat(messages),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                event.error = f"AI response timed out after {timeout:.0f}s"
                self._logger.warning(
                    "common 模式模型调用超时",
                    event_id=event.event_id,
                    timeout_seconds=timeout,
                )
                raise
        after_model = await self._emit_runtime_event(
            "model.call.after", event, messages=messages, response=response
        )
        response = after_model.payload.get("response", response)

        self._record_cache_request(messages, response)

        await self._record_context(
            event,
            messages,
            iteration=1,
            stage="common_model_call",
            response=response,
        )

        content = response.get("content", "")

        usage = (response.get("extensions") or {}).get("usage")
        if isinstance(usage, dict) and hasattr(self._provider, "model"):
            try:
                conv_ref = event.conversation_ref
                await get_usage_tracker().record(
                    module="reply_common",
                    model_name=self._provider.model,
                    input_tokens=usage["input_tokens"],
                    output_tokens=usage["output_tokens"],
                    cache_hit_tokens=usage.get("cache_hit_tokens", 0),
                    cache_miss_tokens=usage.get("cache_miss_tokens", 0),
                    conversation_kind=conv_ref.kind if conv_ref else "",
                    conversation_id=conv_ref.id if conv_ref else "",
                )
                if self._balance_checker is not None:
                    await self._balance_checker.check_and_notify()
            except Exception:
                pass

        text = content.strip() if isinstance(content, str) else str(content)
        event.generated_text = text
        self._record_debug("reply_generated", event, reply_text=text, response=response)
        return text

    def _build_ai_reply_check_prompt(self, text: str) -> str:
        result = process_reply_text(
            text,
            bot_name=self._get_bot_name(),
            fallback_template=self._get_long_reply_fallback_template(),
            max_length=self._get_long_reply_max_length(),
            max_sentence_count=self._get_long_reply_max_sentence_count(),
        )
        lines = [
            "[AI回复检查]",
            "你刚才准备直接发送以下回复，但配置要求先检查切分后的分条回复。",
            f"原文：{result.original_text}",
            "切分结果：",
        ]
        for index, message in enumerate(result.messages, start=1):
            lines.append(f"{index}. {message}")
        if result.fallback_used:
            lines.append(
                f"注意：因 {result.reason or '未知原因'}，已触发默认回复替换，当前切分结果为默认回复文本。"
            )
            if self._get_enable_ai_reply_regenerate():
                lines.append(
                    "默认回复不是你的原意，请重新生成一个更简短的版本（不超过"
                    f"{self._get_long_reply_max_length()}字符、不超过"
                    f"{self._get_long_reply_max_sentence_count()}条），"
                    "然后直接调用 send_reply 发送新文本，无需设置 ai_check_approved。"
                )
            else:
                lines.append(
                    "如确认使用当前默认回复，请调用 send_reply，传入原 text、"
                    "segments 为上述切分结果、ai_check_approved=true。"
                    "如不应发送任何回复，请调用 cancel。"
                )
        else:
            lines.append(
                "如果没有严重问题或歧义，请调用 send_reply，传入原 text、segments 为上述切分结果、ai_check_approved=true。"
            )
            lines.append(
                "如果切分有问题但仍要发送原文，请调用 send_reply 并设置 send_original=true；不应发送则调用 cancel。"
            )
        return "\n".join(lines)

    # ── 发送回复 ──

    async def _send_reply(
        self,
        event: ReplyEvent,
        text: str,
        reply_to_message_id: int | None = None,
        mention_user_ids: list[int] | None = None,
        segments: list[str] | None = None,
        send_original: bool = False,
        images: list[int] | None = None,
        merge_text_with_image: bool = False,
    ) -> None:
        # post-reply hooks：可对回复文本做后处理
        text = await self._apply_post_reply_hooks(event, text) or text
        return await self._sender.send_reply(
            event,
            text,
            reply_to_message_id=reply_to_message_id,
            mention_user_ids=mention_user_ids,
            segments=segments,
            send_original=send_original,
            images=images,
            merge_text_with_image=merge_text_with_image,
        )

    def _push_self_sent_message(
        self,
        queue: Any,
        queue_copy: Any,
        queue_key: str,
        conv_ref: ConversationRef,
        text: str,
    ) -> None:
        self._sender.push_self_sent_message(
            queue, queue_copy, queue_key, conv_ref, text
        )

    def _can_use_markdown_image(self, text: str) -> bool:
        return self._sender._can_use_markdown_image(text)

    async def _render_long_reply_as_image(self, text: str) -> Path:
        return await self._sender._render_long_reply_as_image(text)

    def _build_reply_messages(
        self,
        text: str,
        *,
        segments: list[str] | None = None,
        send_original: bool = False,
    ) -> list[str]:
        return self._sender._build_reply_messages(
            text, segments=segments, send_original=send_original
        )

    @staticmethod
    def _build_reply_segments(
        *,
        text: str,
        conversation_kind: str,
        reply_to_message_id: int | None = None,
        mention_user_ids: list[int] | None = None,
    ) -> list[dict]:
        return ReplySender.build_reply_segments(
            text=text,
            conversation_kind=conversation_kind,
            reply_to_message_id=reply_to_message_id,
            mention_user_ids=mention_user_ids,
        )

    def _resolve_image_entries(self, image_numbers: list[int]) -> list[Any]:
        return self._sender._resolve_image_entries(image_numbers)

    # ── 工具方法 ──

    @staticmethod
    def _api_succeeded(result: Any) -> bool:
        if result is None:
            return False
        if not isinstance(result, dict):
            return True
        status = result.get("status")
        if status is None:
            return True
        return status == "ok"

    @staticmethod
    def _build_conversation_ref(
        message: PrivateMessage | GroupMessage,
        queue_key: str,
    ) -> ConversationRef:
        from neobot_adapter.model.message import GroupMessage

        if isinstance(message, GroupMessage):
            return ConversationRef(kind="group", id=queue_key)
        # 处理合成的后台通知消息（非标准 GroupMessage/PrivateMessage 实例）
        msg_type = getattr(message, "message_type", "")
        if msg_type == "group":
            return ConversationRef(kind="group", id=queue_key)
        return ConversationRef(kind="private", id=queue_key)

    @staticmethod
    def _build_chat_context(event: ReplyEvent, queue_key: str) -> str | None:
        """构建当前聊天环境描述，注入给子 Agent。"""
        from neobot_adapter.model.message import GroupMessage

        message = event.message
        if message is None:
            return None

        sender_name = ""
        sender_id = ""
        if hasattr(message, "sender") and message.sender is not None:
            sender_name = (message.sender.card or message.sender.nickname or "").strip()
        if hasattr(message, "user_id") and message.user_id is not None:
            sender_id = str(message.user_id)

        msg_type = getattr(message, "message_type", "")
        if isinstance(message, GroupMessage) or msg_type == "group":
            group_id = getattr(message, "group_id", None) or queue_key
            lines = [
                "[当前聊天环境]",
                "会话类型：群聊",
                f"群号：{group_id}",
            ]
            if sender_name and sender_id:
                lines.append(f"消息发送者：{sender_name}（QQ：{sender_id}）")
            elif sender_id:
                lines.append(f"消息发送者QQ：{sender_id}")
            return "\n".join(lines)

        lines = [
            "[当前聊天环境]",
            "会话类型：私聊",
        ]
        if sender_name and sender_id:
            lines.append(f"聊天对象：{sender_name}（QQ：{sender_id}）")
        elif sender_id:
            lines.append(f"聊天对象QQ：{sender_id}")
        return "\n".join(lines)
