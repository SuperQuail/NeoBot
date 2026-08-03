"""emoji/mapping 测试：QQ 表情映射完整性、lookup/search 关键词与无效 ID 行为。"""

from __future__ import annotations

from neobot_app.emoji.mapping import (
    QQ_EMOJI_MAP,
    list_all_emoji,
    lookup_emoji,
    search_emoji,
)


def test_lookup_emoji_returns_known_name_and_hint() -> None:
    """Arrange: 已知表情 ID 0/14/424；Act: lookup_emoji；Assert: 返回 (名称, 提示) 二元组且内容正确。"""
    assert lookup_emoji(0) == ("惊讶", "😮")
    assert lookup_emoji(14) == ("微笑", "🙂")
    assert lookup_emoji(424) == ("戳戳", "戳一戳 — QQ聊天常用戳一戳表情")


def test_lookup_emoji_returns_none_for_invalid_ids() -> None:
    """Arrange: 缺失 ID 17、超大 ID、负数；Act: lookup_emoji；Assert: 全部返回 None 而非抛异常。"""
    assert lookup_emoji(17) is None
    assert lookup_emoji(99999) is None
    assert lookup_emoji(-1) is None
    assert lookup_emoji(12952) is None


def test_search_emoji_matches_name_and_hint_keywords() -> None:
    """Arrange: 关键词「微笑」「666」「戳」；Act: search_emoji；Assert: 结果命中预期 ID 且字段完整。"""
    smile_ids = {item["id"] for item in search_emoji("微笑")}
    assert 14 in smile_ids

    six_ids = {item["id"] for item in search_emoji("666")}
    assert 356 in six_ids

    poke_ids = {item["id"] for item in search_emoji("戳")}
    assert 181 in poke_ids
    assert 424 in poke_ids

    sample = search_emoji("微笑")[0]
    assert set(sample) == {"id", "name", "hint"}


def test_search_emoji_blank_or_no_match_returns_empty_list() -> None:
    """Arrange: 空白关键词与无匹配关键词；Act: search_emoji；Assert: 均返回空列表。"""
    assert search_emoji("") == []
    assert search_emoji("   ") == []
    assert search_emoji("完全不存在的关键词xyz") == []


def test_list_all_emoji_returns_defensive_copy() -> None:
    """Arrange: 原映射表；Act: list_all_emoji 并修改返回副本；Assert: 副本改动不影响原表且长度一致。"""
    snapshot = list_all_emoji()

    snapshot[999999] = ("hack", "x")
    snapshot.clear()

    assert 999999 not in QQ_EMOJI_MAP
    assert len(QQ_EMOJI_MAP) > 100
    assert len(list_all_emoji()) == len(QQ_EMOJI_MAP)


def test_mapping_integrity_all_entries_valid_and_ids_unique() -> None:
    """Arrange: 完整 QQ_EMOJI_MAP；Act: 遍历校验；Assert: 所有 ID 非负唯一、值为非空 (名称, 提示) 二元组。"""
    ids = list(QQ_EMOJI_MAP)
    assert len(ids) == len(set(ids))
    assert all(emoji_id >= 0 for emoji_id in ids)

    for emoji_id, (name, hint) in QQ_EMOJI_MAP.items():
        assert isinstance(emoji_id, int)
        assert isinstance(name, str) and name
        assert isinstance(hint, str) and hint
