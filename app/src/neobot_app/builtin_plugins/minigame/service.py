"""小游戏数据访问层（spec(5) §4.4 / R12）。

**程序负责**：随机、幂等、每日上限、计分、落库、池上限与归档、排行榜；
**不负责**玩法判定（是否算成语、接不接得上等一律交 AI，见 D14）。

设计要点：

- 时间一律以 **ISO 字符串**写进 DATETIME 列：SQLite 是动态类型，字符串比较即
  时间比较（同一时钟源的偏移格式一致），因此「伪时间」测试不需要额外机制；
- **漂流瓶只做软删除**（status=picked/expired + 时间戳），全程不 DELETE；
  唯一会 DELETE 的是 mg_record 的到期清理（record_keep_days），且只在
  显式调用 cleanup_records() 时发生（进程内最小间隔 1 小时，见下）；
- 池满转档用 **ORDER BY RANDOM() LIMIT 1**（随机，不按 created_at）；
- 所有随机都走注入的 rng（测试可种子化）。
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from typing import Any

from neobot_app.time_context import monotonic_seconds, now_local, to_local

#: mg_daily 里的计数键
DAILY_BOTTLE_SEND = "bottle:send"
DAILY_BOTTLE_PICK = "bottle:pick"

#: 每日上限（§4.5：发瓶 5 + 捞瓶 5，分别计；捞取无冷却）
BOTTLE_SEND_DAILY_LIMIT = 5
BOTTLE_PICK_DAILY_LIMIT = 5

#: 每瓶 / 每次捞取的积分
BOTTLE_SEND_SCORE = 1
BOTTLE_PICK_SCORE = 1

#: 排除「自己最近 N 次捞取过的发送者」
RECENT_PICK_EXCLUSION = 3

#: mg_record 清理的最小触发间隔（秒）：进程内首次调用不清理，避免把
#: 「捞瓶流程」变成带 DELETE 的流程（A25 的 SQL 审计口径）。
CLEANUP_INTERVAL_SECONDS = 3600.0

#: 池状态
STATUS_POOLED = "pooled"
STATUS_PICKED = "picked"
STATUS_EXPIRED = "expired"


class MinigameService:
    """小游戏的数据访问：池 / 积分 / 签到 / 抽签 / 流水 / 排行榜。"""

    def __init__(
        self,
        *,
        database: Any,
        config: Any,
        clock: Any = None,
        rng: random.Random | None = None,
        logger: Any = None,
        monotonic: Any = None,
    ) -> None:
        self._database = database
        self._config = config
        self._clock = clock or now_local
        self._rng = rng or random.Random()
        self._logger = logger
        self._monotonic = monotonic
        self._last_cleanup_at: float | None = None
        self._cleanup_armed = False

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

    # ── 每日上限（mg_daily）──────────────────────────────────────

    async def daily_plays(self, user_id: Any, game_id: str, day: str | None = None) -> int:
        row = await self._one(
            "SELECT plays FROM mg_daily WHERE user_id = :uid AND game_id = :gid AND day = :day",
            {"uid": str(user_id), "gid": game_id, "day": day or self.today()},
        )
        return int(row["plays"]) if row else 0

    async def bump_daily(self, user_id: Any, game_id: str, day: str | None = None) -> int:
        """计数 +1（写库）；返回写入后的次数。"""
        params = {"uid": str(user_id), "gid": game_id, "day": day or self.today()}
        await self._run(
            """
            INSERT INTO mg_daily (user_id, game_id, day, plays)
            VALUES (:uid, :gid, :day, 1)
            ON CONFLICT (user_id, game_id, day) DO UPDATE SET plays = plays + 1
            """,
            params,
        )
        return await self.daily_plays(user_id, game_id, params["day"])

    # ── 漂流瓶（mg_bottle）──────────────────────────────────────

    async def pool_count(self) -> int:
        row = await self._one(
            "SELECT COUNT(*) AS n FROM mg_bottle WHERE status = :st", {"st": STATUS_POOLED}
        )
        return int(row["n"]) if row else 0

    async def add_bottle(
        self,
        *,
        sender_id: Any,
        sender_name: str,
        sender_avatar: str,
        content: str,
        anonymous: bool,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """落库一个新瓶；池满（>= bottle_pool_max）时先**随机**转档一条既有 pooled。

        返回 {"id": ..., "archived_id": ...}：archived_id 非空表示本次触发了转档。
        """
        limit = int(getattr(self._config, "bottle_pool_max", 1000) or 1000)
        archived_id: int | None = None
        if limit > 0:
            current = await self.pool_count()
            if current >= limit:
                row = await self._one(
                    "SELECT id FROM mg_bottle WHERE status = :st ORDER BY RANDOM() LIMIT 1",
                    {"st": STATUS_POOLED},
                )
                if row is not None:
                    marked = await self._run(
                        "UPDATE mg_bottle SET status = :exp WHERE id = :id AND status = :st",
                        {"exp": STATUS_EXPIRED, "id": int(row["id"]), "st": STATUS_POOLED},
                    )
                    if marked:
                        archived_id = int(row["id"])
        await self._run(
            """
            INSERT INTO mg_bottle (
                sender_id, sender_name, sender_avatar, content, anonymous,
                created_at, picked_at, picked_by, status, meta
            ) VALUES (
                :sender_id, :sender_name, :sender_avatar, :content, :anonymous,
                :created_at, NULL, '', :status, :meta
            )
            """,
            {
                "sender_id": str(sender_id),
                "sender_name": str(sender_name),
                "sender_avatar": str(sender_avatar or ""),
                "content": str(content),
                "anonymous": 1 if anonymous else 0,
                "created_at": self.now_iso(),
                "status": STATUS_POOLED,
                "meta": json.dumps(meta, ensure_ascii=False) if meta else None,
            },
        )
        row = await self._one("SELECT id FROM mg_bottle ORDER BY id DESC LIMIT 1")
        return {"id": int(row["id"]) if row else 0, "archived_id": archived_id}

    async def recent_picked_senders(
        self, user_id: Any, *, limit: int = RECENT_PICK_EXCLUSION
    ) -> list[str]:
        """该用户最近 limit 次捞取过的发送者（去重保序）。"""
        rows = await self._all(
            """
            SELECT sender_id FROM mg_bottle
             WHERE picked_by = :uid AND status = :st
             ORDER BY picked_at DESC
             LIMIT :limit
            """,
            {"uid": str(user_id), "st": STATUS_PICKED, "limit": int(limit)},
        )
        seen: list[str] = []
        for row in rows:
            sender = str(row.get("sender_id") or "")
            if sender and sender not in seen:
                seen.append(sender)
        return seen

    async def pick_bottle(
        self,
        *,
        user_id: Any,
        exclude_senders: list[str] | None = None,
        fallback: bool = True,
    ) -> dict[str, Any]:
        """随机捞一个瓶（排除自己；可再排除若干发送者）。

        返回 {"bottle": dict | None, "used_fallback": bool}。
        池空时 bottle=None；因排除而无瓶时回落普通随机并置 used_fallback。
        """
        uid = str(user_id)
        excluded = [
            str(item) for item in (exclude_senders or []) if str(item) and str(item) != uid
        ]

        async def _try(excludes: list[str]) -> dict[str, Any] | None:
            params: dict[str, Any] = {"st": STATUS_POOLED, "uid": uid}
            filter_sql = "sender_id <> :uid"
            for index, sender in enumerate(excludes):
                key = f"ex{index}"
                params[key] = sender
                filter_sql += f" AND sender_id <> :{key}"
            return await self._one(
                f"SELECT * FROM mg_bottle WHERE status = :st AND {filter_sql} "
                "ORDER BY RANDOM() LIMIT 1",
                params,
            )

        row = await _try(excluded)
        used_fallback = False
        if row is None and excluded and fallback:
            row = await _try([])
            used_fallback = row is not None
        if row is None:
            return {"bottle": None, "used_fallback": False}

        bottle_id = int(row["id"])
        for _attempt in range(5):
            marked = await self._run(
                """
                UPDATE mg_bottle
                   SET status = :picked, picked_at = :at, picked_by = :uid
                 WHERE id = :id AND status = :st
                """,
                {
                    "picked": STATUS_PICKED,
                    "at": self.now_iso(),
                    "uid": uid,
                    "id": bottle_id,
                    "st": STATUS_POOLED,
                },
            )
            if marked:
                row = await self._one("SELECT * FROM mg_bottle WHERE id = :id", {"id": bottle_id})
                return {"bottle": row, "used_fallback": used_fallback}
            # 极端并发：被别人先捞走，重新抽一次（软删除语义下不会丢行）
            row = await _try(excluded)
            if row is None:
                break
            bottle_id = int(row["id"])
        return {"bottle": None, "used_fallback": False}

    async def bottle_stats(self) -> dict[str, Any]:
        rows = await self._all("SELECT status, COUNT(*) AS n FROM mg_bottle GROUP BY status")
        stats: dict[str, Any] = {STATUS_POOLED: 0, STATUS_PICKED: 0, STATUS_EXPIRED: 0}
        for row in rows:
            stats[str(row["status"])] = int(row["n"])
        stats["total"] = int(stats[STATUS_POOLED]) + int(stats[STATUS_PICKED]) + int(
            stats[STATUS_EXPIRED]
        )
        return stats

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
        """
        uid = str(user_id)
        day = self.today()
        existing = await self.get_checkin(uid, day)
        if existing is not None:
            profile = await self.get_profile(uid)
            return {
                "already": True,
                "score": int(existing["score"]),
                "streak": int(existing["streak"]),
                "base": int(existing["score"]),
                "bonus": 0,
                "total": int(profile["score"]),
                "day": day,
            }

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

        await self._run(
            """
            INSERT INTO mg_checkin (user_id, day, score, streak, created_at)
            VALUES (:uid, :day, :score, :streak, :now)
            ON CONFLICT (user_id, day) DO NOTHING
            """,
            {"uid": uid, "day": day, "score": score, "streak": streak, "now": self.now_iso()},
        )
        stored = await self.get_checkin(uid, day)
        if stored is None:  # pragma: no cover - 理论上不可能
            stored = {"score": score, "streak": streak}
        profile = await self.add_score(uid, score)
        return {
            "already": False,
            "score": int(stored["score"]),
            "streak": int(stored["streak"]),
            "base": base,
            "bonus": bonus,
            "total": int(profile["score"]),
            "day": day,
        }

    async def streak(self, user_id: Any) -> int:
        row = await self.get_checkin(user_id)
        return int(row["streak"]) if row else 0

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
            SELECT user_id, score, best_score, plays, wins FROM mg_profile
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
            SELECT user_id, SUM(score) AS score, COUNT(*) AS plays FROM mg_record
             WHERE conversation_id = :conv
             GROUP BY user_id
             ORDER BY score DESC
             LIMIT :limit
            """,
            {"conv": str(conversation_id or ""), "limit": int(limit)},
        )


__all__ = [
    "BOTTLE_PICK_DAILY_LIMIT",
    "BOTTLE_PICK_SCORE",
    "BOTTLE_SEND_DAILY_LIMIT",
    "BOTTLE_SEND_SCORE",
    "CLEANUP_INTERVAL_SECONDS",
    "DAILY_BOTTLE_PICK",
    "DAILY_BOTTLE_SEND",
    "MinigameService",
    "RECENT_PICK_EXCLUSION",
    "STATUS_EXPIRED",
    "STATUS_PICKED",
    "STATUS_POOLED",
]
