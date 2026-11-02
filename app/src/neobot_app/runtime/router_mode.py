"""Router 模式：按聊天流启用的受限工具面与任务表注入。

设计边界：

- 本服务只记录「哪个聊天流处于 Router 模式」，以及插件注册的任务表
  provider；具体任务的创建/推进/取消全部由 dsh_router 插件负责。
- 没有插件时永远不会有会话被激活，普通聊天流的工具面与提示词完全不变。
- 状态只保存在内存：进程重启后复位。插件在重连 daemon 后会重新对账任务，
  需要继续路由时再显式 activate。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

#: 任务表 provider：入参是 pipeline_key（``group:<号>`` / ``private:<QQ>``），
#: 返回一段紧凑的任务表文本；返回空串/None 表示不需要注入。
RouterContextProvider = Callable[[str], str | None]


@dataclass(slots=True)
class RouterSession:
    """一个处于 Router 模式的聊天流。"""

    pipeline_key: str
    owner_user_id: int | None = None
    task_ids: tuple[str, ...] = ()
    activated_at: float = field(default_factory=time.monotonic)
    reason: str = ""


class RouterModeService:
    """聊天流 -> Router 模式的内存登记处。"""

    def __init__(self) -> None:
        self._sessions: dict[str, RouterSession] = {}
        self._context_provider: RouterContextProvider | None = None

    # ── 任务表 provider（dsh_router 插件在 on_load 时注册）──────────

    def set_context_provider(self, provider: RouterContextProvider | None) -> None:
        """注册/清除任务表 provider；插件卸载时必须传 None 清除。"""
        self._context_provider = provider

    # ── 开关 ────────────────────────────────────────────────────

    def activate(
        self,
        pipeline_key: str,
        *,
        owner_user_id: int | None = None,
        task_ids: tuple[str, ...] | list[str] = (),
        reason: str = "",
    ) -> RouterSession:
        """启用某个聊天流的 Router 模式（幂等，重复调用会刷新元数据）。"""
        key = str(pipeline_key or "").strip()
        if not key:
            raise ValueError("pipeline_key is required")
        session = RouterSession(
            pipeline_key=key,
            owner_user_id=owner_user_id,
            task_ids=tuple(str(item) for item in task_ids),
            reason=str(reason or ""),
        )
        self._sessions[key] = session
        return session

    def deactivate(self, pipeline_key: str, *, reason: str = "") -> bool:
        """关闭某个聊天流；返回此前是否处于 Router 模式。``reason`` 供日志/调用方使用。"""
        del reason  # 保留参数语义，服务本身不记录退出原因
        key = str(pipeline_key or "").strip()
        if not key:
            return False
        return self._sessions.pop(key, None) is not None

    def is_active(self, pipeline_key: str) -> bool:
        key = str(pipeline_key or "").strip()
        return bool(key) and key in self._sessions

    def session(self, pipeline_key: str) -> RouterSession | None:
        return self._sessions.get(str(pipeline_key or "").strip())

    def snapshot(self) -> list[dict[str, object]]:
        """只读快照（面板/调试用）。"""
        return [
            {
                "pipeline_key": item.pipeline_key,
                "owner_user_id": item.owner_user_id,
                "task_ids": list(item.task_ids),
                "activated_at": item.activated_at,
                "reason": item.reason,
            }
            for item in self._sessions.values()
        ]

    def clear(self) -> None:
        """进程收尾/测试用：清空全部会话。"""
        self._sessions.clear()

    # ── 提示词注入 ──────────────────────────────────────────────

    def build_context(self, pipeline_key: str) -> str | None:
        """取该聊天流的任务表文本；未激活、未注册 provider 或 provider 失败时返回 None。"""
        key = str(pipeline_key or "").strip()
        if not key or key not in self._sessions:
            return None
        provider = self._context_provider
        if provider is None:
            return None
        try:
            text = provider(key)
        except Exception:
            # 注入失败不能影响回复；插件侧另有日志。
            return None
        if text is None:
            return None
        text = str(text).strip()
        return text or None


__all__ = ["RouterContextProvider", "RouterModeService", "RouterSession"]
