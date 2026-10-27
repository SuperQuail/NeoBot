"""CookiesNetworkMixin：拆分自 manager.py"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path


class CookiesNetworkMixin:
    """Cookie 读写与网络请求拦截。"""

    # ── Cookie 管理 ──

    async def save_cookies(self) -> int:
        cookies = self.page.cookies()
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)
        self.cookie_file.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
        return len(cookies)

    async def load_cookies(self) -> int:
        if not self.cookie_file.exists():
            return 0
        cookies = json.loads(self.cookie_file.read_text(encoding="utf-8"))
        for c in cookies:
            try:
                self.page.set.cookies(c)
            except Exception:
                pass
        return len(cookies)

    async def get_cookie_string(self, domain: str | None = None) -> str:
        cookies = self.page.cookies()
        if domain:
            cookies = [c for c in cookies if domain in str(c.get("domain", ""))]
        return "; ".join(f"{c['name']}={c['value']}" for c in cookies)

    async def get_all_cookies(self) -> list[dict]:
        return self.page.cookies()

    async def set_cookies(self, cookies: list[dict]) -> dict:
        try:
            page = await self._ensure_page()
            count = 0
            for c in cookies:
                try:
                    await asyncio.to_thread(page.set.cookies, c)
                    count += 1
                except Exception:
                    pass
            return {"success": True, "count": count}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def clear_cookies(self) -> dict:
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(
                page.run_js,
                "document.cookie.split(';').forEach(c => { "
                "document.cookie = c.trim().split('=')[0] + '=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/'; "
                "})",
            )
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def cookies_set_curl(self, filepath: str) -> dict:
        """从 cURL cookie 文件导入 cookie。"""
        try:
            page = await self._ensure_page()
            content = Path(filepath).read_text(encoding="utf-8")
            imported = 0
            if content.strip().startswith("[") or content.strip().startswith("{"):
                try:
                    data = json.loads(content)
                    if isinstance(data, dict):
                        data = [data]
                    return await self.set_cookies(data)
                except json.JSONDecodeError:
                    pass
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("HttpOnly"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 7:
                    cookie = {
                        "name": parts[5], "value": parts[6],
                        "domain": parts[0], "path": parts[2],
                        "secure": parts[3] == "TRUE",
                    }
                    try:
                        await asyncio.to_thread(page.set.cookies, cookie)
                        imported += 1
                    except Exception:
                        pass
            return {"success": True, "count": imported}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── 网络拦截 ──

    async def network_route(self, url_pattern: str, mock_body: str = "", abort: bool = False) -> dict:
        try:
            page = await self._ensure_page()
            if abort:
                page.listen.start(url_pattern)
                page.listen.wait()
            else:
                page.listen.start(url_pattern)
            return {"success": True, "pattern": url_pattern, "abort": abort}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def network_unroute(self, url_pattern: str = "") -> dict:
        """移除网络请求拦截。"""
        try:
            page = await self._ensure_page()
            page.listen.stop()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def network_requests(self, filter_str: str = "") -> dict:
        """查看已追踪的网络请求。"""
        try:
            page = await self._ensure_page()
            steps = page.listen.steps()
            requests_list = []
            for i, s in enumerate(steps):
                url = str(s.url) if hasattr(s, 'url') else ""
                if filter_str and filter_str not in url:
                    continue
                requests_list.append({
                    "index": i,
                    "url": url,
                    "method": s.method if hasattr(s, 'method') else "GET",
                    "status": s.status if hasattr(s, 'status') else 0,
                })
            return {"success": True, "requests": requests_list}
        except Exception as e:
            return {"success": False, "error": str(e)}
