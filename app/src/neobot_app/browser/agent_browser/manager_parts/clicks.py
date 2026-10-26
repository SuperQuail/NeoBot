"""ClickMixin：拆分自 manager.py"""

from __future__ import annotations

import asyncio
import json


class ClickMixin:
    """元素定位与点击类交互。"""

    # ── 元素交互 ──

    def _find_element(self, selector: str, timeout: float = 0):
        """同步查找元素，支持 @ref / CSS / text= / 模糊 text 回退。"""
        import re
        page = self.page
        if selector.startswith("@e"):
            from .snapshot import get_element_by_ref_sync
            return get_element_by_ref_sync(page, selector)
        if ":has-text(" in selector:
            m = re.search(r':has-text\(\s*["\']?([^"\')\s]+)["\']?\s*\)', selector)
            clean = re.sub(r':has-text\([^)]+\)', '', selector).strip()
            if clean:
                el = page.ele(f"css:{clean}", timeout=timeout)
                if el:
                    return el
            if m:
                return page.ele(f"text={m.group(1)}", timeout=timeout)
            return None
        if "," in selector:
            parts = [s.strip() for s in selector.split(",")]
            for part in parts:
                if part:
                    el = page.ele(f"css:{part}", timeout=timeout)
                    if el:
                        return el
            return None
        if selector.startswith(("tag:", "css:", "text:", "xpath:", "@")):
            el = page.ele(selector, timeout=timeout)
        else:
            el = page.ele(f"css:{selector}", timeout=timeout)
        if el is None:
            clean = re.sub(r'[#\.\[\]:>\s,=""()]', ' ', selector)
            words = [w for w in clean.split() if len(w) > 1]
            for w in words:
                el = page.ele(f"text={w}", timeout=timeout)
                if el:
                    return el
        return el

    async def _click_detected(self, page, url_before, el) -> bool:
        """检查点击是否已生效（URL 变化或元素脱离 DOM）。"""
        if page.url != url_before:
            return True
        try:
            attached = await asyncio.to_thread(
                page.run_js, "return document.body.contains(arguments[0])", el
            )
            return not attached
        except Exception:
            return False

    async def click(self, selector: str, index: int = 0) -> dict:
        """点击元素，多阶段回退策略确保 SPA 页面兼容。"""
        try:
            page = await self._ensure_page()

            match_count = 0
            if index > 0:
                css_sel = f"css:{selector}" if not selector.startswith(
                    ("tag:", "css:", "text:", "xpath:", "@")
                ) else selector
                els = await asyncio.to_thread(lambda: page.eles(css_sel, timeout=0))
                if not els:
                    return {"success": False, "error": f"未找到元素: {selector}"}
                if index >= len(els):
                    return {"success": False, "error": f"索引 {index} 超出范围 (共 {len(els)} 个匹配)"}
                el = els[index]
                match_count = len(els)
            else:
                el = await asyncio.to_thread(self._find_element, selector)
                if el is not None and not selector.startswith(("tag:", "text:", "xpath:", "@")):
                    try:
                        css_sel = f"css:{selector}" if not selector.startswith("css:") else selector
                        all_matches = await asyncio.to_thread(lambda: page.eles(css_sel, timeout=0))
                        match_count = len(all_matches)
                    except Exception:
                        pass

            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}

            tag = await asyncio.to_thread(lambda: el.tag)
            text = await asyncio.to_thread(lambda: el.text)
            url_before = page.url
            tab_ids_before = len(page._browser.tab_ids)

            # Phase 1: 原生 DrissionPage click
            phase1_ok = True
            try:
                await asyncio.to_thread(el.click)
            except Exception:
                phase1_ok = False
            await asyncio.sleep(0.2)
            if await self._click_detected(page, url_before, el) or len(page._browser.tab_ids) > tab_ids_before:
                return {"success": True, "tag": tag, "text": (text or "")[:100], "url": page.url, "match_count": match_count}
            if phase1_ok:
                return {"success": True, "tag": tag, "text": (text or "")[:100], "url": page.url, "match_count": match_count}

            # Phase 2: 仅在 Phase 1 抛异常时执行
            await asyncio.to_thread(
                page.run_js,
                """(function(el) {
                    ['mousedown', 'mouseup', 'click'].forEach(function(type) {
                        el.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, view: window}));
                    });
                })(arguments[0]);""",
                el,
            )
            await asyncio.sleep(0.2)
            if await self._click_detected(page, url_before, el) or len(page._browser.tab_ids) > tab_ids_before:
                return {"success": True, "tag": tag, "text": (text or "")[:100], "url": page.url, "match_count": match_count}

            # Phase 3: 向上查找可点击父元素并派发事件
            await asyncio.to_thread(
                page.run_js,
                """(function(el) {
                    var target = el.closest('a, button, [onclick], [role=button], .vui_tabs--nav-link, [data-click]');
                    if (target && target !== el) {
                        ['mousedown', 'mouseup', 'click'].forEach(function(type) {
                            target.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, view: window}));
                        });
                    }
                })(arguments[0]);""",
                el,
            )
            await asyncio.sleep(0.3)
            if await self._click_detected(page, url_before, el) or len(page._browser.tab_ids) > tab_ids_before:
                return {"success": True, "tag": tag, "text": (text or "")[:100], "url": page.url, "match_count": match_count}

            # Phase 4: 仅当元素本身是 <a> 标签时用 href 导航
            await asyncio.to_thread(
                page.run_js,
                """(function(el) {
                    if (el.tagName === 'A' && el.href && el.href !== '#' && !el.href.startsWith('javascript:')) {
                        location.href = el.href;
                    }
                })(arguments[0]);""",
                el,
            )
            await asyncio.sleep(0.5)

            return {"success": True, "tag": tag, "text": (text or "")[:100], "url": page.url, "match_count": match_count}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def find_elements(self, keyword: str, max_results: int = 30) -> dict:
        """搜索当前页面中匹配关键词的元素，返回结构化列表供 AI 参考。"""
        try:
            page = await self._ensure_page()
            js = """(function(kw, limit) {
                var results = [];
                var all = document.querySelectorAll('a, button, input, textarea, select, [role=button], [onclick], label, span, li, img, h1, h2, h3, h4, p, div[class]');
                var kw_lower = kw.toLowerCase();
                var seen = new Set();
                for (var i = 0; i < all.length && results.length < limit; i++) {
                    var el = all[i];
                    if (seen.has(el)) continue;
                    var text = (el.innerText || '').trim();
                    var ph = el.placeholder || '';
                    var aria_label = el.getAttribute('aria-label') || '';
                    var value = el.value || '';
                    var alt = el.alt || '';
                    var title_attr = el.title || '';
                    var href = el.getAttribute('href') || '';
                    var cls = el.className || '';
                    if (typeof cls === 'object') cls = cls.baseVal || '';
                    var match_text = text.toLowerCase().indexOf(kw_lower) !== -1;
                    var match_ph = ph.toLowerCase().indexOf(kw_lower) !== -1;
                    var match_aria = aria_label.toLowerCase().indexOf(kw_lower) !== -1;
                    var match_val = value.toLowerCase().indexOf(kw_lower) !== -1;
                    var match_alt = alt.toLowerCase().indexOf(kw_lower) !== -1;
                    var match_title = title_attr.toLowerCase().indexOf(kw_lower) !== -1;
                    var match_href = href.toLowerCase().indexOf(kw_lower) !== -1;
                    var match_cls = cls.toLowerCase().indexOf(kw_lower) !== -1;
                    if (match_text || match_ph || match_aria || match_val || match_alt || match_title || match_href || match_cls) {
                        var rect = el.getBoundingClientRect();
                        var selector = el.tagName.toLowerCase();
                        if (el.id) selector += '#' + el.id;
                        else if (cls) {
                            var classPart = cls.split(/\\s+/).filter(function(c){return c && c.indexOf(':')===-1 && !c.startsWith('hover') && !c.startsWith('active');})[0];
                            if (classPart) selector += '.' + classPart;
                        }
                        var context = '';
                        var parent = el.parentElement;
                        for (var depth = 0; depth < 5 && parent && parent !== document.body; depth++) {
                            var pText = (parent.innerText || '').trim().substring(0, 120);
                            if (pText && pText !== text) {
                                context = pText;
                                break;
                            }
                            parent = parent.parentElement;
                        }
                        var siblingText = '';
                        var container = el.closest('[class*="card"], [class*="item"], [class*="list"], li, [class*="result"], [class*="search"]');
                        if (container) {
                            var containerText = (container.innerText || '').trim().substring(0, 200);
                            var selfText = text.substring(0, 100);
                            if (containerText.indexOf(selfText) !== -1) {
                                siblingText = containerText.replace(selfText, '[...]').substring(0, 120);
                            }
                        }
                        var dataAttrs = '';
                        var dataKeys = [];
                        for (var j = 0; j < el.attributes.length; j++) {
                            var attr = el.attributes[j];
                            if (attr.name.indexOf('data-') === 0 && attr.value) {
                                dataKeys.push(attr.name + '=' + attr.value.substring(0, 30));
                            }
                        }
                        if (dataKeys.length) dataAttrs = dataKeys.join('; ');
                        results.push({
                            tag: el.tagName.toLowerCase(),
                            text: text.substring(0, 100),
                            href: href,
                            placeholder: ph,
                            aria_label: aria_label,
                            selector: selector,
                            visible: rect.width > 0 && rect.height > 0,
                            top: Math.round(rect.top),
                            left: Math.round(rect.left),
                            index: i,
                            context: context.substring(0, 120),
                            sibling_text: siblingText.substring(0, 120),
                            data_attrs: dataAttrs,
                            exact: text.toLowerCase() === kw_lower,
                        });
                        var descendants = el.querySelectorAll('*');
                        for (var d = 0; d < descendants.length; d++) seen.add(descendants[d]);
                    }
                }
                return JSON.stringify(results);
            })(arguments[0], arguments[1]);"""
            raw = await asyncio.to_thread(page.run_js, js, keyword, max_results)
            if raw:
                items = json.loads(raw)
                return {"success": True, "items": items, "count": len(items)}
            return {"success": True, "items": [], "count": 0}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def click_new_tab(self, selector: str) -> dict:
        """点击元素并在新标签页中打开链接。"""
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            href = await asyncio.to_thread(lambda: el.attr("href"))
            if href:
                result = await self.new_tab(href)
                return result
            await asyncio.to_thread(el.click, as_new_tab=True)
            await asyncio.sleep(0.15)
            return {"success": True, "action": "click_new_tab"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def dblclick(self, selector: str) -> dict:
        """双击元素。"""
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            await asyncio.to_thread(
                self.page.run_js,
                "arguments[0].dispatchEvent(new MouseEvent('dblclick', {bubbles: true}))",
                el,
            )
            await asyncio.sleep(0.2)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
