"""Cross-chat communication agent and background task manager.

Receives cross-chat relay tasks from the main agent, reads source/target chat
context, determines what to communicate, and sends notifications to target chats
via BackgroundNotificationHub.
"""

from __future__ import annotations

import asyncio
import json
import os
import traceback
from collections.abc import AsyncIterator
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from neobot_chat import Agent
from neobot_chat.providers.base import Provider
from neobot_chat.schema.protocol import ToolExecutor
from neobot_chat.schema.types import (
    ChatChunk,
    State,
    ToolAccessPolicy,
    ToolAccessRule,
    ToolDefinition,
    ToolGuardContext,
)
from neobot_chat.tools.toolset import ToolSpec, Toolset
from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.statistics.tracker import (
    CURRENT_CONVERSATION_ID,
    CURRENT_CONVERSATION_KIND,
    CURRENT_USAGE_MODULE,
    get_usage_tracker,
)
from neobot_app.time_context import monotonic_seconds

if TYPE_CHECKING:
    from neobot_adapter import OneBotAdapter
    from neobot_app.config.schemas.bot import BotConfig
    from neobot_app.message.queue_impl import MessageQueue

EXPOSED_TO_MAIN_AGENT_NAME = "cross_chat"
EXPOSED_TO_MAIN_AGENT_DESCRIPTION = (
    "跨聊天/跨群通信与信息查询。将当前聊天中的信息或指令传达给另一个聊天（群或私聊），"
    "或查询其他聊天的聊天记录并将信息回报给主 Agent。"
    "支持两种调用模式：fire_and_forget（提交后立即返回，后台执行通信任务，不阻塞回复链路）"
    "和 wait（等待通信任务完成并返回结果）。"
    "支持两种通知模式：no_response（目标聊天独立处理，不需要回应）"
    "和 response（目标聊天处理完成后回传结果给源聊天）。"
    "支持信息查询模式：获取指定聊天的聊天记录、了解其他聊天的讨论内容，"
    "使用 [mode: wait] 并在 task 中描述要查询的信息，"
    "示例 task：'[mode: wait] 获取群123456最近在聊什么，告诉我主要内容'。"
    "当用户明确要求向其他聊天传递消息、询问意见、转达信息、了解其他聊天动态时，必须委托本 agent。"
    "在 task 中使用 [mode: fire_and_forget] 或 [mode: wait] 指定调用模式，"
    "使用 [notify: no_response] 或 [notify: response] 指定通知模式。"
    "示例 task：'[mode: fire_and_forget] [notify: no_response] 告知群123456：本群用户789说hello'"
    "注意：收到跨聊天消息通知或回复时，应直接使用 send_reply 转达，"
    "绝对不要再次委托本 agent 处理这些通知和回复。"
)
EXPOSED_TO_MAIN_AGENT_SHORT_DESCRIPTION = (
    "跨聊天通信与信息查询，传递消息到其他群/私聊或查询其他聊天记录"
)

_CROSS_CHAT_CONTEXT: ContextVar[str] = ContextVar("cross_chat_context", default="")
_CROSS_CHAT_RESULT: ContextVar[str] = ContextVar("cross_chat_result", default="")
_CROSS_CHAT_TARGET_KIND: ContextVar[str] = ContextVar("cross_chat_target_kind", default="")
_CROSS_CHAT_TARGET_ID: ContextVar[str] = ContextVar("cross_chat_target_id", default="")
_CROSS_CHAT_REPORT_MODE: ContextVar[bool] = ContextVar("cross_chat_report_mode", default=False)


def _tool_def(name: str, description: str, parameters: dict[str, Any]) -> ToolDefinition:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", **parameters},
        },
    }


def _default_resolver(
    args: dict[str, Any], context: ToolGuardContext, policy: ToolAccessPolicy
) -> ToolAccessRule:
    return ToolAccessRule(action="allow")


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _safe_call_stack(skip: int = 1, max_frames: int = 10) -> str:
    """Return a safe call-stack summary string, resilient to ReadError on Windows."""
    frames: list[str] = []
    try:
        for f in traceback.extract_stack()[: -skip][-max_frames:]:
            try:
                fname = f.filename.split(os.sep)[-1] if os.sep in f.filename else f.filename.split("/")[-1]
                frames.append(f"{fname}:{f.lineno}/{f.name}")
            except Exception:
                frames.append("<?>:?")
    except Exception:
        pass
    return " <- ".join(reversed(frames)) if frames else "(unavailable)"


class CrossChatAgentConfig:
    """跨聊天通信 Agent 配置。"""

    def __init__(
        self,
        *,
        enabled: bool = True,
        timeout_seconds: float = 600.0,
        max_iterations: int = 20,
        notification_retry_seconds: int = 30,
        max_retries: int = 1,
        startup_grace_seconds: float = 3.0,
        max_tasks_per_pipeline: int = 5,
        max_history_fetch_multiplier: int = 2,
    ) -> None:
        self.enabled = enabled
        self.timeout_seconds = timeout_seconds
        self.max_iterations = max_iterations
        self.notification_retry_seconds = notification_retry_seconds
        self.max_retries = max_retries
        self.startup_grace_seconds = startup_grace_seconds
        self.max_tasks_per_pipeline = max_tasks_per_pipeline
        self.max_history_fetch_multiplier = max_history_fetch_multiplier

    @classmethod
    def from_schema(cls, config: Any | None) -> "CrossChatAgentConfig":
        if config is None:
            return cls()
        return cls(
            enabled=bool(getattr(config, "enabled", True)),
            timeout_seconds=float(getattr(config, "timeout_seconds", 600) or 600),
            max_iterations=int(getattr(config, "max_iterations", 20) or 20),
            notification_retry_seconds=int(getattr(config, "notification_retry_seconds", 30) or 30),
            max_retries=int(getattr(config, "max_retries", 1) or 0),
            startup_grace_seconds=float(getattr(config, "startup_grace_seconds", 3.0) or 3.0),
            max_tasks_per_pipeline=int(getattr(config, "max_tasks_per_pipeline", 5) or 5),
            max_history_fetch_multiplier=int(getattr(config, "max_history_fetch_multiplier", 2) or 2),
        )


