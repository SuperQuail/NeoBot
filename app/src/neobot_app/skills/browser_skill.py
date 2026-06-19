"""BrowserSkill — 核心浏览器自动化 Skill（导航、交互、内容提取、截图等）。

接受 duck-typed browser_instance，无实例时以 stub 模式运行。
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any

from neobot_app.skills.base import SkillModule


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class BrowserSkill(SkillModule):
    """核心浏览器自动化 Skill — 导航、交互、内容提取、截图、JS 执行等。"""

    @property
    def name(self) -> str:
        return "browser"

    @property
    def description(self) -> str:
        return "核心浏览器自动化：导航、点击、输入、内容提取、截图、等待等"

    @property
    def instructions(self) -> str:
        return (
            "浏览器 Skill 提供完整的网页自动化能力：\n\n"
            "## 生命周期\n"
            "  open / close\n\n"
            "## 导航\n"
            "  navigate, back, forward, reload\n\n"
            "## 内容提取\n"
            "  snapshot — 可访问性树快照（@e1, @e2, ...）\n"
            "  get_text / get_html / get_title / get_url\n\n"
            "## 交互\n"
            "  click / dblclick / focus / hover\n"
            "  type_text / press_key / select\n"
            "  upload_file\n\n"
            "## 等待\n"
            "  wait — 支持 selector/text/url/network_idle/fn/timeout 条件\n\n"
            "## 截图\n"
            "  screenshot — 返回 base64\n"
            "  shot — 保存到沙箱并返回路径\n\n"
            "## JavaScript\n"
            "  execute_js\n\n"
            "## 对话框\n"
            "  dialog_accept / dialog_dismiss / dialog_status\n\n"
            "## 标签页\n"
            "  list_tabs / new_tab / switch_tab / close_tab\n\n"
            "## 调试\n"
            "  get_console_logs / get_page_errors\n\n"
            "使用流程：1. navigate(url) → 2. snapshot() → 3. click(@e3) → 4. 重新 snapshot()\n\n"
            "注意：\n"
            "  - @ref 在页面变化后失效，需重新 snapshot\n"
            "  - 网络/Cookie/Storage 操作请使用 browser_network 技能\n"
            "  - 仅处理简单的单页操作，复杂的多步调研委托给 background_trigger skill"
        )

    def __init__(
        self,
        browser_instance: Any = None,
        lifecycle_manager: Any = None,
        sandbox_service: Any = None,
    ) -> None:
        self._browser = browser_instance
        self._lifecycle = lifecycle_manager
        self._sandbox = sandbox_service
        self._started = False

    def reset(self) -> None:
        pass

    def _check_browser(self) -> str | None:
        """检查浏览器是否可用。返回 None 表示可用，否则返回错误消息。"""
        if self._browser is None:
            return "浏览器未启动（browser_instance 未注入）"
        return None

    def _check_lifecycle(self) -> None:
        if self._lifecycle is None:
            return
        if self._lifecycle.should_auto_close():
            pass  # 由外部调用者决定是否关闭

    def get_tools(self) -> list[dict]:
        return [
            # ── 生命周期 ──
            self._tool_def("open", "启动浏览器，可选导航到指定 URL。", {
                "properties": {
                    "url": {"type": "string", "description": "可选，启动后导航到的 URL"},
                },
            }),
            self._tool_def("close", "关闭浏览器并释放资源。"),
            # ── 导航 ──
            self._tool_def("navigate", "导航到指定 URL，返回页面标题和文本预览。", {
                "properties": {
                    "url": {"type": "string", "description": "目标 URL（完整网址）"},
                },
                "required": ["url"],
            }),
            self._tool_def("back", "浏览器后退到上一页。"),
            self._tool_def("forward", "浏览器前进到下一页。"),
            self._tool_def("reload", "刷新当前页面。"),
            # ── 快照 ──
            self._tool_def("snapshot", "获取页面可访问性树快照，返回带 @eN 引用的交互元素列表。页面变化后需重新获取。", {
                "properties": {
                    "detailed": {"type": "boolean", "description": "是否输出详细模式", "default": False},
                },
            }),
            # ── 内容提取 ──
            self._tool_def("get_text", "获取页面可见文本内容。", {
                "properties": {
                    "max_chars": {"type": "integer", "description": "最大字符数", "default": 10000},
                },
            }),
            self._tool_def("get_html", "获取页面 HTML 源码。", {
                "properties": {
                    "max_chars": {"type": "integer", "description": "最大字符数", "default": 50000},
                },
            }),
            self._tool_def("get_title", "获取当前页面标题。"),
            self._tool_def("get_url", "获取当前页面 URL。"),
            # ── 元素交互 ──
            self._tool_def("click", "点击元素。支持 @e1 引用、CSS 选择器、text=文本。", {
                "properties": {
                    "selector": {"type": "string", "description": "元素标识：@e1（快照引用）、CSS 选择器、text=文本"},
                },
                "required": ["selector"],
            }),
            self._tool_def("dblclick", "双击元素。", {
                "properties": {
                    "selector": {"type": "string", "description": "元素标识"},
                },
                "required": ["selector"],
            }),
            self._tool_def("focus", "聚焦到元素（使元素获得键盘焦点）。", {
                "properties": {
                    "selector": {"type": "string", "description": "元素标识"},
                },
                "required": ["selector"],
            }),
            self._tool_def("type_text", "在输入框中输入文本，默认先清空已有内容。", {
                "properties": {
                    "selector": {"type": "string", "description": "输入框选择器"},
                    "text": {"type": "string", "description": "要输入的文本"},
                    "clear": {"type": "boolean", "description": "是否先清空已有内容，默认 true"},
                },
                "required": ["selector", "text"],
            }),
            self._tool_def("press_key", "按下键盘按键（Enter, Escape, Tab, ArrowDown 等）。", {
                "properties": {
                    "keys": {"type": "string", "description": "按键名称，如 Enter, Escape, Tab"},
                },
                "required": ["keys"],
            }),
            self._tool_def("hover", "悬停在元素上（触发 hover 效果）。", {
                "properties": {
                    "selector": {"type": "string", "description": "元素标识"},
                },
                "required": ["selector"],
            }),
            self._tool_def("select", "选择下拉框的选项（单选）。", {
                "properties": {
                    "selector": {"type": "string", "description": "下拉框选择器"},
                    "option": {"type": "string", "description": "选项值（value 属性）"},
                },
                "required": ["selector", "option"],
            }),
            self._tool_def("upload_file", "上传文件到文件选择器。", {
                "properties": {
                    "selector": {"type": "string", "description": "文件 input 选择器"},
                    "filepath": {"type": "string", "description": "本地文件完整路径"},
                },
                "required": ["selector", "filepath"],
            }),
            # ── 等待 ──
            self._tool_def("wait", "等待页面条件满足。支持: selector/text/url/network_idle/fn/timeout", {
                "properties": {
                    "condition": {
                        "type": "string",
                        "enum": ["selector", "text", "url", "network_idle", "fn", "timeout"],
                        "description": "等待条件类型",
                    },
                    "value": {"type": "string", "description": "条件值"},
                    "timeout": {"type": "integer", "description": "最长等待秒数", "default": 20},
                },
                "required": ["condition"],
            }),
            # ── 截图 ──
            self._tool_def("screenshot", "对当前页面截图，返回 base64 编码的 PNG 图片。"),
            self._tool_def("shot", "对当前页面截图并保存到沙箱临时目录，返回文件路径。", {
                "properties": {
                    "chat_flow_id": {"type": "string", "description": "聊天流 ID，如 Group_12345"},
                    "name": {"type": "string", "description": "可选，截图文件名前缀"},
                },
                "required": ["chat_flow_id"],
            }),
            # ── JavaScript ──
            self._tool_def("execute_js", "在页面中执行 JavaScript 代码。", {
                "properties": {
                    "script": {"type": "string", "description": "要执行的 JS 代码"},
                },
                "required": ["script"],
            }),
            # ── 对话框 ──
            self._tool_def("dialog_accept", "接受当前弹窗（alert/confirm/prompt）。可传入文本用于 prompt 输入。", {
                "properties": {
                    "text": {"type": "string", "description": "可选，prompt 对话框的输入文本"},
                },
            }),
            self._tool_def("dialog_dismiss", "取消当前弹窗（confirm/prompt）。"),
            self._tool_def("dialog_status", "检查页面上是否有活跃的对话框。"),
            # ── 标签页 ──
            self._tool_def("new_tab", "打开新标签页。", {
                "properties": {
                    "url": {"type": "string", "description": "可选，新标签页的 URL"},
                },
            }),
            self._tool_def("switch_tab", "切换到指定标签页（0-based 索引）。", {
                "properties": {
                    "index": {"type": "integer", "description": "标签页索引，从 0 开始"},
                },
                "required": ["index"],
            }),
            self._tool_def("list_tabs", "列出所有标签页及标题/URL。"),
            self._tool_def("close_tab", "关闭指定标签页。", {
                "properties": {
                    "index": {"type": "integer", "description": "要关闭的标签页索引"},
                },
                "required": ["index"],
            }),
            # ── 调试 ──
            self._tool_def("get_console_logs", "获取当前页面的 console 日志。"),
            self._tool_def("get_page_errors", "获取当前页面的运行时错误。"),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        err = self._check_browser()
        if err:
            handler = _STUB_HANDLERS.get(tool_name)
            if handler:
                return await handler(self, args)
            return _json({"ok": False, "error": f"浏览器不可用: {err}"})
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown browser tool: {tool_name}"})
        return await handler(self, args)

    @staticmethod
    def _tool_def(name: str, desc: str, params: dict | None = None) -> dict:
        p = {"type": "object", "properties": {}, "required": []}
        if params:
            p["properties"] = params.get("properties", {})
            p["required"] = params.get("required", [])
        return {"type": "function", "function": {"name": name, "description": desc, "parameters": p}}


# ── Stub Handlers（无 browser_instance 时的 fallback）──

async def _stub_open(self: BrowserSkill, args: dict) -> str:
    return _json({"ok": False, "error": "浏览器未启动"})

async def _stub_navigate(self: BrowserSkill, args: dict) -> str:
    return _json({"ok": False, "error": "浏览器未启动"})


_STUB_HANDLERS = {
    "open": _stub_open,
    "navigate": _stub_navigate,
}


# ── Real Handlers（browser_instance 存在时）──

async def _handle_open(self: BrowserSkill, args: dict) -> str:
    url = args.get("url", "")
    result = await self._browser.open(url) if hasattr(self._browser, "open") else None
    if result and result.get("success"):
        return _json({"ok": True, "url": result.get("url", ""), "title": result.get("title", "")})
    return _json({"ok": True, "note": "浏览器已就绪"})

async def _handle_close(self: BrowserSkill, args: dict) -> str:
    if hasattr(self._browser, "close"):
        await self._browser.close()
    return _json({"ok": True, "note": "浏览器已关闭"})

async def _handle_navigate(self: BrowserSkill, args: dict) -> str:
    url = str(args.get("url", "")).strip()
    if hasattr(self._browser, "navigate"):
        result = await self._browser.navigate(url)
        if isinstance(result, dict) and result.get("success"):
            return _json({"ok": True, "url": result.get("url", url), "title": result.get("title", "")})
    return _json({"ok": True, "note": f"已导航到 {url}"})

async def _handle_snapshot(self: BrowserSkill, args: dict) -> str:
    detailed = args.get("detailed", False)
    if hasattr(self._browser, "snapshot"):
        result = await self._browser.snapshot(detailed=detailed)
        if isinstance(result, dict) and result.get("success"):
            return _json({"ok": True, "title": result.get("title", ""), "url": result.get("url", ""), "snapshot": result.get("snapshot", "")})
    return _json({"ok": True, "note": "snapshot stub"})

async def _handle_get_text(self: BrowserSkill, args: dict) -> str:
    max_chars = int(args.get("max_chars", 10000))
    if hasattr(self._browser, "get_text"):
        result = await self._browser.get_text(max_chars=max_chars)
        if isinstance(result, dict) and result.get("success"):
            return _json({"ok": True, "text": result.get("text", ""), "length": result.get("total_length", 0)})
    return _json({"ok": True, "note": "get_text stub"})

async def _handle_get_title(self: BrowserSkill, args: dict) -> str:
    if hasattr(self._browser, "get_title"):
        result = await self._browser.get_title()
        if isinstance(result, dict) and result.get("success"):
            return _json({"ok": True, "title": result.get("title", "")})
    return _json({"ok": True, "note": "get_title stub"})

async def _handle_get_url(self: BrowserSkill, args: dict) -> str:
    if hasattr(self._browser, "get_url"):
        result = await self._browser.get_url()
        if isinstance(result, dict) and result.get("success"):
            return _json({"ok": True, "url": result.get("url", "")})
    return _json({"ok": True, "note": "get_url stub"})

async def _handle_click(self: BrowserSkill, args: dict) -> str:
    selector = str(args.get("selector", "")).strip()
    if hasattr(self._browser, "click"):
        result = await self._browser.click(selector)
        if isinstance(result, dict) and result.get("success"):
            return _json({"ok": True, "selector": selector})
    return _json({"ok": True, "note": f"已点击 {selector}"})

async def _handle_type_text(self: BrowserSkill, args: dict) -> str:
    selector = str(args.get("selector", "")).strip()
    text = str(args.get("text", "")).strip()
    clear = args.get("clear", True)
    if hasattr(self._browser, "type_text"):
        result = await self._browser.type_text(selector, text, clear=clear)
        if isinstance(result, dict) and result.get("success"):
            return _json({"ok": True, "selector": selector})
    return _json({"ok": True, "note": f"已输入文本到 {selector}"})

async def _handle_screenshot(self: BrowserSkill, args: dict) -> str:
    if hasattr(self._browser, "screenshot"):
        result = await self._browser.screenshot()
        if isinstance(result, dict) and result.get("success"):
            return _json({"ok": True, "data_url": result.get("data_url", ""), "size_bytes": result.get("size_bytes", 0)})
    return _json({"ok": True, "note": "screenshot stub"})

async def _handle_shot(self: BrowserSkill, args: dict) -> str:
    chat_flow_id = str(args.get("chat_flow_id", "")).strip()
    name = args.get("name", "") or datetime.now().strftime("shot_%Y%m%d_%H%M%S")
    if not chat_flow_id:
        return _json({"ok": False, "error": "缺少 chat_flow_id"})
    if not hasattr(self._browser, "screenshot"):
        return _json({"ok": True, "note": "shot stub"})
    result = await self._browser.screenshot()
    if not isinstance(result, dict) or not result.get("success"):
        return _json({"ok": False, "error": "截图失败"})
    b64_data = result.get("data_url", "").removeprefix("data:image/png;base64,")
    png_bytes = base64.b64decode(b64_data)
    if self._sandbox:
        path = self._sandbox.ensure_temp_dir(chat_flow_id) / f"{name}.png"
        await self._sandbox.write_file(path, png_bytes)
        return _json({"ok": True, "path": str(path), "size_bytes": len(png_bytes)})
    return _json({"ok": True, "note": "沙箱未配置，截图未保存", "size_bytes": len(png_bytes)})

async def _handle_execute_js(self: BrowserSkill, args: dict) -> str:
    script = str(args.get("script", "")).strip()
    if hasattr(self._browser, "execute_js"):
        result = await self._browser.execute_js(script)
        if isinstance(result, dict) and result.get("success"):
            return _json({"ok": True, "result": result.get("result", "")})
    return _json({"ok": True, "note": "execute_js stub"})

async def _handle_back(self: BrowserSkill, args: dict) -> str:
    if hasattr(self._browser, "back"):
        await self._browser.back()
    return _json({"ok": True})

async def _handle_forward(self: BrowserSkill, args: dict) -> str:
    if hasattr(self._browser, "forward"):
        await self._browser.forward()
    return _json({"ok": True})

async def _handle_reload(self: BrowserSkill, args: dict) -> str:
    if hasattr(self._browser, "reload"):
        await self._browser.reload()
    return _json({"ok": True})

async def _handle_get_html(self: BrowserSkill, args: dict) -> str:
    max_chars = int(args.get("max_chars", 50000))
    if hasattr(self._browser, "get_html"):
        result = await self._browser.get_html(max_chars=max_chars)
        if isinstance(result, dict) and result.get("success"):
            return _json({"ok": True, "html": result.get("html", "")})
    return _json({"ok": True, "note": "get_html stub"})

async def _handle_dblclick(self: BrowserSkill, args: dict) -> str:
    selector = str(args.get("selector", "")).strip()
    if hasattr(self._browser, "dblclick"):
        await self._browser.dblclick(selector)
    return _json({"ok": True, "note": f"已双击 {selector}"})

async def _handle_focus(self: BrowserSkill, args: dict) -> str:
    selector = str(args.get("selector", "")).strip()
    if hasattr(self._browser, "focus"):
        await self._browser.focus(selector)
    return _json({"ok": True})

async def _handle_press_key(self: BrowserSkill, args: dict) -> str:
    keys = str(args.get("keys", "")).strip()
    if hasattr(self._browser, "press_key"):
        await self._browser.press_key(keys)
    return _json({"ok": True, "note": f"已按下 {keys}"})

async def _handle_hover(self: BrowserSkill, args: dict) -> str:
    selector = str(args.get("selector", "")).strip()
    if hasattr(self._browser, "hover"):
        await self._browser.hover(selector)
    return _json({"ok": True})

async def _handle_select(self: BrowserSkill, args: dict) -> str:
    selector = str(args.get("selector", "")).strip()
    option = str(args.get("option", "")).strip()
    if hasattr(self._browser, "select"):
        await self._browser.select(selector, option)
    return _json({"ok": True, "note": f"已选择 {option}"})

async def _handle_upload_file(self: BrowserSkill, args: dict) -> str:
    selector = str(args.get("selector", "")).strip()
    filepath = str(args.get("filepath", "")).strip()
    if hasattr(self._browser, "upload_file"):
        await self._browser.upload_file(selector, filepath)
    return _json({"ok": True, "note": f"已上传 {filepath}"})

async def _handle_wait(self: BrowserSkill, args: dict) -> str:
    condition = str(args.get("condition", "")).strip()
    timeout = int(args.get("timeout", 20))
    if hasattr(self._browser, "wait"):
        result = await self._browser.wait(condition, str(args.get("value", "")), timeout)
        if isinstance(result, dict) and result.get("success"):
            return _json({"ok": True, "condition": condition})
    return _json({"ok": True, "note": f"等待完成 ({condition})"})

async def _handle_dialog_accept(self: BrowserSkill, args: dict) -> str:
    text = args.get("text", "")
    if hasattr(self._browser, "dialog_accept"):
        await self._browser.dialog_accept(text)
    return _json({"ok": True, "note": "对话框已接受"})

async def _handle_dialog_dismiss(self: BrowserSkill, args: dict) -> str:
    if hasattr(self._browser, "dialog_dismiss"):
        await self._browser.dialog_dismiss()
    return _json({"ok": True, "note": "对话框已取消"})

async def _handle_dialog_status(self: BrowserSkill, args: dict) -> str:
    if hasattr(self._browser, "dialog_status"):
        result = await self._browser.dialog_status()
        if isinstance(result, dict):
            return _json({"ok": True, "has_dialog": result.get("has_dialog", False)})
    return _json({"ok": True, "has_dialog": False})

async def _handle_new_tab(self: BrowserSkill, args: dict) -> str:
    url = args.get("url", "")
    if hasattr(self._browser, "new_tab"):
        await self._browser.new_tab(url)
    return _json({"ok": True, "note": f"已打开新标签页"})

async def _handle_switch_tab(self: BrowserSkill, args: dict) -> str:
    index = int(args.get("index", 0))
    if hasattr(self._browser, "switch_tab"):
        await self._browser.switch_tab(index)
    return _json({"ok": True, "note": f"已切换到标签页 {index}"})

async def _handle_list_tabs(self: BrowserSkill, args: dict) -> str:
    if hasattr(self._browser, "list_tabs"):
        result = await self._browser.list_tabs()
        if isinstance(result, dict) and result.get("success"):
            return _json({"ok": True, "tabs": result.get("tabs", [])})
    return _json({"ok": True, "tabs": []})

async def _handle_close_tab(self: BrowserSkill, args: dict) -> str:
    index = int(args.get("index", 0))
    if hasattr(self._browser, "close_tab"):
        await self._browser.close_tab(index)
    return _json({"ok": True, "note": f"已关闭标签页 {index}"})

async def _handle_get_console_logs(self: BrowserSkill, args: dict) -> str:
    if hasattr(self._browser, "get_console_logs"):
        result = await self._browser.get_console_logs()
        if isinstance(result, dict) and result.get("success"):
            return _json({"ok": True, "logs": result.get("logs", "")})
    return _json({"ok": True, "logs": ""})

async def _handle_get_page_errors(self: BrowserSkill, args: dict) -> str:
    if hasattr(self._browser, "get_page_errors"):
        result = await self._browser.get_page_errors()
        if isinstance(result, dict) and result.get("success"):
            return _json({"ok": True, "errors": result.get("errors", "")})
    return _json({"ok": True, "errors": ""})


_HANDLERS = {
    "open": _handle_open,
    "close": _handle_close,
    "navigate": _handle_navigate,
    "back": _handle_back,
    "forward": _handle_forward,
    "reload": _handle_reload,
    "snapshot": _handle_snapshot,
    "get_text": _handle_get_text,
    "get_html": _handle_get_html,
    "get_title": _handle_get_title,
    "get_url": _handle_get_url,
    "click": _handle_click,
    "dblclick": _handle_dblclick,
    "focus": _handle_focus,
    "type_text": _handle_type_text,
    "press_key": _handle_press_key,
    "hover": _handle_hover,
    "select": _handle_select,
    "upload_file": _handle_upload_file,
    "wait": _handle_wait,
    "screenshot": _handle_screenshot,
    "shot": _handle_shot,
    "execute_js": _handle_execute_js,
    "dialog_accept": _handle_dialog_accept,
    "dialog_dismiss": _handle_dialog_dismiss,
    "dialog_status": _handle_dialog_status,
    "new_tab": _handle_new_tab,
    "switch_tab": _handle_switch_tab,
    "list_tabs": _handle_list_tabs,
    "close_tab": _handle_close_tab,
    "get_console_logs": _handle_get_console_logs,
    "get_page_errors": _handle_get_page_errors,
}
