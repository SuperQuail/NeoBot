"""ImageStagingPool 测试：存入/取出、TTL 过期清理、重复去重与多会话隔离。"""

from __future__ import annotations

import re

import pytest

import neobot_app.image_pool as image_pool_module
from neobot_app.image_pool import ImageStagingPool


@pytest.fixture()
def fake_clock(monkeypatch):
    """可控单调时钟：返回浮点数序列，越界后停留在最后值。"""
    values = [100.0]
    monkeypatch.setattr(
        image_pool_module.time,
        "monotonic",
        lambda: values[-1],
    )
    return values


def test_put_returns_auto_key_and_get_returns_full_entry(tmp_path, fake_clock) -> None:
    """Arrange: 临时图片文件与默认 TTL；Act: put 后 get；Assert: 自动 key 为 8 位十六进制且字段完整、过期时间符合 TTL。"""
    pool = ImageStagingPool(ttl_seconds=300)
    image_path = tmp_path / "pic.png"
    image_path.write_bytes(b"png-data")

    key = pool.put("conv-1", image_path, source="chat")

    assert re.fullmatch(r"[0-9a-f]{8}", key)
    staged = pool.get("conv-1", key)
    assert staged is not None
    assert staged.file_path == image_path
    assert staged.source == "chat"
    assert staged.size == 8
    assert staged.mime_type == "image/png"
    assert staged.expires_at - staged.created_at == 300


def test_put_same_key_overwrites_and_auto_keys_are_unique(tmp_path, fake_clock) -> None:
    """Arrange: 同一会话两个文件；Act: 相同 key 重复 put 与两次自动 key put；Assert: 重复 key 覆盖旧条目、自动 key 互不相同。"""
    pool = ImageStagingPool()
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    first.write_bytes(b"1")
    second.write_bytes(b"2")

    key_a = pool.put("c", first, key="same", source="a")
    key_b = pool.put("c", second, key="same", source="b")

    assert key_a == key_b == "same"
    staged = pool.get("c", "same")
    assert staged is not None
    assert staged.source == "b"
    assert staged.file_path == second
    auto_1 = pool.put("c", first)
    auto_2 = pool.put("c", first)
    assert auto_1 != auto_2


def test_ttl_expiration_removes_expired_entries(tmp_path, fake_clock) -> None:
    """Arrange: TTL=10 的池并放入一张图；Act: 时钟前移 11 秒后 get/list；Assert: 条目已过期且 get 返回 None、list 为空。"""
    pool = ImageStagingPool(ttl_seconds=10)
    image_path = tmp_path / "pic.png"
    image_path.write_bytes(b"data")
    key = pool.put("c", image_path)

    assert pool.get("c", key) is not None
    fake_clock.append(111.0)

    assert pool.get("c", key) is None
    assert pool.list("c") == []
    assert pool._cleanup_expired("c") == 0


def test_list_orders_newest_first_and_remove_clear_semantics(tmp_path, fake_clock) -> None:
    """Arrange: 时钟推进间隔放入三张图；Act: list/remove/clear/clear_all；Assert: 列表新到旧、remove 返回状态、clear 返回数量。"""
    pool = ImageStagingPool()
    paths = [tmp_path / f"{i}.png" for i in range(3)]
    for path in paths:
        path.write_bytes(b"x")
    keys = []
    for index, path in enumerate(paths):
        fake_clock.append(200.0 + index)
        keys.append(pool.put("c", path, source=f"s{index}"))

    listed = pool.list("c")
    assert [item.key for item in listed] == keys[::-1]
    assert [item.source for item in listed] == ["s2", "s1", "s0"]

    assert pool.remove("c", keys[0]) is True
    assert pool.remove("c", keys[0]) is False
    assert pool.list("c")[0].key == keys[2]

    assert pool.clear("c") == 2
    assert pool.clear("c") == 0
    assert pool.clear_all() == 0


def test_put_with_missing_file_uses_zero_size_and_png_fallback(tmp_path, fake_clock) -> None:
    """Arrange: 指向不存在文件的路径；Act: put 后 get；Assert: size 为 0 且 mime_type 回退为 image/png。"""
    pool = ImageStagingPool()
    missing = tmp_path / "missing.png"

    key = pool.put("c", missing, source="external")

    staged = pool.get("c", key)
    assert staged is not None
    assert staged.size == 0
    assert staged.mime_type == "image/png"


def test_zero_ttl_expires_on_first_read(tmp_path, fake_clock) -> None:
    """Arrange: ttl_seconds=0 的池；Act: 放入后时钟前移 1 秒再读取；Assert: 条目立即过期。"""
    pool = ImageStagingPool(ttl_seconds=0)
    image_path = tmp_path / "pic.png"
    image_path.write_bytes(b"data")
    key = pool.put("c", image_path)

    fake_clock.append(101.0)

    assert pool.get("c", key) is None
