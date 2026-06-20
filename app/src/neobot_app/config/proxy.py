"""配置代理 — 支持运行时原子替换内部配置，所有引用方自动看见新值。

同时提供常用配置路径的快捷属性，避免 3+ 层嵌套访问。
"""

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

    # ── 快捷属性（避免 config.agent.xxx.enabled 等深层嵌套）─────

    @property
    def bot_account(self) -> int:
        return self._inner.bot.account

    @property
    def bot_nick_name(self) -> str:
        return self._inner.bot.nick_name

    @property
    def chat_reply_mode(self) -> str:
        return getattr(self._inner.chat, "reply_mode", "agent") or "agent"

    @property
    def chat_reply_cooldown_seconds(self) -> int:
        val = getattr(self._inner.chat, "reply_cooldown_seconds", None)
        return val if isinstance(val, int) else 2

    @property
    def drawing_enabled(self) -> bool:
        return bool(getattr(getattr(self._inner.agent, "creator", None), "enabled", False))

    @property
    def browser_enabled(self) -> bool:
        browser = getattr(self._inner.agent, "browser", None)
        return bool(getattr(browser, "enabled", False)) if browser is not None else False

    # ── 通用代理 ─────────────────────────────────────────────

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
