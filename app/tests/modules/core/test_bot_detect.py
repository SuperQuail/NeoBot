"""neobot_app.bot_detect BotDetector 官方机器人 UIN 区间识别测试。"""

from __future__ import annotations

from types import SimpleNamespace

import neobot_adapter.request.private as private_module
from neobot_app.bot_detect import BotDetector


class _FakeAdapter:
    """仅占位的假适配器，refresh 通过 monkeypatch 注入 get_robot_uin_range。"""

    pass


def _range_response(*items: dict) -> SimpleNamespace:
    """构造 get_robot_uin_range 的假响应对象。"""
    return SimpleNamespace(data=[SimpleNamespace(**item) for item in items])


async def test_refresh_without_adapter_keeps_empty_ranges() -> None:
    """Arrange: adapter 为 None；Act: refresh 后查询；Assert: 区间为空且识别为 False。"""
    detector = BotDetector(adapter=None)

    await detector.refresh()

    assert detector.ranges == []
    assert detector.is_official_bot(10001) is False


async def test_refresh_queries_and_caches_ranges(monkeypatch) -> None:
    """Arrange: API 返回两组区间；Act: refresh；Assert: 区间被缓存且边界内识别为 True。"""
    detector = BotDetector(adapter=_FakeAdapter())

    async def fake_get_robot_uin_range():
        return _range_response(
            {"minUin": 10001, "maxUin": 10010},
            {"minUin": 20000, "maxUin": 20005},
        )

    monkeypatch.setattr(private_module, "get_robot_uin_range", fake_get_robot_uin_range)

    await detector.refresh()

    assert detector.ranges == [(10001, 10010), (20000, 20005)]


async def test_refresh_swallows_api_errors(monkeypatch) -> None:
    """Arrange: API 抛出异常；Act: refresh；Assert: 不抛错且区间保持为空（异常路径）。"""
    detector = BotDetector(adapter=_FakeAdapter())

    async def fake_get_robot_uin_range():
        raise RuntimeError("backend down")

    monkeypatch.setattr(private_module, "get_robot_uin_range", fake_get_robot_uin_range)

    await detector.refresh()

    assert detector.ranges == []


async def test_refresh_ignores_null_data_and_missing_fields(monkeypatch) -> None:
    """Arrange: data 为 None 或条目缺少 minUin/maxUin；Act: refresh；Assert: 无效条目被跳过。"""
    detector = BotDetector(adapter=_FakeAdapter())

    async def fake_missing_fields():
        return SimpleNamespace(data=[SimpleNamespace(minUin=None, maxUin=5), None])

    monkeypatch.setattr(private_module, "get_robot_uin_range", fake_missing_fields)
    await detector.refresh()
    assert detector.ranges == []

    async def fake_null_response():
        return SimpleNamespace(data=None)

    monkeypatch.setattr(private_module, "get_robot_uin_range", fake_null_response)
    await detector.refresh()
    assert detector.ranges == []


def test_is_official_bot_boundary_is_inclusive() -> None:
    """Arrange: 区间 [10001, 10010]；Act: 边界值/越界值查询；Assert: 边界含、越界不含。"""
    detector = BotDetector(adapter=None)
    detector._ranges = [(10001, 10010)]

    assert detector.is_official_bot(10001) is True
    assert detector.is_official_bot(10010) is True
    assert detector.is_official_bot(10000) is False
    assert detector.is_official_bot(10011) is False
    assert detector.is_official_bot("10005") is True


def test_is_official_bot_rejects_invalid_user_id() -> None:
    """Arrange: 有区间但 user_id 非法（非数字/None/浮点）；Act: 查询；Assert: 返回 False 不抛错。"""
    detector = BotDetector(adapter=None)
    detector._ranges = [(10001, 10010)]

    assert detector.is_official_bot("abc") is False
    assert detector.is_official_bot(None) is False
    assert detector.is_official_bot(12.5) is False


def test_ranges_property_returns_copy() -> None:
    """Arrange: 内部区间已设置；Act: 修改属性返回值；Assert: 内部数据不受影响。"""
    detector = BotDetector(adapter=None)
    detector._ranges = [(1, 2)]

    returned = detector.ranges
    returned.append((3, 4))

    assert detector._ranges == [(1, 2)]
