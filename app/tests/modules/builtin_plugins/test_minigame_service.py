"""小游戏数据层（规格 §4.4-§4.8 的落库语义）。

覆盖：表结构与模型一致、漂流瓶软删除 + 永不按时间转档 + 池满随机转档、
每日计数、最近 3 次排除、签到随机与连续、抽签每日幂等、流水清理、排行榜。
全部走真实 SQLite（临时目录），**不联网**。
"""

from __future__ import annotations

import random
import sqlalchemy
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pytest

from neobot_app.builtin_plugins import minigame
from neobot_app.builtin_plugins.minigame import models
from neobot_app.builtin_plugins.minigame.config import MinigameConfig
from neobot_app.builtin_plugins.minigame.service import (
    BOTTLE_PICK_DAILY_LIMIT,
    BOTTLE_SEND_DAILY_LIMIT,
    DAILY_BOTTLE_PICK,
    DAILY_BOTTLE_SEND,
    STATUS_EXPIRED,
    STATUS_PICKED,
    STATUS_POOLED,
    MinigameService,
)


@dataclass
class FakeClock:
    """可控时钟（伪时间）。"""

    value: datetime

    def __call__(self) -> datetime:
        return self.value

    def advance(self, **kwargs: Any) -> None:
        self.value = self.value + timedelta(**kwargs)