@dataclass
class CrossChatTask:
    """后台跨聊天通信任务记录。"""

    task_id: str
    pipeline_key: str
    source_kind: str
    source_id: str
    target_kind: str
    target_id: str
    instruction: str
    delegate_context: str = ""
    call_mode: str = "fire_and_forget"
    notification_mode: str = "no_response"
    status: str = "running"
    result_message: str | None = None
    response_content: str | None = None
    notified: bool = False
    notification_count: int = 0
    created_at: float = field(default_factory=monotonic_seconds)


class CrossChatManager:
    """管理后台跨聊天通信任务的提交、通知与重试。"""

    def __init__(
        self,
        *,
        config: CrossChatAgentConfig | None = None,
        logger: Logger | None = None,
        notification_hub: Any = None,
        adapter: Any = None,
        group_message_queue: Any = None,
        friend_message_queue: Any = None,
        bot_config: Any = None,
    ) -> None:
        self._config = config or CrossChatAgentConfig()
        self._logger = logger or NullLogger()
        self._notification_hub = notification_hub
        self._adapter = adapter
        self._group_queue = group_message_queue
        self._friend_queue = friend_message_queue
        self._bot_config = bot_config
        self._tasks: dict[str, CrossChatTask] = {}
        self._agent: Any = None
        self._response_events: dict[str, asyncio.Event] = {}
        self._response_contents: dict[str, str] = {}

    def set_agent(self, agent: Any) -> None:
        self._agent = agent

    def set_orchestrator(self, orchestrator: Any) -> None:
        self._orchestrator = orchestrator

    def _pipeline_key(self, kind: str, conv_id: str) -> str:
        return f"{kind}:{conv_id}"

    def _get_active_task_count(self, pipeline_key: str) -> int:
        return sum(
            1 for t in self._tasks.values()
            if t.pipeline_key == pipeline_key and t.status == "running"
        )

    def _enforce_task_limit(self, pipeline_key: str) -> None:
        limit = self._config.max_tasks_per_pipeline
        if limit <= 0:
            return
        pipeline_tasks = [
            t for t in self._tasks.values()
            if t.pipeline_key == pipeline_key
        ]
        if len(pipeline_tasks) <= limit:
            return
        pipeline_tasks.sort(key=lambda t: t.created_at)
        removed = 0
        for task in pipeline_tasks:
            if len(pipeline_tasks) - removed <= limit:
                break
            if task.status == "running":
                continue
            self._tasks.pop(task.task_id, None)
            removed += 1
            self._logger.info(
                "跨聊天通信任务超出上限已自动销毁",
                task_id=task.task_id,
                pipeline_key=pipeline_key,
                status=task.status,
                limit=limit,
            )

    def get_pipeline_status(self, pipeline_key: str) -> dict[str, Any]:
        active_count = 0
        recent: list[dict[str, Any]] = []
        for task in self._tasks.values():
            if task.pipeline_key == pipeline_key:
                if task.status == "running":
                    active_count += 1
                recent.append({
                    "task_id": task.task_id,
                    "status": task.status,
                    "target_kind": task.target_kind,
                    "target_id": task.target_id,
                    "call_mode": task.call_mode,
                    "notification_mode": task.notification_mode,
                    "notified": task.notified,
                    "created_at": task.created_at,
                })
        return {
            "cross_chat_active_tasks": active_count,
            "cross_chat_recent_tasks": recent[-5:],
        }

    async def submit(self, task: CrossChatTask) -> str:
        if self._agent is None:
            return _json({"ok": False, "error": "跨聊天通信 Agent 未配置"})

        self._tasks[task.task_id] = task
        self._enforce_task_limit(task.pipeline_key)

        self._logger.info(
            "[CROSS_CHAT_DIAG] submit() 创建后台任务",
            task_id=task.task_id,
            pipeline_key=task.pipeline_key,
            target=f"{task.target_kind}:{task.target_id}",
            call_mode=task.call_mode,
            notification_mode=task.notification_mode,
            call_stack=_safe_call_stack(skip=1, max_frames=8),
        )

        bg = asyncio.create_task(self._run_cross_chat(task))
        bg.add_done_callback(lambda _: None)

        grace = min(self._config.startup_grace_seconds, 3.0)
        await asyncio.sleep(grace)
        if task.status == "failed":
            return _json({"ok": False, "error": task.result_message or "跨聊天通信任务启动失败"})

        self._logger.info(
            "后台跨聊天通信任务已启动",
            task_id=task.task_id,
            pipeline_key=task.pipeline_key,
            target=f"{task.target_kind}:{task.target_id}",
            call_mode=task.call_mode,
            notification_mode=task.notification_mode,
        )
        return _json({
            "ok": True,
            "status": "running",
            "task_id": task.task_id,
            "message": f"跨聊天通信任务已启动，目标：{task.target_kind} {task.target_id}",
        })

    async def _run_cross_chat(self, task: CrossChatTask) -> None:
        self._logger.info(
            "[CROSS_CHAT_DIAG] _run_cross_chat() 开始执行",
            task_id=task.task_id,
            is_report=_CROSS_CHAT_REPORT_MODE.get(False),
        )
        try:
            state: State = {
                "messages": [{"role": "user", "content": task.instruction}],
                "_delegate_context": task.delegate_context,
            }
            result_state = await asyncio.wait_for(
                self._agent.invoke(state),
                timeout=self._config.timeout_seconds,
            )

            result = _CROSS_CHAT_RESULT.get("")
            if not result:
                messages = result_state.get("messages", [])
                for msg in reversed(messages):
                    if msg.get("role") == "assistant" and msg.get("content"):
                        content = str(msg["content"])
                        if "send_to_chat" not in content:
                            result = content
                        break

            if not result:
                raise RuntimeError("跨聊天通信 Agent 未提交要传达的消息内容")

            task.result_message = result
            task.status = "completed"

            is_report = _CROSS_CHAT_REPORT_MODE.get(False)

            if is_report:
                self._logger.info(
                    "[CROSS_CHAT_DIAG] _run_cross_chat() 查询模式完成，跳过通知",
                    task_id=task.task_id,
                    result_length=len(result),
                )
            else:
                # 从 send_to_chat 工具调用中获取跨聊天 Agent 确定的实际目标
                parsed_kind = _CROSS_CHAT_TARGET_KIND.get("")
                parsed_id = _CROSS_CHAT_TARGET_ID.get("")
                if parsed_kind:
                    task.target_kind = parsed_kind
                if parsed_id:
                    task.target_id = parsed_id

                # 校验目标信息完整性
                if not task.target_kind or not task.target_id:
                    raise RuntimeError(
                        f"跨聊天通信目标不完整：kind={task.target_kind!r} id={task.target_id!r}"
                    )

                self._logger.info(
                    "[CROSS_CHAT_DIAG] _run_cross_chat() 即将调用 _send_notification_to_target",
                    task_id=task.task_id,
                    target=f"{task.target_kind}:{task.target_id}",
                    notification_count_before=task.notification_count,
                )
                await self._send_notification_to_target(task)

        except asyncio.TimeoutError:
            task.status = "timeout"
            task.result_message = f"跨聊天通信超时 ({self._config.timeout_seconds}s)"
            self._logger.warning("后台跨聊天通信任务超时", task_id=task.task_id)
        except Exception as exc:
            task.status = "failed"
            task.result_message = str(exc)
            self._logger.warning(
                "后台跨聊天通信任务失败",
                task_id=task.task_id,
                error=str(exc),
            )

    async def _send_notification_to_target(self, task: CrossChatTask) -> None:
        target_label = f"{task.target_kind} {task.target_id}"

        task.notification_count += 1
        self._logger.info(
            "[CROSS_CHAT_DIAG] _send_notification_to_target() 被调用",
            task_id=task.task_id,
            notification_count=task.notification_count,
            target=target_label,
            notification_mode=task.notification_mode,
            already_notified=task.notified,
            call_stack=_safe_call_stack(skip=1, max_frames=10),
        )

        notification = self._build_notification_text(task)

        if self._notification_hub is not None:
            await self._publish_hub_notification(task, notification)
            self._logger.info(
                "[CROSS_CHAT_DIAG] _send_notification_to_target() publish 完成",
                task_id=task.task_id,
                target=target_label,
                notification_count=task.notification_count,
            )
            return

        self._logger.warning("通知推送失败：notification_hub 为空", task_id=task.task_id)

    async def _publish_hub_notification(
        self, task: CrossChatTask, notification: str
    ) -> bool:
        if self._notification_hub is None:
            return False

        def _on_consumed(n: Any) -> None:
            task.notified = True
            self._logger.info(
                "[CROSS_CHAT_DIAG] 通知 on_consumed 回调触发",
                task_id=task.task_id,
            )

        pipeline_key = self._pipeline_key(task.target_kind, task.target_id)
        self._logger.info(
            "[CROSS_CHAT_DIAG] _publish_hub_notification() 即将调用 hub.publish()",
            task_id=task.task_id,
            pipeline_key=pipeline_key,
            notification_preview=notification[:120],
        )
        try:
            return await self._notification_hub.publish(
                source="cross_chat",
                kind=task.target_kind,
                conversation_id=task.target_id,
                content=notification,
                manager_name="cross_chat",
                reasons=["cross-chat communication"],
                metadata={
                    "task_id": task.task_id,
                    "source_kind": task.source_kind,
                    "source_id": task.source_id,
                    "notification_mode": task.notification_mode,
                },
                on_consumed=_on_consumed,
            )
        except Exception:
            return False

    def _build_notification_text(self, task: CrossChatTask) -> str:
        source_label = self._build_source_label(task)

        if task.notification_mode == "response":
            return (
                "<这是新的必须要回答的内容>\n"
                f"跨聊天消息通知（需要回复）\n\n"
                f"来源：{source_label}\n"
                f"传达内容：{task.result_message}\n\n"
                f"任务ID：{task.task_id}\n"
                "此消息需要回复。处理完成后，请使用 delegate 工具委托 cross_chat agent，"
                f"task 格式为：'[respond to task_id={task.task_id}] 你的回复内容'。\n"
                "注意：仅用于发送回复时使用上述 delegate 格式，"
                "转达消息本身请直接使用 send_reply，不要另外创建新的跨聊天任务。\n"
                "</这是新的必须要回答的内容>"
            )
        return (
            "<这是新的必须要回答的内容>\n"
            f"跨聊天消息通知\n\n"
            f"来源：{source_label}\n"
            f"传达内容：{task.result_message}\n\n"
            "请将此消息自然地向当前聊天成员转达。"
            "这是来自其他聊天的消息，你只需作为传话人使用 send_reply 转述即可。"
            "严禁委托 cross_chat 或创建新的跨聊天任务来处理此消息"
            "（此消息本身就是跨聊天通信的结果，不需要再次跨聊天）。\n"
            "</这是新的必须要回答的内容>"
        )

    def _build_source_label(self, task: CrossChatTask) -> str:
        """从 delegate_context 中解析中文可读的来源标签。

        delegate_context 格式示例：
          [当前聊天环境]
          会话类型：群聊
          群号：123456
          消息发送者：唐天（QQ：789）

          或私聊：
          [当前聊天环境]
          会话类型：私聊
          聊天对象：唐天（QQ：789）
        """
        import re

        ctx = task.delegate_context or ""

        # 解析会话类型
        chat_type = ""
        m = re.search(r"会话类型：(\S+)", ctx)
        if m:
            ct = m.group(1)
            chat_type = "群聊" if "群" in ct else "私聊"

        # 解析群号 / QQ号
        chat_id = ""
        m = re.search(r"群号：(\d+)", ctx)
        if m:
            chat_id = m.group(1)
        if not chat_id:
            m = re.search(r"聊天对象：.*QQ：(\d+)", ctx)
            if m:
                chat_id = m.group(1)
        if not chat_id:
            chat_id = task.source_id

        # 解析发送者 / 聊天对象
        sender_info = ""
        m = re.search(r"消息发送者：(.+)", ctx)
        if m:
            sender_info = m.group(1).strip()
        else:
            m = re.search(r"聊天对象：(.+)", ctx)
            if m:
                sender_info = m.group(1).strip()

        # 构建中文标签
        parts: list[str] = []
        if chat_type == "群聊":
            parts.append(f"群聊（群号：{chat_id}）")
        elif chat_type == "私聊":
            parts.append(f"QQ私聊（QQ号：{chat_id}）")
        else:
            # fallback: 兼容旧格式 [当前会话] kind=xxx id=xxx
            kind_map = {"group": "群聊", "private": "私聊"}
            kind_cn = kind_map.get(task.source_kind, task.source_kind)
            parts.append(f"{kind_cn}（ID：{task.source_id}）")

        if sender_info:
            parts.append(f"发言人：{sender_info}")

        return "，".join(parts)

    def register_response(self, task_id: str, response_content: str) -> None:
        """Register a response from a target chat, unblocking any waiters."""
        self._response_contents[task_id] = response_content
        event = self._response_events.get(task_id)
        if event is not None:
            event.set()

    async def wait_for_response(self, task_id: str, timeout: float = 600.0) -> str | None:
        """Wait for a response from the target chat (for wait + response mode)."""
        event = asyncio.Event()
        self._response_events[task_id] = event
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return self._response_contents.get(task_id)
        except asyncio.TimeoutError:
            return None
        finally:
            self._response_events.pop(task_id, None)
            self._response_contents.pop(task_id, None)

    async def send_response_to_source(self, task_id: str, response_content: str) -> bool:
        """Send a response from target chat back to the source chat."""
        task = self._tasks.get(task_id)
        if task is None:
            self._logger.warning("send_response_to_source: 任务不存在", task_id=task_id)
            return False

        kind_cn = "群聊" if task.target_kind == "group" else "私聊"
        id_label = "群号" if task.target_kind == "group" else "QQ号"
        target_label = f"{kind_cn}（{id_label}：{task.target_id}）"
        notification = (
            "<这是新的必须要回答的内容>\n"
            f"跨聊天回复通知\n\n"
            f"你之前委托的跨聊天通信任务（{task_id}）收到了来自 {target_label} 的回复。\n"
            f"回复内容：{response_content}\n\n"
            "请直接使用 send_reply 将此回复告知用户。"
            "严禁委托 cross_chat 或创建新的跨聊天任务来处理此回复"
            "（这是已有跨聊天任务的回复，不需要再次跨聊天）。\n"
            "</这是新的必须要回答的内容>"
        )

        if self._notification_hub is None:
            return False

        try:
            await self._notification_hub.publish(
                source="cross_chat",
                kind=task.source_kind,
                conversation_id=task.source_id,
                content=notification,
                manager_name="cross_chat",
                reasons=["cross-chat response"],
                metadata={"task_id": task_id, "is_response": True},
            )
            self._logger.info(
                "跨聊天回复已发送回源聊天",
                task_id=task_id,
                source=f"{task.source_kind}:{task.source_id}",
            )
            return True
        except Exception as exc:
            self._logger.warning(
                "跨聊天回复发送失败",
                task_id=task_id,
                error=str(exc),
            )
            return False

    async def shutdown(self) -> None:
        for task in list(self._tasks.values()):
            if task.status == "running":
                task.status = "failed"
                task.result_message = "系统关闭，任务被取消"
        self._tasks.clear()
        self._response_events.clear()
        self._response_contents.clear()


