"""PageReadMixin：拆分自 manager.py"""

from __future__ import annotations

import asyncio
import json


class PageReadMixin:
    """页面导航与读取：URL、文本、HTML、标题、页面信息与 JS 执行。"""

    # ── 高可用页面操作包装 ──

    async def navigate(self, url: str) -> str:
        await self._navigate(url)
        return self.page.title

    async def current_url(self) -> str:
        return self.page.url

    async def get_text(self) -> str:
        text = await asyncio.to_thread(self.page.run_js, "return document.body.innerText || ''")
        return text or ""

    async def get_text_range(self, offset: int = 0, limit: int = 2000) -> str:
        """获取页面文本的指定范围（offset 到 offset+limit），避免传输全文。"""
        js = f"return (document.body.innerText || '').substring({offset}, {offset + limit})"
        result = await asyncio.to_thread(self.page.run_js, js)
        return str(result or "")

    async def get_text_length(self) -> int:
        """仅返回文本总长度，不传输全文。"""
        js = "return (document.body.innerText || '').length"
        result = await asyncio.to_thread(self.page.run_js, js)
        try:
            return int(result)
        except (ValueError, TypeError):
            return 0

    async def get_page_info(self) -> dict:
        """获取页面结构信息：标题、URL、文本长度、各级标题列表。"""
        js = r"""
        (function() {
            var headings = [];
            var els = document.querySelectorAll('h1, h2, h3, h4, h5, h6');
            for (var i = 0; i < els.length; i++) {
                var h = els[i];
                var level = parseInt(h.tagName.substring(1));
                var t = (h.innerText || '').trim().substring(0, 120);
                if (t) headings.push({level: level, text: t});
            }
            var links = document.querySelectorAll('a[href]');
            var linkCount = links.length;
            var tc = document.body.innerText || '';
            var words = tc.replace(/\s+/g, ' ').trim().split(' ').length;
            return JSON.stringify({
                title: document.title || '',
                url: location.href,
                text_length: tc.length,
                word_count: words,
                heading_count: headings.length,
                headings: headings,
                link_count: linkCount,
            });
        })()
        """
        result = await asyncio.to_thread(self.page.run_js, js)
        if not result:
            return {"title": "", "url": "", "text_length": 0, "word_count": 0, "heading_count": 0, "headings": [], "link_count": 0}
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"title": "", "url": "", "text_length": 0, "word_count": 0, "heading_count": 0, "headings": [], "link_count": 0}

    async def get_html(self, max_chars: int = 50000) -> str:
        if max_chars and max_chars < 200000:
            html = await asyncio.to_thread(
                self.page.run_js,
                f"return document.documentElement.outerHTML.substring(0, {max_chars})"
            )
            return html or ""
        return self.page.html

    async def get_title(self) -> str:
        return self.page.title

    async def execute_js(self, script: str) -> str:
        """执行 JS。先尝试语句模式，脚本无 return 且结果为空时尝试表达式模式。"""
        trimmed = script.strip()
        result = await asyncio.to_thread(self.page.run_js, script)
        if (result is None or str(result).strip() == ""
                or "SyntaxError" in str(result) or "Uncaught" in str(result)):
            if "return " not in trimmed:
                try:
                    expr_result = await asyncio.to_thread(self.page.run_js, script, as_expr=True)
                    if expr_result and "SyntaxError" not in str(expr_result) and "Uncaught" not in str(expr_result):
                        return str(expr_result)
                except Exception:
                    pass
        return str(result) if result is not None else ""

    async def pushstate(self, url: str) -> dict:
        """SPA 客户端导航。"""
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(
                page.run_js,
                f"window.history.pushState({{}}, '', '{url}'); "
                f"window.dispatchEvent(new PopStateEvent('popstate'));",
            )
            await asyncio.sleep(0.2)
            return {"success": True, "url": page.url}
        except Exception as e:
            return {"success": False, "error": str(e)}