class FakeMono:
    def __init__(self, value: float = 1000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


@pytest.fixture
async def clock() -> FakeClock:
    return FakeClock(datetime(2026, 9, 13, 10, 0, 0))


@pytest.fixture
async def db(tmp_path):
    database = minigame.create_database()
    await database.bind(tmp_path / "databases")
    try:
        yield database
    finally:
        await database.close()


def _service(
    db: Any,
    clock: FakeClock,
    *,
    config: MinigameConfig | None = None,
    seed: int = 20260913,
    mono: FakeMono | None = None,
) -> MinigameService:
    return MinigameService(
        database=db,
        config=config or MinigameConfig(),
        clock=clock,
        rng=random.Random(seed),
        monotonic=mono or FakeMono(),
    )


async def _add(
    service: MinigameService,
    *,
    sender: str,
    content: str = "你好",
    anonymous: bool = False,
) -> dict[str, Any]:
    return await service.add_bottle(
        sender_id=sender,
        sender_name=f"用户{sender}",
        sender_avatar="",
        content=content,
        anonymous=anonymous,
    )


# ── 结构 ─────────────────────────────────────────────────────────


async def test_tables_match_models(db: Any) -> None:
    """迁移 DDL 与 models 声明必须一致（六张表、列名集合）。"""
    from sqlalchemy import text

    expected = {
        name: {column.name for column in model.__table__.columns}
        for name, model in models.TABLES.items()
    }
    assert set(expected) == {
        "mg_profile",
        "mg_bottle",
        "mg_daily",
        "mg_checkin",
        "mg_fortune",
        "mg_record",
    }
    async with db.session() as session:
        for table, columns in expected.items():
            result = await session.execute(text(f"PRAGMA table_info({table})"))
            actual = {row[1] for row in result}
            assert actual == columns, table


async def test_database_is_plugin_owned(db: Any) -> None:
    """插件独立库：文件名 minigame.db，落在插件数据目录下。"""
    assert db.filename == "minigame.db"
    assert db.path is not None and db.path.name == "minigame.db"


# ── 漂流瓶 ───────────────────────────────────────────────────────


async def test_pick_is_soft_delete_and_never_returned_again(db: Any, clock: FakeClock) -> None:
    """A25：捞走后行仍在（status=picked + picked_at/picked_by），且不再被捞到。"""
    service = _service(db, clock)
    await _add(service, sender="1001")

    outcome = await service.pick_bottle(user_id="2002")
    bottle = outcome["bottle"]
    assert bottle is not None
    assert bottle["status"] == STATUS_PICKED
    assert bottle["picked_by"] == "2002"
    assert bottle["picked_at"]

    row = await service._one("SELECT * FROM mg_bottle WHERE id = :id", {"id": bottle["id"]})
    assert row is not None, "软删除：行必须保留"
    assert row["status"] == STATUS_PICKED
    assert await service.pool_count() == 0
    # 唯一一条已被捞走 => 再捞只能空
    assert (await service.pick_bottle(user_id="2002"))["bottle"] is None


async def test_bottle_flow_contains_no_delete(db: Any, clock: FakeClock, monkeypatch) -> None:
    """A25：发瓶 / 捞瓶全流程无任何 DELETE 语句（SQL 审计）。"""
    seen: list[str] = []
    original = sqlalchemy.text

    def spy(sql: str, *args: Any, **kwargs: Any) -> Any:
        seen.append(str(sql))
        return original(sql, *args, **kwargs)

    monkeypatch.setattr(sqlalchemy, "text", spy)

    service = _service(db, clock)
    await _add(service, sender="1001", content="给我一杯忘情水")
    await _add(service, sender="1002", anonymous=True)
    await service.pick_bottle(user_id="2002")
    await service.pick_bottle(user_id="2002")
    await service.bottle_stats()

    assert seen, "必须真的执行过 SQL"
    assert not [sql for sql in seen if "DELETE" in sql.upper()]
    # 也不允许用 UPDATE 之外的物理删除花招
    assert not [sql for sql in seen if "DROP" in sql.upper()]


async def test_pool_never_archives_by_time(db: Any, clock: FakeClock) -> None:
    """A26：伪时间推进 90 天后，池内瓶仍为 pooled 可捞。"""
    service = _service(db, clock)
    await _add(service, sender="1001")
    await _add(service, sender="1002")

    clock.advance(days=90)

    assert await service.pool_count() == 2
    outcome = await service.pick_bottle(user_id="2002")
    assert outcome["bottle"] is not None
    assert outcome["bottle"]["status"] == STATUS_PICKED


async def test_pool_full_archives_random_row_not_oldest(db: Any, clock: FakeClock) -> None:
    """A26：池满时随机转档一条既有 pooled（不是 created_at 最旧），且无 DELETE。"""
    config = MinigameConfig(bottle_pool_max=2)
    service = _service(db, config=config, clock=clock)
    await _add(service, sender="1001")
    await _add(service, sender="1002")

    archived_in_order: list[bool] = []
    for index in range(24):
        pooled = await service._all(
            "SELECT id FROM mg_bottle WHERE status = :st ORDER BY id", {"st": STATUS_POOLED}
        )
        pooled_ids = [int(row["id"]) for row in pooled]
        assert len(pooled_ids) == 2  # 池规模由上限控制
        oldest = pooled_ids[0]
        result = await _add(service, sender=f"9{index:03d}", content=f"第 {index} 个")
        assert result["archived_id"] is not None, "池满必须先转档一条"
        archived_in_order.append(int(result["archived_id"]) == oldest)
        assert await service.pool_count() == 2

    assert not all(archived_in_order), (
        "转档必须是随机的：24 次全部命中『最旧那条』的概率是 2**-24"
    )
    stats = await service.bottle_stats()
    # 首次转档只有 1 条（池从 2 满 -> 转 1 加 1），之后每次再加都转 1 条
    assert stats[STATUS_EXPIRED] == len(archived_in_order)
    assert stats[STATUS_POOLED] == 2
    assert stats["total"] == 2 + len(archived_in_order)


async def test_exclusions_and_fallback(db: Any, clock: FakeClock) -> None:
    """A28（服务层）：排除自己与最近 3 次捞取过的发送者，无瓶时回落普通随机。"""
    service = _service(db, clock)
    await _add(service, sender="1001")
    await _add(service, sender="1002")
    await _add(service, sender="1003")
    await _add(service, sender="1004")
    await _add(service, sender="2002")  # 自己的瓶

    first = await service.pick_bottle(user_id="2002")
    assert first["bottle"]["sender_id"] != "2002"
    excluded = await service.recent_picked_senders("2002")
    assert excluded == [first["bottle"]["sender_id"]]

    remaining = {"1001", "1002", "1003", "1004"} - set(excluded)
    second = await service.pick_bottle(user_id="2002", exclude_senders=excluded)
    assert second["bottle"]["sender_id"] in remaining
    assert second["used_fallback"] is False

    # 把剩下两个都排除掉 => 回落普通随机并标记
    third = await service.pick_bottle(
        user_id="2002", exclude_senders=["1001", "1002", "1003", "1004"]
    )
    assert third["bottle"] is not None
    assert third["used_fallback"] is True


async def test_recent_picked_senders_keeps_three() -> None:
    """最近 3 次排除：窗口由 RECENT_PICK_EXCLUSION 决定。"""
    from neobot_app.builtin_plugins.minigame.service import RECENT_PICK_EXCLUSION

    assert RECENT_PICK_EXCLUSION == 3


# ── 每日上限 ─────────────────────────────────────────────────────


async def test_daily_counters_are_separate(db: Any, clock: FakeClock) -> None:
    """A24/A27（服务层）：发瓶与捞瓶分别计数，上限各 5，跨日归零。"""
    service = _service(db, clock)
    for _ in range(BOTTLE_SEND_DAILY_LIMIT):
        assert await service.bump_daily("2002", DAILY_BOTTLE_SEND) <= BOTTLE_SEND_DAILY_LIMIT
    assert await service.daily_plays("2002", DAILY_BOTTLE_SEND) == BOTTLE_SEND_DAILY_LIMIT
    assert await service.daily_plays("2002", DAILY_BOTTLE_PICK) == 0

    for _ in range(BOTTLE_PICK_DAILY_LIMIT):
        await service.bump_daily("2002", DAILY_BOTTLE_PICK)
    assert await service.daily_plays("2002", DAILY_BOTTLE_PICK) == BOTTLE_PICK_DAILY_LIMIT

    clock.advance(days=1)
    assert await service.daily_plays("2002", DAILY_BOTTLE_SEND) == 0
    assert await service.daily_plays("2002", DAILY_BOTTLE_PICK) == 0


# ── 签到与积分 ───────────────────────────────────────────────────


async def test_checkin_random_range_streak_and_bonus_cap(db: Any, clock: FakeClock) -> None:
    """A32：随机 1-10 + 连续每天 +1（上限 +5）；同日重复不加分。"""
    config = MinigameConfig(checkin_score_min=1, checkin_score_max=10)
    service = _service(db, config=config, clock=clock)

    total = 0
    for day in range(1, 9):
        result = await service.checkin("2002")
        assert result["already"] is False
        assert 1 <= result["base"] <= 10
        assert result["score"] == result["base"] + min(day - 1, 5)
        total += result["score"]
        assert result["total"] == total
        clock.advance(days=1)

    # 第 9 天：连续 9 天 => 附加仍是上限 5
    result = await service.checkin("2002")
    assert result["bonus"] == 5
    assert result["streak"] == 9

    # 同一自然日重复签到：不加分，返回既有结果
    before = result["total"]
    again = await service.checkin("2002")
    assert again["already"] is True
    assert again["score"] == result["score"]
    assert again["streak"] == result["streak"]
    assert again["total"] == before
    assert await service.points("2002") == before


async def test_checkin_break_resets_streak(db: Any, clock: FakeClock) -> None:
    """A32/R28：断签连续天数归零（不提供补签）。"""
    service = _service(db, clock)
    first = await service.checkin("2002")
    assert first["streak"] == 1

    clock.advance(days=1)
    await service.checkin("2002")
    assert (await service.get_checkin("2002"))["streak"] == 2

    clock.advance(days=5)
    after_break = await service.checkin("2002")
    assert after_break["streak"] == 1
    assert after_break["bonus"] == 0


async def test_profile_score_accumulates(db: Any, clock: FakeClock) -> None:
    service = _service(db, clock)
    assert await service.points("2002") == 0
    profile = await service.add_score("2002", 3, play=True)
    assert profile["score"] == 3 and profile["plays"] == 1
    profile = await service.add_score("2002", 4, play=True, win=True)
    assert profile["score"] == 7 and profile["plays"] == 2 and profile["wins"] == 1
    assert profile["best_score"] == 7


# ── 抽签 ─────────────────────────────────────────────────────────


async def test_fortune_is_once_per_day(db: Any, clock: FakeClock) -> None:
    """A35：当日首次落库；同日再抽返回同一结果；跨日才重抽。"""
    service = _service(db, clock)
    row = await service.draw_fortune("2002", result_key="good", result_text="顺风局")
    assert row["result_key"] == "good"

    again = await service.draw_fortune("2002", result_key="bad", result_text="不宜")
    assert again["result_key"] == "good", "已抽过不重抽"
    assert await service.get_fortune("2002") is not None

    clock.advance(days=1)
    assert await service.get_fortune("2002") is None
    next_day = await service.draw_fortune("2002", result_key="great", result_text="大吉")
    assert next_day["result_key"] == "great"


async def test_fortune_does_not_change_points(db: Any, clock: FakeClock) -> None:
    """A35：抽签不附带积分。"""
    service = _service(db, clock)
    await service.draw_fortune("2002", result_key="flat", result_text="无事发生")
    assert await service.points("2002") == 0


# ── 流水与排行榜 ─────────────────────────────────────────────────


async def test_record_cleanup_respects_keep_days(db: Any, clock: FakeClock) -> None:
    config = MinigameConfig(record_keep_days=30)
    service = _service(db, config=config, clock=clock)
    await service.add_record(user_id="2002", game_id="bottle:send", score=1)
    clock.advance(days=40)
    await service.add_record(user_id="2002", game_id="bottle:send", score=1)
    assert await service.count_records() == 2

    removed = await service.cleanup_records()
    assert removed == 1
    assert await service.count_records() == 1


async def test_leaderboard_pages_and_group_rank(db: Any, clock: FakeClock) -> None:
    service = _service(db, clock)
    for index, score in enumerate([1, 5, 9, 3]):
        await service.add_score(f"100{index}", score, play=True)
        await service.add_record(
            user_id=f"100{index}",
            game_id="chengyu",
            score=score,
            conversation_id="888" if index < 2 else "999",
        )

    page = await service.leaderboard(page=1, page_size=3)
    assert page["total"] == 4
    assert [row["score"] for row in page["rows"]] == [9, 5, 3]
    page2 = await service.leaderboard(page=2, page_size=3)
    assert [row["score"] for row in page2["rows"]] == [1]

    group = await service.group_leaderboard("888")
    assert {row["user_id"] for row in group} == {"1000", "1001"}
    assert await service.group_leaderboard("777") == []
