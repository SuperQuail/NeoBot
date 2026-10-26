"""解题工具执行器：组合各工具分组的入口类。"""

from __future__ import annotations

from neobot_chat.schema.protocol import ToolExecutor

from .execution_tools import ProblemSolverToolExecutionMixin
from .tool_core import ProblemSolverToolCoreMixin
from .tool_definitions import ProblemSolverToolDefinitionsMixin


class ProblemSolverToolExecutor(
    ProblemSolverToolDefinitionsMixin,
    ProblemSolverToolCoreMixin,
    ProblemSolverToolExecutionMixin,
    ToolExecutor,
):
    """解题 Agent 的工具执行器，包含联网搜索、文件读写、Python 执行、图片解析。"""
