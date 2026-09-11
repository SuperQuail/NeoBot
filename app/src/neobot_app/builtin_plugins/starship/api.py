"""星舰游戏 HTTP 接口（挂在面板端口下，路径为 {prefix}/api/...）。

面板自身的 /api/* 仍然由面板提供，游戏终端直接复用它们；这里只提供游戏特有
的数据：舰船状态、小游戏目录、排行榜与成就。
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from aiohttp import web
from sqlalchemy import delete, func, select

from . import minigames as minigames_module
from .models import AchievementRecord, ScoreRecord

#: 昵称长度上限
PLAYER_NAME_LIMIT = 32


def _json_ok(data: Any = None) -> web.Response:
    payload: dict[str, Any] = {"ok": True}
    if isinstance(data, dict):
        payload.update(data)
    elif data is not None:
        payload["data"] = data
    return web.json_response(payload)


def _json_error(message: str, *, status: int = 400, **extra: Any) -> web.Response:
    return web.json_response({"ok": False, "error": message, **extra}, status=status)


def _clean_player(value: Any) -> str:
    text = str(value or "").strip()
    text = "".join(char for char in text if char.isprintable())
    return text[:PLAYER_NAME_LIMIT] or "舰长"


class StarshipApi:
    """星舰接口实现。"""

    def __init__(
        self,
        *,
        config: Any,
        database: Any,
        logger: Any,
        services: Any = None,
        plugin_control: Any = None,
        adapter: Any = None,
        started_at: float | None = None,
    ) -> None:
        self.config = config
        self.database = database
        self.logger = logger
        self.services = services
        self.plugin_control = plugin_control
        self.adapter = adapter
        self.started_at = started_at or time.time()

    # ------------------------------------------------------------------
    # 基础信息
    # ------------------------------------------------------------------

    async def bootstrap(self, request: web.Request, *, base: str = "") -> web.Response:
        """一次拿全游戏启动所需的配置（游戏页面只调用一次）。"""
        return _json_ok(
            {
                "title": self.config.title,
                "prefix": self.config.prefix,
                "panel_base": base,
                "quality": self.config.default_quality,
                "allow_minigames": self.config.allow_minigames,
                "enable_audio": self.config.enable_audio,
                "jump_interval_minutes": self.config.jump_interval_minutes,
                "leaderboard_size": self.config.leaderboard_size,
                "minigames": minigames_module.registry.catalog(),
                "version": "1.0.0",
                "server_time": datetime.now(timezone.utc).isoformat(),
            }
        )

    def _service(self, name: str) -> Any:
        registry = self.services
        if registry is None:
            return None
        getter = getattr(registry, "get", None)
        if not callable(getter):
            return None
        try:
            return getter(name)
        except Exception:
            return None

    def power_state(self) -> dict[str, Any]:
        """运行状态（待机 / 运行中）——与面板 /api/admin/power 同源。"""
        service = self._service("standby_service")
        if service is None:
            return {"available": False, "state": "running", "standby": False}
        try:
            status = dict(service.status())
        except Exception:
            return {"available": False, "state": "running", "standby": False}
        status["available"] = True
        return status

    def plugin_summary(self) -> dict[str, int]:
        control = self.plugin_control
        if control is None:
            return {"total": 0, "running": 0, "error": 0}
        try:
            snapshots = list(control.snapshot())
        except Exception:
            return {"total": 0, "running": 0, "error": 0}
        return {
            "total": len(snapshots),
            "running": sum(1 for item in snapshots if item.state == "running"),
            "error": sum(1 for item in snapshots if item.state == "error"),
        }

    async def status(self, request: web.Request) -> web.Response:
        """舰船状态：待机 / 运行、在位插件、连接情况与运行时长。

        游戏 HUD 与「舰桥主控台」用它决定全舰供电状态：待机时舰船进入低功耗，
        大部分终端不可用（游戏内表现为熄屏 + STANDBY 提示）。
        """
        power = self.power_state()
        adapter = self.adapter
        online = bool(getattr(adapter, "connected", False)) if adapter is not None else False
        return _json_ok(
            {
                "standby": bool(power.get("standby")),
                "power_state": str(power.get("state") or "running"),
                "power_available": bool(power.get("available")),
                "reason": power.get("reason"),
                "operator": power.get("operator"),
                "since_text": power.get("since_text"),
                "standby_seconds": power.get("standby_seconds"),
                "connect_onebot": power.get("connect_onebot"),
                "online": online,
                "plugins": self.plugin_summary(),
                "uptime_seconds": int(max(0.0, time.time() - self.started_at)),
                "now": datetime.now(timezone.utc).isoformat(),
            }
        )

    async def minigames(self, request: web.Request) -> web.Response:
        return _json_ok({"items": minigames_module.registry.catalog()})

    # ------------------------------------------------------------------
    # 排行榜 / 成就
    # ------------------------------------------------------------------

    async def scores(self, request: web.Request) -> web.Response:
        game_id = str(request.query.get("game") or "").strip()
        try:
            limit = int(request.query.get("limit") or self.config.leaderboard_size)
        except ValueError:
            limit = self.config.leaderboard_size
        limit = max(1, min(limit, 100))
        spec = minigames_module.registry.get(game_id)
        if game_id and spec is None:
            return _json_error(f"未知的小游戏: {game_id}", status=404)
        try:
            async with self.database.session() as session:
                statement = select(ScoreRecord)
                if game_id:
                    statement = statement.where(ScoreRecord.game == game_id)
                order = (
                    ScoreRecord.score.desc()
                    if spec is None or spec.higher_is_better
                    else ScoreRecord.score.asc()
                )
                statement = statement.order_by(order, ScoreRecord.created_at.asc()).limit(limit)
                rows = list(await session.scalars(statement))
                totals = dict(
                    (
                        await session.execute(
                            select(ScoreRecord.game, func.count(ScoreRecord.id)).group_by(
                                ScoreRecord.game
                            )
                        )
                    ).all()
                )
        except Exception as exc:
            self.logger.warning(f"读取星舰排行榜失败: {exc}")
            return _json_error("读取排行榜失败", status=500)
        return _json_ok(
            {
                "game": game_id or None,
                "items": [self._score_payload(row) for row in rows],
                "totals": {str(key): int(value) for key, value in totals.items()},
            }
        )

    @staticmethod
    def _score_payload(row: ScoreRecord) -> dict[str, Any]:
        created = row.created_at
        if isinstance(created, datetime) and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return {
            "id": row.id,
            "game": row.game,
            "score": int(row.score),
            "duration_ms": int(row.duration_ms),
            "player": row.player,
            "detail": row.detail,
            "created_at": created.isoformat() if isinstance(created, datetime) else "",
        }

    async def submit_score(self, request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except Exception as exc:
            return _json_error(f"请求体不是有效 JSON: {exc}", status=400)
        if not isinstance(payload, dict):
            return _json_error("请求体必须是 JSON 对象", status=400)
        game_id = str(payload.get("game") or "").strip()
        try:
            score = minigames_module.registry.validate_score(game_id, payload.get("score"))
        except ValueError as exc:
            return _json_error(str(exc), status=400)
        try:
            duration = max(0, min(int(payload.get("duration_ms") or 0), 24 * 3600 * 1000))
        except (TypeError, ValueError):
            duration = 0
        detail = str(payload.get("detail") or "")[:512]
        player = _clean_player(payload.get("player"))
        record = ScoreRecord(
            game=game_id,
            score=score,
            duration_ms=duration,
            player=player,
            detail=detail,
        )
        try:
            async with self.database.transaction() as session:
                session.add(record)
            async with self.database.session() as session:
                best = await session.scalar(
                    select(func.max(ScoreRecord.score)).where(ScoreRecord.game == game_id)
                )
                rank = await session.scalar(
                    select(func.count(ScoreRecord.id)).where(
                        ScoreRecord.game == game_id, ScoreRecord.score > score
                    )
                )
        except Exception as exc:
            self.logger.warning(f"星舰成绩写入失败: {exc}")
            return _json_error("成绩保存失败", status=500)
        return _json_ok(
            {
                "saved": True,
                "best": int(best or 0),
                "rank": int(rank or 0) + 1,
                "score": score,
                "player": player,
            }
        )

    async def achievements(self, request: web.Request) -> web.Response:
        try:
            async with self.database.session() as session:
                rows = list(
                    await session.scalars(
                        select(AchievementRecord).order_by(AchievementRecord.last_at.desc())
                    )
                )
        except Exception as exc:
            self.logger.warning(f"读取星舰成就失败: {exc}")
            return _json_error("读取成就失败", status=500)
        return _json_ok(
            {
                "items": [
                    {
                        "key": row.key,
                        "count": int(row.count),
                        "detail": row.detail,
                        "first_at": row.first_at.isoformat() if row.first_at else "",
                        "last_at": row.last_at.isoformat() if row.last_at else "",
                    }
                    for row in rows
                ]
            }
        )

    async def unlock(self, request: web.Request) -> web.Response:
        """解锁 / 累加一个成就（游戏内里程碑，例如首次跃迁、击毁 100 个小行星）。"""
        try:
            payload = await request.json()
        except Exception as exc:
            return _json_error(f"请求体不是有效 JSON: {exc}", status=400)
        if not isinstance(payload, dict):
            return _json_error("请求体必须是 JSON 对象", status=400)
        key = str(payload.get("key") or "").strip()[:64]
        if not key:
            return _json_error("缺少成就标识", status=400)
        detail = str(payload.get("detail") or "")[:256]
        now = datetime.now(timezone.utc)
        try:
            async with self.database.transaction() as session:
                row = await session.get(AchievementRecord, key)
                if row is None:
                    row = AchievementRecord(
                        key=key, count=1, first_at=now, last_at=now, detail=detail
                    )
                    session.add(row)
                else:
                    row.count = int(row.count) + 1
                    row.last_at = now
                    if detail:
                        row.detail = detail
            async with self.database.session() as session:
                total = await session.scalar(select(func.count()).select_from(AchievementRecord))
        except Exception as exc:
            self.logger.warning(f"星舰成就写入失败: {exc}")
            return _json_error("成就保存失败", status=500)
        return _json_ok({"unlocked": True, "key": key, "total": int(total or 0)})

    async def reset_scores(self, request: web.Request) -> web.Response:
        """清空排行榜（面板管理员操作；游戏内需要二次确认）。"""
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        game_id = str((payload or {}).get("game") or "").strip()
        try:
            async with self.database.transaction() as session:
                statement = delete(ScoreRecord)
                if game_id:
                    statement = statement.where(ScoreRecord.game == game_id)
                await session.execute(statement)
        except Exception as exc:
            self.logger.warning(f"清空星舰排行榜失败: {exc}")
            return _json_error("清空失败", status=500)
        return _json_ok({"cleared": True, "game": game_id or None})


__all__ = ["StarshipApi"]
