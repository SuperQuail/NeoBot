"""自修复 Agent：监控累积的异常，进行诊断并在安全的前提下尝试恢复，
然后通过后台通知中枢告知管理员。

架构与 ProblemSolverManager/Agent 保持一致（参见 problem_solver.py）：
  SelfHealManager   — 异常聚合、节流提交、通知
  SelfHealAgent     — 由 LLM 驱动的诊断 Agent，携带工具集
  SelfHealToolExecutor — 读取错误 / 日志 / 自身源码，写调试报告，
                      运行 run_python、search_web、parse_image，以及少量
                      安全的修复钩子（清除绘图冷却、触发图片清理）。

通知分两个阶段：
  1. submit() 立即触发        -> source="self_heal_start"（「已开始工作」）
  2. heal 任务结束时          -> source="self_heal_result"（诊断 + debug_file）

管理员聊天流程使用与 `admin_account` 的私聊（回退到 chat.admin_accounts[0]）。
"""

from __future__ import annotations

from .self_heal_parts.agent import (  # noqa: F401  # 兼容旧的模块级导入
    SelfHealAgent,
    _FALLBACK_SYSTEM_PROMPT,
    _build_system_prompt,
    build_self_heal_agent,
)
from .self_heal_parts.manager import SelfHealManager  # noqa: F401
from .self_heal_parts.models import (  # noqa: F401
    EXPOSED_TO_MAIN_AGENT_DESCRIPTION,
    EXPOSED_TO_MAIN_AGENT_NAME,
    LOGGER_PREFIX,
    RESULT_SOURCE,
    START_SOURCE,
    HealTask,
    SelfHealAgentConfig,
    _HEAL_TASK,
    _default_resolver,
    _json,
    _tool_def,
)
from .self_heal_parts.source_tools import (  # noqa: F401
    _FORBIDDEN_SOURCE_BASENAMES,
    _FORBIDDEN_SOURCE_SUFFIXES,
    _common_project_root,
    _is_within_any_root,
)
from .self_heal_parts.tool_executor import SelfHealToolExecutor  # noqa: F401
