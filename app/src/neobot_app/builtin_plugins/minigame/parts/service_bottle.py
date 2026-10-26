"""漂流瓶：每日名额、发瓶/捞瓶与瓶池统计。"""

from __future__ import annotations

import json
from typing import Any

from .service_constants import RECENT_PICK_EXCLUSION, STATUS_EXPIRED, STATUS_PICKED, STATUS_POOLED


class _ServiceBottleMixin:
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
