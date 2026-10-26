"""运行期依赖转发：保持 orchestrator.py 仍是 asyncio / monotonic_seconds 的补丁点。"""

from __future__ import annotations

from typing import Any


def _facade() -> Any:
    from neobot_app.reply import orchestrator

    return orchestrator


class _ModuleProxy:
    def __init__(self, name: str) -> None:
        self._name = name

    def __getattr__(self, attr: str) -> Any:
        return getattr(getattr(_facade(), self._name), attr)


asyncio = _ModuleProxy("asyncio")


def monotonic_seconds() -> float:
    return _facade().monotonic_seconds()
