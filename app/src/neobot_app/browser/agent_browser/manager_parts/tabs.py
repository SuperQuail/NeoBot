"""TabsMixin：拆分自 manager.py"""

from __future__ import annotations

import asyncio
from typing import Any

from .._compat import ChromiumBase


class TabsMixin:
    """标签页/窗口的打开、切换、列举与关闭。"""

    # ── 标签页管理 ──

    async def _open_temporary_page(self) -> tuple[ChromiumBase, ChromiumBase]:
        """Open and activate an isolated blank tab, retaining the current page."""
        original = await self._ensure_page()
        tab_ids_before = set(original._browser.tab_ids)
        temporary = None
        tab_id = None
        try:
            temporary = await asyncio.to_thread(self._session_page.new_tab, None)
            tab_id = getattr(temporary, "tab_id", None)
            if tab_id is None:
                tab_id = next(
                    tid for tid in original._browser.tab_ids if tid not in tab_ids_before
                )
                temporary = self._session_page.get_tab(tab_id)
            await asyncio.to_thread(original._browser.activate_tab, tab_id)
            self._tab_pages[tab_id] = temporary
            self._page = temporary
            return original, temporary
        except BaseException:
            if tab_id is None:
                tab_id = next(
                    (tid for tid in original._browser.tab_ids if tid not in tab_ids_before),
                    None,
                )
            if tab_id is not None:
                try:
                    await asyncio.to_thread(
                        original.run_cdp, "Target.closeTarget", targetId=tab_id
                    )
                except Exception:
                    pass
                self._tab_pages.pop(tab_id, None)
            try:
                await asyncio.to_thread(
                    original._browser.activate_tab, original.tab_id
                )
            except Exception:
                pass
            self._page = original
            raise

    async def _close_temporary_page(
        self, temporary: ChromiumBase, original: ChromiumBase | None
    ) -> None:
        """Close an isolated tab and restore the exact page that was active."""
        tab_id = temporary.tab_id
        try:
            await asyncio.to_thread(
                temporary.run_cdp, "Target.closeTarget", targetId=tab_id
            )
        finally:
            self._tab_pages.pop(tab_id, None)
            if original is not None:
                try:
                    await asyncio.to_thread(
                        original._browser.activate_tab, original.tab_id
                    )
                finally:
                    self._page = original

    async def new_tab(self, url: str = "") -> dict:
        """新建标签页并自动激活。"""
        try:
            page = await self._ensure_page()
            tab_ids_before = list(page._browser.tab_ids)
            await asyncio.to_thread(self._session_page.new_tab, url or None)
            await asyncio.sleep(0.2)
            tab_ids = list(page._browser.tab_ids)
            for tid in tab_ids:
                if tid not in tab_ids_before:
                    await asyncio.to_thread(page._browser.activate_tab, tid)
                    tab = self._session_page.get_tab(tid)
                    self._tab_pages[tid] = tab
                    self._page = tab
                    break
            return {"success": True, "url": url or "", "title": self.page.title}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def new_tab_label(self, label: str, url: str = "") -> dict:
        """新建标签页并命名（标签名可在后续切换时用）。"""
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(page._browser.new_tab, url or None)
            await asyncio.sleep(0.2)
            tab_ids = page._browser.tab_ids
            self._tab_labels[label] = tab_ids[-1]
            return {"success": True, "label": label, "url": url}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def switch_tab(self, index: int) -> dict:
        try:
            if index < 0:
                return {"success": False, "error": f"索引 {index} 无效"}
            await self._ensure_page()
            sp = self._session_page
            tab_ids = list(sp._browser.tab_ids)
            if index >= len(tab_ids):
                return {"success": False, "error": f"索引 {index} 超出范围 (共 {len(tab_ids)} 个)"}
            target_id = tab_ids[index]
            await asyncio.to_thread(sp._browser.activate_tab, target_id)
            if target_id in self._tab_pages:
                self._page = self._tab_pages[target_id]
            else:
                tab = sp.get_tab(target_id)
                self._tab_pages[target_id] = tab
                self._page = tab
            return {"success": True, "index": index, "total": len(tab_ids),
                    "title": self.page.title}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def switch_tab_by_label(self, label: str) -> dict:
        """通过标签名切换标签页。"""
        try:
            target_id = self._tab_labels.get(label)
            if not target_id:
                return {"success": False, "error": f"未找到标签: {label}"}
            page = await self._ensure_page()
            await asyncio.to_thread(page._browser.activate_tab, target_id)
            if target_id in self._tab_pages:
                self._page = self._tab_pages[target_id]
            else:
                tab = self._session_page.get_tab(target_id)
                self._tab_pages[target_id] = tab
                self._page = tab
            await asyncio.sleep(0.2)
            return {"success": True, "label": label, "title": self.page.title}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def list_tabs(self) -> list[dict]:
        try:
            page = await self._ensure_page()
            tab_ids = page._browser.tab_ids
            target_infos = await asyncio.to_thread(
                lambda: page._browser._run_cdp('Target.getTargets')['targetInfos']
            )
            valid_ids = set(tab_ids)
            label_map = {v: k for k, v in self._tab_labels.items()}
            result = []
            idx = 0
            for info in target_infos:
                tid = info['targetId']
                if tid in valid_ids and info.get('type') in ('page', 'webview'):
                    result.append({
                        "index": idx,
                        "tab_id": tid,
                        "label": label_map.get(tid, ""),
                        "title": info.get('title', ''),
                        "url": info.get('url', ''),
                        "active": tid == page.tab_id,
                    })
                    idx += 1
            return result
        except Exception as e:
            return [{"error": str(e)}]

    async def close_tab(self, index: int) -> dict:
        try:
            page = await self._ensure_page()
            tab_ids = page._browser.tab_ids
            if index < 0 or index >= len(tab_ids):
                return {"success": False, "error": f"索引 {index} 超出范围"}
            target_id = tab_ids[index]
            is_active = target_id == page.tab_id
            await asyncio.to_thread(page.run_cdp, "Target.closeTarget", targetId=target_id)
            self._tab_pages.pop(target_id, None)
            for lbl, tid in list(self._tab_labels.items()):
                if tid == target_id:
                    del self._tab_labels[lbl]
            if is_active and len(tab_ids) > 1:
                remaining = [t for t in tab_ids if t != target_id]
                new_id = remaining[0]
                await asyncio.to_thread(page._browser.activate_tab, new_id)
                if new_id in self._tab_pages:
                    self._page = self._tab_pages[new_id]
                else:
                    tab = self._session_page.get_tab(new_id)
                    self._tab_pages[new_id] = tab
                    self._page = tab
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def close_tabs(self, indices: list[int] | None = None, others: bool = False) -> dict:
        """批量关闭标签页。"""
        try:
            page = await self._ensure_page()
            tab_ids = list(page._browser.tab_ids)

            if others:
                current_id = page.tab_id
                target_ids = [tid for tid in tab_ids if tid != current_id]
            elif indices:
                target_ids = []
                for idx in indices:
                    if 0 <= idx < len(tab_ids):
                        target_ids.append(tab_ids[idx])
            else:
                return {"success": False, "error": "请指定 indices 或设置 others=true"}

            if not target_ids:
                return {"success": True, "closed": 0}

            closed = 0
            for target_id in target_ids:
                try:
                    await asyncio.to_thread(page.run_cdp, "Target.closeTarget", targetId=target_id)
                    self._tab_pages.pop(target_id, None)
                    closed += 1
                except Exception:
                    pass

            current_id = page.tab_id
            remaining = [tid for tid in tab_ids if tid not in target_ids]
            if current_id in target_ids and remaining:
                new_id = remaining[0]
                await asyncio.to_thread(page._browser.activate_tab, new_id)
                if new_id in self._tab_pages:
                    self._page = self._tab_pages[new_id]
                else:
                    tab = self._session_page.get_tab(new_id)
                    self._tab_pages[new_id] = tab
                    self._page = tab

            return {"success": True, "closed": closed}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def close_current_tab(self) -> dict:
        """关闭当前标签页。"""
        try:
            page = await self._ensure_page()
            current_id = page.tab_id
            tab_ids = page._browser.tab_ids
            current_idx = tab_ids.index(current_id) if current_id in tab_ids else 0
            return await self.close_tab(current_idx)
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def window_new(self) -> dict:
        """新建浏览器窗口。"""
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(page.run_cdp, 'Target.createTarget', url='about:blank', newWindow=True)
            await asyncio.sleep(1)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def create_tab(self, url: str = "") -> Any:
        """创建新标签页，返回独立的 ChromiumTab 对象。"""
        await self._ensure_page()
        tab = await asyncio.to_thread(self._session_page.new_tab, url or None)
        try:
            tab.timeout = 2
        except Exception:
            pass
        return tab