class CrossChatToolExecutor(ToolExecutor):
    """跨聊天通信 Agent 的工具执行器。"""

    def __init__(
        self,
        *,
        logger: Logger | None = None,
        adapter: Any = None,
        group_message_queue: Any = None,
        friend_message_queue: Any = None,
        bot_config: Any = None,
        max_history_fetch_multiplier: int = 2,
    ) -> None:
        self._logger = logger or NullLogger()
        self._adapter = adapter
        self._group_queue = group_message_queue
        self._friend_queue = friend_message_queue
        self._bot_config = bot_config
        self._max_history_fetch_multiplier = max_history_fetch_multiplier

    def definitions(self) -> list[ToolDefinition]:
        return [
            _tool_def(
                "get_chat_context",
                "读取源聊天的消息上下文和消息编号映射，"
                "用于理解当前聊天的讨论内容和对话环境。"
                "返回内容包括聊天记录和消息编号映射。",
                {"properties": {}, "required": []},
            ),
            _tool_def(
                "fetch_chat_messages",
                "获取指定聊天（群聊或私聊）的消息记录。"
                "如果目标聊天没有消息队列或队列过短，会自动从服务器拉取历史消息。"
                "最多允许获取 2 倍于观察窗口的消息。"
                "用于了解目标聊天的近期对话，判断传达时机和方式。",
                {
                    "properties": {
                        "kind": {
                            "type": "string",
                            "enum": ["group", "private"],
                            "description": "聊天类型：group=群聊, private=私聊",
                        },
                        "id": {
                            "type": "string",
                            "description": "群号（群聊）或 QQ 号（私聊）",
                        },
                    },
                    "required": ["kind", "id"],
                },
            ),
            _tool_def(
                "send_to_chat",
                "提交要传达给目标聊天的消息内容。"
                "消息应为自然语言，描述要向目标聊天传达的信息。"
                "调用后任务视为完成。",
                {
                    "properties": {
                        "target_kind": {
                            "type": "string",
                            "enum": ["group", "private"],
                            "description": "目标聊天类型",
                        },
                        "target_id": {
                            "type": "string",
                            "description": "目标群号或 QQ 号",
                        },
                        "message": {
                            "type": "string",
                            "description": "要传达的自然语言消息内容。应包含需要转达的核心信息，"
                            "格式自然，像是有人在替别人传话。",
                        },
                    },
                    "required": ["target_kind", "target_id", "message"],
                },
            ),
            _tool_def(
                "report_back",
                "将查询到的信息回报给主 Agent（不发送给其他聊天）。"
                "当任务只是查询信息（如获取聊天记录、了解讨论内容）"
                "而不需要向目标聊天传达消息时使用。"
                "report 内容应包含从聊天记录中提取的关键信息和分析结果。"
                "调用后任务视为完成。",
                {
                    "properties": {
                        "report": {
                            "type": "string",
                            "description": "回报给主 Agent 的信息内容，包含查询到的聊天记录摘要、"
                            "讨论主题、关键信息等。",
                        },
                    },
                    "required": ["report"],
                },
            ),
        ]

    async def execute(self, name: str, args: dict) -> str:
        if name == "get_chat_context":
            return await self._execute_get_chat_context(args)
        if name == "fetch_chat_messages":
            return await self._execute_fetch_chat_messages(args)
        if name == "send_to_chat":
            return self._execute_send_to_chat(args)
        if name == "report_back":
            return self._execute_report_back(args)
        return f"未知工具: {name}"

    async def _execute_get_chat_context(self, args: dict) -> str:
        context = _CROSS_CHAT_CONTEXT.get("")
        if not context:
            return "无聊天上下文可用（可能未通过主Agent委托调用）"
        return context

    async def _execute_fetch_chat_messages(self, args: dict) -> str:
        kind = str(args.get("kind") or "").strip().lower()
        conv_id = str(args.get("id") or "").strip()

        if kind not in ("group", "private"):
            return "错误：kind 必须为 group 或 private"

        if not conv_id:
            return "错误：id 不能为空"

        if kind == "group":
            queue = self._group_queue
            obs_window = getattr(
                getattr(self._bot_config, "chat", None),
                "max_group_chat_observations", 100,
            )
        else:
            queue = self._friend_queue
            obs_window = getattr(
                getattr(self._bot_config, "chat", None),
                "max_friend_chat_observations", 100,
            )

        if queue is None:
            return f"错误：{kind} 类型的消息队列未配置"

        current_size = queue.size(conv_id)
        need_fetch = current_size < obs_window

        if need_fetch and self._adapter is not None:
            fetch_count = min(
                obs_window * self._max_history_fetch_multiplier,
                200,
            )
            try:
                if kind == "group":
                    history = await self._adapter.get_group_msg_history(
                        group_id=int(conv_id),
                        count=fetch_count,
                    )
                else:
                    history = await self._adapter.get_friend_msg_history(
                        user_id=int(conv_id),
                        count=fetch_count,
                    )

                messages = getattr(history, "data", None)
                if messages is None:
                    messages = getattr(history, "messages", None)
                if messages is None and isinstance(history, dict):
                    messages = history.get("data") or history.get("messages")

                if messages and isinstance(messages, list):
                    for msg_data in reversed(messages):
                        queue.push_history(conv_id, msg_data)
                    new_size = queue.size(conv_id)
                    self._logger.info(
                        f"已拉取 {kind} {conv_id} 的历史消息",
                        fetched=len(messages),
                        queue_size=new_size,
                    )
                else:
                    return f"未获取到 {kind} {conv_id} 的历史消息（API 返回为空）"

            except Exception as exc:
                self._logger.warning(
                    f"拉取历史消息失败: {kind} {conv_id}",
                    error=str(exc),
                )
                if current_size == 0:
                    return f"错误：无法获取 {kind} {conv_id} 的消息（队列为空且历史拉取失败：{exc}）"

        text = queue.to_text(conv_id)
        if not text:
            return f"{kind} {conv_id} 当前没有消息记录"

        label = "群聊" if kind == "group" else "私聊"
        return f"<{label} {conv_id} 的消息记录>\n{text}\n</{label} {conv_id} 的消息记录>"

    def _execute_send_to_chat(self, args: dict) -> str:
        target_kind = str(args.get("target_kind") or "").strip().lower()
        target_id = str(args.get("target_id") or "").strip()
        message = str(args.get("message") or "").strip()

        if target_kind not in ("group", "private"):
            return "错误：target_kind 必须为 group 或 private"

        if not target_id:
            return "错误：target_id 不能为空"

        if not message:
            return "错误：message 不能为空"

        _CROSS_CHAT_RESULT.set(message)
        _CROSS_CHAT_TARGET_KIND.set(target_kind)
        _CROSS_CHAT_TARGET_ID.set(target_id)
        _CROSS_CHAT_REPORT_MODE.set(False)
        return _json({
            "ok": True,
            "status": "submitted",
            "target": f"{target_kind}:{target_id}",
            "message_preview": message[:200],
        })

    def _execute_report_back(self, args: dict) -> str:
        report = str(args.get("report") or "").strip()

        if not report:
            return "错误：report 不能为空"

        _CROSS_CHAT_RESULT.set(report)
        _CROSS_CHAT_REPORT_MODE.set(True)
        return _json({
            "ok": True,
            "status": "reported",
            "report_preview": report[:200],
        })


