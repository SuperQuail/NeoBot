"""表情包清单查询（由 service.py 拆分）。"""

from __future__ import annotations

from neobot_app.emoji.service_parts.models import EmojiEntry


class _QueryMixin:
    def list_entries(self) -> list[tuple[int, EmojiEntry]]:
        """返回所有表情包，按 effective_use_count（实际发送 + 候选曝光）从少到多排列。"""
        self._notify_disk_changed()
        sorted_entries = sorted(
            self._entries.items(), key=lambda item: item[1].effective_use_count
        )
        return sorted_entries

    def list_entries_paginated(
        self,
        offset: int = 0,
        limit: int | None = None,
    ) -> tuple[list[tuple[int, EmojiEntry]], int, bool]:
        """分页返回表情包列表，按使用次数从少到多排列。

        Returns (items, total, has_more)
        """
        self._notify_disk_changed()
        limit = limit if limit is not None else self._page_size
        sorted_entries = sorted(
            self._entries.items(), key=lambda item: item[1].effective_use_count
        )
        total = len(sorted_entries)
        page = sorted_entries[offset : offset + limit]
        has_more = offset + limit < total
        return page, total, has_more

    def search_entries(self, keyword: str, limit: int | None = None) -> list[tuple[int, EmojiEntry]]:
        """搜索表情包描述和文件名，按使用次数从少到多排列。"""
        self._notify_disk_changed()
        limit = limit if limit is not None else self._page_size
        kw = keyword.lower()
        matches: list[tuple[int, EmojiEntry]] = []
        for number, entry in self._entries.items():
            if kw in entry.analysis_text.lower() or kw in entry.file_name.lower():
                matches.append((number, entry))
        matches.sort(key=lambda item: item[1].effective_use_count)
        return matches[:limit]

    def build_list_text(
        self,
        offset: int = 0,
        limit: int | None = None,
    ) -> str:
        """构建表情包清单文本（list_emojis 工具的返回值），按 effective_use_count 从少到多排列。

        格式为 [编号]: [爱用][表情包：描述 | 已用N次]；超出本页时附带翻页提示。
        只作为工具结果按需返回，不再注入系统提示词——用量后缀与排序会随使用次数变化，
        放进 system 前缀会让整段缓存失效。
        """
        self._notify_disk_changed()
        if not self._entries:
            return ""
        limit = limit if limit is not None else self._page_size
        sorted_entries = sorted(
            self._entries.items(), key=lambda item: item[1].effective_use_count
        )
        page = sorted_entries[offset : offset + limit]

        lines: list[str] = []
        for number, entry in page:
            usage_info = f" | 已用{entry.use_count}次" if entry.use_count > 0 else ""
            favorite_mark = "[爱用]" if entry.is_favorite else ""
            lines.append(
                f"[{number}]: {favorite_mark}[表情包：{entry.analysis_text}{usage_info}]"
            )

        total = len(sorted_entries)
        header = f"共{total}个表情包"
        if total > limit:
            header += f"，当前显示第{offset + 1}-{min(offset + limit, total)}个"
            if offset > 0:
                header += f"，往前翻页: list_emojis(offset={max(0, offset - limit)})"
            if offset + limit < total:
                header += f"，往后翻页: list_emojis(offset={offset + limit})"
        return header + "\n" + "\n".join(lines)
