from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from typing import Any

from pydantic import BaseModel

from neobot_adapter.model.response import GroupMemberData, StrangerInfoData
from neobot_modloader.users import UserDirectory, UserProfile


class _Response:
    def __init__(self, data: Any) -> None:
        self.data = data


class FakeUserAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.members: dict[tuple[int, int], GroupMemberData | None] = {}
        self.member_list: list[GroupMemberData] | None = None
        self.strangers: dict[int, StrangerInfoData | None] = {}
        self.member_info_error: Exception | None = None
        self.member_list_error: Exception | None = None
        self.stranger_error: Exception | None = None

    async def get_group_member_info(
        self, group_id: int, user_id: int, no_cache: bool = False
    ) -> _Response:
        self.calls.append(("get_group_member_info", (group_id, user_id)))
        if self.member_info_error is not None:
            raise self.member_info_error
        return _Response(self.members.get((group_id, user_id)))

    async def get_group_member_list(self, group_id: int, no_cache: bool = False) -> _Response:
        self.calls.append(("get_group_member_list", (group_id,)))
        if self.member_list_error is not None:
            raise self.member_list_error
        return _Response(self.member_list)

    async def get_stranger_info(self, user_id: int) -> _Response:
        self.calls.append(("get_stranger_info", (user_id,)))
        if self.stranger_error is not None:
            raise self.stranger_error
        return _Response(self.strangers.get(user_id))


def _with_now(adapter: FakeUserAdapter, now: list[float]) -> UserDirectory:
    users = UserDirectory(adapter)
    users._now = lambda: now[0]  # type: ignore[method-assign]
    return users


class _GatedStrangerAdapter(FakeUserAdapter):
    """记录 get_stranger_info 的最大并发深度，用于验证兜底路径并发。"""

    def __init__(self) -> None:
        super().__init__()
        self._in_flight = 0
        self.max_in_flight = 0

    async def get_stranger_info(self, user_id: int) -> _Response:
        self._in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self._in_flight)
        try:
            await asyncio.sleep(0)
            return await super().get_stranger_info(user_id)
        finally:
            self._in_flight -= 1


class _GatedMemberAdapter(FakeUserAdapter):
    """记录 get_group_member_info 的并发深度，用于并发 get 一致性测试。"""

    def __init__(self) -> None:
        super().__init__()
        self._in_flight = 0
        self.max_in_flight = 0

    async def get_group_member_info(
        self, group_id: int, user_id: int, no_cache: bool = False
    ) -> _Response:
        self._in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self._in_flight)
        try:
            await asyncio.sleep(0.01)
            return await super().get_group_member_info(group_id, user_id, no_cache=no_cache)
        finally:
            self._in_flight -= 1


class UserProfileTest(unittest.TestCase):
    def test_display_name_prefers_card_then_nickname_then_user_id(self) -> None:
        self.assertEqual(
            UserProfile(user_id="1", nickname="昵称", card="群名片").display_name, "群名片"
        )
        self.assertEqual(UserProfile(user_id="1", nickname="昵称").display_name, "昵称")
        self.assertEqual(UserProfile(user_id="1").display_name, "1")


