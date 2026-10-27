"""StorageMixin：拆分自 manager.py"""

from __future__ import annotations

import asyncio
import json


class StorageMixin:
    """localStorage/sessionStorage 读写与 init script 管理。"""

    # ── Storage 管理 ──

    async def storage_get(self, key: str = "") -> dict:
        try:
            page = await self._ensure_page()
            if key:
                value = await asyncio.to_thread(page.run_js, f"return localStorage.getItem('{key}')")
                return {"success": True, "key": key, "value": str(value) if value else ""}
            data = await asyncio.to_thread(page.run_js, "return JSON.stringify(window.localStorage)")
            return {"success": True, "all": json.loads(data) if data else {}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def storage_set(self, key: str, value: str) -> dict:
        try:
            page = await self._ensure_page()
            safe_val = json.dumps(value)
            await asyncio.to_thread(page.run_js, f"localStorage.setItem('{key}', {safe_val})")
            return {"success": True, "key": key}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def storage_clear(self) -> dict:
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(page.run_js, "localStorage.clear()")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def storage_session_get(self, key: str = "") -> dict:
        try:
            page = await self._ensure_page()
            if key:
                value = await asyncio.to_thread(page.run_js, f"return sessionStorage.getItem('{key}')")
                return {"success": True, "key": key, "value": str(value) if value else ""}
            data = await asyncio.to_thread(page.run_js, "return JSON.stringify(window.sessionStorage)")
            return {"success": True, "all": json.loads(data) if data else {}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def storage_session_set(self, key: str, value: str) -> dict:
        try:
            page = await self._ensure_page()
            safe_val = json.dumps(value)
            await asyncio.to_thread(page.run_js, f"sessionStorage.setItem('{key}', {safe_val})")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def storage_session_clear(self) -> dict:
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(page.run_js, "sessionStorage.clear()")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Init Scripts ──

    async def add_init_script(self, js: str) -> dict:
        """添加页面加载前注入的 JS。"""
        try:
            page = await self._ensure_page()
            script_id = await asyncio.to_thread(
                page.run_cdp, "Page.addScriptToEvaluateOnNewDocument", source=js,
            )
            self._init_scripts[str(script_id.get("identifier", ""))] = js
            return {"success": True, "id": str(script_id.get("identifier", ""))}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def remove_init_script(self, script_id: str) -> dict:
        """移除注入脚本。"""
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(
                page.run_cdp, "Page.removeScriptToEvaluateOnNewDocument", identifier=script_id,
            )
            self._init_scripts.pop(script_id, None)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
