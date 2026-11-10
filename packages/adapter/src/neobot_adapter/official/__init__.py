"""QQ 官方机器人内嵌协议适配器（official 模式）。

子模块按依赖方向分层：identity/settings（纯数据）→ auth/gateway（连接与鉴权）→
media → send → events → actions → adapter。包入口用惰性导出，避免其它子模块的
import 触发整条适配器依赖链。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neobot_adapter.official.adapter import OfficialAdapter
    from neobot_adapter.official.settings import OfficialSettings

__all__ = ["OfficialAdapter", "OfficialSettings"]


def __getattr__(name: str) -> Any:
    if name == "OfficialAdapter":
        from neobot_adapter.official.adapter import OfficialAdapter

        return OfficialAdapter
    if name == "OfficialSettings":
        from neobot_adapter.official.settings import OfficialSettings

        return OfficialSettings
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