class FromEventTest(unittest.TestCase):
    def test_from_event_never_calls_adapter(self) -> None:
        adapter = FakeUserAdapter()
        users = UserDirectory(adapter)

        group = users.from_event(
            {
                "message_type": "group",
                "group_id": 10,
                "sender": {"user_id": 42, "nickname": "昵称", "card": "群名片", "role": "admin"},
            }
        )

        self.assertEqual(adapter.calls, [])
        self.assertEqual(group.user_id, "42")
        self.assertEqual(group.group_id, "10")
        self.assertEqual(group.card, "群名片")
        self.assertEqual(group.display_name, "群名片")
        self.assertEqual(group.raw["role"], "admin")

        private = users.from_event(
            {"message_type": "private", "user_id": 7, "sender": {"user_id": 7, "nickname": "独行"}}
        )

        self.assertEqual(adapter.calls, [])
        self.assertIsNone(private.card)
        self.assertIsNone(private.group_id)
        self.assertIsNone(private.avatar_url)
        self.assertEqual(private.display_name, "独行")

    def test_from_event_accepts_base_model(self) -> None:
        class Event(BaseModel):
            message_type: str
            group_id: int | None = None
            sender: dict[str, Any] = {}

        users = UserDirectory(FakeUserAdapter())
        profile = users.from_event(
            Event(message_type="group", group_id=5, sender={"user_id": 9, "card": "卡片"})
        )

        self.assertEqual(profile.user_id, "9")
        self.assertEqual(profile.display_name, "卡片")
        self.assertEqual(profile.group_id, "5")

    def test_from_event_sender_missing_or_none(self) -> None:
        users = UserDirectory(FakeUserAdapter())

        profile = users.from_event({"message_type": "group", "group_id": 0})

        self.assertEqual(profile.user_id, "")
        self.assertEqual(profile.group_id, "0")
        self.assertEqual(profile.display_name, "")

    def test_from_event_sender_base_model(self) -> None:
        class Sender(BaseModel):
            user_id: int = 0
            nickname: str = ""
            card: str | None = None

        users = UserDirectory(FakeUserAdapter())
        profile = users.from_event(
            {"message_type": "group", "group_id": 5, "sender": Sender(user_id=9, nickname="x")}
        )

        self.assertEqual(profile.user_id, "9")
        self.assertEqual(profile.display_name, "x")

    def test_from_event_empty_card_falls_back_to_nickname(self) -> None:
        users = UserDirectory(FakeUserAdapter())

        profile = users.from_event(
            {"sender": {"user_id": 1, "nickname": "昵称", "card": ""}}
        )

        self.assertEqual(profile.display_name, "昵称")


