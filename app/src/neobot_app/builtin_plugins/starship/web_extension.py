"""星舰游戏的 HTTP 扩展：把游戏页面与接口挂到面板的同一个端口上。

页面路径：{面板 base_path}{starship.route}/（例如 /game/）
接口路径：{面板 base_path}{starship.route}/api/...

面板负责鉴权（auth_prefixes 声明的 /api 必须先登录）与目录穿越防护
（StaticAssetDirectory），本模块只做路由分发与静态资源映射。

不在游戏页面时零开销：这里没有任何后台任务，只有请求到达才会执行。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aiohttp import web

from neobot_app.panel_web import StaticAssetDirectory

from .api import StarshipApi, _json_error

WEB_ROOT = Path(__file__).resolve().parent / "web"
INDEX_FILE = WEB_ROOT / "index.html"
BUILD_HINT = (
    "星舰游戏前端资源缺失（web/ 目录）。\n"
    "开发环境请在 app/src/neobot_app/builtin_plugins/starship/frontend "
    "执行 pnpm install && pnpm build 生成产物；"
    "发布包应自带编译后的 web/ 内容。"
)


class StarshipWebExtension:
    """面板 HTTP 扩展实现（协议见 dashboard/web_extension.py）。"""

    name = "starship"

    def __init__(
        self,
        *,
        config: Any,
        api: StarshipApi,
        logger: Any,
        web_root: Path | None = None,
    ) -> None:
        self.config = config
        self.api = api
        self.logger = logger
        self.web_root = Path(web_root or WEB_ROOT)
        self.index_file = self.web_root / "index.html"
        self._assets = StaticAssetDirectory(
            self.web_root / "assets", max_age=31536000, immutable=True
        )
        self._images = StaticAssetDirectory(self.web_root / "image", max_age=86400)

    # ------------------------------------------------------------------
    # 协议实现
    # ------------------------------------------------------------------

    @property
    def prefix(self) -> str:
        return self.config.prefix

    @property
    def prefixes(self) -> tuple[str, ...]:
        return (self.prefix,)

    @property
    def auth_prefixes(self) -> tuple[str, ...]:
        # 页面与静态资源保持与面板一致（资源不需要登录，数据接口需要）
        return (f"{self.prefix}/api",)

    def panel_entry(self) -> dict[str, str] | None:
        """面板侧栏入口；show_in_sidebar=false 时不显示。"""
        if not bool(self.config.show_in_sidebar):
            return None
        return {
            "title": str(self.config.title),
            "path": f"{self.prefix}/",
            "icon": "game",
            "description": "进入 3D 星舰，把控制台当成飞船终端来用",
        }

    async def handle_request(
        self, request: web.Request, path: str
    ) -> web.StreamResponse | None:
        prefix = self.prefix
        if path == prefix:
            # 目录形式访问，保证页面内的相对资源路径正确（相对路径基准是 /game/）
            return web.Response(status=302, headers={"Location": request.path + "/"})
        if path == f"{prefix}/" or path == f"{prefix}/index.html":
            return self._index()
        if path.startswith(f"{prefix}/api/"):
            return await self._api(request, path[len(prefix) + len("/api") :], path)
        if path.startswith(f"{prefix}/assets/"):
            return self._assets.response(path[len(f"{prefix}/assets/") :])
        if path.startswith(f"{prefix}/image/"):
            return self._images.response(path[len(f"{prefix}/image/") :])
        if path == f"{prefix}/favicon.ico":
            icon = self.web_root / "image" / "icon.webp"
            if icon.is_file():
                return web.FileResponse(
                    icon, headers={"Cache-Control": "public, max-age=86400"}
                )
            return web.Response(status=404)
        return None

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _index(self) -> web.StreamResponse:
        if not self.index_file.is_file():
            return web.Response(text=BUILD_HINT, content_type="text/plain", status=503)
        return web.FileResponse(self.index_file, headers={"Cache-Control": "no-store"})

    async def _api(
        self, request: web.Request, tail: str, path: str
    ) -> web.StreamResponse:
        route = tail.strip("/")
        # 面板 base_path（反向代理子路径部署时非空）：request.path 去掉扩展路径
        base = request.path[: len(request.path) - len(path)] if path else ""
        try:
            if route == "bootstrap":
                return await self.api.bootstrap(request, base=base.rstrip("/"))
            if route == "status":
                return await self.api.status(request)
            if route == "minigames":
                return await self.api.minigames(request)
            if route == "scores":
                if request.method == "POST":
                    return await self.api.submit_score(request)
                return await self.api.scores(request)
            if route == "scores/reset" and request.method == "POST":
                return await self.api.reset_scores(request)
            if route == "achievements":
                if request.method == "POST":
                    return await self.api.unlock(request)
                return await self.api.achievements(request)
            if route == "health":
                return web.json_response({"ok": True, "plugin": self.name})
        except web.HTTPException:
            raise
        except Exception as exc:
            self.logger.exception(f"星舰接口处理失败 path={request.path}: {exc}")
            return _json_error("服务器处理请求失败", status=500)
        return _json_error("接口不存在", status=404)


__all__ = ["StarshipWebExtension", "WEB_ROOT"]
