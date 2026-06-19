"""BackgroundAgent — 后台 Agent 轻量统一框架。

提供后台 Agent 的基础抽象和工具函数，不强制继承。
现有 Manager（ProblemSolverManager、CrossChatManager 等）可选择性适配。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal
from uuid import uuid4


def create_background_task_id(prefix: str = "bg") -> str:
    """生成标准格式的后台任务 ID。"""
    return f"{prefix}_{uuid4().hex[:12]}"


class BackgroundTaskInfo:
    """后台任务元数据。"""

    def __init__(
        self,
        *,
        task_id: str,
        pipeline_key: str,
        status: Literal["running", "completed", "failed", "timeout"] = "running",
        created_at: float = 0.0,
    ) -> None:
        self.task_id = task_id
        self.pipeline_key = pipeline_key
        self.status = status
        self.created_at = created_at


class BackgroundAgentBase(ABC):
    """后台 Agent 基类（可选继承，非强制）。

    子类需实现 submit、get_status、shutdown 三个核心方法。
    """

    @abstractmethod
    async def submit(self, pipeline_key: str, **kwargs: Any) -> str:
        """提交后台任务，返回立即响应（JSON 字符串）。"""

    @abstractmethod
    def get_status(self, pipeline_key: str) -> dict[str, Any]:
        """查询指定管线的后台任务状态。"""

    @abstractmethod
    def shutdown(self) -> None:
        """关闭所有后台任务，释放资源。"""
