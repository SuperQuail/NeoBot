"""自修复任务管理器（聚合错误、节流派发、两阶段通知）。"""

from __future__ import annotations

from .manager_core import SelfHealManagerCoreMixin
from .manager_heal import SelfHealManagerHealMixin


class SelfHealManager(SelfHealManagerCoreMixin, SelfHealManagerHealMixin):
    """聚合 loguru ERROR sink 捕获的错误，当达到阈值时派发一次自修复
    Agent 调用。

    生命周期：
      * record(payload)   — 由日志 sink 调用（sink 运行在日志线程 → 由
        sink 自身通过 call_soon_threadsafe 转交到运行中的事件循环；
        本方法只负责收集并执行节流逻辑）。
      * submit(...)       — 启动一个后台修复任务，并立即发出开始通知。
      * trigger_now(...)  — 手动触发入口（暂未接入技能）。
      * shutdown()        — 取消所有运行中的任务。
    """
