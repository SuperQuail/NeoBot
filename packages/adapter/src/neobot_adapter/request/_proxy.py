"""请求模块核心代理

提供 CoreProxy，允许 request 子模块在模块级使用 `core.call_api()`，
同时避免在导入时就需要一个真实的 AdapterCore 实例

request 子模块全部是 OneBot 动作。双通道（OneBot + 官方）同时运行时，
两个适配器都会绑定核心；这里按通道分行保存，并让 request 助手固定优先
使用 OneBot 通道的核心：否则官方后启动会覆盖单例绑定，get_image /
set_msg_emoji_like / get_robot_uin_range 会落到官方后端并得到「不支持」。

使用方式：
    from neobot_adapter.request._proxy import core_proxy as core
    # 在 OneBotAdapter.start() 中调用 bind_core(real_core, "onebot")
"""

from __future__ import annotations

from typing import Any, Optional

from neobot_adapter.interfaces import CoreLike

#: request 助手默认面向的通道（它们都是 OneBot 动作）。
DEFAULT_CHANNEL = "onebot"


class CoreProxy:
    """按通道延迟绑定的 AdapterCore 代理

    导入时创建，运行时通过 bind() 绑定真实实例；调用 call_api 前必须至少
    绑定一个通道，否则抛出 RuntimeError。优先使用 DEFAULT_CHANNEL，只有
    该通道未绑定且恰好只有一个通道绑定时才回退到它（保持官方单通道模式下
    「动作不支持」而不是抛异常的旧行为）。
    """

    def __init__(self) -> None:
        self._cores: dict[str, CoreLike] = {}

    def bind(self, core: CoreLike, channel: str = DEFAULT_CHANNEL) -> None:
        self._cores[str(channel)] = core

    def unbind(self, channel: str = DEFAULT_CHANNEL) -> None:
        self._cores.pop(str(channel), None)

    @property
    def is_bound(self) -> bool:
        return bool(self._cores)

    def _get_core(self) -> CoreLike:
        core = self._cores.get(DEFAULT_CHANNEL)
        if core is not None:
            return core
        if len(self._cores) == 1:
            return next(iter(self._cores.values()))
        raise RuntimeError(
            "AdapterCore 尚未绑定请先调用 OneBotAdapter.start() 或手动 bind_core()"
        )

    async def call_api(
        self, action: str, params: dict[str, Any], timeout: float = 5, websocket: Any = None
    ) -> Optional[dict[str, Any]]:
        return await self._get_core().call_api(action, params, timeout, websocket)

    def call_api_sync(
        self, action: str, params: dict[str, Any], timeout: float = 5, websocket: Any = None
    ) -> Optional[dict[str, Any]]:
        return self._get_core().call_api_sync(action, params, timeout, websocket)


# 全局单例代理 — request 子模块共享
core_proxy = CoreProxy()


def bind_core(real_core: CoreLike, channel: str = DEFAULT_CHANNEL) -> None:
    """绑定真实的核心实例；channel 区分 OneBot / 官方两个后端。"""
    core_proxy.bind(real_core, channel)


def unbind_core(channel: str = DEFAULT_CHANNEL) -> None:
    """解绑对应通道的核心。"""
    core_proxy.unbind(channel)
