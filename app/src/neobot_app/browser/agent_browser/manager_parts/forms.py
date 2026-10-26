"""FormsMixin：拆分自 manager.py"""

from __future__ import annotations

import asyncio
from pathlib import Path


class FormsMixin:
    """键盘输入与表单/滚动/拖拽类交互。"""

    async def focus(self, selector: str) -> dict:
        """聚焦到元素。"""
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            await asyncio.to_thread(el.focus)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def type_text(self, selector: str, text: str, clear: bool = True) -> dict:
        """在输入框中输入文本，失败时回退到 JS。"""
        try:
            page = await self._ensure_page()
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            if clear:
                try:
                    await asyncio.to_thread(el.clear)
                except Exception:
                    pass
            try:
                await asyncio.to_thread(el.input, text)
            except Exception:
                await asyncio.to_thread(
                    page.run_js,
                    "arguments[0].value = arguments[1];"
                    "arguments[0].dispatchEvent(new Event('input', {bubbles: true}));"
                    "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));"
                    "arguments[0].dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true}));"
                    "arguments[0].dispatchEvent(new KeyboardEvent('keyup', {key:'Enter', bubbles:true}));",
                    el, text,
                )
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def press_key(self, keys: str) -> dict:
        """按下键盘按键（Enter, Escape, Tab 等）。"""
        try:
            page = await self._ensure_page()
            safe_key = keys.replace("'", "\\'")
            await asyncio.to_thread(
                page.run_js,
                f"""
                (() => {{
                    var el = document.activeElement;
                    if (!el) return;
                    el.dispatchEvent(new KeyboardEvent('keydown', {{key:'{safe_key}', bubbles:true, cancelable:true}}));
                    el.dispatchEvent(new KeyboardEvent('keypress', {{key:'{safe_key}', bubbles:true, cancelable:true}}));
                    el.dispatchEvent(new KeyboardEvent('keyup', {{key:'{safe_key}', bubbles:true, cancelable:true}}));
                    if ('{safe_key}' === 'Enter') {{
                        var form = el.closest('form');
                        if (form) {{
                            form.dispatchEvent(new Event('submit', {{bubbles:true, cancelable:true}}));
                            var btn = form.querySelector('button[type=submit], input[type=submit]');
                            if (btn) btn.click();
                        }}
                    }}
                }})();
                """,
            )
            await asyncio.sleep(0.2)
            return {"success": True, "keys": keys}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def press_combo(self, combo: str) -> dict:
        """按下组合键，如 'Control+a', 'Alt+Tab'。"""
        try:
            page = await self._ensure_page()
            keys = combo.split("+")
            main_key = keys[-1]
            js = (
                f"document.activeElement?.dispatchEvent(new KeyboardEvent('keydown', {{"
                f"key: '{main_key}', bubbles: true, cancelable: true, "
                f"ctrlKey: {'true' if any(k.lower()=='control' for k in keys) else 'false'}, "
                f"altKey: {'true' if any(k.lower()=='alt' for k in keys) else 'false'}, "
                f"shiftKey: {'true' if any(k.lower()=='shift' for k in keys) else 'false'}, "
                f"metaKey: {'true' if any(k.lower()=='meta' for k in keys) else 'false'}}}))"
            )
            await asyncio.to_thread(page.run_js, js)
            await asyncio.sleep(0.15)
            return {"success": True, "combo": combo}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def key_down(self, key: str) -> dict:
        """按住按键。"""
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(
                page.run_js,
                f"document.activeElement?.dispatchEvent(new KeyboardEvent('keydown', {{key: '{key}', bubbles: true}}))",
            )
            return {"success": True, "key": key}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def key_up(self, key: str) -> dict:
        """释放按键。"""
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(
                page.run_js,
                f"document.activeElement?.dispatchEvent(new KeyboardEvent('keyup', {{key: '{key}', bubbles: true}}))",
            )
            return {"success": True, "key": key}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def check(self, selector: str) -> dict:
        """勾选复选框。"""
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            checked = await asyncio.to_thread(lambda: el.checked)
            if not checked:
                await asyncio.to_thread(el.click)
            return {"success": True, "checked": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def uncheck(self, selector: str) -> dict:
        """取消勾选复选框。"""
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            checked = await asyncio.to_thread(lambda: el.checked)
            if checked:
                await asyncio.to_thread(el.click)
            return {"success": True, "checked": False}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def select_option(self, selector: str, option: str) -> dict:
        """选择下拉框选项（单选）。"""
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            await asyncio.to_thread(el.select, option)
            return {"success": True, "value": option}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def select_multi(self, selector: str, options: list[str]) -> dict:
        """下拉框多选。"""
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            for opt in options:
                await asyncio.to_thread(el.select, opt)
            return {"success": True, "values": options}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def hover(self, selector: str) -> dict:
        """悬停在元素上。"""
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            await asyncio.to_thread(el.hover)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def scroll(self, direction: str = "down", amount: int = 500) -> dict:
        """滚动页面。"""
        try:
            page = await self._ensure_page()
            if direction == "top":
                await asyncio.to_thread(page.run_js, "window.scrollTo(0, 0)")
            elif direction == "bottom":
                await asyncio.to_thread(page.run_js, "window.scrollTo(0, document.body.scrollHeight)")
            elif direction == "down":
                await asyncio.to_thread(page.run_js, f"window.scrollBy(0, {amount})")
            elif direction == "up":
                await asyncio.to_thread(page.run_js, f"window.scrollBy(0, -{amount})")
            await asyncio.sleep(0.2)
            return {"success": True, "direction": direction}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def scrollintoview(self, selector: str) -> dict:
        """将元素滚动到可视区域。"""
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            await asyncio.to_thread(el.run_js, "this.scrollIntoView({behavior: 'instant', block: 'center'})")
            await asyncio.sleep(0.2)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def drag_n_drop(self, source_selector: str, target_selector: str) -> dict:
        """拖拽元素到目标位置。"""
        try:
            page = await self._ensure_page()
            src = await asyncio.to_thread(self._find_element, source_selector)
            tgt = await asyncio.to_thread(self._find_element, target_selector)
            if src is None:
                return {"success": False, "error": f"未找到拖拽源: {source_selector}"}
            if tgt is None:
                return {"success": False, "error": f"未找到目标: {target_selector}"}
            src_rect = await asyncio.to_thread(lambda: src.rect)
            tgt_rect = await asyncio.to_thread(lambda: tgt.rect)
            js = (
                f"var src = document.elementFromPoint({src_rect['x'] + src_rect['width']/2}, {src_rect['y'] + src_rect['height']/2});"
                f"var evt = new MouseEvent('mousedown', {{bubbles: true}});"
                f"src?.dispatchEvent(evt);"
                f"var evt2 = new MouseEvent('mousemove', {{bubbles: true, clientX: {tgt_rect['x'] + tgt_rect['width']/2}, clientY: {tgt_rect['y'] + tgt_rect['height']/2}}});"
                f"document.dispatchEvent(evt2);"
                f"var evt3 = new MouseEvent('mouseup', {{bubbles: true}});"
                f"document.dispatchEvent(evt3);"
            )
            await asyncio.to_thread(page.run_js, js)
            await asyncio.sleep(0.2)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def upload_file(self, selector: str, filepath: str) -> dict:
        """上传文件到文件选择器。"""
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            resolved = str(Path(filepath).resolve())
            if not Path(resolved).exists():
                return {"success": False, "error": f"文件不存在: {resolved}"}
            await asyncio.to_thread(el.input, resolved)
            return {"success": True, "file": resolved}
        except Exception as e:
            return {"success": False, "error": str(e)}
