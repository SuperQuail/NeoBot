"""面板 HTTP 扩展的公共契约与工具（供官方插件复用）。

放在应用层而不是 dashboard 插件内部，是为了让依赖面板的插件可以
**正常导入**（import neobot_app.panel_web）而不必去 import 面板插件的内部
模块 —— 后者会让 dashboard 包在 sys.modules 里出现两份（插件加载器用的是
合成模块名），容易踩坑。

面板侧的使用方式见 builtin_plugins/dashboard/web_extension.py。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from aiohttp import web

ExtensionRequestPermission = Literal["read", "operate", "manage"]
_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@runtime_checkable
class DashboardWebExtension(Protocol):
    """面板 HTTP 扩展协议。"""

    @property
    def name(self) -> str:
        """扩展名（唯一，用于注册与注销）。"""

    @property
    def prefixes(self) -> tuple[str, ...]:
        """本扩展负责的路径前缀（已去掉面板 base_path，例如 "/game"）。"""

    @property
    def auth_prefixes(self) -> tuple[str, ...]:
        """需要面板登录会话的路径前缀（通常只有 /xxx/api）。"""

    def panel_entry(self) -> dict[str, str] | None:
        """面板侧栏入口元数据：{title, path, icon, description}；None 表示不显示。"""

    async def handle_request(self, request: web.Request, path: str) -> web.StreamResponse | None:
        """处理请求；返回 None 表示交给面板继续兜底。"""


@runtime_checkable
class DashboardWebPermissionProvider(Protocol):
    """扩展可选的权限声明；不改变旧扩展必须实现的协议成员。"""

    def request_permission(self, method: str, path: str) -> ExtensionRequestPermission:
        """对 auth_prefixes 内的请求声明读取、普通操作或面板管理权限。

        path 已去掉面板 base_path。普通操作仍需登录和 CSRF；管理操作额外受
        manage_plugins / allow_remote_manage 约束，不能用此声明公开数据接口。
        """


def extension_request_permission(extension: Any, *, method: str, path: str) -> ExtensionRequestPermission:
    """解析受保护请求的权限，旧扩展写操作默认要求管理权限。"""
    method = method.upper()
    declaration = getattr(extension, "request_permission", None)
    if declaration is None:
        return "read" if method in _READ_METHODS else "manage"
    if not callable(declaration):
        raise ValueError("扩展 request_permission 必须可调用")
    permission = declaration(method, path)
    if permission not in {"read", "operate", "manage"}:
        raise ValueError("扩展必须声明 read、operate 或 manage 权限")
    if permission == "read" and method not in _READ_METHODS:
        raise ValueError("扩展写操作不能声明为 read 权限")
    return permission


class StaticAssetDirectory:
    """把一个目录安全地暴露成静态资源。

    路径解析统一走 resolve()：禁止绝对路径、..、盘符与 symlink 逃逸；
    任何解析失败的请求都按 404 处理，不向调用方泄露真实路径。
    """

    def __init__(
        self,
        root: Path,
        *,
        max_age: int = 3600,
        immutable: bool = False,
    ) -> None:
        self.root = Path(root).resolve()
        self.max_age = int(max_age)
        self.immutable = bool(immutable)

    def resolve(self, relative: str) -> Path | None:
        candidate = str(relative or "").lstrip("/")
        if not candidate:
            return None
        if ".." in Path(candidate).parts:
            return None
        try:
            target = (self.root / candidate).resolve()
            target.relative_to(self.root)
        except (OSError, ValueError):
            return None
        return target if target.is_file() else None

    def cache_control(self) -> str:
        if self.immutable:
            return f"public, max-age={self.max_age}, immutable"
        return f"public, max-age={self.max_age}"

    def response(self, relative: str) -> web.StreamResponse:
        target = self.resolve(relative)
        if target is None:
            return web.Response(status=404)
        return web.FileResponse(target, headers={"Cache-Control": self.cache_control()})


def extension_metadata(extension: Any) -> dict[str, Any]:
    """把扩展对象转成面板可展示的元数据（不依赖具体实现类型）。"""
    entry: dict[str, str] | None = None
    getter = getattr(extension, "panel_entry", None)
    if callable(getter):
        try:
            raw = getter()
        except Exception:
            raw = None
        if isinstance(raw, dict):
            entry = {str(key): str(value) for key, value in raw.items()}
    return {
        "name": str(getattr(extension, "name", "") or ""),
        "prefixes": [str(item) for item in (getattr(extension, "prefixes", ()) or ())],
        "auth_prefixes": [str(item) for item in (getattr(extension, "auth_prefixes", ()) or ())],
        "panel": entry,
    }


__all__ = [
    "DashboardWebExtension",
    "DashboardWebPermissionProvider",
    "ExtensionRequestPermission",
    "StaticAssetDirectory",
    "extension_metadata",
    "extension_request_permission",
]
