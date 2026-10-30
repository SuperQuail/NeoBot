"""聊天与面板共用的订阅业务，不承担调用入口的身份校验。"""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from sqlalchemy import select

from . import db

MAX_TARGET_LENGTH = 256
_DIGITS = re.compile("[0-9]+")


def parse_target(raw: str) -> tuple[str, int]:
    """识别房间号、直播链接、空间链接及 uid: 写法。"""
    text = (raw or "").strip()
    if not text or len(text) > MAX_TARGET_LENGTH:
        raise ValueError("目标不能为空或超过 256 个字符")
    lowered = text.lower()
    if "space.bilibili.com" in lowered or lowered.startswith("uid"):
        match = _DIGITS.search(text)
        if match is None:
            raise ValueError("没有从输入里找到 UID")
        return "uid", int(match.group(0))
    if "live.bilibili.com" in lowered:
        match = _DIGITS.search(text)
        if match is None:
            raise ValueError("没有从链接里找到房间号")
        return "room", int(match.group(0))
    if text.isdigit():
        return "room", int(text)
    raise ValueError("请提供房间号、短号、直播间链接或 UP 主空间链接")


async def push_defaults(state: Any, group_id: int) -> tuple[bool, bool]:
    """新增订阅优先采用群设置；重复订阅不会重置已有开关。"""
    async with state.database.session() as session:
        setting = db.setting_view(await db.get_group_setting(session, group_id))
    if setting is None:
        return bool(state.config.default_push_live), bool(
            state.config.default_push_live_end
        )
    return setting.default_push_live, setting.default_push_live_end


class SubscriptionService:
    """只处理解析、存储和状态，供不同权限入口复用。"""

    def __init__(self, state: Any) -> None:
        self.state = state

    async def resolve(self, target: str) -> dict[str, Any]:
        kind, value = parse_target(target)
        return await self.state.resolve_target(kind, value)

    async def create(
        self, group_id: int, target: str
    ) -> tuple[db.SubscriptionView, bool]:
        return await self.create_resolved(group_id, await self.resolve(target))

    async def create_resolved(
        self, group_id: int, resolved: dict[str, Any]
    ) -> tuple[db.SubscriptionView, bool]:
        push_live, push_live_end = await push_defaults(self.state, group_id)
        async with self.state.database.transaction() as session:
            row, created = await db.upsert_subscription(
                session,
                group_id=group_id,
                room_id=resolved["room_id"],
                short_id=resolved.get("short_id", 0),
                uid=resolved.get("uid", 0),
                name=resolved.get("name", ""),
                avatar_url=resolved.get("avatar_url", ""),
                push_live=push_live,
                push_live_end=push_live_end,
            )
            view = db.sub_view(row)
        if self.state.poller is not None:
            self.state.poller.request_check()
        return view, created

    async def remove(self, group_id: int, room_id: int) -> bool:
        async with self.state.database.transaction() as session:
            return await db.remove_subscription(session, group_id, room_id)

    async def toggle(
        self,
        group_id: int,
        room_id: int,
        *,
        push_live: bool | None = None,
        push_live_end: bool | None = None,
    ) -> db.SubscriptionView | None:
        async with self.state.database.transaction() as session:
            return db.sub_view(
                await db.set_subscription_flags(
                    session,
                    group_id,
                    room_id,
                    push_live=push_live,
                    push_live_end=push_live_end,
                )
            )

    async def list(self, group_id: int | None = None) -> list[dict[str, Any]]:
        query = (
            select(db.Subscription, db.RoomState)
            .outerjoin(
                db.RoomState,
                db.RoomState.room_id == db.Subscription.room_id,
            )
            .order_by(db.Subscription.group_id, db.Subscription.room_id)
        )
        if group_id is not None:
            query = query.where(db.Subscription.group_id == group_id)
        async with self.state.database.session() as session:
            records = await session.execute(query)
            return [
                {
                    **asdict(db.sub_view(row)),
                    "live_status": status.live_status if status is not None else None,
                    "checked_at": status.checked_at if status is not None else None,
                }
                for row, status in records
            ]

    async def health(self, group_id: int | None = None) -> dict[str, Any]:
        rows = await self.list(group_id)
        poller = self.state.poller
        task = self.state._task
        running = task is not None and not task.done()
        error = poller.last_error if poller is not None else "轮询器尚未装配"
        if not running:
            message = "轮询任务尚未运行，请先启动插件。"
        elif not rows:
            message = "尚未添加订阅，选择群并粘贴直播间链接即可开始。"
        elif error:
            message = "最近检查未全部成功，请查看错误并稍后重新检查。"
        elif any(row["checked_at"] is None for row in rows):
            message = "订阅已保存，正在等待首次直播间检查。"
        else:
            message = "正在监听，直播间状态变化后会按推送开关通知群。"
        return {
            "running": running,
            "subscriptions": len(rows),
            "watched_rooms": len({row["room_id"] for row in rows}),
            "checked_at": poller.last_finished_at if poller is not None else None,
            "success_at": poller.last_success_at if poller is not None else None,
            "checked": poller.last_stats.checked if poller is not None else 0,
            "failed": poller.last_stats.failed if poller is not None else 0,
            "error": error,
            "message": message,
        }

    async def ready(self) -> dict[str, Any]:
        health = await self.health()
        query = (
            select(db.Subscription.room_id)
            .join(
                db.RoomState,
                db.RoomState.room_id == db.Subscription.room_id,
            )
            .where(db.RoomState.checked_at >= db.Subscription.created_at)
            .limit(1)
        )
        async with self.state.database.session() as session:
            observed = await session.scalar(query)
        completed = bool(
            health["running"]
            and not health["error"]
            and health["success_at"] is not None
            and observed is not None
        )
        return {"completed": completed, "reason": health["message"]}
