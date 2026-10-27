"""Problem Solver 智能体与后台任务管理器。

接收主 Agent 下发的复杂推理问题，将其作为后台任务运行，把解答结果
转换为 Markdown 图片，并通知主 Agent。
"""

from __future__ import annotations

from .problem_solver_parts.agent import (  # noqa: F401  # 兼容旧的模块级导入
    ProblemSolverAgent,
    build_problem_solver_agent,
)
from .problem_solver_parts.manager import ProblemSolverManager  # noqa: F401
from .problem_solver_parts.models import (  # noqa: F401
    EXPOSED_TO_MAIN_AGENT_DESCRIPTION,
    EXPOSED_TO_MAIN_AGENT_NAME,
    EXPOSED_TO_MAIN_AGENT_SHORT_DESCRIPTION,
    ProblemSolverAgentConfig,
    SolveTask,
    _CHAT_FLOW_ID,
    _MAX_AGENT_ITERATIONS,
    _MODE_NOTE_NATIVE,
    _MODE_NOTE_PTC,
    _SOLUTION_RESULT,
    _SOLVER_CHAT_CONTEXT,
    _TOOL_CONTEXT,
    _default_resolver,
    _json,
    _tool_def,
)
from .problem_solver_parts.prompts import (  # noqa: F401
    _FALLBACK_RUNTIME_TEMPLATE,
    _FALLBACK_SYSTEM_PROMPT,
    _build_system_prompt,
    _runtime_template,
)
from .problem_solver_parts.tool_executor import ProblemSolverToolExecutor  # noqa: F401
from .problem_solver_parts.toolset_builder import build_problem_solver_toolset  # noqa: F401
