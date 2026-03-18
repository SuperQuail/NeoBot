from __future__ import annotations

from neobot_chat.graph.constants import END
from neobot_chat.graph.executor import CompiledGraph
from neobot_chat.graph.graph import StateGraph
from neobot_chat.graph.types import StateNode
from neobot_chat.schema.exceptions import GraphError
from neobot_chat.schema.protocol import StatePreprocessor
from neobot_chat.schema.types import State


class Workflow:
    """基于 Graph 的链式工作流"""

    def __init__(self, preprocessor: StatePreprocessor | None = None):
        self._steps: list[tuple[str, StateNode]] = []
        self._compiled: CompiledGraph | None = None
        self._preprocessor = preprocessor

    def add_step(self, func: StateNode) -> Workflow:
        self._steps.append((f"step_{len(self._steps)}", func))
        self._compiled = None
        return self

    def compile(self) -> CompiledGraph:
        if self._compiled is not None:
            return self._compiled
        if not self._steps:
            raise GraphError("Workflow has no steps")

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
