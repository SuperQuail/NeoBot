"""BrowserAgentWrapper — 生产级 Duck-Typed 浏览器适配器。

包装 agent_browser.AgentBrowser，提供 BrowserSkill/BrowserNetworkSkill/BrowserVideoSkill
期望的完整接口。每个方法返回 dict（含 "success" 键）。
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from neobot_app.browser.agent_browser import AgentBrowser


class BrowserAgentWrapper:
    """包装 AgentBrowser 的生产适配器。

    - 首次工具调用时懒启动
    - 每次工具调用后通知 lifecycle_manager
    - 截图/录屏路径经 user_data_dir 管理
    """

    def __init__(
        self,
        data_dir: str | Path,
        headless: bool = True,
        port: int = 0,
        browser_path: str = "",
        lifecycle_manager: Any = None,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._headless = headless
        self._port = port
        self._browser_path = browser_path
        self._lifecycle = lifecycle_manager
        self._agent: AgentBrowser | None = None

    @property
    def user_data_dir(self) -> str:
        return str(self._data_dir)

    # ── 生命周期 ──

    async def _ensure(self) -> AgentBrowser:
        if self._agent is None:
            self._agent = AgentBrowser(
                headless=self._headless,
                port=self._port,
                user_data_dir=str(self._data_dir),
                browser_path=self._browser_path,
            )
        if not self._agent._started:
            await self._agent.start()
            if self._lifecycle:
                self._lifecycle.set_browser_instance(self)
        return self._agent

    async def open(self, url: str = "") -> dict:
        agent = await self._ensure()
        result = await agent.open(url)
        await self._notify_lifecycle()
        return result

    async def close(self) -> dict:
        if self._agent is not None:
            await self._agent.close()
            self._agent = None
        return {"success": True, "action": "close"}

    async def _notify_lifecycle(self) -> None:
        """每次工具调用后尝试自动关闭浏览器。"""
        if self._lifecycle is None:
            return
        try:
            if self._lifecycle.should_auto_close():
                await self.close()
        except Exception:
            pass

    # ── 导航 ──

    async def navigate(self, url: str, wait_content: bool = True) -> dict:
        agent = await self._ensure()
        result = await agent.navigate(url, wait_content=wait_content)
        await self._notify_lifecycle()
        return result

    async def back(self) -> dict:
        agent = await self._ensure()
        result = await agent.back()
        await self._notify_lifecycle()
        return result

    async def forward(self) -> dict:
        agent = await self._ensure()
        result = await agent.forward()
        await self._notify_lifecycle()
        return result

    async def reload(self) -> dict:
        agent = await self._ensure()
        result = await agent.reload()
        await self._notify_lifecycle()
        return result

    # ── 页面快照 ──

    async def snapshot(self, detailed: bool = False) -> dict:
        agent = await self._ensure()
        result = await agent.snapshot(detailed=detailed)
        await self._notify_lifecycle()
        return result

    # ── 内容提取 ──

    async def get_text(self, max_chars: int = 10000, offset: int = 0) -> dict:
        agent = await self._ensure()
        result = await agent.get_text(max_chars=max_chars, offset=offset)
        await self._notify_lifecycle()
        return result

    async def get_html(self, max_chars: int = 50000) -> dict:
        agent = await self._ensure()
        result = await agent.get_html(max_chars=max_chars)
        await self._notify_lifecycle()
        return result

    async def get_title(self) -> dict:
        agent = await self._ensure()
        result = await agent.get_title()
        await self._notify_lifecycle()
        return result

    async def get_url(self) -> dict:
        agent = await self._ensure()
        result = await agent.get_url()
        await self._notify_lifecycle()
        return result

    # ── 元素交互 ──

    async def click(self, selector: str, index: int = 0) -> dict:
        agent = await self._ensure()
        result = await agent.click(selector, index=index)
        await self._notify_lifecycle()
        return result

    async def dblclick(self, selector: str) -> dict:
        agent = await self._ensure()
        result = await agent.dblclick(selector)
        await self._notify_lifecycle()
        return result

    async def focus(self, selector: str) -> dict:
        agent = await self._ensure()
        result = await agent.focus(selector)
        await self._notify_lifecycle()
        return result

    async def type_text(self, selector: str, text: str, clear: bool = True) -> dict:
        agent = await self._ensure()
        result = await agent.type_text(selector, text, clear=clear)
        await self._notify_lifecycle()
        return result

    async def press_key(self, keys: str) -> dict:
        agent = await self._ensure()
        result = await agent.press_key(keys)
        await self._notify_lifecycle()
        return result

    async def hover(self, selector: str) -> dict:
        agent = await self._ensure()
        result = await agent.hover(selector)
        await self._notify_lifecycle()
        return result

    async def select(self, selector: str, option: str) -> dict:
        agent = await self._ensure()
        result = await agent.select(selector, option)
        await self._notify_lifecycle()
        return result

    async def upload_file(self, selector: str, filepath: str) -> dict:
        agent = await self._ensure()
        result = await agent.upload_file(selector, filepath)
        await self._notify_lifecycle()
        return result

    async def scroll(self, direction: str = "down", amount: int = 500) -> dict:
        agent = await self._ensure()
        result = await agent.scroll(direction, amount)
        await self._notify_lifecycle()
        return result

    async def scrollintoview(self, selector: str) -> dict:
        agent = await self._ensure()
        result = await agent.scrollintoview(selector)
        await self._notify_lifecycle()
        return result

    async def drag_n_drop(self, source_selector: str, target_selector: str) -> dict:
        agent = await self._ensure()
        result = await agent.drag_n_drop(source_selector, target_selector)
        await self._notify_lifecycle()
        return result

    # ── 等待 ──

    async def wait(self, seconds: float = 2.0) -> dict:
        agent = await self._ensure()
        result = await agent.wait(seconds)
        await self._notify_lifecycle()
        return result

    # ── 截图 ──

    async def screenshot(self) -> dict:
        agent = await self._ensure()
        result = await agent.screenshot()
        await self._notify_lifecycle()
        return result

    # ── JavaScript ──

    async def execute_js(self, script: str) -> dict:
        agent = await self._ensure()
        result = await agent.execute_js(script)
        await self._notify_lifecycle()
        return result

    # ── 对话框 ──

    async def dialog_accept(self, text: str = "") -> dict:
        agent = await self._ensure()
        result = await agent.dialog_accept(text)
        await self._notify_lifecycle()
        return result

    async def dialog_dismiss(self) -> dict:
        agent = await self._ensure()
        result = await agent.dialog_dismiss()
        await self._notify_lifecycle()
        return result

    async def dialog_status(self) -> dict:
        agent = await self._ensure()
        result = await agent.dialog_status()
        await self._notify_lifecycle()
        return result

    # ── 标签页管理 ──

    async def new_tab(self, url: str = "") -> dict:
        agent = await self._ensure()
        result = await agent.new_tab(url)
        await self._notify_lifecycle()
        return result

    async def switch_tab(self, index: int) -> dict:
        agent = await self._ensure()
        result = await agent.switch_tab(index)
        await self._notify_lifecycle()
        return result

    async def list_tabs(self) -> dict:
        agent = await self._ensure()
        result = await agent.list_tabs()
        await self._notify_lifecycle()
        return result

    async def close_tab(self, index: int) -> dict:
        agent = await self._ensure()
        result = await agent.close_tab(index)
        await self._notify_lifecycle()
        return result

    # ── Cookie ──

    async def get_cookies(self, domain: str | None = None) -> dict:
        agent = await self._ensure()
        result = await agent.get_cookies(domain=domain)
        await self._notify_lifecycle()
        return result

    async def set_cookies(self, cookies: list[dict]) -> dict:
        agent = await self._ensure()
        result = await agent.set_cookies(cookies)
        await self._notify_lifecycle()
        return result

    async def clear_cookies(self) -> dict:
        agent = await self._ensure()
        result = await agent.clear_cookies()
        await self._notify_lifecycle()
        return result

    # ── 网络拦截 ──

    async def network_route(self, url_pattern: str, mock_body: str = "", abort: bool = False) -> dict:
        agent = await self._ensure()
        result = await agent.network_route(url_pattern, mock_body, abort)
        await self._notify_lifecycle()
        return result

    async def network_unroute(self, url_pattern: str = "") -> dict:
        agent = await self._ensure()
        result = await agent.network_unroute(url_pattern)
        await self._notify_lifecycle()
        return result

    async def network_requests(self, filter_str: str = "") -> dict:
        agent = await self._ensure()
        result = await agent.network_requests(filter_str)
        await self._notify_lifecycle()
        return result

    # ── Storage ──

    async def storage_get(self, key: str = "") -> dict:
        agent = await self._ensure()
        result = await agent.storage_get(key)
        await self._notify_lifecycle()
        return result

    async def storage_set(self, key: str, value: str) -> dict:
        agent = await self._ensure()
        result = await agent.storage_set(key, value)
        await self._notify_lifecycle()
        return result

    async def storage_clear(self) -> dict:
        agent = await self._ensure()
        result = await agent.storage_clear()
        await self._notify_lifecycle()
        return result

    async def storage_session_get(self, key: str = "") -> dict:
        agent = await self._ensure()
        result = await agent.storage_session_get(key)
        await self._notify_lifecycle()
        return result

    async def storage_session_set(self, key: str, value: str) -> dict:
        agent = await self._ensure()
        result = await agent.storage_session_set(key, value)
        await self._notify_lifecycle()
        return result

    async def storage_session_clear(self) -> dict:
        agent = await self._ensure()
        result = await agent.storage_session_clear()
        await self._notify_lifecycle()
        return result

    # ── 浏览器设置 ──

    async def set_viewport(self, width: int, height: int, device_scale_factor: float = 1.0) -> dict:
        agent = await self._ensure()
        result = await agent.set_viewport(width, height, device_scale_factor)
        await self._notify_lifecycle()
        return result

    async def set_device(self, name: str) -> dict:
        agent = await self._ensure()
        result = await agent.set_device(name)
        await self._notify_lifecycle()
        return result

    async def set_geolocation(self, latitude: float, longitude: float) -> dict:
        agent = await self._ensure()
        result = await agent.set_geolocation(latitude, longitude)
        await self._notify_lifecycle()
        return result

    async def set_offline(self, offline: bool) -> dict:
        agent = await self._ensure()
        result = await agent.set_offline(offline)
        await self._notify_lifecycle()
        return result

    # ── 调试 ──

    async def get_console_logs(self) -> dict:
        agent = await self._ensure()
        return await agent.get_console_logs()

    async def get_page_errors(self) -> dict:
        agent = await self._ensure()
        return await agent.get_page_errors()

    # ── 录屏 ──

    async def record_start(self, filepath: str = "") -> dict:
        agent = await self._ensure()
        result = await agent.record_start(filepath)
        await self._notify_lifecycle()
        return result

    async def record_stop(self) -> dict:
        agent = await self._ensure()
        result = await agent.record_stop()
        await self._notify_lifecycle()
        return result

    async def record_restart(self, filepath: str = "") -> dict:
        agent = await self._ensure()
        result = await agent.record_restart(filepath)
        await self._notify_lifecycle()
        return result
