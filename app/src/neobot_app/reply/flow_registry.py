"""聊天流状态登记处（网页面板只读视图）。

按 pipeline_key（`group:<群号>` / `private:<QQ号>`）记录每条聊天流最近一次构建的
system 提示词、最近一次模型请求的消息列表、模型名与活动状态，供面板「聊天流」页
查看「这条聊天流现在到底发了什么给模型」。

设计约束：
- 纯内存、有界、只读：登记失败不影响回复管线，任何异常都在内部吞掉；
- 存储的是**拷贝**而不是调用方的消息列表，避免面板长期持有整段对话历史；
- 后台任务由各管理器提供 provider 聚合（绘图 / 定时任务 / 解题 / 通知中心），
  与 check_background_tasks 工具同源，不做第二套统计。
"""

from __future__ import annotations

import inspect
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from neobot_contracts.ports.logging import Logger, NullLogger

#: 最多保留多少条聊天流（超出后淘汰最久未更新的）
DEFAULT_MAX_FLOWS = 128
#: 每条聊天流最多保留多少条消息
DEFAULT_MAX_MESSAGES = 80
#: 单条消息保留的最大字符数（面板预览用，超出截断）
DEFAULT_MAX_MESSAGE_CHARS = 4000
#: system 提示词保留的最大字符数
DEFAULT_MAX_PROMPT_CHARS = 40000
#: 单条聊天流的快照最长保留时间（秒）：超过后仍可查看，只是标记为陈旧
STALE_AFTER_SECONDS = 3600.0


@dataclass
class ChatFlowState:
    """单条聊天流的最近一次运行快照。"""

    pipeline_key: str
    conversation_kind: str = ""
    conversation_id: str = ""
    system_prompt: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    model: str = ""
    iterations: int = 0
    active: bool = False
    total_messages: int = 0
    started_at: float = 0.0
    updated_at: float = 0.0


def _clip(text: str, limit: int) -> tuple[str, bool]:
    """截断文本，返回 (截断后文本, 是否被截断)。"""
    if limit <= 0 or len(text) <= limit:
        return text, False
    return text[:limit], True


