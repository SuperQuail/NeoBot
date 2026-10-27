"""构造解题 Agent 的 Toolset（执行器 + 工具规格）。"""

from __future__ import annotations

from typing import Any

from neobot_chat.schema.types import (
    ToolAccessPolicy,
)
from neobot_chat.tools.toolset import ToolSpec, Toolset
from neobot_contracts.ports.logging import Logger


from .models import (
    ProblemSolverAgentConfig,
    _default_resolver,
)

from .tool_executor import ProblemSolverToolExecutor

def build_problem_solver_toolset(
    *,
    config: ProblemSolverAgentConfig | None = None,
    logger: Logger | None = None,
    policy: ToolAccessPolicy | None = None,
    web_search_config: dict | None = None,
    sandbox_service: Any = None,
    vision_provider: Any = None,
) -> Toolset:
    executor = ProblemSolverToolExecutor(
        logger=logger,
        web_search_config=web_search_config,
        sandbox_service=sandbox_service,
        vision_provider=vision_provider,
    )
    specs = [
        ToolSpec(definition=d, access_resolver=_default_resolver)
        for d in executor.definitions()
    ]
    return Toolset(executor=executor, specs=specs, policy=policy or ToolAccessPolicy())
