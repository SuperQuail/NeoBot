"""插件消息处理器的「交主管线」意图通道（spec(5) §1.4 R13/R14 的实现基础）。

背景：`ctx.block_ai_reply()` 只能**拦住** AI 回复，插件消息处理器没有任何
把控制权**交回**主回复管线（并携带提示词 / 声明预激活技能）的手段。本模块补上
这条通用能力（不是给小游戏开特例，第三方插件同样可用）：

- 插件在消息处理器里调用 `ctx.agent_reply(background, preactivate=[...])`；
- 该调用经 `request_agent_reply` 落到**本次事件的 EventContext**上（一次性、
  随事件对象传递、消费即清除），事件管线再走**既有**的「命令结果触发一次回复」
  通路，因此不新造管线；
- `preactivate` 里的技能名会在本轮回复构建工具表时被按需激活，使这些
  `{plugin}__{tool}` 在该轮模型调用里即可直接调用。

实现说明：处理器拿到的 `ctx` 是插件运行时上下文（每个插件一个、跨事件复用），
它不知道当前事件，所以这里用 **ContextVar** 在 `PluginHookBus.dispatch` 期间
绑定当前 EventContext；dispatch 结束后在 finally 里复位。ContextVar 是
任务/上下文作用域的，不会跨请求串台，也不留进程级可变状态。
"""

from __future__ import annotations

from collections.abc import Sequence
from contextvars import ContextVar
from typing import Any

#: 当前正在分发的事件上下文（由 PluginHookBus.dispatch 绑定；无事件时为 None）
_CURRENT_EVENT_CONTEXT: ContextVar[Any | None] = ContextVar(
    "neobot_plugin_current_event_context", default=None
)


def bind_event_context(ctx: Any) -> Any:
    """绑定当前事件上下文，返回用于复位的 token。"""
    return _CURRENT_EVENT_CONTEXT.set(ctx)


def reset_event_context(token: Any) -> None:
    """复位事件上下文绑定（必须在 finally 中调用）。"""
    try:
        _CURRENT_EVENT_CONTEXT.reset(token)
    except (ValueError, LookupError):  # pragma: no cover - 跨上下文复位时忽略
        pass


def current_event_context() -> Any | None:
    return _CURRENT_EVENT_CONTEXT.get()


def normalize_preactivate(preactivate: Any) -> tuple[str, ...]:
    """规范化预激活技能名（去空、去重、保序）。"""
    if preactivate is None:
        return ()
    if isinstance(preactivate, str) or not isinstance(preactivate, Sequence):
        values = [preactivate]
    else:
        values = list(preactivate)
    seen: list[str] = []
    for item in values:
        name = str(item or "").strip()
        if name and name not in seen:
            seen.append(name)
    return tuple(seen)


def request_agent_reply(background: Any = "", *, preactivate: Any = ()) -> bool:
    """请求「把本轮交回主回复管线」。

    返回是否登记成功；**永不抛异常**（消息路径上的任何失败都只是「这次不生效」）。
    """
    try:
        ctx = _CURRENT_EVENT_CONTEXT.get()
        if ctx is None:
            return False
        recorder = getattr(ctx, "agent_reply", None)
        if not callable(recorder):
            return False
        recorder(str(background or ""), preactivate=normalize_preactivate(preactivate))
        return True
    except Exception:
        return False


__all__ = [
    "bind_event_context",
    "current_event_context",
    "normalize_preactivate",
    "request_agent_reply",
    "reset_event_context",
]
