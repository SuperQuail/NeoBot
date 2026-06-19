"""
agent-browser — AI 代理浏览器操作层

将 BrowserManager 的低级操作封装为 AI 友好的高级动作函数。
每个动作返回结构化结果（dict），方便 AI 解析。
"""
from __future__ import annotations

import asyncio
import base64
from datetime import datetime
from pathlib import Path
from typing import Any

from .manager import BrowserManager
from .snapshot import snapshot_page


class AgentBrowser:
    """AI 代理浏览器 — 高级操作接口。"""

    def __init__(self, headless: bool = True, port: int = 0, user_data_dir: str | Path | None = None, browser_path: str = ""):
        self._manager = BrowserManager(headless=headless, port=port, user_data_dir=user_data_dir, browser_path=browser_path)
        self._started = False

    async def start(self) -> None:
        if not self._started:
            await self._manager.start()
            self._started = True

    async def close(self) -> None:
        await self._manager.close()
        self._started = False

    @property
    def user_data_dir(self) -> str:
        return self._manager.user_data_dir

    # ── 内部辅助 ──

    def _result(
        self, success: bool, data: dict[str, Any] | None = None, error: str = "",
    ) -> dict:
        result = {"success": success, "timestamp": datetime.now().isoformat()}
        if data:
            result.update(data)
        if error:
            result["error"] = error
        return result

    async def _ensure(self) -> BrowserManager:
        if not self._started:
            await self.start()
        return self._manager

    # ── 生命周期 ──

    async def open(self, url: str = "") -> dict:
        """启动浏览器，可选导航到 URL。"""
        mgr = await self._ensure()
        try:
            result = await mgr.open(url)
            return self._result(result["success"], result)
        except Exception as e:
            return self._result(False, error=str(e))

    async def connect(self, port: int) -> dict:
        """连接到已运行的浏览器 CDP 端口。"""
        try:
            mgr = await self._ensure()
            result = await mgr.connect(port)
            return self._result(result["success"], result)
        except Exception as e:
            return self._result(False, error=str(e))

    async def launch_headed(self, url: str | None = None) -> dict:
        """以有头模式重新启动浏览器（适合人工处理验证码/登录）。"""
        try:
            await self.close()
            self._started = False
            self._manager = BrowserManager(headless=False, port=self._manager._port, user_data_dir=self._manager.user_data_dir)
            result = await self._manager.launch_headed(url)
            self._started = True
            return self._result(result["success"], result)
        except Exception as e:
            return self._result(False, error=str(e))

    # ── 导航 ──

    async def navigate(self, url: str, wait_content: bool = True) -> dict:
        """导航到 URL。返回标题、URL 和文本预览。"""
        mgr = await self._ensure()
        try:
            title = await mgr.navigate(url)
            if wait_content:
                for _ in range(16):
                    total = await mgr.get_text_length()
                    if total > 200:
                        break
                    await asyncio.sleep(0.5)
            preview = await mgr.get_text_range(0, 2000)
            total = await mgr.get_text_length()
            return self._result(True, {
                "action": "navigate",
                "url": await mgr.current_url(),
                "title": title,
                "text_length": total,
                "text_preview": preview,
            })
        except Exception as e:
            return self._result(False, error=str(e))

    async def wait(self, seconds: float = 2.0) -> dict:
        """等待页面加载/渲染，完成后返回页面信息。"""
        mgr = await self._ensure()
        try:
            info = await mgr.wait(seconds)
            return self._result(True, {
                "action": "wait",
                "title": info["title"],
                "url": info["url"],
                "text_length": info["text_length"],
            })
        except Exception as e:
            return self._result(False, error=str(e))

    async def back(self) -> dict:
        """浏览器后退。"""
        mgr = await self._ensure()
        try:
            await mgr.execute_js("window.history.back()")
            await asyncio.sleep(0.3)
            return self._result(True, {
                "action": "back",
                "url": await mgr.current_url(),
                "title": await mgr.get_title(),
            })
        except Exception as e:
            return self._result(False, error=str(e))

    async def forward(self) -> dict:
        """浏览器前进。"""
        mgr = await self._ensure()
        try:
            await mgr.execute_js("window.history.forward()")
            await asyncio.sleep(0.3)
            return self._result(True, {
                "action": "forward",
                "url": await mgr.current_url(),
                "title": await mgr.get_title(),
            })
        except Exception as e:
            return self._result(False, error=str(e))

    async def reload(self) -> dict:
        """刷新当前页面。"""
        mgr = await self._ensure()
        try:
            await mgr.execute_js("location.reload()")
            await asyncio.sleep(0.3)
            return self._result(True, {
                "action": "reload",
                "url": await mgr.current_url(),
                "title": await mgr.get_title(),
            })
        except Exception as e:
            return self._result(False, error=str(e))

    async def pushstate(self, url: str) -> dict:
        """SPA 客户端导航（pushState）。"""
        mgr = await self._ensure()
        try:
            result = await mgr.pushstate(url)
            return self._result(result["success"], result)
        except Exception as e:
            return self._result(False, error=str(e))

    # ── 页面快照 ──

    async def snapshot(self, detailed: bool = False) -> dict:
        """获取页面可访问性快照（带 @ref 引用）。"""
        mgr = await self._ensure()
        try:
            page = mgr.page
            snap = await snapshot_page(page, detailed=detailed)
            return self._result(True, {
                "action": "snapshot",
                "snapshot": snap,
                "url": await mgr.current_url(),
                "title": await mgr.get_title(),
            })
        except Exception as e:
            return self._result(False, error=str(e))

    # ── 内容提取 ──

    async def get_text(self, max_chars: int = 10000, offset: int = 0) -> dict:
        """获取页面可见文本。"""
        mgr = await self._ensure()
        try:
            total = await mgr.get_text_length()
            text = await mgr.get_text_range(offset, max_chars)
            truncated = (offset + max_chars) < total
            return self._result(True, {
                "action": "get_text",
                "text": text,
                "total_length": total,
                "offset": offset,
                "truncated": truncated,
                "url": await mgr.current_url(),
                "title": await mgr.get_title(),
            })
        except Exception as e:
            return self._result(False, error=str(e))

    async def get_page_info(self) -> dict:
        """获取页面结构概览：标题、URL、文本长度、各级标题列表、链接数。"""
        mgr = await self._ensure()
        try:
            info = await mgr.get_page_info()
            return self._result(True, {
                "action": "get_page_info",
                "title": info.get("title", ""),
                "url": info.get("url", ""),
                "text_length": info.get("text_length", 0),
                "word_count": info.get("word_count", 0),
                "heading_count": info.get("heading_count", 0),
                "headings": info.get("headings", []),
                "link_count": info.get("link_count", 0),
            })
        except Exception as e:
            return self._result(False, error=str(e))

    async def get_html(self, max_chars: int = 50000) -> dict:
        """获取页面 HTML。"""
        mgr = await self._ensure()
        try:
            html = await mgr.get_html()
            truncated = len(html) > max_chars
            return self._result(True, {
                "action": "get_html",
                "html": html[:max_chars],
                "total_length": len(html),
                "truncated": truncated,
            })
        except Exception as e:
            return self._result(False, error=str(e))

    async def get_title(self) -> dict:
        """获取页面标题。"""
        mgr = await self._ensure()
        try:
            return self._result(True, {
                "action": "get_title",
                "title": await mgr.get_title(),
            })
        except Exception as e:
            return self._result(False, error=str(e))

    async def get_url(self) -> dict:
        """获取当前页面 URL。"""
        mgr = await self._ensure()
        try:
            return self._result(True, {
                "action": "get_url",
                "url": await mgr.current_url(),
            })
        except Exception as e:
            return self._result(False, error=str(e))

    # ── 元素交互 ──

    async def click(self, selector: str, index: int = 0) -> dict:
        """点击元素。selector 支持 @e1 引用、CSS 选择器、text=文本。index 指定第 N 个匹配元素。"""
        mgr = await self._ensure()
        try:
            actual_selector = selector
            if selector.startswith("@e"):
                from .snapshot import get_element_by_ref_sync
                el = await asyncio.to_thread(
                    get_element_by_ref_sync, mgr.page, selector
                )
                if el is None:
                    return self._result(
                        False, error=f"快照引用 {selector} 已过期，请重新获取快照"
                    )
                actual_selector = f"text={el.text}" if el.text else el.selector

            result = await mgr.click(actual_selector, index=index)
            if result["success"]:
                return self._result(True, {
                    "action": "click",
                    "selector": selector,
                    "index": index,
                    "tag": result.get("tag", ""),
                    "text": result.get("text", ""),
                })
            return self._result(False, error=result.get("error", "点击失败"))
        except Exception as e:
            return self._result(False, error=str(e))

    async def click_new_tab(self, selector: str) -> dict:
        """点击元素并在新标签页中打开链接。"""
        mgr = await self._ensure()
        try:
            result = await mgr.click_new_tab(selector)
            return self._result(result["success"], result)
        except Exception as e:
            return self._result(False, error=str(e))

    async def dblclick(self, selector: str) -> dict:
        """双击元素。"""
        mgr = await self._ensure()
        try:
            result = await mgr.dblclick(selector)
            return self._result(result["success"], result)
        except Exception as e:
            return self._result(False, error=str(e))

    async def focus(self, selector: str) -> dict:
        """聚焦到元素。"""
        mgr = await self._ensure()
        try:
            result = await mgr.focus(selector)
            return self._result(result["success"], result)
        except Exception as e:
            return self._result(False, error=str(e))

    async def type_text(self, selector: str, text: str, clear: bool = True) -> dict:
        """在输入框中输入文本。clear=True 先清空再输入。"""
        mgr = await self._ensure()
        try:
            result = await mgr.type_text(selector, text, clear=clear)
            return self._result(result["success"], result)
        except Exception as e:
            return self._result(False, error=str(e))

    async def press_key(self, keys: str) -> dict:
        """按下键盘按键（Enter, Escape, Tab 等）。"""
        mgr = await self._ensure()
        try:
            result = await mgr.press_key(keys)
            return self._result(result["success"], result)
        except Exception as e:
            return self._result(False, error=str(e))

    async def press_combo(self, combo: str) -> dict:
        """按下组合键，如 'Control+a', 'Alt+Tab'。"""
        mgr = await self._ensure()
        try:
            result = await mgr.press_combo(combo)
            return self._result(result["success"], result)
        except Exception as e:
            return self._result(False, error=str(e))

    async def key_down(self, key: str) -> dict:
        """按住按键。"""
        mgr = await self._ensure()
        try:
            result = await mgr.key_down(key)
            return self._result(result["success"], result)
        except Exception as e:
            return self._result(False, error=str(e))

    async def key_up(self, key: str) -> dict:
        """释放按键。"""
        mgr = await self._ensure()
        try:
            result = await mgr.key_up(key)
            return self._result(result["success"], result)
        except Exception as e:
            return self._result(False, error=str(e))

    async def check(self, selector: str) -> dict:
        """勾选复选框。"""
        mgr = await self._ensure()
        try:
            result = await mgr.check(selector)
            return self._result(result["success"], result)
        except Exception as e:
            return self._result(False, error=str(e))

    async def uncheck(self, selector: str) -> dict:
        """取消勾选复选框。"""
        mgr = await self._ensure()
        try:
            result = await mgr.uncheck(selector)
            return self._result(result["success"], result)
        except Exception as e:
            return self._result(False, error=str(e))

    async def select(self, selector: str, option: str) -> dict:
        """选择下拉框选项。"""
        mgr = await self._ensure()
        try:
            result = await mgr.select_option(selector, option)
            return self._result(result["success"], result)
        except Exception as e:
            return self._result(False, error=str(e))

    async def select_multi(self, selector: str, options: list[str]) -> dict:
        """下拉框多选。"""
        mgr = await self._ensure()
        try:
            result = await mgr.select_multi(selector, options)
            return self._result(result["success"], result)
        except Exception as e:
            return self._result(False, error=str(e))

    async def hover(self, selector: str) -> dict:
        """悬停在元素上。"""
        mgr = await self._ensure()
        try:
            result = await mgr.hover(selector)
            return self._result(result["success"], result)
        except Exception as e:
            return self._result(False, error=str(e))

    async def scroll(self, direction: str = "down", amount: int = 500) -> dict:
        """滚动页面。"""
        mgr = await self._ensure()
        try:
            result = await mgr.scroll(direction, amount)
            return self._result(result["success"], result)
        except Exception as e:
            return self._result(False, error=str(e))

    async def scrollintoview(self, selector: str) -> dict:
        """将元素滚动到可视区域。"""
        mgr = await self._ensure()
        try:
            result = await mgr.scrollintoview(selector)
            return self._result(result["success"], result)
        except Exception as e:
            return self._result(False, error=str(e))

    async def drag_n_drop(self, source_selector: str, target_selector: str) -> dict:
        """拖拽元素到目标位置。"""
        mgr = await self._ensure()
        try:
            result = await mgr.drag_n_drop(source_selector, target_selector)
            return self._result(result["success"], result)
        except Exception as e:
            return self._result(False, error=str(e))

    async def upload_file(self, selector: str, filepath: str) -> dict:
        """上传文件到文件选择器。"""
        mgr = await self._ensure()
        try:
            result = await mgr.upload_file(selector, filepath)
            return self._result(result["success"], result)
        except Exception as e:
            return self._result(False, error=str(e))

    # ── 元素查询 ──

    async def get_element_text(self, selector: str) -> dict:
        """获取指定元素的文本内容。"""
        mgr = await self._ensure()
        return await mgr.get_element_text(selector)

    async def get_element_html(self, selector: str) -> dict:
        """获取指定元素的 innerHTML。"""
        mgr = await self._ensure()
        return await mgr.get_element_html(selector)

    async def get_element_attr(self, selector: str, attr: str) -> dict:
        """获取指定元素的属性值。"""
        mgr = await self._ensure()
        return await mgr.get_element_attr(selector, attr)

    async def get_element_value(self, selector: str) -> dict:
        """获取输入框的当前值。"""
        mgr = await self._ensure()
        return await mgr.get_element_value(selector)

    async def get_box(self, selector: str) -> dict:
        """获取元素的 bounding box。"""
        mgr = await self._ensure()
        return await mgr.get_box(selector)

    async def get_count(self, selector: str) -> dict:
        """统计匹配选择器的元素数量。"""
        mgr = await self._ensure()
        return await mgr.get_count(selector)

    async def get_styles(self, selector: str) -> dict:
        """获取元素的计算样式。"""
        mgr = await self._ensure()
        return await mgr.get_styles(selector)

    # ── 状态检查 ──

    async def is_visible(self, selector: str) -> dict:
        """检查元素是否可见。"""
        mgr = await self._ensure()
        return await mgr.is_visible(selector)

    async def is_enabled(self, selector: str) -> dict:
        """检查元素是否可用。"""
        mgr = await self._ensure()
        return await mgr.is_enabled(selector)

    async def is_checked(self, selector: str) -> dict:
        """检查复选框/单选框是否选中。"""
        mgr = await self._ensure()
        return await mgr.is_checked(selector)

    # ── 对话框处理 ──

    async def dialog_accept(self, text: str = "") -> dict:
        """接受对话框。"""
        mgr = await self._ensure()
        return await mgr.dialog_accept(text)

    async def dialog_dismiss(self) -> dict:
        """取消对话框。"""
        mgr = await self._ensure()
        return await mgr.dialog_dismiss()

    async def dialog_status(self) -> dict:
        """检查对话框状态。"""
        mgr = await self._ensure()
        return await mgr.dialog_status()

    # ── Frame 切换 ──

    async def frame(self, selector_or_name: str) -> dict:
        """切换到指定 iframe 或 'main' 回到主文档。"""
        mgr = await self._ensure()
        return await mgr.frame(selector_or_name)

    # ── 等待操作 ──

    async def wait(
        self,
        condition: str = "timeout",
        value: str = "",
        timeout: int = 20,
    ) -> dict:
        """等待页面条件满足。"""
        mgr = await self._ensure()
        return await mgr.wait(condition, value, timeout)

    # ── 浏览器设置 ──

    async def set_viewport(self, width: int, height: int, device_scale_factor: float = 1.0) -> dict:
        """设置视口大小。"""
        mgr = await self._ensure()
        return await mgr.set_viewport(width, height, device_scale_factor)

    async def set_device(self, name: str) -> dict:
        """模拟移动设备（如 'iPhone 14', 'Pixel 7'）。"""
        mgr = await self._ensure()
        return await mgr.set_device(name)

    async def set_geolocation(self, latitude: float, longitude: float) -> dict:
        """模拟地理位置。"""
        mgr = await self._ensure()
        return await mgr.set_geolocation(latitude, longitude)

    async def set_offline(self, offline: bool) -> dict:
        """模拟离线/在线状态。"""
        mgr = await self._ensure()
        return await mgr.set_offline(offline)

    async def set_headers(self, headers: dict) -> dict:
        """设置自定义 HTTP 头。"""
        mgr = await self._ensure()
        return await mgr.set_headers(headers)

    async def set_credentials(self, username: str, password: str) -> dict:
        """设置 HTTP Basic Auth 凭据。"""
        mgr = await self._ensure()
        return await mgr.set_credentials(username, password)

    async def set_media(self, color_scheme: str = "", reduced_motion: str = "") -> dict:
        """模拟媒体特性（color-scheme, prefers-reduced-motion）。"""
        mgr = await self._ensure()
        return await mgr.set_media(color_scheme, reduced_motion)

    # ── 截图 ──

    async def screenshot(self) -> dict:
        """截图并保存为 JPEG 文件，返回文件路径（而非 base64 避免浪费 token）。"""
        mgr = await self._ensure()
        try:
            jpg_bytes = await mgr.screenshot(full_page=False)
            shot_dir = Path(self._manager.user_data_dir) / "screenshots"
            shot_dir.mkdir(parents=True, exist_ok=True)
            fname = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            shot_path = shot_dir / fname
            shot_path.write_bytes(jpg_bytes)
            return self._result(True, {
                "action": "screenshot",
                "path": str(shot_path),
                "size_bytes": len(jpg_bytes),
            })
        except Exception as e:
            return self._result(False, error=str(e))

    async def shot(self, name: str = "") -> dict:
        """截图保存到文件，返回文件路径。"""
        mgr = await self._ensure()
        try:
            shot_dir = Path(self._manager.user_data_dir) / "screenshots"
            shot_dir.mkdir(parents=True, exist_ok=True)
            fname = f"{name or 'shot'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            shot_path = shot_dir / fname
            png_bytes = await mgr.screenshot(path=shot_path)
            return self._result(True, {
                "action": "shot",
                "path": str(shot_path),
                "size_bytes": len(png_bytes),
                "name": name or "shot",
            })
        except Exception as e:
            return self._result(False, error=str(e))

    async def screenshot_annotated(self, name: str = "") -> dict:
        """截图并标注元素编号。"""
        mgr = await self._ensure()
        return await mgr.screenshot_annotated(name)

    # ── JavaScript ──

    async def execute_js(self, script: str) -> dict:
        """执行 JavaScript。"""
        mgr = await self._ensure()
        try:
            result = await mgr.execute_js(script)
            return self._result(True, {
                "action": "execute_js",
                "result": result,
            })
        except Exception as e:
            return self._result(False, error=str(e))

    # ── 标签页管理 ──

    async def new_tab(self, url: str = "") -> dict:
        """打开新标签页。"""
        mgr = await self._ensure()
        result = await mgr.new_tab(url)
        return self._result(result["success"], result)

    async def new_tab_label(self, label: str, url: str = "") -> dict:
        """新建标签页并命名（后续可通过标签名切换）。"""
        mgr = await self._ensure()
        result = await mgr.new_tab_label(label, url)
        return self._result(result["success"], result)

    async def switch_tab(self, index: int) -> dict:
        """切换到指定标签页（按索引）。"""
        mgr = await self._ensure()
        result = await mgr.switch_tab(index)
        return self._result(result["success"], result)

    async def switch_tab_by_label(self, label: str) -> dict:
        """通过标签名切换标签页。"""
        mgr = await self._ensure()
        result = await mgr.switch_tab_by_label(label)
        return self._result(result["success"], result)

    async def list_tabs(self) -> dict:
        """列出所有标签页。"""
        mgr = await self._ensure()
        tabs = await mgr.list_tabs()
        return self._result(True, {"action": "list_tabs", "tabs": tabs})

    async def close_tab(self, index: int) -> dict:
        """关闭标签页。"""
        mgr = await self._ensure()
        result = await mgr.close_tab(index)
        return self._result(result["success"], result)

    async def close_tabs(self, indices: list[int] | None = None, others: bool = False) -> dict:
        """批量关闭标签页。"""
        mgr = await self._ensure()
        result = await mgr.close_tabs(indices=indices, others=others)
        return self._result(result["success"], result)

    async def close_current_tab(self) -> dict:
        """关闭当前标签页。"""
        mgr = await self._ensure()
        result = await mgr.close_current_tab()
        return self._result(result["success"], result)

    async def window_new(self) -> dict:
        """新建浏览器窗口。"""
        mgr = await self._ensure()
        result = await mgr.window_new()
        return self._result(result["success"], result)

    async def create_tab(self, url: str = ""):
        """创建新标签页，返回独立 ChromiumTab 对象（用于并发操作）。"""
        mgr = await self._ensure()
        return await mgr.create_tab(url)

    # ── Cookie 管理 ──

    async def get_cookies(self, domain: str | None = None) -> dict:
        """获取 cookies。"""
        mgr = await self._ensure()
        try:
            if domain:
                cookie_str = await mgr.get_cookie_string(domain)
                return self._result(True, {
                    "action": "get_cookies",
                    "cookie_string": cookie_str,
                })
            cookies = await mgr.get_all_cookies()
            return self._result(True, {"action": "get_cookies", "cookies": cookies})
        except Exception as e:
            return self._result(False, error=str(e))

    async def set_cookies(self, cookies: list[dict]) -> dict:
        """设置 cookies。"""
        mgr = await self._ensure()
        return await mgr.set_cookies(cookies)

    async def save_cookies(self) -> dict:
        """持久化保存 cookies 到文件。"""
        mgr = await self._ensure()
        try:
            count = await mgr.save_cookies()
            return self._result(True, {"action": "save_cookies", "count": count})
        except Exception as e:
            return self._result(False, error=str(e))

    async def load_cookies(self) -> dict:
        """从文件加载 cookies。"""
        mgr = await self._ensure()
        try:
            count = await mgr.load_cookies()
            return self._result(True, {"action": "load_cookies", "count": count})
        except Exception as e:
            return self._result(False, error=str(e))

    async def clear_cookies(self) -> dict:
        """清除浏览器 cookies。"""
        mgr = await self._ensure()
        return await mgr.clear_cookies()

    async def cookies_set_curl(self, filepath: str) -> dict:
        """从 cURL cookie 文件导入 cookie。"""
        mgr = await self._ensure()
        return await mgr.cookies_set_curl(filepath)

    # ── 网络拦截 ──

    async def network_route(
        self, url_pattern: str, mock_body: str = "", abort: bool = False
    ) -> dict:
        """拦截/模拟网络请求。"""
        mgr = await self._ensure()
        return await mgr.network_route(url_pattern, mock_body, abort)

    async def network_unroute(self, url_pattern: str = "") -> dict:
        """移除网络请求拦截。"""
        mgr = await self._ensure()
        return await mgr.network_unroute(url_pattern)

    async def network_requests(self, filter_str: str = "") -> dict:
        """查看已追踪的网络请求。"""
        mgr = await self._ensure()
        return await mgr.network_requests(filter_str)

    # ── Storage 管理 ──

    async def storage_get(self, key: str = "") -> dict:
        """获取 localStorage。"""
        mgr = await self._ensure()
        return await mgr.storage_get(key)

    async def storage_set(self, key: str, value: str) -> dict:
        """设置 localStorage。"""
        mgr = await self._ensure()
        return await mgr.storage_set(key, value)

    async def storage_clear(self) -> dict:
        """清除 localStorage。"""
        mgr = await self._ensure()
        return await mgr.storage_clear()

    async def storage_session_get(self, key: str = "") -> dict:
        """获取 sessionStorage。"""
        mgr = await self._ensure()
        return await mgr.storage_session_get(key)

    async def storage_session_set(self, key: str, value: str) -> dict:
        """设置 sessionStorage。"""
        mgr = await self._ensure()
        return await mgr.storage_session_set(key, value)

    async def storage_session_clear(self) -> dict:
        """清除 sessionStorage。"""
        mgr = await self._ensure()
        return await mgr.storage_session_clear()

    # ── Init Scripts ──

    async def add_init_script(self, js: str) -> dict:
        """添加页面加载前注入的 JS。"""
        mgr = await self._ensure()
        return await mgr.add_init_script(js)

    async def remove_init_script(self, script_id: str) -> dict:
        """移除注入脚本。"""
        mgr = await self._ensure()
        return await mgr.remove_init_script(script_id)

    # ── 状态持久化 ──

    async def state_save(self, filepath: str = "") -> dict:
        """保存浏览器状态（cookies + localStorage）。"""
        mgr = await self._ensure()
        return await mgr.state_save(filepath)

    async def state_load(self, filepath: str = "") -> dict:
        """恢复浏览器状态。"""
        mgr = await self._ensure()
        return await mgr.state_load(filepath)

    # ── 调试 ──

    async def get_console_logs(self) -> dict:
        """获取页面 console 日志。"""
        mgr = await self._ensure()
        return await mgr.get_console_logs()

    async def clear_console_logs(self) -> dict:
        """清除页面 console 日志。"""
        mgr = await self._ensure()
        return await mgr.clear_console_logs()

    async def get_page_errors(self) -> dict:
        """获取页面错误。"""
        mgr = await self._ensure()
        return await mgr.get_page_errors()

    async def clear_page_errors(self) -> dict:
        """清除页面错误。"""
        mgr = await self._ensure()
        return await mgr.clear_page_errors()

    async def highlight_element(self, selector: str) -> dict:
        """在页面中高亮元素。"""
        mgr = await self._ensure()
        return await mgr.highlight_element(selector)

    # ── 录屏 ──

    async def record_start(self, filepath: str = "") -> dict:
        """开始录屏。"""
        mgr = await self._ensure()
        return await mgr.record_start(filepath)

    async def record_stop(self) -> dict:
        """停止录屏并保存为 GIF。"""
        mgr = await self._ensure()
        return await mgr.record_stop()

    async def record_restart(self, filepath: str = "") -> dict:
        """重启录屏。"""
        mgr = await self._ensure()
        return await mgr.record_restart(filepath)

    # ── 信息 ──

    async def status(self) -> dict:
        """获取浏览器状态。"""
        mgr = await self._ensure()
        try:
            return self._result(True, {
                "action": "status",
                "url": await mgr.current_url(),
                "title": await mgr.get_title(),
                "tabs": await mgr.list_tabs(),
            })
        except Exception as e:
            return self._result(False, error=str(e))

    async def info(self) -> dict:
        """获取 AgentBrowser 帮助信息。"""
        return {
            "success": True,
            "actions": [
                "open(url) — 启动浏览器并可选导航",
                "connect(port) — 连接到已运行的浏览器",
                "launch_headed(url) — 有头模式重启（处理验证码/登录）",
                "navigate(url) — 导航到 URL",
                "back() / forward() / reload() — 页面导航",
                "pushstate(url) — SPA 客户端导航",
                "snapshot() — 获取页面可访问性快照（@ref 引用）",
                "get_text() / get_html() / get_title() / get_url() — 页面内容",
                "click(selector) — 点击（支持 @e1, CSS, text=）",
                "click_new_tab(selector) — 点击并在新标签页打开",
                "dblclick(selector) — 双击",
                "focus(selector) — 聚焦",
                "hover(selector) — 悬停",
                "scroll(direction) / scrollintoview(selector) — 滚动",
                "drag_n_drop(source, target) — 拖拽",
                "type_text(selector, text) — 输入文本",
                "press_key(keys) — 按键（Enter, Escape, Tab）",
                "press_combo(combo) — 组合键（Ctrl+A, Alt+Tab）",
                "key_down(key) / key_up(key) — 按住/释放按键",
                "check(selector) / uncheck(selector) — 复选框",
                "select(selector, option) — 下拉框单选",
                "select_multi(selector, options) — 下拉框多选",
                "upload_file(selector, filepath) — 文件上传",
                "get_element_text/html/attr/value(selector) — 元素查询",
                "get_styles(selector) — 计算样式",
                "get_box(selector) / get_count(selector) — 元素信息",
                "is_visible(selector) / is_enabled(selector) / is_checked(selector) — 状态检查",
                "screenshot() — 截图 base64",
                "shot(name) — 截图保存到文件",
                "screenshot_annotated(name) — 标注元素编号的截图",
                "execute_js(script) — 执行 JavaScript",
                "dialog_accept/dialog_dismiss/dialog_status — 对话框",
                "frame(selector_or_name) — iframe 切换",
                "wait(condition, value, timeout) — 等待（selector/text/url/network_idle/fn）",
                "new_tab(url) / new_tab_label(label, url) — 新建标签页",
                "switch_tab(index) / switch_tab_by_label(label) — 切换",
                "list_tabs() / close_tab(index) / close_current_tab() — 标签页管理",
                "window_new() — 新建浏览器窗口",
                "get_cookies/set_cookies/save_cookies/load_cookies/clear_cookies — Cookie",
                "cookies_set_curl(filepath) — cURL 格式导入",
                "network_route(pattern) / network_unroute — 拦截",
                "network_requests(filter) — 查看追踪的请求",
                "storage_get/set/clear — localStorage",
                "storage_session_get/set/clear — sessionStorage",
                "set_viewport(w, h, dsf) — 视口大小",
                "set_device(name) — 模拟移动设备",
                "set_geolocation(lat, lng) — 地理位置",
                "set_offline(bool) — 离线模拟",
                "set_headers(dict) / set_credentials(user, pass) — HTTP 头/认证",
                "set_media(color_scheme, reduced_motion) — 媒体特性",
                "add_init_script(js) / remove_init_script(id) — 页面注入 JS",
                "state_save(path) / state_load(path) — 保存/恢复浏览器状态",
                "get_console_logs/clear_console_logs — console 日志",
                "get_page_errors/clear_page_errors — 页面错误",
                "highlight_element(selector) — 高亮元素",
                "record_start(path) / record_stop() / record_restart() — 录屏",
                "status() — 浏览器状态",
            ],
        }
