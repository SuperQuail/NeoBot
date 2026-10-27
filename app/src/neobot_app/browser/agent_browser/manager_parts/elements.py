"""ElementQueryMixin：拆分自 manager.py"""

from __future__ import annotations

import asyncio
import json


class ElementQueryMixin:
    """元素属性查询与可见/可用/勾选状态判断。"""

    # ── 元素查询 ──

    async def get_element_text(self, selector: str) -> dict:
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            text = await asyncio.to_thread(lambda: el.text)
            return {"success": True, "text": (text or "")[:5000]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_element_html(self, selector: str) -> dict:
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            html = await asyncio.to_thread(lambda: el.html)
            return {"success": True, "html": (html or "")[:10000]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_element_attr(self, selector: str, attr: str) -> dict:
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            value = await asyncio.to_thread(lambda: el.attr(attr))
            return {"success": True, "attribute": attr, "value": value or ""}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_element_value(self, selector: str) -> dict:
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            value = await asyncio.to_thread(lambda: el.value)
            return {"success": True, "value": value or ""}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_box(self, selector: str) -> dict:
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            rect = await asyncio.to_thread(lambda: el.rect)
            return {"success": True, "box": rect}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_count(self, selector: str) -> dict:
        try:
            page = await self._ensure_page()
            count = await asyncio.to_thread(lambda: len(page.eles(selector)))
            return {"success": True, "count": count, "selector": selector}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_styles(self, selector: str) -> dict:
        """获取元素的计算样式。"""
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            styles = await asyncio.to_thread(
                self.page.run_js,
                "var s=window.getComputedStyle(arguments[0]);"
                "return JSON.stringify({color:s.color,backgroundColor:s.backgroundColor,"
                "fontSize:s.fontSize,fontFamily:s.fontFamily,fontWeight:s.fontWeight,"
                "display:s.display,visibility:s.visibility,opacity:s.opacity,"
                "width:s.width,height:s.height,margin:s.margin,padding:s.padding,"
                "border:s.border,textAlign:s.textAlign});",
                el,
            )
            return {"success": True, "styles": json.loads(styles) if styles else {}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── 状态检查 ──

    async def is_visible(self, selector: str) -> dict:
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            displayed = await asyncio.to_thread(el.is_displayed)
            return {"success": True, "visible": displayed}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def is_enabled(self, selector: str) -> dict:
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            disabled = await asyncio.to_thread(el.attr, "disabled")
            return {"success": True, "enabled": disabled is None}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def is_checked(self, selector: str) -> dict:
        """检查复选框/单选框是否选中。"""
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            checked = await asyncio.to_thread(lambda: el.checked)
            return {"success": True, "checked": bool(checked)}
        except Exception as e:
            return {"success": False, "error": str(e)}
