"""用户档案与积分账户：读写 mg_profile、加分与扣分。"""

from __future__ import annotations

import random
from datetime import datetime
from datetime import timedelta
from typing import Any
from neobot_app.time_context import monotonic_seconds
from neobot_app.time_context import to_local


class _ServiceProfileMixin:
    # ── 基础工具 ─────────────────────────────────────────────────

    @property
    def config(self) -> Any:
        return self._config

    @property
    def database(self) -> Any:
        return self._database

    def now(self) -> datetime:
        return self._clock()

    def now_iso(self) -> str:
        return self._clock().isoformat()

    def today(self) -> str:
        """自然日（本地时区）的 YYYY-MM-DD。"""
        return to_local(self._clock()).date().isoformat()

    def day_offset(self, days: int) -> str:
        return (to_local(self._clock()).date() + timedelta(days=days)).isoformat()

    def _monotonic_now(self) -> float:
        if self._monotonic is not None:
            return float(self._monotonic())
        return monotonic_seconds()

    def rng(self) -> random.Random:
        return self._rng

    async def _all(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        from sqlalchemy import text

        async with self._database.transaction() as session:
            result = await session.execute(text(sql), dict(params or {}))
            return [dict(row._mapping) for row in result]

    async def _one(self, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        rows = await self._all(sql, params)
        return rows[0] if rows else None

    async def _run(self, sql: str, params: dict[str, Any] | None = None) -> int:
        from sqlalchemy import text

        async with self._database.transaction() as session:
            result = await session.execute(text(sql), dict(params or {}))
            return int(result.rowcount or 0)

    async def remember_user_name(self, user_id: Any, user_name: Any) -> bool:
        """把昵称记进 `mg_profile.user_name`（榜单卡片用），返回是否写到了行。

        尽力而为：空名、未建过行的用户都直接跳过，**永不抛异常** —— 昵称只是展示信息，
        不能因为它影响玩法。行只在首次加分/签到时创建（`ensure_profile`），
        因此顺序上「先报昵称、后得分」的常见路径也能落到同一行。
        """
        uid = str(user_id or "").strip()
        name = str(user_name or "").strip()[:128]
        if not uid or not name:
            return False
        try:
            changed = await self._run(
                "UPDATE mg_profile SET user_name = :name WHERE user_id = :uid",
                {"name": name, "uid": uid},
            )
        except Exception:
            return False
        return changed > 0

    # ── 积分账户（mg_profile）────────────────────────────────────

    async def ensure_profile(self, user_id: Any) -> dict[str, Any]:
        uid = str(user_id)
        await self._run(
            """
            INSERT INTO mg_profile (user_id, score, best_score, plays, wins, updated_at)
            VALUES (:uid, 0, 0, 0, 0, :now)
            ON CONFLICT (user_id) DO NOTHING
            """,
            {"uid": uid, "now": self.now_iso()},
        )
        row = await self._one("SELECT * FROM mg_profile WHERE user_id = :uid", {"uid": uid})
        return row or {"user_id": uid, "score": 0, "best_score": 0, "plays": 0, "wins": 0}

    async def get_profile(self, user_id: Any) -> dict[str, Any]:
        row = await self._one(
            "SELECT * FROM mg_profile WHERE user_id = :uid", {"uid": str(user_id)}
        )
        if row is None:
            return await self.ensure_profile(user_id)
        return row

    async def points(self, user_id: Any) -> int:
        row = await self._one(
            "SELECT score FROM mg_profile WHERE user_id = :uid", {"uid": str(user_id)}
        )
        return int(row["score"]) if row else 0

    async def add_score(
        self,
        user_id: Any,
        delta: int,
        *,
        play: bool = False,
        win: bool = False,
    ) -> dict[str, Any]:
        """加分并（可选）累计场次 / 胜场；返回更新后的档案。"""
        uid = str(user_id)
        await self.ensure_profile(uid)
        await self._run(
            """
            UPDATE mg_profile
               SET score = score + :delta,
                   best_score = MAX(best_score, score + :delta),
                   plays = plays + :plays,
                   wins = wins + :wins,
                   updated_at = :now
             WHERE user_id = :uid
            """,
            {
                "uid": uid,
                "delta": int(delta),
                "plays": 1 if play else 0,
                "wins": 1 if win else 0,
                "now": self.now_iso(),
            },
        )
        return await self.ensure_profile(uid)

    async def apply_points(
        self,
        user_id: Any,
        delta: int,
        *,
        allow_negative: bool = False,
        play: bool = False,
        win: bool = False,
    ) -> dict[str, Any]:
        """原子增减积分（给其它插件用的写入口，见插件能力 points.add）。

        与 add_score 的差别集中在**扣分**：余额不足时必须语义明确，因此

        - delta >= 0：直接加上（等价 add_score）；
        - delta < 0 且 allow_negative=False（默认）：把 score + delta >= 0 写进
          UPDATE 的 WHERE，**整笔生效或整笔不生效**，不做部分扣减——并发下
          也不会扣成负数；
        - delta < 0 且 allow_negative=True：允许扣成负数（罚分场景）。

        返回 ``{"applied": int, "insufficient": bool, "profile": dict}``：
        insufficient=True 时 applied=0，profile 是当前档案（未被改动）。
        """
        uid = str(user_id)
        amount = int(delta)
        await self.ensure_profile(uid)
        if amount == 0:
            return {
                "applied": 0,
                "insufficient": False,
                "profile": await self.get_profile(uid),
            }

        sql = (
            "UPDATE mg_profile "
            "SET score = score + :delta, "
            "best_score = MAX(best_score, score + :delta), "
            "plays = plays + :plays, wins = wins + :wins, updated_at = :now "
            "WHERE user_id = :uid"
        )
        if amount < 0 and not allow_negative:
            sql += " AND score + :delta >= 0"
        changed = await self._run(
            sql,
            {
                "uid": uid,
                "delta": amount,
                "plays": 1 if play else 0,
                "wins": 1 if win else 0,
                "now": self.now_iso(),
            },
        )
        profile = await self.get_profile(uid)
        if changed <= 0 and amount < 0 and not allow_negative:
            return {"applied": 0, "insufficient": True, "profile": profile}
        return {"applied": amount, "insufficient": False, "profile": profile}