class GetTest(unittest.IsolatedAsyncioTestCase):
    async def test_group_member_success(self) -> None:
        adapter = FakeUserAdapter()
        adapter.members[(10, 42)] = GroupMemberData(
            group_id=10, user_id=42, nickname="昵称", card="群名片", role="admin", title="头衔"
        )
        users = UserDirectory(adapter)

        profile = await users.get("42", group_id="10")

        self.assertEqual(profile.user_id, "42")
        self.assertEqual(profile.nickname, "昵称")
        self.assertEqual(profile.card, "群名片")
        self.assertEqual(profile.role, "admin")
        self.assertEqual(profile.title, "头衔")
        self.assertEqual(profile.group_id, "10")
        self.assertEqual(profile.display_name, "群名片")
        self.assertEqual(adapter.calls, [("get_group_member_info", (10, 42))])

    async def test_group_failure_falls_back_to_stranger(self) -> None:
        adapter = FakeUserAdapter()
        adapter.strangers[42] = StrangerInfoData(user_id=42, nickname="全局昵称")
        users = UserDirectory(adapter)

        profile = await users.get("42", group_id="10")

        self.assertEqual(profile.nickname, "全局昵称")
        self.assertIsNone(profile.group_id)
        self.assertEqual(profile.display_name, "全局昵称")
        self.assertEqual(
            adapter.calls,
            [("get_group_member_info", (10, 42)), ("get_stranger_info", (42,))],
        )

    async def test_group_member_exception_falls_back_to_stranger(self) -> None:
        adapter = FakeUserAdapter()
        adapter.member_info_error = RuntimeError("api down")
        adapter.strangers[42] = StrangerInfoData(user_id=42, nickname="备用")
        users = UserDirectory(adapter)

        profile = await users.get("42", group_id="10")

        self.assertEqual(profile.display_name, "备用")
        self.assertEqual(len(adapter.calls), 2)

    async def test_group_failure_reuses_cached_stranger(self) -> None:
        adapter = FakeUserAdapter()
        adapter.strangers[42] = StrangerInfoData(user_id=42, nickname="全局昵称")
        users = UserDirectory(adapter)

        await users.get("42", group_id="10")
        await users.get("42", group_id="10")

        # 群成员信息每次都重试，但陌生人兜底应命中 (uid, None) 缓存，不再重复请求
        self.assertEqual(
            [name for name, _ in adapter.calls],
            ["get_group_member_info", "get_stranger_info", "get_group_member_info"],
        )

    async def test_group_failure_then_global_query_hits_stranger_cache(self) -> None:
        adapter = FakeUserAdapter()
        adapter.strangers[42] = StrangerInfoData(user_id=42, nickname="全局昵称")
        users = UserDirectory(adapter)

        await users.get("42", group_id="10")
        profile = await users.get("42")

        self.assertEqual(profile.display_name, "全局昵称")
        self.assertEqual(
            [name for name, _ in adapter.calls],
            ["get_group_member_info", "get_stranger_info"],
        )

    async def test_non_numeric_group_id_degrades_to_stranger(self) -> None:
        adapter = FakeUserAdapter()
        adapter.strangers[42] = StrangerInfoData(user_id=42, nickname="备用")
        users = UserDirectory(adapter)

        profile = await users.get("42", group_id="abc")

        self.assertEqual(profile.display_name, "备用")
        self.assertEqual([name for name, _ in adapter.calls], ["get_stranger_info"])

    async def test_all_fail_returns_placeholder(self) -> None:
        adapter = FakeUserAdapter()
        users = UserDirectory(adapter)

        profile = await users.get("42", group_id="10")

        self.assertEqual(profile.user_id, "42")
        self.assertIsNone(profile.nickname)
        self.assertIsNone(profile.card)
        self.assertIsNone(profile.group_id)
        self.assertEqual(profile.display_name, "42")
        self.assertEqual(adapter.calls, [("get_group_member_info", (10, 42)), ("get_stranger_info", (42,))])

    async def test_non_numeric_user_id_returns_placeholder(self) -> None:
        adapter = FakeUserAdapter()
        users = UserDirectory(adapter)

        profile = await users.get("not-a-number")

        self.assertEqual(profile.user_id, "not-a-number")
        self.assertEqual(profile.display_name, "not-a-number")
        self.assertEqual(adapter.calls, [])

    async def test_zero_user_and_group_id(self) -> None:
        adapter = FakeUserAdapter()
        adapter.members[(0, 0)] = GroupMemberData(group_id=0, user_id=0, nickname="zero")
        users = UserDirectory(adapter)

        profile = await users.get("0", group_id="0")

        self.assertEqual(profile.user_id, "0")
        self.assertEqual(profile.group_id, "0")
        self.assertEqual(profile.display_name, "zero")

    async def test_group_member_missing_user_id_uses_requested_uid(self) -> None:
        adapter = FakeUserAdapter()
        adapter.members[(10, 42)] = GroupMemberData(group_id=10, user_id=None, nickname="n")
        users = UserDirectory(adapter)

        profile = await users.get("42", group_id="10")

        self.assertEqual(profile.user_id, "42")

    async def test_stranger_missing_user_id_uses_requested_uid(self) -> None:
        adapter = FakeUserAdapter()
        adapter.strangers[42] = SimpleNamespace(user_id=None, nickname="n")  # type: ignore[assignment]
        users = UserDirectory(adapter)

        profile = await users.get("42")

        self.assertEqual(profile.user_id, "42")

    async def test_display_name_method(self) -> None:
        adapter = FakeUserAdapter()
        adapter.members[(10, 42)] = GroupMemberData(group_id=10, user_id=42, nickname="n", card="c")
        users = UserDirectory(adapter)

        self.assertEqual(await users.display_name("42", group_id="10"), "c")

    async def test_display_name_empty_card_and_nickname_falls_back_to_user_id(self) -> None:
        adapter = FakeUserAdapter()
        adapter.members[(10, 42)] = GroupMemberData(group_id=10, user_id=42, nickname="", card="")
        users = UserDirectory(adapter)

        self.assertEqual(await users.display_name("42", group_id="10"), "42")

    async def test_group_total_failure_propagates_negative_cache_to_global(self) -> None:
        # (uid, group_id) 全失败写入 failed 负缓存后，随后以 group_id=None 查询
        # 应命中 (uid, None) 负缓存，不重复请求刚失败的 get_stranger_info
        adapter = FakeUserAdapter()
        now = [0.0]
        users = _with_now(adapter, now)

        await users.get("42", group_id="10")
        self.assertEqual(len(adapter.calls), 2)

        profile = await users.get("42")

        self.assertEqual(profile.user_id, "42")
        self.assertEqual(len(adapter.calls), 2)

    async def test_refresh_failure_does_not_poison_live_global_cache(self) -> None:
        # refresh 场景下 stranger 新请求失败，不应覆盖 (uid, None) 中仍有效的成功缓存
        adapter = FakeUserAdapter()
        adapter.strangers[42] = StrangerInfoData(user_id=42, nickname="全局")
        users = UserDirectory(adapter)

        await users.get("42")
        self.assertEqual(len(adapter.calls), 1)

        adapter.strangers[42] = None
        await users.get("42", group_id="10", refresh=True)
        self.assertEqual(len(adapter.calls), 3)

        profile = await users.get("42")

        self.assertEqual(profile.display_name, "全局")
        self.assertEqual(len(adapter.calls), 3)

    async def test_malformed_cache_entry_is_evicted_and_recovers(self) -> None:
        adapter = FakeUserAdapter()
        adapter.strangers[42] = StrangerInfoData(user_id=42, nickname="全局")
        users = UserDirectory(adapter)

        users._cache[("42", None)] = ("old-format-tuple",)  # type: ignore[assignment]

        profile = await users.get("42")

        self.assertEqual(profile.display_name, "全局")
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(len(users._cache[("42", None)]), 3)

        await users.get("42")
        self.assertEqual(len(adapter.calls), 1)

    async def test_malformed_cache_fetched_at_recovers(self) -> None:
        adapter = FakeUserAdapter()
        adapter.strangers[42] = StrangerInfoData(user_id=42, nickname="全局")
        users = UserDirectory(adapter)

        users._cache[("42", None)] = (UserProfile(user_id="42"), None, False)  # type: ignore[assignment]

        profile = await users.get("42")

        self.assertEqual(profile.display_name, "全局")
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(len(users._cache[("42", None)]), 3)

    async def test_concurrent_get_same_key_returns_consistent_results(self) -> None:
        # 设计上无 per-key 锁（TTL 粗粒度去抖覆盖收益），并发同 key 允许重复请求，
        # 但结果必须一致且无损坏
        adapter = _GatedMemberAdapter()
        adapter.members[(10, 42)] = GroupMemberData(
            group_id=10, user_id=42, nickname="昵称", card="群名片", role="admin"
        )
        users = UserDirectory(adapter)

        p1, p2 = await asyncio.gather(
            users.get("42", group_id="10"),
            users.get("42", group_id="10"),
        )

        self.assertEqual(p1.card, "群名片")
        self.assertEqual(p2.card, "群名片")
        self.assertEqual(p1.user_id, p2.user_id)
        self.assertEqual(p1.display_name, p2.display_name)
        self.assertEqual(adapter.max_in_flight, 2)

    async def test_not_configured_raises(self) -> None:
        users = UserDirectory(None)

        with self.assertRaisesRegex(RuntimeError, "UserDirectory not configured"):
            await users.get("42")
        with self.assertRaisesRegex(RuntimeError, "UserDirectory not configured"):
            await users.get("42", group_id="10")
        with self.assertRaisesRegex(RuntimeError, "UserDirectory not configured"):
            await users.get_many(["42"], group_id="10")


