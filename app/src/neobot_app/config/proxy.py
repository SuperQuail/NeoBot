"""配置代理 — 支持运行时原子替换内部配置，所有引用方自动看见新值。"""

from __future__ import annotations

from typing import Any


class ConfigProxy:
    def __init__(self, config: Any) -> None:
        object.__setattr__(self, "_config", config)

    def reload(self, config: Any) -> None:
        object.__setattr__(self, "_config", config)

    @property
    def _inner(self) -> Any:
        return object.__getattribute__(self, "_config")

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self._inner, name, value)

    def __delattr__(self, name: str) -> None:
        delattr(self._inner, name)

    def __dir__(self) -> list[str]:
        return dir(self._inner)

    def __repr__(self) -> str:
        return f"ConfigProxy({self._inner!r})"