def _build_system_prompt(config: CrossChatAgentConfig | None, *, peer_descriptions: str = "") -> str:
    cfg = config or CrossChatAgentConfig()
    return (
        "你是跨聊天通信 Agent (cross_chat)，负责在不同聊天（群聊/私聊）之间传递信息，"
        "以及查询其他聊天的记录并回报。\n\n"
        "工作模式：\n\n"
        "A) 跨聊天通信模式（发送消息到目标聊天）：\n"
        "1. 使用 get_chat_context 获取源聊天的上下文，了解当前正在讨论什么\n"
        "2. 如需了解目标聊天的近期对话以判断传达时机，使用 fetch_chat_messages 拉取目标聊天消息\n"
        "3. 结合源聊天上下文和目标聊天上下文，确定要传达的内容和方式\n"
        "4. 使用 send_to_chat 提交你要传达给目标聊天的消息\n\n"
        "B) 信息查询模式（获取聊天记录回报主 Agent）：\n"
        "1. 使用 fetch_chat_messages 拉取指定聊天的消息记录\n"
        "2. 分析聊天记录，提取关键信息：讨论主题、重要消息、用户动态等\n"
        "3. 使用 report_back 将分析结果回报给主 Agent\n"
        "4. 如果同时需要了解源聊天上下文，可使用 get_chat_context\n\n"
        "通信原则：\n"
        "- 准确转达源聊天的核心信息，不添油加醋，不歪曲原意\n"
        "- 考虑目标聊天的上下文，判断传达时机是否合适\n"
        "- 如果目标聊天正在讨论不相关的话题，可在消息中建议合适的传达时机\n"
        "- 传达格式应自然，像是有人在替别人传话，包含必要的背景信息\n"
        "- 如果源聊天信息不足以确定要传达什么，使用 get_chat_context 获取更多上下文\n"
        "- fetch_chat_messages 最多可拉取 2 倍观察窗口的历史消息，如仍不足应基于已有信息判断\n\n"
        "查询回报原则：\n"
        "- 根据任务描述判断是通信模式还是查询模式：涉及查询、了解、查看聊天的使用查询模式\n"
        "- 查询回报时应提取关键信息，结构化地呈现，让主 Agent 可以直接使用\n"
        "- 如果查询不到有效信息，在 report 中如实说明\n\n"
        "格式要求：\n"
        "- 通信模式必须使用 send_to_chat 提交最终要传达的消息\n"
        "- 查询模式必须使用 report_back 提交回报内容\n"
        "- 一个任务中只能使用 send_to_chat 或 report_back 之一，不能两者都使用\n"
        "- send_to_chat 的 message 参数应为自然语言，描述要向目标聊天传达的内容\n"
        f"{peer_descriptions}\n"
        f"- 超时时间: {cfg.timeout_seconds} 秒\n"
    )


