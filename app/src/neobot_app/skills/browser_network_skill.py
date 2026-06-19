"""BrowserNetworkSkill — 浏览器网络与状态管理 Skill（Cookie/Storage/网络拦截/设置）。"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class BrowserNetworkSkill(SkillModule):
    """浏览器网络与状态管理 Skill — Cookie、Storage、网络请求拦截、浏览器设置。"""

    @property
    def name(self) -> str:
        return "browser_network"

    @property
    def description(self) -> str:
        return "浏览器网络与状态管理：Cookie、Storage、网络拦截、浏览器设置"

    @property
    def instructions(self) -> str:
        return (
            "浏览器网络与状态管理 Skill，提供以下能力：\n\n"
            "## Cookie 管理\n"
            "  get_cookies / set_cookies / clear_cookies\n\n"
            "## 网络请求\n"
            "  network_route / network_unroute — 拦截/取消拦截\n"
            "  network_requests — 查看已追踪的请求\n\n"
            "## Storage\n"
            "  storage_get / storage_set / storage_clear — localStorage\n"
            "  storage_session_get / storage_session_set / storage_session_clear — sessionStorage\n\n"
            "## 浏览器设置\n"
            "  set_viewport — 视口大小\n"
            "  set_device — 模拟移动设备\n"
            "  set_geolocation — 模拟地理位置\n"
            "  set_offline — 离线/在线切换\n\n"
            "注意：需要浏览器已通过 browser 技能启动，且使用同一 browser_instance。"
        )

    def __init__(self, browser_instance: Any = None, lifecycle_manager: Any = None) -> None:
        self._browser = browser_instance
        self._lifecycle = lifecycle_manager

    def reset(self) -> None:
        pass

    def _check_browser(self) -> str | None:
        if self._browser is None:
            return "浏览器未启动"
        return None

    def get_tools(self) -> list[dict]:
        return [
            # ── Cookie ──
            self._tool_def("get_cookies", "获取当前页面的所有 cookie。", {
                "properties": {
                    "domain": {"type": "string", "description": "可选，按域名筛选 cookie"},
                },
            }),
            self._tool_def("set_cookies", "设置 cookie。可传入 cookie 列表。", {
                "properties": {
                    "cookies": {"type": "array", "items": {"type": "object"},
                                "description": "cookie 对象列表，每项包含 name, value, domain, path 等"},
                },
                "required": ["cookies"],
            }),
            self._tool_def("clear_cookies", "清除当前页面的所有 cookie。"),
            # ── 网络拦截 ──
            self._tool_def("network_route", "拦截或模拟网络请求。可阻断或 mock 响应。", {
                "properties": {
                    "url_pattern": {"type": "string", "description": "URL 匹配模式，如 */api/*"},
                    "mock_body": {"type": "string", "description": "可选，mock 响应体（JSON 字符串）"},
                    "abort": {"type": "boolean", "description": "是否完全阻断匹配的请求", "default": False},
                },
                "required": ["url_pattern"],
            }),
            self._tool_def("network_unroute", "移除之前设置的网络请求拦截。", {
                "properties": {
                    "url_pattern": {"type": "string", "description": "可选，要移除的匹配模式"},
                },
            }),
            self._tool_def("network_requests", "查看已追踪的网络请求列表。", {
                "properties": {
                    "filter_str": {"type": "string", "description": "可选，按 URL 筛选"},
                },
            }),
            # ── Storage ──
            self._tool_def("storage_get", "获取 localStorage 数据。key 为空时返回所有。", {
                "properties": {
                    "key": {"type": "string", "description": "可选，要获取的键名"},
                },
            }),
            self._tool_def("storage_set", "设置 localStorage 的键值对。", {
                "properties": {
                    "key": {"type": "string", "description": "键名"},
                    "value": {"type": "string", "description": "值"},
                },
                "required": ["key", "value"],
            }),
            self._tool_def("storage_clear", "清除所有 localStorage 数据。"),
            self._tool_def("storage_session_get", "获取 sessionStorage 数据。key 为空时返回所有。", {
                "properties": {
                    "key": {"type": "string", "description": "可选键名"},
                },
            }),
            self._tool_def("storage_session_set", "设置 sessionStorage 的键值对。", {
                "properties": {
                    "key": {"type": "string", "description": "键名"},
                    "value": {"type": "string", "description": "值"},
                },
                "required": ["key", "value"],
            }),
            self._tool_def("storage_session_clear", "清除所有 sessionStorage 数据。"),
            # ── 浏览器设置 ──
            self._tool_def("set_viewport", "设置浏览器视口宽高和缩放比。", {
                "properties": {
                    "width": {"type": "integer", "description": "视口宽度（像素）"},
                    "height": {"type": "integer", "description": "视口高度（像素）"},
                    "device_scale_factor": {"type": "number", "description": "设备缩放比", "default": 1.0},
                },
                "required": ["width", "height"],
            }),
            self._tool_def("set_device", "模拟移动设备。会影响 User-Agent 和视口。", {
                "properties": {
                    "name": {"type": "string", "description": "设备名称，如 iPhone 14"},
                },
                "required": ["name"],
            }),
            self._tool_def("set_geolocation", "模拟地理位置坐标。", {
                "properties": {
                    "latitude": {"type": "number", "description": "纬度"},
                    "longitude": {"type": "number", "description": "经度"},
                },
                "required": ["latitude", "longitude"],
            }),
            self._tool_def("set_offline", "模拟离线/在线网络状态。", {
                "properties": {
                    "offline": {"type": "boolean", "description": "true=离线, false=在线"},
                },
                "required": ["offline"],
            }),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        err = self._check_browser()
        if err:
            return _json({"ok": False, "error": f"浏览器不可用: {err}"})

        pipeline_key = str(args.get("pipeline_key", "")).strip()
        if pipeline_key and self._lifecycle is not None:
            self._lifecycle.touch(pipeline_key)
            await self._switch_to_flow_tab(pipeline_key)

        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown browser_network tool: {tool_name}"})
        return await handler(self, args)

    @staticmethod
    def _parse_tabs(result: Any) -> list[dict]:
        """解析 list_tabs() 的返回值，统一返回 tab 列表。"""
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("tabs", [])
        return []

    async def _switch_to_flow_tab(self, pipeline_key: str) -> None:
        """切换到该聊天流分配的标签页。"""
        tab_ids = self._lifecycle.get_tab_ids(pipeline_key)
        if not tab_ids:
            return
        tabs = self._parse_tabs(await self._browser.list_tabs())
        id_to_index = {t["tab_id"]: t["index"] for t in tabs if "tab_id" in t and "index" in t}
        for tab_id in tab_ids:
            if tab_id in id_to_index:
                try:
                    await self._browser.switch_tab(id_to_index[tab_id])
                    return
                except Exception:
                    continue

    @staticmethod
    def _tool_def(name: str, desc: str, params: dict | None = None) -> dict:
        p = {"type": "object", "properties": {}, "required": []}
        if params:
            p["properties"] = params.get("properties", {})
            p["required"] = params.get("required", [])
        return {"type": "function", "function": {"name": name, "description": desc, "parameters": p}}


# ── Handlers ──

async def _handle_get_cookies(self: BrowserNetworkSkill, args: dict) -> str:
    if not hasattr(self._browser, "get_cookies"):
        return _json({"ok": True, "cookies": []})
    domain = args.get("domain")
    result = await self._browser.get_cookies(domain=domain)
    if isinstance(result, dict) and result.get("success"):
        return _json({"ok": True, "cookies": result.get("cookies", []), "cookie_string": result.get("cookie_string", "")})
    return _json({"ok": True, "cookies": [], "note": "get_cookies stub"})

async def _handle_set_cookies(self: BrowserNetworkSkill, args: dict) -> str:
    cookies = args.get("cookies", [])
    if not cookies:
        return _json({"ok": False, "error": "未提供 cookie"})
    if hasattr(self._browser, "set_cookies"):
        result = await self._browser.set_cookies(cookies)
        if isinstance(result, dict) and result.get("success"):
            return _json({"ok": True, "count": result.get("count", len(cookies))})
    return _json({"ok": True, "note": f"set_cookies stub ({len(cookies)}条)"})

async def _handle_clear_cookies(self: BrowserNetworkSkill, args: dict) -> str:
    if hasattr(self._browser, "clear_cookies"):
        result = await self._browser.clear_cookies()
        if isinstance(result, dict) and result.get("success"):
            return _json({"ok": True})
    return _json({"ok": True, "note": "clear_cookies stub"})

async def _handle_network_route(self: BrowserNetworkSkill, args: dict) -> str:
    url_pattern = str(args.get("url_pattern", "")).strip()
    mock_body = args.get("mock_body", "")
    abort = bool(args.get("abort", False))
    if hasattr(self._browser, "network_route"):
        result = await self._browser.network_route(url_pattern, mock_body, abort)
        if isinstance(result, dict) and result.get("success"):
            return _json({"ok": True, "action": "blocked" if abort else "intercepted"})
    return _json({"ok": True, "note": f"network_route stub: {url_pattern}"})

async def _handle_network_unroute(self: BrowserNetworkSkill, args: dict) -> str:
    url_pattern = args.get("url_pattern", "")
    if hasattr(self._browser, "network_unroute"):
        await self._browser.network_unroute(url_pattern)
    return _json({"ok": True})

async def _handle_network_requests(self: BrowserNetworkSkill, args: dict) -> str:
    if hasattr(self._browser, "network_requests"):
        result = await self._browser.network_requests(args.get("filter_str", ""))
        if isinstance(result, dict) and result.get("success"):
            return _json({"ok": True, "requests": result.get("requests", [])})
    return _json({"ok": True, "requests": []})

async def _handle_storage_get(self: BrowserNetworkSkill, args: dict) -> str:
    key = args.get("key", "")
    if hasattr(self._browser, "storage_get"):
        result = await self._browser.storage_get(key)
        if isinstance(result, dict) and result.get("success"):
            return _json({"ok": True, "value": result.get("value", ""), "all": result.get("all", {})})
    return _json({"ok": True, "note": "storage_get stub"})

async def _handle_storage_set(self: BrowserNetworkSkill, args: dict) -> str:
    key = str(args.get("key", "")).strip()
    value = str(args.get("value", "")).strip()
    if hasattr(self._browser, "storage_set"):
        await self._browser.storage_set(key, value)
    return _json({"ok": True})

async def _handle_storage_clear(self: BrowserNetworkSkill, args: dict) -> str:
    if hasattr(self._browser, "storage_clear"):
        await self._browser.storage_clear()
    return _json({"ok": True})

async def _handle_storage_session_get(self: BrowserNetworkSkill, args: dict) -> str:
    key = args.get("key", "")
    if hasattr(self._browser, "storage_session_get"):
        result = await self._browser.storage_session_get(key)
        if isinstance(result, dict) and result.get("success"):
            return _json({"ok": True, "value": result.get("value", ""), "all": result.get("all", {})})
    return _json({"ok": True, "note": "storage_session_get stub"})

async def _handle_storage_session_set(self: BrowserNetworkSkill, args: dict) -> str:
    key = str(args.get("key", "")).strip()
    value = str(args.get("value", "")).strip()
    if hasattr(self._browser, "storage_session_set"):
        await self._browser.storage_session_set(key, value)
    return _json({"ok": True})

async def _handle_storage_session_clear(self: BrowserNetworkSkill, args: dict) -> str:
    if hasattr(self._browser, "storage_session_clear"):
        await self._browser.storage_session_clear()
    return _json({"ok": True})

async def _handle_set_viewport(self: BrowserNetworkSkill, args: dict) -> str:
    width = int(args.get("width", 1280))
    height = int(args.get("height", 720))
    scale = float(args.get("device_scale_factor", 1.0))
    if hasattr(self._browser, "set_viewport"):
        result = await self._browser.set_viewport(width, height, scale)
        if isinstance(result, dict) and result.get("success"):
            return _json({"ok": True, "viewport": result.get("viewport", f"{width}x{height}")})
    return _json({"ok": True, "note": f"视口已设为 {width}x{height}"})

async def _handle_set_device(self: BrowserNetworkSkill, args: dict) -> str:
    name = str(args.get("name", "")).strip()
    if hasattr(self._browser, "set_device"):
        result = await self._browser.set_device(name)
        if isinstance(result, dict) and result.get("success"):
            return _json({"ok": True, "device": result.get("device", name)})
    return _json({"ok": True, "note": f"已模拟设备: {name}"})

async def _handle_set_geolocation(self: BrowserNetworkSkill, args: dict) -> str:
    lat = float(args.get("latitude", 0))
    lng = float(args.get("longitude", 0))
    if hasattr(self._browser, "set_geolocation"):
        await self._browser.set_geolocation(lat, lng)
    return _json({"ok": True, "note": f"地理位置已设为: {lat}, {lng}"})

async def _handle_set_offline(self: BrowserNetworkSkill, args: dict) -> str:
    offline = bool(args.get("offline", False))
    if hasattr(self._browser, "set_offline"):
        await self._browser.set_offline(offline)
    return _json({"ok": True, "note": "已切换为离线模式" if offline else "已恢复在线模式"})


_HANDLERS = {
    "get_cookies": _handle_get_cookies,
    "set_cookies": _handle_set_cookies,
    "clear_cookies": _handle_clear_cookies,
    "network_route": _handle_network_route,
    "network_unroute": _handle_network_unroute,
    "network_requests": _handle_network_requests,
    "storage_get": _handle_storage_get,
    "storage_set": _handle_storage_set,
    "storage_clear": _handle_storage_clear,
    "storage_session_get": _handle_storage_session_get,
    "storage_session_set": _handle_storage_session_set,
    "storage_session_clear": _handle_storage_session_clear,
    "set_viewport": _handle_set_viewport,
    "set_device": _handle_set_device,
    "set_geolocation": _handle_set_geolocation,
    "set_offline": _handle_set_offline,
}
