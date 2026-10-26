"""抽签、流水与排行榜：抽签落库、记录清理与两种榜单。"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from neobot_app.time_context import to_local

from .service_constants import CLEANUP_INTERVAL_SECONDS


class _ServiceRecordsMixin:
    # ── 抽签（mg_fortune）──────────────────────────────────────

    async def get_fortune(self, user_id: Any, day: str | None = None) -> dict[str, Any] | None:
        return await self._one(
            "SELECT * FROM mg_fortune WHERE user_id = :uid AND day = :day",
            {"uid": str(user_id), "day": day or self.today()},
        )

    async def draw_fortune(
        self, user_id: Any, *, result_key: str, result_text: str
    ) -> dict[str, Any]:
        """当日首次落库；已抽过则返回既有结果（不重抽、不改动）。"""
        uid = str(user_id)
        day = self.today()
        await self._run(
            """
            INSERT INTO mg_fortune (user_id, day, result_key, result_text, drawn_at)
            VALUES (:uid, :day, :key, :text, :now)
            ON CONFLICT (user_id, day) DO NOTHING
            """,
            {
                "uid": uid,
                "day": day,
                "key": str(result_key),
                "text": str(result_text),
                "now": self.now_iso(),
            },
        )
        row = await self.get_fortune(uid, day)
        assert row is not None
        return row

    # ── 流水与排行榜（mg_record / mg_profile）────────────────────

    async def add_record(
        self,
        *,
        user_id: Any,
        game_id: str,
        score: int,
        conversation_id: Any = "",
    ) -> None:
        await self._run(
            """
            INSERT INTO mg_record (user_id, game_id, score, conversation_id, created_at)
            VALUES (:uid, :gid, :score, :conv, :now)
            """,
            {
                "uid": str(user_id),
                "gid": str(game_id),
                "score": int(score),
                "conv": str(conversation_id or ""),
                "now": self.now_iso(),
            },
        )
        await self._maybe_cleanup()

    async def _maybe_cleanup(self) -> None:
        """按最小间隔（1 小时，进程内）触发 mg_record 到期清理。

        进程刚启动的第一个小时不会清理：这样「发瓶 / 捞瓶」流程不会出现
        任何 DELETE（A25 的 SQL 审计口径），而长期运行终会清理。
        """
        now = self._monotonic_now()
        if not self._cleanup_armed:
            self._last_cleanup_at = now
            self._cleanup_armed = True
            return
        last = self._last_cleanup_at if self._last_cleanup_at is not None else now
        if now - last < CLEANUP_INTERVAL_SECONDS:
            return
        self._last_cleanup_at = now
        await self.cleanup_records()

    async def cleanup_records(self) -> int:
        """删除超过 record_keep_days 的流水；返回删除条数。"""
        keep = int(getattr(self._config, "record_keep_days", 30) or 30)
        cutoff = (to_local(self._clock()) - timedelta(days=keep)).isoformat()
        return await self._run(
            "DELETE FROM mg_record WHERE created_at < :cutoff", {"cutoff": cutoff}
        )

    async def count_records(self) -> int:
        row = await self._one("SELECT COUNT(*) AS n FROM mg_record")
        return int(row["n"]) if row else 0

    async def leaderboard(self, *, page: int = 1, page_size: int = 10) -> dict[str, Any]:
        """全局积分榜（本群榜见 group_leaderboard）。"""
        total_row = await self._one("SELECT COUNT(*) AS n FROM mg_profile")
        total = int(total_row["n"]) if total_row else 0
        offset = max(0, (int(page) - 1) * int(page_size))
        rows = await self._all(
            """
            SELECT user_id, user_name, score, best_score, plays, wins FROM mg_profile
             ORDER BY score DESC, updated_at ASC
             LIMIT :limit OFFSET :offset
            """,
            {"limit": int(page_size), "offset": offset},
        )
        return {"total": total, "page": int(page), "page_size": int(page_size), "rows": rows}

    async def group_leaderboard(
        self, conversation_id: Any, *, limit: int = 10
    ) -> list[dict[str, Any]]:
        return await self._all(
            """
            SELECT r.user_id,
                   SUM(r.score) AS score,
                   COUNT(*) AS plays,
                   COALESCE(p.user_name, '') AS user_name
              FROM mg_record r
              LEFT JOIN mg_profile p ON p.user_id = r.user_id
             WHERE r.conversation_id = :conv
             GROUP BY r.user_id
             ORDER BY score DESC
             LIMIT :limit
            """,
            {"conv": str(conversation_id or ""), "limit": int(limit)},
        )