def build_cross_chat_toolset(
    *,
    config: CrossChatAgentConfig | None = None,
    logger: Logger | None = None,
    adapter: Any = None,
    group_message_queue: Any = None,
    friend_message_queue: Any = None,
    bot_config: Any = None,
    policy: ToolAccessPolicy | None = None,
) -> Toolset:
    cfg = config or CrossChatAgentConfig()
    executor = CrossChatToolExecutor(
        logger=logger,
        adapter=adapter,
        group_message_queue=group_message_queue,
        friend_message_queue=friend_message_queue,
        bot_config=bot_config,
        max_history_fetch_multiplier=cfg.max_history_fetch_multiplier,
    )
    specs = [
        ToolSpec(definition=d, access_resolver=_default_resolver)
        for d in executor.definitions()
    ]
    return Toolset(executor=executor, specs=specs, policy=policy or ToolAccessPolicy())


class CrossChatAgent:
    """LLM-backed agent dedicated to cross-chat communication."""

    def __init__(
        self,
        provider: Provider,
        *,
        config: CrossChatAgentConfig | None = None,
        logger: Logger | None = None,
        manager: CrossChatManager | None = None,
        toolset: Toolset | None = None,
        peer_descriptions: str = "",
    ) -> None:
        cfg = config or CrossChatAgentConfig()
        self._logger = logger or NullLogger()
        self.description = EXPOSED_TO_MAIN_AGENT_DESCRIPTION
        self._manager = manager
        self._config = cfg
        self._toolset = toolset
        self.tool_definitions = toolset.definitions() if toolset else []

        async def _record_usage(model_name, input_tokens, output_tokens):
            await get_usage_tracker().record(
                module=CURRENT_USAGE_MODULE.get(""),
                model_name=model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                conversation_kind=CURRENT_CONVERSATION_KIND.get(""),
                conversation_id=CURRENT_CONVERSATION_ID.get(""),
            )

        self._agent = Agent(
            provider,
            toolset=self._toolset,
            description=self.description,
            system_prompt=_build_system_prompt(cfg, peer_descriptions=peer_descriptions),
            on_model_usage=_record_usage,
            max_iterations=cfg.max_iterations,
            command_timeout=cfg.timeout_seconds,
            logger=logger or NullLogger(),
        )

    def _parse_modes(self, instruction: str) -> tuple[str, str, str, str]:
        """Extract mode markers from instruction text.

        Returns (clean_instruction, call_mode, notification_mode, target_spec).
        """
        import re

        call_mode = "fire_and_forget"
        notif_mode = "no_response"
        target_kind = ""
        target_id = ""

        m = re.search(r"\[mode:\s*(\w+)\]", instruction, re.IGNORECASE)
        if m:
            mode_val = m.group(1).lower()
            if mode_val in ("wait", "fire_and_forget", "fire_and_forget"):
                call_mode = mode_val
            instruction = instruction[:m.start()] + instruction[m.end():]

        m = re.search(r"\[notify:\s*(\w+)\]", instruction, re.IGNORECASE)
        if m:
            notif_val = m.group(1).lower()
            if notif_val in ("no_response", "response"):
                notif_mode = notif_val
            instruction = instruction[:m.start()] + instruction[m.end():]

        m = re.search(
            r"(?:告诉|通知|发给|告知)\s*(群|私聊|好友)\s*(\d+)",
            instruction,
        )
        if m:
            k = m.group(1)
            target_kind = "group" if k == "群" else "private"
            target_id = m.group(2)

        return instruction.strip(), call_mode, notif_mode, target_kind, target_id

    async def invoke(self, state: State) -> State:
        messages = state.get("messages", [])
        last_msg = messages[-1]["content"] if messages else ""
        instruction = str(last_msg) if last_msg else ""

        clean_instr, call_mode, notif_mode, target_kind, target_id = self._parse_modes(instruction)

        self._logger.info(
            "[CROSS_CHAT_DIAG] CrossChatAgent.invoke() 入口",
            call_mode=call_mode,
            notif_mode=notif_mode,
            target_kind=target_kind,
            target_id=target_id,
            instruction_preview=clean_instr[:120] if clean_instr else "(empty)",
            is_response="respond to task_id=" in instruction.lower(),
        )

        if "respond to task_id=" in instruction.lower():
            return await self._handle_response(state, instruction)

        if call_mode == "fire_and_forget" and self._manager is not None:
            return await self._invoke_fire_and_forget(
                state, clean_instr, call_mode, notif_mode, target_kind, target_id
            )

        return await self._invoke_wait(
            state, clean_instr, call_mode, notif_mode
        )

    async def _invoke_fire_and_forget(
        self,
        state: State,
        instruction: str,
        call_mode: str,
        notif_mode: str,
        target_kind: str,
        target_id: str,
    ) -> State:
        delegate_context = str(state.get("_delegate_context") or "")

        source_kind, source_id = self._parse_source_from_context(delegate_context)

        pipeline_key = f"{source_kind}:{source_id}"

        task = CrossChatTask(
            task_id=f"xchat_{uuid4().hex[:12]}",
            pipeline_key=pipeline_key,
            source_kind=source_kind,
            source_id=source_id,
            target_kind=target_kind,
            target_id=target_id,
            instruction=instruction,
            delegate_context=delegate_context,
            call_mode=call_mode,
            notification_mode=notif_mode,
        )

        result_json = await self._manager.submit(task)
        result = json.loads(result_json)

        if result.get("ok"):
            ack = (
                f"已提交跨聊天通信任务 (task_id={result['task_id']})。"
                f"目标：{target_kind or '待Agent判断'} {target_id or '待Agent判断'}。"
                f"任务将在后台执行，不阻塞当前回复。"
            )
        else:
            ack = f"跨聊天通信任务提交失败：{result.get('error', '未知错误')}"

        return {
            **state,
            "messages": [
                *state.get("messages", []),
                {"role": "assistant", "content": ack},
            ],
        }

    async def _invoke_wait(
        self,
        state: State,
        instruction: str,
        call_mode: str,
        notif_mode: str,
    ) -> State:
        token_ctx = _CROSS_CHAT_CONTEXT.set(
            str(state.get("_delegate_context") or "")
        )
        token_mod = CURRENT_USAGE_MODULE.set("agent:cross_chat")

        delegate_context = str(state.get("_delegate_context") or "")
        source_kind, source_id = self._parse_source_from_context(delegate_context)

        try:
            invoke_state = {
                "messages": [{"role": "user", "content": instruction}],
                "_delegate_context": delegate_context,
            }
            result_state = await self._agent.invoke(invoke_state)

            result = _CROSS_CHAT_RESULT.get("")
            final_messages = list(result_state.get("messages", []))
            is_report = _CROSS_CHAT_REPORT_MODE.get(False)

            if result and is_report:
                final_messages.append({
                    "role": "assistant",
                    "content": result,
                })
            elif result and self._manager is not None:
                target_kind = _CROSS_CHAT_TARGET_KIND.get("")
                target_id = _CROSS_CHAT_TARGET_ID.get("")
                task = CrossChatTask(
                    task_id=f"xchat_{uuid4().hex[:12]}",
                    pipeline_key=f"{source_kind}:{source_id}",
                    source_kind=source_kind,
                    source_id=source_id,
                    target_kind=target_kind or "group",
                    target_id=target_id or "",
                    instruction=instruction,
                    delegate_context=delegate_context,
                    call_mode=call_mode,
                    notification_mode=notif_mode,
                    result_message=result,
                )
                await self._manager._send_notification_to_target(task)

                if notif_mode == "response":
                    response = await self._manager.wait_for_response(
                        task.task_id,
                        timeout=self._config.timeout_seconds,
                    )
                    if response:
                        final_messages.append({
                            "role": "assistant",
                            "content": f"目标聊天已回复：{response}",
                        })
                        task.response_content = response
                    else:
                        final_messages.append({
                            "role": "assistant",
                            "content": "等待目标聊天回复超时。",
                        })

            return {**state, "messages": [*state.get("messages", []), *final_messages]}

        finally:
            _CROSS_CHAT_CONTEXT.reset(token_ctx)
            CURRENT_USAGE_MODULE.reset(token_mod)

    async def _handle_response(self, state: State, instruction: str) -> State:
        import re
        m = re.search(r"task_id=(\S+)\]", instruction)
        if not m:
            return {
                **state,
                "messages": [
                    *state.get("messages", []),
                    {"role": "assistant", "content": "错误：未找到 task_id"},
                ],
            }

        task_id = m.group(1).rstrip("]")
        response_text = instruction[instruction.index("]") + 1:].strip() if "]" in instruction else instruction

        if self._manager is not None:
            ok = await self._manager.send_response_to_source(task_id, response_text)
            if ok:
                self._manager.register_response(task_id, response_text)
                ack = f"已发送跨聊天回复到源聊天 (task_id={task_id})。"
            else:
                ack = f"跨聊天回复发送失败 (task_id={task_id})。"
        else:
            ack = "跨聊天通信管理器未配置，无法发送回复。"

        return {
            **state,
            "messages": [
                *state.get("messages", []),
                {"role": "assistant", "content": ack},
            ],
        }

    @staticmethod
    def _parse_source_from_context(context: str) -> tuple[str, str]:
        import re
        m = re.search(r"kind=(\w+)\s+id=(\S+)", context)
        if m:
            return m.group(1), m.group(2)
        return "group", ""

    async def stream_invoke(self, state: State) -> AsyncIterator[ChatChunk]:
        token_ctx = _CROSS_CHAT_CONTEXT.set(
            str(state.get("_delegate_context") or "")
        )
        token_mod = CURRENT_USAGE_MODULE.set("agent:cross_chat")
        try:
            async for chunk in self._agent.stream_invoke(state):
                yield chunk
        finally:
            _CROSS_CHAT_CONTEXT.reset(token_ctx)
            CURRENT_USAGE_MODULE.reset(token_mod)

    async def close(self) -> None:
        await self._agent.close()


def build_cross_chat_agent(
    provider: Provider,
    *,
    config: CrossChatAgentConfig | Any = None,
    logger: Logger | None = None,
    manager: CrossChatManager | None = None,
    adapter: Any = None,
    group_message_queue: Any = None,
    friend_message_queue: Any = None,
    bot_config: Any = None,
    peer_descriptions: str = "",
) -> CrossChatAgent:
    cfg = (
        config if isinstance(config, CrossChatAgentConfig)
        else CrossChatAgentConfig.from_schema(config)
    )
    toolset = build_cross_chat_toolset(
        config=cfg,
        logger=logger,
        adapter=adapter,
        group_message_queue=group_message_queue,
        friend_message_queue=friend_message_queue,
        bot_config=bot_config,
    )
    agent = CrossChatAgent(
        provider=provider, config=cfg, logger=logger, manager=manager, toolset=toolset,
        peer_descriptions=peer_descriptions,
    )
    if manager is not None:
        manager.set_agent(agent._agent)
    return agent
