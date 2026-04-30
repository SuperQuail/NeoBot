from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from neobot_contracts.ports.plugin import PluginContext


class BasePlugin:
    name: str = ""
    version: str = "0.1.0"

    async def on_load(self, ctx: PluginContext) -> None:
        pass

    async def on_start(self) -> None:
        pass

    async def on_stop(self) -> None:
        pass


class FunctionPlugin(BasePlugin):
    def __init__(
        self,
        *,
        name: str,
        setup: Callable[[PluginContext], Any],
        version: str = "0.1.0",
    ) -> None:
        self.name = name
        self.version = version
        self._setup = setup

    async def on_load(self, ctx: PluginContext) -> None:
        result = self._setup(ctx)
        if inspect.isawaitable(result):
            await result
