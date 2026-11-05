"""提供插件包内页面；页面只通过宿主桥接调用业务，不能获得宿主源权限。"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from urllib.parse import quote

from aiohttp import web

from neobot_modloader import ActionError

from ._common import _json_error, _json_ok
from .plugin_surface import _failure

_BRIDGE_FILE = Path(__file__).resolve().parents[1] / "web" / "assets" / "plugin-view-sdk.js"
_UI_FILE = _BRIDGE_FILE.with_name("plugin-view-ui.css")
_VIEW_POLICY = (
    "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob: https:; font-src 'self'; media-src 'self' blob:; "
    "frame-src 'self' blob:; connect-src 'none'; form-action 'none'; base-uri 'self'; "
    "frame-ancestors 'self'; sandbox allow-scripts allow-forms"
)


def apply_plugin_view_headers(request: web.Request, response: web.StreamResponse) -> None:
    """响应级 sandbox 同样保护直接打开页面的情况，不能只依赖父页 iframe 属性。"""
    if request.get("plugin_view_document"):
        response.headers["Content-Security-Policy"] = _VIEW_POLICY
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Cache-Control"] = "no-store"
        # sandbox 文档是空源，模块脚本和字体需允许无凭据读取这些公开分发文件。
        response.headers["Access-Control-Allow-Origin"] = "*"


class PluginViewsMixin:
    async def plugin_views_get(self, request: web.Request) -> web.Response:
        control = self._plugin_control()
        getter = getattr(control, "views", None)
        if not callable(getter):
            return _json_ok(items=[])
        name = request.match_info["name"]
        try:
            descriptions = getter(name)
        except ActionError as error:
            return _failure(error)
        items = [
            {
                **view,
                "url": f"{self.console.base_path}/plugins-ui/{quote(name, safe='')}/{quote(view['id'], safe='')}/"
                + (f"?revision={view['revision']}" if view.get("revision") else ""),
            }
            for view in descriptions
        ]
        return _json_ok(items=items)

    async def plugin_view_asset(self, request: web.Request) -> web.StreamResponse:
        control = self._plugin_control()
        resolver = getattr(control, "view_asset", None)
        if not callable(resolver):
            return _json_error("插件页面不可用", status=404)
        relative = request.match_info.get("asset", "")
        try:
            name, view = request.match_info["name"], request.match_info["view"]
            if relative in {"_sdk.js", "_ui.css"}:
                resolver(name, view, "")
                target = _BRIDGE_FILE if relative == "_sdk.js" else _UI_FILE
                if not target.is_file():
                    return _json_error("页面公共资源尚未构建", status=503)
            else:
                target = resolver(name, view, relative)
        except ActionError as error:
            status = 422 if error.code == "contract_invalid" else 404
            return _json_error(error.message, status=status, code=error.code)
        request["plugin_view_document"] = True
        headers = {"Cache-Control": "no-store"}
        content_type, _ = mimetypes.guess_type(target.name)
        if content_type and (
            content_type.startswith("text/")
            or content_type
            in {
                "application/javascript",
                "application/json",
                "image/svg+xml",
            }
        ):
            headers["Content-Type"] = f"{content_type}; charset=utf-8"
        return web.FileResponse(target, headers=headers)
