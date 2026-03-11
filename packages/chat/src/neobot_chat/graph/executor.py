from __future__ import annotations

from neobot_chat.schema.exceptions import GraphError
from neobot_chat.graph.constants import END
from neobot_chat.graph.types import StateCondition, StateNode
from neobot_chat.schema.types import State


class CompiledGraph:
    """编译后的可执行图"""

    def __init__(
        self,
        nodes: dict[str, StateNode],
        edges: dict[str, str],
        conditional_edges: dict[str, tuple[StateCondition, dict[str, str]]],
        entry_point: str,
        max_steps: int = 100,
    ):
        self._nodes = nodes
        self._edges = edges
        self._conditional_edges = conditional_edges
        self._entry_point = entry_point
        self._max_steps = max_steps

    def _resolve_next(self, current: str, state: State) -> str | None:
        if current in self._conditional_edges:
            condition, mapping = self._conditional_edges[current]
            key = condition(state)
            if key not in mapping:
                raise GraphError(
                    f"Condition on '{current}' returned unmapped key '{key}', "
                    f"expected one of {list(mapping)}"
                )
            return mapping[key]
        return self._edges.get(current)

    async def invoke(self, state: State) -> State:
        current: str | None = self._entry_point

        for _ in range(self._max_steps):
            if current is None or current == END:
                break
            if current not in self._nodes:
                raise GraphError(f"Unknown node '{current}'")
            state = await self._nodes[current](state)
            current = self._resolve_next(current, state)
        else:
            raise GraphError(
                f"Graph exceeded max steps ({self._max_steps}), possible infinite loop"
            )

        return state
