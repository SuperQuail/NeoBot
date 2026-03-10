from __future__ import annotations

from collections.abc import Callable

from neobot_chat.graph.constants import END
from neobot_chat.graph.executor import CompiledGraph
from neobot_chat.graph.graph import StateGraph
from neobot_chat.types import State

# State → State 预处理器（如 inject_skills）
Preprocessor = Callable[[State], State]


class Workflow:
    """基于 Graph 的链式工作流

    可选 preprocessor 在 invoke 前对 state 做预处理（如 skills 注入）::

        from neobot_chat.skills.inject import inject_skills
        from functools import partial

        wf = Workflow(preprocessor=partial(inject_skills, my_skills))
    """

    def __init__(self, preprocessor: Preprocessor | None = None):
        self._steps: list[tuple[str, Callable]] = []
        self._compiled: CompiledGraph | None = None
        self._preprocessor = preprocessor

    def add_step(self, func: Callable) -> Workflow:
        self._steps.append((f"step_{len(self._steps)}", func))
        self._compiled = None
        return self

    def compile(self) -> CompiledGraph:
        if self._compiled is not None:
            return self._compiled
        if not self._steps:
            raise ValueError("Workflow has no steps")

        graph = StateGraph()
        for name, func in self._steps:
            graph.add_node(name, func)

        for (prev, _), (curr, _) in zip(self._steps, self._steps[1:]):
            graph.add_edge(prev, curr)
        graph.add_edge(self._steps[-1][0], END)

        graph.set_entry_point(self._steps[0][0])
        self._compiled = graph.compile()
        return self._compiled

    async def invoke(self, state: State) -> State:
        if self._preprocessor:
            state = self._preprocessor(state)
        return await self.compile().invoke(state)
