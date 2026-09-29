"""并发签到的幂等性回归（P1 修复验证）。

旧实现 checkin() 的顺序是「查重(事务1) → INSERT ON CONFLICT DO NOTHING(事务2)
→ add_score(事务3)」，并发协程都可能在插入前读到 existing=None，于是冲突只丢
行、加分却人人有份：实测 20 路并发一次签到会把账户加到 111 分（应得 ≤10），
并且返回的 already/total 互相矛盾。

本用例在旧代码上必失败（多轮并发下重复记账概率接近 100%），
修复后「占当日名额 + 加分」在同一事务内以 INSERT rowcount 为判据，只记一次。
"""

from __future__ import annotations

import asyncio
import random
from datetime import datetime
from typing import Any

import pytest

from neobot_app.builtin_plugins import minigame
from neobot_app.builtin_plugins.minigame.config import MinigameConfig
from neobot_app.builtin_plugins.minigame.service import MinigameService

#: 每轮并发度；2 路也足以在旧代码上暴露（旧实现 4/5 轮触发）
CONCURRENCY_LEVELS = (2, 8, 20)
#: 每个并发度的重复轮数，避免旧实现的竞态靠运气通过
ROUNDS = 3


@pytest.fixture
async def db(tmp_path):
    database = minigame.create_database()
    await database.bind(tmp_path / "databases")
    try:
        yield database
    finally:
        await database.close()


def _service(db: Any, *, seed: int = 20260930) -> MinigameService:
    return MinigameService(
        database=db,
        config=MinigameConfig(checkin_score_min=1, checkin_score_max=10),
        clock=lambda: datetime(2026, 9, 30, 10, 0, 0),
        rng=random.Random(seed),
        monotonic=lambda: 1000.0,
    )


@pytest.mark.parametrize("concurrency", CONCURRENCY_LEVELS)
async def test_concurrent_checkin_credits_score_once(
    db: Any, concurrency: int
) -> None:
    """同一自然日 N 路并发签到：账户恰好加一次分，返回的 total 一致。"""
    service = _service(db)

    for round_no in range(ROUNDS):
        uid = f"race-{concurrency}-{round_no}"
        results = await asyncio.gather(
            *(service.checkin(uid) for _ in range(concurrency))
        )

        stored = await service.get_checkin(uid)
        assert stored is not None, "并发签到后必须落库 mg_checkin 行"
        stored_score = int(stored["score"])
        stored_streak = int(stored["streak"])

        fresh = [item for item in results if not item["already"]]
        assert len(fresh) == 1, (
            f"N={concurrency} 第{round_no}轮：只有一次签到能占位成功，"
            f"实际 {len(fresh)} 次（重复记账的信号）"
        )

        # 账户分 = 唯一一次落库的分数；绝不能被并发放大成 k 倍
        assert await service.points(uid) == stored_score, (
            f"N={concurrency} 第{round_no}轮：账户分被重复加分"
        )

        # 所有调用方必须看到同一份事实（agent 依据它播报，不能互相矛盾）
        assert {item["total"] for item in results} == {stored_score}
        assert {item["score"] for item in results} == {stored_score}
        assert {item["streak"] for item in results} == {stored_streak}
        assert {item["day"] for item in results} == {stored["day"]}
        assert all(item["already"] is True for item in results if item is not fresh[0])


async def test_concurrent_checkin_then_sequential_repeat_is_idempotent(
    db: Any,
) -> None:
    """并发之后再来一次串行签到：仍是同一结果，不再加分。"""
    service = _service(db)
    uid = "race-then-serial"
    results = await asyncio.gather(*(service.checkin(uid) for _ in range(8)))
    total_after_race = await service.points(uid)

    again = await service.checkin(uid)
    assert again["already"] is True
    assert again["total"] == total_after_race
    assert await service.points(uid) == total_after_race
    assert {item["score"] for item in results} == {again["score"]}
