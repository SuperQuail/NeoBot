"""面板 HTTP 扩展点（实现见 neobot_app.panel_web）。

依赖面板的插件（例如官方星舰游戏插件）不需要自己再开端口：把实现了
DashboardWebExtension 协议的对象交给面板注册，页面与接口就挂在同一个端口、
同一个 base_path 下。

面板负责：

- 路由分发（仅在没有任何内置路由命中时才会问扩展要不要处理）；
- 登录鉴权（auth_prefixes 声明的路径必须先有面板会话）；
- 目录穿越防护（StaticAssetDirectory 已做 realpath 校验）。

协议、静态资源工具与元数据转换统一放在应用层 neobot_app.panel_web，
这里只做转出，方便面板内部与插件共用同一份实现。
"""

from __future__ import annotations

from neobot_app.panel_web import (
    DashboardWebExtension,
    StaticAssetDirectory,
    extension_metadata,
)

__all__ = [
    "DashboardWebExtension",
    "StaticAssetDirectory",
    "extension_metadata",
]