class CacheTest(unittest.IsolatedAsyncioTestCase):
    async def test_success_cached_until_ttl(self) -> None:
        adapter = FakeUserAdapter()
        adapter.members[(10, 42)] = GroupMemberData(group_id=10, user_id=42, nickname="n")
        now = [1000.0]
        users = _with_now(adapter, now)

        await users.get("42", group_id="10")
        await users.get("42", group_id="10")
        self.assertEqual(len(adapter.calls), 1)

        now[0] = 1299.0
        await users.get("42", group_id="10")
        self.assertEqual(len(adapter.calls), 1)

        now[0] = 1300.0
        await users.get("42", group_id="10")
        self.assertEqual(len(adapter.calls), 2)

    async def test_refresh_skips_cache(self) -> None:
        adapter = FakeUserAdapter()
        adapter.members[(10, 42)] = GroupMemberData(group_id=10, user_id=42, nickname="n")
        users = UserDirectory(adapter)

        await users.get("42", group_id="10")
        await users.get("42", group_id="10", refresh=True)

        self.assertEqual(len(adapter.calls), 2)

    async def test_failure_negative_cache_30s(self) -> None:
        adapter = FakeUserAdapter()
        now = [0.0]
        users = _with_now(adapter, now)

        await users.get("42")
        self.assertEqual(len(adapter.calls), 1)

        now[0] = 10.0
        await users.get("42")
        self.assertEqual(len(adapter.calls), 1)

        now[0] = 35.0
        await users.get("42")
        self.assertEqual(len(adapter.calls), 2)

    async def test_stranger_success_cached_with_long_ttl(self) -> None:
        adapter = FakeUserAdapter()
        adapter.strangers[7] = StrangerInfoData(user_id=7, nickname="s")
        now = [0.0]
        users = _with_now(adapter, now)

        await users.get("7")
        now[0] = 100.0
        await users.get("7")

        self.assertEqual(len(adapter.calls), 1)

    async def test_real_member_without_names_is_success_cached(self) -> None:
        # 真实成员 nickname/card 均为 None 是 API 返回的数据，不是占位失败，
        # 应按 SUCCESS_TTL 缓存，而不是被误判为失败负缓存 30s
        adapter = FakeUserAdapter()
        adapter.members[(10, 42)] = GroupMemberData(
            group_id=10, user_id=42, nickname=None, card=None
        )
        now = [0.0]
        users = _with_now(adapter, now)

        await users.get("42", group_id="10")
        now[0] = 100.0
        await users.get("42", group_id="10")

        self.assertEqual(len(adapter.calls), 1)

    async def test_placeholder_still_negative_cached_30s(self) -> None:
        adapter = FakeUserAdapter()
        now = [0.0]
        users = _with_now(adapter, now)

        await users.get("42")
        now[0] = 35.0
        await users.get("42")

        self.assertEqual(len(adapter.calls), 2)


