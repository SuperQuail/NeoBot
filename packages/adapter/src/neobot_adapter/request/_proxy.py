"""请求模块核心代理

提供 CoreProxy，允许 request 子模块在模块级使用 `core.call_api()`，
同时避免在导入时就需要一个真实的 AdapterCore 实例

使用方式：
    from neobot_adapter.request._proxy import core_proxy as core
    # 在 OneBotAdapter.start() 中调用 bind_core(real_core)
"""

from __future__ import annotations

from typing import Any, Optional

from neobot_adapter.receiver.core import AdapterCore


class CoreProxy:
    """延迟绑定的 AdapterCore 代理

    导入时创建，运行时通过 bind() 绑定真实实例
    调用 call_api 等方法前必须先 bind，否则抛出 RuntimeError
    """

    def __init__(self) -> None:
        self._core: AdapterCore | None = None

    def bind(self, core: AdapterCore) -> None:
        self._core = core

    def unbind(self) -> None:
        self._core = None

    @property
    def is_bound(self) -> bool:
        return self._core is not None

    def _get_core(self) -> AdapterCore:
        if self._core is None:
            raise RuntimeError(
                "AdapterCore 尚未绑定请先调用 OneBotAdapter.start() 或手动 bind_core()"
            )
        return self._core

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


def bind_core(real_core: AdapterCore) -> None:
    """绑定真实的 AdapterCore 实例由 OneBotAdapter.start() 调用"""
    core_proxy.bind(real_core)


def unbind_core() -> None:
    """解绑由 OneBotAdapter.stop() 调用"""
    core_proxy.unbind()
