"""后台解题任务管理器（提交、通知与重试）。"""

from __future__ import annotations

from .manager_core import ProblemSolverManagerCoreMixin
from .manager_heal import ProblemSolverManagerHealMixin


class ProblemSolverManager(
    ProblemSolverManagerCoreMixin, ProblemSolverManagerHealMixin
):
    """管理后台解题任务的提交、通知与重试。"""
