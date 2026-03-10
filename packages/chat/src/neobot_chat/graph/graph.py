from __future__ import annotations

from collections.abc import Callable

from neobot_chat.exceptions import GraphError
from neobot_chat.graph.constants import END
from neobot_chat.graph.executor import CompiledGraph


class StateGraph:
    """状态图构建器"""

    def __init__(self):
        self._nodes: dict[str, Callable] = {}
        self._edges: dict[str, str] = {}
        self._conditional_edges: dict[str, tuple[Callable, dict[str, str]]] = {}
        self._entry_point: str | None = None

    def _assert_no_outgoing(self, node: str) -> None:
        if node in self._edges or node in self._conditional_edges:
            raise GraphError(f"Node '{node}' already has outgoing edges")

    def add_node(self, name: str, func: Callable) -> None:
        if name in self._nodes:
            raise GraphError(f"Node '{name}' already exists")
        self._nodes[name] = func

    def add_edge(self, from_node: str, to_node: str) -> None:
        self._assert_no_outgoing(from_node)
        self._edges[from_node] = to_node

    def add_conditional_edges(
            self, from_node: str, condition: Callable, mapping: dict[str, str]
    ) -> None:
        self._assert_no_outgoing(from_node)
        self._conditional_edges[from_node] = (condition, mapping)

    def set_entry_point(self, node: str) -> None:
        self._entry_point = node

    def compile(self) -> CompiledGraph:
        if self._entry_point is None:
            raise GraphError("Entry point not set")
        if self._entry_point not in self._nodes:
            raise GraphError(f"Entry point '{self._entry_point}' not found in nodes")
        valid = set(self._nodes) | {END}
        for src, dst in self._edges.items():
            if dst not in valid:
                raise GraphError(f"Edge '{src}' -> '{dst}': target node not found")
        for src, (_, mapping) in self._conditional_edges.items():
            for dst in mapping.values():
                if dst not in valid:
                    raise GraphError(f"Conditional edge '{src}' -> '{dst}': target node not found")
        return CompiledGraph(
            nodes=self._nodes,
            edges=self._edges,
            conditional_edges=self._conditional_edges,
            entry_point=self._entry_point,
        )