class ChatFlowRegistry:
    """聊天流快照登记处：回复管线写入，网页面板读取。"""

    def __init__(
        self,
        *,
        max_flows: int = DEFAULT_MAX_FLOWS,
        max_messages: int = DEFAULT_MAX_MESSAGES,
        max_message_chars: int = DEFAULT_MAX_MESSAGE_CHARS,
        max_prompt_chars: int = DEFAULT_MAX_PROMPT_CHARS,
        logger: Logger | None = None,
    ) -> None:
        self._max_flows = max(1, int(max_flows))
        self._max_messages = max(1, int(max_messages))
        self._max_message_chars = max(200, int(max_message_chars))
        self._max_prompt_chars = max(1000, int(max_prompt_chars))
        self._logger = logger or NullLogger()
        self._flows: dict[str, ChatFlowState] = {}
        self._task_providers: dict[str, Callable[[str], Any]] = {}

    # ── 写入（仅供回复管线调用） ──

    def record_prompt(
        self,
        pipeline_key: str,
        *,
        system_prompt: str,
        model: str = "",
        conversation_kind: str = "",
        conversation_id: str = "",
    ) -> None:
        """记录本轮构建出的 system 提示词。"""
        state = self._state(pipeline_key)
        if state is None:
            return
        try:
            clipped, _ = _clip(str(system_prompt or ""), self._max_prompt_chars)
            state.system_prompt = clipped
            if model:
                state.model = model
            if conversation_kind:
                state.conversation_kind = conversation_kind
            if conversation_id:
                state.conversation_id = conversation_id
            state.updated_at = time.time()
        except Exception:
            self._logger.debug("记录聊天流提示词失败(忽略)", pipeline_key=pipeline_key)

    def record_request(
        self,
        pipeline_key: str,
        *,
        messages: list[dict[str, Any]],
        model: str = "",
        iteration: int = 0,
    ) -> None:
        """记录最近一次发给模型的消息列表（存拷贝，只保留最近 N 条）。"""
        state = self._state(pipeline_key)
        if state is None:
            return
        try:
            tail = messages[-self._max_messages :] if messages else []
            state.messages = [self._summarize_message(item) for item in tail]
            state.total_messages = len(messages or [])
            state.iterations = max(int(iteration), state.iterations)
            if model:
                state.model = model
            state.updated_at = time.time()
        except Exception:
            self._logger.debug("记录聊天流请求失败(忽略)", pipeline_key=pipeline_key)

    def set_active(self, pipeline_key: str, active: bool) -> None:
        """标记该聊天流当前是否有回复管线在运行。"""
        state = self._state(pipeline_key)
        if state is None:
            return
        try:
            state.active = bool(active)
            if active and not state.started_at:
                state.started_at = time.time()
            if not active:
                state.started_at = 0.0
            state.updated_at = time.time()
        except Exception:
            self._logger.debug("记录聊天流状态失败(忽略)", pipeline_key=pipeline_key)

    # ── 后台任务 provider ──

    def register_task_provider(
        self, name: str, provider: Callable[[str], Any]
    ) -> None:
        """注册后台任务来源：provider(pipeline_key) -> dict（可为协程）。"""
        key = str(name or "").strip()
        if not key or not callable(provider):
            return
        self._task_providers[key] = provider

    # ── 读取（网页面板） ──

    def list_flows(self) -> list[dict[str, Any]]:
        """列出全部聊天流概要，按最近更新倒序。"""
        now = time.time()
        items = [
            {
                "pipeline_key": state.pipeline_key,
                "conversation_kind": state.conversation_kind,
                "conversation_id": state.conversation_id,
                "model": state.model,
                "active": state.active,
                "iterations": state.iterations,
                "message_count": len(state.messages),
                "total_messages": state.total_messages,
                "prompt_chars": len(state.system_prompt),
                "updated_at": state.updated_at,
                "age_seconds": round(now - state.updated_at, 1) if state.updated_at else None,
                "stale": bool(
                    state.updated_at and now - state.updated_at > STALE_AFTER_SECONDS
                ),
            }
            for state in sorted(
                self._flows.values(), key=lambda item: item.updated_at, reverse=True
            )
        ]
        return items

    async def snapshot(self, pipeline_key: str) -> dict[str, Any] | None:
        """返回单条聊天流的完整快照（含 system 提示词、消息与后台任务）。"""
        state = self._flows.get(str(pipeline_key or ""))
        if state is None:
            return None
        background = await self.background_tasks(state.pipeline_key)
        return {
            **self._state_summary(state),
            "system_prompt": state.system_prompt,
            "messages": [dict(item) for item in state.messages],
            "background_tasks": background,
        }

    async def background_tasks(self, pipeline_key: str) -> dict[str, Any]:
        """聚合各管理器提供的后台任务状态；单个来源失败不影响其余来源。"""
        result: dict[str, Any] = {}
        for name, provider in list(self._task_providers.items()):
            try:
                value = provider(pipeline_key)
                if inspect.isawaitable(value):
                    value = await value
            except Exception as exc:
                result[f"{name}_error"] = str(exc)
                continue
            if isinstance(value, dict):
                result.update(value)
        return result

    # ── 内部 ──

    def _state_summary(self, state: ChatFlowState) -> dict[str, Any]:
        now = time.time()
        return {
            "pipeline_key": state.pipeline_key,
            "conversation_kind": state.conversation_kind,
            "conversation_id": state.conversation_id,
            "model": state.model,
            "active": state.active,
            "iterations": state.iterations,
            "message_count": len(state.messages),
            "total_messages": state.total_messages,
            "prompt_chars": len(state.system_prompt),
            "updated_at": state.updated_at,
            "age_seconds": round(now - state.updated_at, 1) if state.updated_at else None,
            "stale": bool(
                state.updated_at and now - state.updated_at > STALE_AFTER_SECONDS
            ),
        }

    def _state(self, pipeline_key: str) -> ChatFlowState | None:
        key = str(pipeline_key or "").strip()
        if not key:
            return None
        state = self._flows.get(key)
        if state is None:
            self._evict_if_needed()
            state = ChatFlowState(pipeline_key=key, updated_at=time.time())
            self._flows[key] = state
        return state

    def _evict_if_needed(self) -> None:
        if len(self._flows) < self._max_flows:
            return
        oldest = min(
            self._flows.values(), key=lambda item: item.updated_at or 0.0, default=None
        )
        if oldest is not None:
            self._flows.pop(oldest.pipeline_key, None)

    def _summarize_message(self, message: Any) -> dict[str, Any]:
        """把一条消息压缩成面板可展示的结构（内容截断、图片只计数）。"""
        if not isinstance(message, dict):
            text, truncated = _clip(str(message), self._max_message_chars)
            return {"role": "unknown", "content": text, "truncated": truncated}
        role = str(message.get("role") or "")
        content = message.get("content")
        parts: list[str] = []
        images = 0
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    part_type = str(part.get("type") or "")
                    if part_type in {"image_url", "image", "input_image"}:
                        images += 1
                    text = part.get("text")
                    if isinstance(text, str) and text:
                        parts.append(text)
                elif isinstance(part, str):
                    parts.append(part)
            raw = "\n".join(parts)
        else:
            raw = "" if content is None else str(content)
        text, truncated = _clip(raw, self._max_message_chars)
        entry: dict[str, Any] = {
            "role": role,
            "content": text,
            "truncated": truncated,
            "chars": len(raw),
        }
        if images:
            entry["images"] = images
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list) and tool_calls:
            entry["tool_calls"] = [
                {
                    "id": str(call.get("id") or "") if isinstance(call, dict) else "",
                    "name": _tool_call_name(call),
                    "arguments": _clip(
                        _tool_call_arguments(call), 400
                    )[0],
                }
                for call in tool_calls
            ]
        tool_call_id = message.get("tool_call_id")
        if tool_call_id:
            entry["tool_call_id"] = str(tool_call_id)
        return entry


def _tool_call_name(call: Any) -> str:
    if not isinstance(call, dict):
        return ""
    function = call.get("function")
    if isinstance(function, dict):
        return str(function.get("name") or "")
    return str(call.get("name") or "")


def _tool_call_arguments(call: Any) -> str:
    if not isinstance(call, dict):
        return ""
    function = call.get("function")
    raw = function.get("arguments") if isinstance(function, dict) else call.get("arguments")
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    try:
        import json

        return json.dumps(raw, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(raw)