class GetManyTest(unittest.IsolatedAsyncioTestCase):
    async def test_empty_input_returns_empty(self) -> None:
        users = UserDirectory(FakeUserAdapter())

        self.assertEqual(await users.get_many([]), {})

    async def test_empty_input_makes_no_adapter_calls(self) -> None:
        adapter = FakeUserAdapter()
        users = UserDirectory(adapter)

        self.assertEqual(await users.get_many([]), {})
        self.assertEqual(adapter.calls, [])

    async def test_empty_input_without_adapter(self) -> None:
        users = UserDirectory(None)

        self.assertEqual(await users.get_many([]), {})

    async def test_all_cache_hit_skips_adapter_entirely(self) -> None:
        adapter = FakeUserAdapter()
        adapter.member_list = [
            GroupMemberData(group_id=10, user_id=1, nickname="a"),
            GroupMemberData(group_id=10, user_id=2, nickname="b"),
        ]
        users = UserDirectory(adapter)

        await users.get_many(["1", "2"], group_id="10")
        calls_after_first = len(adapter.calls)
        result = await users.get_many(["1", "2"], group_id="10")

        self.assertEqual(len(adapter.calls), calls_after_first)
        self.assertEqual(result["1"].display_name, "a")
        self.assertEqual(result["2"].display_name, "b")

    async def test_all_cache_hit_without_group_skips_adapter(self) -> None:
        adapter = FakeUserAdapter()
        adapter.strangers[1] = StrangerInfoData(user_id=1, nickname="a")
        users = UserDirectory(adapter)

        await users.get_many(["1"])
        calls_after_first = len(adapter.calls)
        result = await users.get_many(["1"])

        self.assertEqual(len(adapter.calls), calls_after_first)
        self.assertEqual(result["1"].display_name, "a")

    async def test_get_many_hits_cache_populated_by_refresh(self) -> None:
        # get_many 无 refresh 参数：只读缓存 + 缺失逐人回退，refresh 写入的缓存应被复用
        adapter = FakeUserAdapter()
        adapter.members[(10, 1)] = GroupMemberData(group_id=10, user_id=1, nickname="a")
        users = UserDirectory(adapter)

        await users.get("1", group_id="10", refresh=True)
        result = await users.get_many(["1"], group_id="10")

        self.assertEqual(result["1"].display_name, "a")
        self.assertEqual(len(adapter.calls), 1)

    async def test_group_uses_single_list_call_and_falls_back(self) -> None:
        adapter = FakeUserAdapter()
        adapter.member_list = [
            GroupMemberData(group_id=10, user_id=1, nickname="a", card="A"),
            GroupMemberData(group_id=10, user_id=2, nickname="b", card="B"),
        ]
        adapter.strangers[3] = StrangerInfoData(user_id=3, nickname="c")
        users = UserDirectory(adapter)

        result = await users.get_many(["1", "2", "3"], group_id="10")

        self.assertEqual(result["1"].display_name, "A")
        self.assertEqual(result["2"].display_name, "B")
        self.assertEqual(result["3"].display_name, "c")
        self.assertEqual(
            [name for name, _ in adapter.calls],
            ["get_group_member_list", "get_group_member_info", "get_stranger_info"],
        )

    async def test_single_uid_skips_member_list(self) -> None:
        # 单 uid 未命中缓存时直接逐人查询，避免整群拉 member list 的大请求
        adapter = FakeUserAdapter()
        adapter.member_list = [GroupMemberData(group_id=10, user_id=1, nickname="a")]
        adapter.members[(10, 1)] = GroupMemberData(group_id=10, user_id=1, nickname="a")
        users = UserDirectory(adapter)

        result = await users.get_many(["1"], group_id="10")

        self.assertEqual(result["1"].display_name, "a")
        self.assertEqual(
            [name for name, _ in adapter.calls], ["get_group_member_info"]
        )

    async def test_group_list_failure_degrades_to_per_person(self) -> None:
        adapter = FakeUserAdapter()
        adapter.member_list_error = RuntimeError("list down")
        adapter.members[(10, 1)] = GroupMemberData(group_id=10, user_id=1, nickname="a")
        adapter.members[(10, 2)] = GroupMemberData(group_id=10, user_id=2, nickname="b")
        users = UserDirectory(adapter)

        result = await users.get_many(["1", "2"], group_id="10")

        self.assertEqual(result["1"].nickname, "a")
        self.assertEqual(result["2"].nickname, "b")
        self.assertEqual(
            [name for name, _ in adapter.calls],
            ["get_group_member_list", "get_group_member_info", "get_group_member_info"],
        )

    async def test_get_many_non_member_fallback_is_concurrent(self) -> None:
        adapter = _GatedStrangerAdapter()
        adapter.member_list = [GroupMemberData(group_id=10, user_id=1, nickname="a")]
        adapter.strangers[2] = StrangerInfoData(user_id=2, nickname="b")
        adapter.strangers[3] = StrangerInfoData(user_id=3, nickname="c")
        users = UserDirectory(adapter)

        result = await users.get_many(["1", "2", "3"], group_id="10")

        self.assertEqual(list(result), ["1", "2", "3"])
        self.assertEqual(result["2"].display_name, "b")
        self.assertEqual(result["3"].display_name, "c")
        # 两个非成员的兜底 get 应并发执行（顺序 await 时最大深度为 1）
        self.assertEqual(adapter.max_in_flight, 2)

    async def test_without_group_concurrent_per_person(self) -> None:
        adapter = FakeUserAdapter()
        adapter.strangers[1] = StrangerInfoData(user_id=1, nickname="a")
        adapter.strangers[2] = StrangerInfoData(user_id=2, nickname="b")
        users = UserDirectory(adapter)

        result = await users.get_many(["1", "2"])

        self.assertEqual(result["1"].display_name, "a")
        self.assertEqual(result["2"].display_name, "b")
        self.assertEqual(
            [name for name, _ in adapter.calls], ["get_stranger_info", "get_stranger_info"]
        )

    async def test_dedupes_normalizes_and_preserves_order(self) -> None:
        adapter = FakeUserAdapter()
        adapter.members[(10, 1)] = GroupMemberData(group_id=10, user_id=1, nickname="a")
        users = UserDirectory(adapter)

        result = await users.get_many(["1", 1, "1"], group_id="10")

        self.assertEqual(list(result), ["1"])
        self.assertEqual([name for name, _ in adapter.calls], ["get_group_member_info"])

    async def test_second_call_hits_cache(self) -> None:
        adapter = FakeUserAdapter()
        adapter.members[(10, 1)] = GroupMemberData(group_id=10, user_id=1, nickname="a")
        users = UserDirectory(adapter)

        await users.get_many(["1"], group_id="10")
        await users.get_many(["1"], group_id="10")

        self.assertEqual(len(adapter.calls), 1)

    async def test_mixed_cache_hit_and_miss_preserves_input_order(self) -> None:
        # 混合缓存命中/未命中时结果顺序应与输入顺序一致（与全未命中路径一致）
        adapter = FakeUserAdapter()
        adapter.members[(10, 1)] = GroupMemberData(group_id=10, user_id=1, nickname="a")
        adapter.members[(10, 2)] = GroupMemberData(group_id=10, user_id=2, nickname="b")
        users = UserDirectory(adapter)

        await users.get("1", group_id="10")
        result = await users.get_many(["2", "1"], group_id="10")

        self.assertEqual(list(result), ["2", "1"])
        self.assertEqual([p.nickname for p in result.values()], ["b", "a"])

    async def test_mixed_cache_hit_and_miss(self) -> None:
        adapter = FakeUserAdapter()
        adapter.member_list = [GroupMemberData(group_id=10, user_id=1, nickname="a")]
        adapter.strangers[2] = StrangerInfoData(user_id=2, nickname="b")
        users = UserDirectory(adapter)

        await users.get_many(["1", "2"], group_id="10")
        result = await users.get_many(["1", "2"], group_id="10")

        self.assertEqual(result["1"].display_name, "a")
        self.assertEqual(result["2"].display_name, "b")
        # 首次：member list 命中 1、兜底 get 2；二次：1 命中缓存、2 走单 uid 逐人查询
        self.assertEqual(
            [name for name, _ in adapter.calls],
            [
                "get_group_member_list",
                "get_group_member_info",
                "get_stranger_info",
                "get_group_member_info",
            ],
        )

    async def test_get_many_non_numeric_uid(self) -> None:
        adapter = FakeUserAdapter()
        adapter.member_list = [GroupMemberData(group_id=10, user_id=1, nickname="a")]
        users = UserDirectory(adapter)

        result = await users.get_many(["1", "not-a-number"], group_id="10")

        self.assertEqual(result["not-a-number"].user_id, "not-a-number")
        self.assertEqual(result["not-a-number"].display_name, "not-a-number")

    async def test_get_many_non_numeric_group_id(self) -> None:
        adapter = FakeUserAdapter()
        adapter.strangers[1] = StrangerInfoData(user_id=1, nickname="a")
        adapter.strangers[2] = StrangerInfoData(user_id=2, nickname="b")
        users = UserDirectory(adapter)

        result = await users.get_many(["1", "2"], group_id="abc")

        self.assertEqual(result["1"].display_name, "a")
        self.assertEqual(result["2"].display_name, "b")

    async def test_list_members_feed_get_cache(self) -> None:
        adapter = FakeUserAdapter()
        adapter.member_list = [
            GroupMemberData(group_id=10, user_id=1, nickname="a", card="A"),
            GroupMemberData(group_id=10, user_id=2, nickname="b", card="B"),
        ]
        users = UserDirectory(adapter)

        await users.get_many(["1", "2"], group_id="10")
        profile = await users.get("1", group_id="10")

        self.assertEqual(profile.card, "A")
        self.assertEqual(len(adapter.calls), 1)


if __name__ == "__main__":
    unittest.main()
