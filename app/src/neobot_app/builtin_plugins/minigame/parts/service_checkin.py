"""签到：连续天数与幂等领取。"""

from __future__ import annotations

from typing import Any


class _ServiceCheckinMixin:
    # ── 签到（mg_checkin）───────────────────────────────────────

    async def get_checkin(self, user_id: Any, day: str | None = None) -> dict[str, Any] | None:
        return await self._one(
            "SELECT * FROM mg_checkin WHERE user_id = :uid AND day = :day",
            {"uid": str(user_id), "day": day or self.today()},
        )

    async def checkin(self, user_id: Any) -> dict[str, Any]:
        """每日签到（幂等）。

        返回 {"already": bool, "score": int, "streak": int, "base": int,
        "bonus": int, "total": int, "day": str}；同一自然日重复签到不加分，
        并返回既有结果。

        「占当日名额 + 加分」在**同一事务**内完成，并以 mg_checkin 的 INSERT
        rowcount 作为加分前提：并发重复签到只有一个调用方拿到 rowcount=1 并
        加分，其余调用方按已签到返回既有结果，因此不会重复记账，
        already/total 也不会互相矛盾。
        """
        uid = str(user_id)
        day = self.today()
        existing = await self.get_checkin(uid, day)
        if existing is not None:
            return self._checkin_result(
                already=True,
                stored=existing,
                profile=await self.get_profile(uid),
                base=int(existing["score"]),
                bonus=0,
                day=day,
            )

        low = int(getattr(self._config, "checkin_score_min", 1))
        high = int(getattr(self._config, "checkin_score_max", 10))
        if high < low:
            low, high = high, low
        base = int(self._rng.randint(low, high))

        yesterday = await self.get_checkin(uid, self.day_offset(-1))
        streak = int(yesterday["streak"]) + 1 if yesterday is not None else 1
        per_day = int(getattr(self._config, "checkin_streak_bonus", 1))
        cap = int(getattr(self._config, "checkin_streak_bonus_cap", 5))
        bonus = min(max(streak - 1, 0) * per_day, cap)
        score = base + bonus

        claimed, stored, profile = await self._claim_checkin(
            uid, day, score=score, streak=streak
        )
        if not claimed:
            # 并发下当日名额已被别的调用方占走：以对方落库的结果为准，本次不加分。
            return self._checkin_result(
                already=True,
                stored=stored,
                profile=profile,
                base=int(stored["score"]),
                bonus=0,
                day=day,
            )
        return self._checkin_result(
            already=False,
            stored=stored,
            profile=profile,
            base=base,
            bonus=bonus,
            day=day,
        )

    @staticmethod
    def _checkin_result(
        *,
        already: bool,
        stored: dict[str, Any],
        profile: dict[str, Any],
        base: int,
        bonus: int,
        day: str,
    ) -> dict[str, Any]:
        """统一签到返回值：already=True 的调用方也必须与落库事实一致。"""
        return {
            "already": already,
            "score": int(stored["score"]),
            "streak": int(stored["streak"]),
            "base": base,
            "bonus": bonus,
            "total": int(profile["score"]),
            "day": day,
        }

    async def _claim_checkin(
        self, uid: str, day: str, *, score: int, streak: int
    ) -> tuple[bool, dict[str, Any], dict[str, Any]]:
        """原子占位并加分，返回 (是否由本次占位, 签到行, 加分后的档案)。

        插入 mg_checkin 与 mg_profile 加分在同一事务内提交；rowcount=0 表示
        当日名额已被并发调用方占走，此时**不加分**——这是幂等的唯一判据，
        不能再依赖事务外读到的 existing（那正是并发重复记账的根因）。
        """
        from sqlalchemy import text

        now = self.now_iso()
        async with self._database.transaction() as session:
            inserted = int(
                (
                    await session.execute(
                        text(
                            """
                            INSERT INTO mg_checkin (user_id, day, score, streak, created_at)
                            VALUES (:uid, :day, :score, :streak, :now)
                            ON CONFLICT (user_id, day) DO NOTHING
                            """
                        ),
                        {
                            "uid": uid,
                            "day": day,
                            "score": int(score),
                            "streak": int(streak),
                            "now": now,
                        },
                    )
                ).rowcount
                or 0
            )
            if inserted:
                # 与 add_score(uid, score) 等价，但必须与本事务的占位同生共死。
                await session.execute(
                    text(
                        """
                        INSERT INTO mg_profile (user_id, score, best_score, plays, wins, updated_at)
                        VALUES (:uid, 0, 0, 0, 0, :now)
                        ON CONFLICT (user_id) DO NOTHING
                        """
                    ),
                    {"uid": uid, "now": now},
                )
                await session.execute(
                    text(
                        """
                        UPDATE mg_profile
                           SET score = score + :delta,
                               best_score = MAX(best_score, score + :delta),
                               plays = plays + :plays,
                               wins = wins + :wins,
                               updated_at = :now
                         WHERE user_id = :uid
                        """
                    ),
                    {"uid": uid, "delta": int(score), "plays": 0, "wins": 0, "now": now},
                )
            stored_row = (
                await session.execute(
                    text("SELECT * FROM mg_checkin WHERE user_id = :uid AND day = :day"),
                    {"uid": uid, "day": day},
                )
            ).first()
            profile_row = (
                await session.execute(
                    text("SELECT * FROM mg_profile WHERE user_id = :uid"), {"uid": uid}
                )
            ).first()

        stored = (
            dict(stored_row._mapping)
            if stored_row is not None
            else {"score": int(score), "streak": int(streak)}
        )
        profile = (
            dict(profile_row._mapping)
            if profile_row is not None
            else await self.ensure_profile(uid)
        )
        return inserted > 0, stored, profile

    async def streak(self, user_id: Any) -> int:
        row = await self.get_checkin(user_id)
        return int(row["streak"]) if row else 0
