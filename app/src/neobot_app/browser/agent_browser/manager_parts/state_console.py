"""StateConsoleMixin：拆分自 manager.py"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path


class StateConsoleMixin:
    """状态持久化、控制台/页面错误读取与元素高亮。"""

    # ── 状态持久化 ──

    async def state_save(self, filepath: str = "") -> dict:
        """保存浏览器状态（cookies + localStorage）。"""
        try:
            page = await self._ensure_page()
            path = Path(filepath) if filepath else Path(self._user_data_dir) / "browser_state.json"
            cookies = page.cookies()
            ls_data = await asyncio.to_thread(page.run_js, "return JSON.stringify(window.localStorage)")
            state = {
                "cookies": cookies,
                "localStorage": json.loads(ls_data) if ls_data else {},
                "url": page.url,
                "timestamp": time.time(),
            }
            path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            return {"success": True, "path": str(path), "cookie_count": len(cookies)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def state_load(self, filepath: str = "") -> dict:
        """恢复浏览器状态。"""
        try:
            page = await self._ensure_page()
            path = Path(filepath) if filepath else Path(self._user_data_dir) / "browser_state.json"
            if not path.exists():
                return {"success": False, "error": f"状态文件不存在: {path}"}
            state = json.loads(path.read_text(encoding="utf-8"))
            loaded = 0
            for c in state.get("cookies", []):
                try:
                    await asyncio.to_thread(page.set.cookies, c)
                    loaded += 1
                except Exception:
                    pass
            ls = state.get("localStorage", {})
            for k, v in ls.items():
                safe_val = json.dumps(str(v))
                await asyncio.to_thread(page.run_js, f"localStorage.setItem('{k}', {safe_val})")
            return {"success": True, "cookie_count": loaded, "ls_keys": len(ls)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @property
    def _state_file(self) -> Path:
        return Path(self._user_data_dir) / "browser_state.json"

    async def _persist_state(self) -> None:
        """内部方法：持久化 cookie 和 localStorage 到 JSON 文件（关闭前调用）。"""
        if self._page is None:
            return
        try:
            cookies = self._page.cookies()
            ls_data = await asyncio.to_thread(
                self._page.run_js, "return JSON.stringify(window.localStorage)"
            )
            state = {
                "cookies": cookies,
                "localStorage": json.loads(ls_data) if ls_data else {},
                "url": self._page.url,
                "timestamp": time.time(),
            }
            self._state_file.write_text(
                json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    async def _restore_persisted_state(self) -> None:
        """内部方法：从 JSON 文件恢复 cookie 和 localStorage（启动后调用）。"""
        if not self._state_file.exists():
            return
        try:
            state = json.loads(self._state_file.read_text(encoding="utf-8"))
            for c in state.get("cookies", []):
                try:
                    self._page.set.cookies(c)
                except Exception:
                    pass
        except Exception:
            pass

    # ── 调试 ──

    async def get_console_logs(self) -> dict:
        """获取页面 console 日志。"""
        try:
            page = await self._ensure_page()
            logs = await asyncio.to_thread(
                page.run_js,
                "return (window.__consoleLogs || []).join('\\n')",
            )
            return {"success": True, "logs": str(logs) if logs else ""}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def clear_console_logs(self) -> dict:
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(page.run_js, "window.__consoleLogs = []")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_page_errors(self) -> dict:
        """获取页面错误。"""
        try:
            page = await self._ensure_page()
            errors = await asyncio.to_thread(
                page.run_js,
                "return (window.__pageErrors || []).join('\\n')",
            )
            return {"success": True, "errors": str(errors) if errors else ""}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def clear_page_errors(self) -> dict:
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(page.run_js, "window.__pageErrors = []")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def highlight_element(self, selector: str) -> dict:
        """在页面中高亮元素。"""
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            await asyncio.to_thread(
                el.run_js,
                "this.style.outline = '3px solid red';"
                "this.style.outlineOffset = '2px';"
                "this.scrollIntoView({behavior: 'smooth', block: 'center'});",
            )
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
