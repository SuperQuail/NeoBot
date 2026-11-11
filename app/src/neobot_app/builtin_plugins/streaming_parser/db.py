"""数据表、迁移与仓储函数。

表结构：
- subscriptions：某个群订阅了哪个直播间，以及该直播间的推送开关；
- group_settings：每个群的卡片风格、AI 回复开关；
- room_states：每个直播间最近一次的直播状态（用于识别开播/下播跳变）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    select,
    text,
)
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from neobot_modloader import Migration

DATABASE_NAME = "main"
DATABASE_FILENAME = "streaming_parser.db"


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Subscription(Base):
    """群 -> 直播间 的订阅关系。"""

    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("group_id", "platform", "room_id", name="uq_subscription"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    #: 会话本地 ID：OneBot 是数字群号，官方通道是 openid 字符串（统一存 TEXT）。
    group_id: Mapped[str] = mapped_column(String(64), index=True)
    platform: Mapped[str] = mapped_column(String(32), default="bilibili")
    room_id: Mapped[int] = mapped_column(BigInteger, index=True)
    short_id: Mapped[int] = mapped_column(BigInteger, default=0)
    uid: Mapped[int] = mapped_column(BigInteger, default=0)
    name: Mapped[str] = mapped_column(String(128), default="")
    avatar_url: Mapped[str] = mapped_column(String(512), default="")
    push_live: Mapped[bool] = mapped_column(Boolean, default=True)
    push_live_end: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class GroupSetting(Base):
    """群级别的插件设置。"""

    __tablename__ = "group_settings"

    group_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    card_style: Mapped[str] = mapped_column(String(32), default="random")
    ai_reply_live: Mapped[bool] = mapped_column(Boolean, default=True)
    ai_reply_live_end: Mapped[bool] = mapped_column(Boolean, default=False)
    # 该群「新订阅」的默认推送开关
    default_push_live: Mapped[bool] = mapped_column(Boolean, default=True)
    default_push_live_end: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class RoomState(Base):
    """直播间最近一次观测到的状态，用来识别开播/下播跳变。"""

    __tablename__ = "room_states"

    room_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    live_status: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(256), default="")
    cover_url: Mapped[str] = mapped_column(String(512), default="")
    area_name: Mapped[str] = mapped_column(String(64), default="")
    online: Mapped[int] = mapped_column(Integer, default=0)
    live_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_live_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


async def _create_initial_schema(connection: AsyncConnection) -> None:
    await connection.run_sync(Base.metadata.create_all)


async def _group_id_as_text(connection: AsyncConnection) -> None:
    """v2：group_id 从 INTEGER 改成 TEXT，官方通道的 openid 才能落库。

    SQLite 不支持改列类型，只能重建表：创建新表 -> CAST 旧值 -> 换名。
    旧值仍是数字群号，CAST 成文本后与 OneBot 侧保持一致。
    """
    await connection.execute(
        text(
            """
            CREATE TABLE subscriptions_v2 (
                id INTEGER NOT NULL PRIMARY KEY,
                group_id VARCHAR(64) NOT NULL,
                platform VARCHAR(32) NOT NULL,
                room_id BIGINT NOT NULL,
                short_id BIGINT NOT NULL,
                uid BIGINT NOT NULL,
                name VARCHAR(128) NOT NULL,
                avatar_url VARCHAR(512) NOT NULL,
                push_live BOOLEAN NOT NULL,
                push_live_end BOOLEAN NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                CONSTRAINT uq_subscription UNIQUE (group_id, platform, room_id)
            )
            """
        )
    )
    await connection.execute(
        text(
            """
            INSERT INTO subscriptions_v2 (
                id, group_id, platform, room_id, short_id, uid, name,
                avatar_url, push_live, push_live_end, created_at, updated_at
            )
            SELECT
                id, CAST(group_id AS TEXT), platform, room_id, short_id, uid, name,
                avatar_url, push_live, push_live_end, created_at, updated_at
            FROM subscriptions
            """
        )
    )
    await connection.execute(text("DROP TABLE subscriptions"))
    await connection.execute(text("ALTER TABLE subscriptions_v2 RENAME TO subscriptions"))
    await connection.execute(
        text("CREATE INDEX IF NOT EXISTS ix_subscriptions_group_id ON subscriptions (group_id)")
    )
    await connection.execute(
        text("CREATE INDEX IF NOT EXISTS ix_subscriptions_room_id ON subscriptions (room_id)")
    )
    await connection.execute(
        text(
            """
            CREATE TABLE group_settings_v2 (
                group_id VARCHAR(64) NOT NULL PRIMARY KEY,
                card_style VARCHAR(32) NOT NULL,
                ai_reply_live BOOLEAN NOT NULL,
                ai_reply_live_end BOOLEAN NOT NULL,
                default_push_live BOOLEAN NOT NULL,
                default_push_live_end BOOLEAN NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )
    )
    await connection.execute(
        text(
            """
            INSERT INTO group_settings_v2 (
                group_id, card_style, ai_reply_live, ai_reply_live_end,
                default_push_live, default_push_live_end, updated_at
            )
            SELECT
                CAST(group_id AS TEXT), card_style, ai_reply_live, ai_reply_live_end,
                default_push_live, default_push_live_end, updated_at
            FROM group_settings
            """
        )
    )
    await connection.execute(text("DROP TABLE group_settings"))
    await connection.execute(text("ALTER TABLE group_settings_v2 RENAME TO group_settings"))


MIGRATIONS: list[Migration] = [
    Migration(version=1, name="initial-schema", upgrade=_create_initial_schema),
    Migration(version=2, name="group-id-as-text", upgrade=_group_id_as_text),
]


@dataclass(frozen=True)
class SubscriptionView:
    """订阅的只读快照。

    为什么需要它：PluginDatabase 的 transaction() 退出时会 commit，SQLAlchemy 会把 ORM 实例
    标记为 expired；会话关闭后再读属性会抛 DetachedInstanceError。所有跨会话边界的读取
    都必须先在会话内把值拷成这样的纯数据对象。
    """

    group_id: str
    room_id: int
    uid: int = 0
    short_id: int = 0
    name: str = ""
    avatar_url: str = ""
    push_live: bool = True
    push_live_end: bool = False


@dataclass(frozen=True)
class GroupSettingView:
    """群设置的只读快照。"""

    group_id: str
    card_style: str = "random"
    ai_reply_live: bool = True
    ai_reply_live_end: bool = False
    default_push_live: bool = True
    default_push_live_end: bool = False


@dataclass(frozen=True)
class RoomStateView:
    """直播间状态的只读快照。"""

    room_id: int
    live_status: int = 0
    title: str = ""
    cover_url: str = ""
    area_name: str = ""
    online: int = 0


def _group_id_text(value: Any) -> str:
    """群会话 ID 统一存文本：int 群号 -> "123"，官方 openid 原样。"""
    return str(value if value is not None else "").strip()


def sub_view(row: Subscription | None) -> SubscriptionView | None:
    """Subscription -> 纯数据快照（必须在会话内调用）。"""
    if row is None:
        return None
    return SubscriptionView(
        group_id=_group_id_text(row.group_id),
        room_id=int(row.room_id),
        uid=int(row.uid or 0),
        short_id=int(row.short_id or 0),
        name=str(row.name or ""),
        avatar_url=str(row.avatar_url or ""),
        push_live=bool(row.push_live),
        push_live_end=bool(row.push_live_end),
    )


def setting_view(row: GroupSetting | None) -> GroupSettingView | None:
    """GroupSetting -> 纯数据快照（必须在会话内调用）。"""
    if row is None:
        return None
    return GroupSettingView(
        group_id=_group_id_text(row.group_id),
        card_style=str(row.card_style or "random"),
        ai_reply_live=bool(row.ai_reply_live),
        ai_reply_live_end=bool(row.ai_reply_live_end),
        default_push_live=bool(row.default_push_live),
        default_push_live_end=bool(row.default_push_live_end),
    )


def room_view(row: RoomState | None) -> RoomStateView | None:
    """RoomState -> 纯数据快照（必须在会话内调用）。"""
    if row is None:
        return None
    return RoomStateView(
        room_id=int(row.room_id),
        live_status=int(row.live_status or 0),
        title=str(row.title or ""),
        cover_url=str(row.cover_url or ""),
        area_name=str(row.area_name or ""),
        online=int(row.online or 0),
    )


# ── 仓储函数 ──────────────────────────────────────────────────────────────


async def list_group_subscriptions(session: AsyncSession, group_id: int | str) -> list[Subscription]:
    result = await session.scalars(
        select(Subscription)
        .where(Subscription.group_id == _group_id_text(group_id))
        .order_by(Subscription.room_id)
    )
    return list(result)


async def get_subscription(
    session: AsyncSession, group_id: int | str, room_id: int
) -> Subscription | None:
    return await session.scalar(
        select(Subscription).where(
            Subscription.group_id == _group_id_text(group_id),
            Subscription.room_id == int(room_id),
            Subscription.platform == "bilibili",
        )
    )


async def upsert_subscription(
    session: AsyncSession,
    *,
    group_id: int | str,
    room_id: int,
    short_id: int = 0,
    uid: int = 0,
    name: str = "",
    avatar_url: str = "",
    push_live: bool = True,
    push_live_end: bool = False,
) -> tuple[Subscription, bool]:
    """新增或更新订阅；返回 (订阅, 是否新建)。"""
    existing = await get_subscription(session, group_id, room_id)
    if existing is not None:
        existing.short_id = short_id or existing.short_id
        existing.uid = uid or existing.uid
        existing.name = name or existing.name
        existing.avatar_url = avatar_url or existing.avatar_url
        existing.updated_at = _now()
        return existing, False
    row = Subscription(
        group_id=_group_id_text(group_id),
        platform="bilibili",
        room_id=int(room_id),
        short_id=int(short_id or 0),
        uid=int(uid or 0),
        name=name,
        avatar_url=avatar_url,
        push_live=bool(push_live),
        push_live_end=bool(push_live_end),
    )
    session.add(row)
    return row, True


async def remove_subscription(session: AsyncSession, group_id: int | str, room_id: int) -> bool:
    row = await get_subscription(session, group_id, room_id)
    if row is None:
        return False
    await session.delete(row)
    return True


async def set_subscription_flags(
    session: AsyncSession,
    group_id: int | str,
    room_id: int,
    *,
    push_live: bool | None = None,
    push_live_end: bool | None = None,
) -> Subscription | None:
    row = await get_subscription(session, group_id, room_id)
    if row is None:
        return None
    if push_live is not None:
        row.push_live = bool(push_live)
    if push_live_end is not None:
        row.push_live_end = bool(push_live_end)
    row.updated_at = _now()
    return row


async def get_group_setting(session: AsyncSession, group_id: int | str) -> GroupSetting | None:
    return await session.get(GroupSetting, _group_id_text(group_id))


async def ensure_group_setting(
    session: AsyncSession, group_id: int | str, defaults: dict[str, Any] | None = None
) -> GroupSetting:
    row = await session.get(GroupSetting, _group_id_text(group_id))
    if row is not None:
        return row
    defaults = defaults or {}
    row = GroupSetting(
        group_id=_group_id_text(group_id),
        card_style=str(defaults.get("card_style", "random")),
        ai_reply_live=bool(defaults.get("ai_reply_live", True)),
        ai_reply_live_end=bool(defaults.get("ai_reply_live_end", False)),
        default_push_live=bool(defaults.get("default_push_live", True)),
        default_push_live_end=bool(defaults.get("default_push_live_end", False)),
    )
    session.add(row)
    return row


async def distinct_room_ids(session: AsyncSession) -> list[int]:
    """所有被监听的直播间（跨群去重），轮询只需要这些。"""
    result = await session.scalars(
        select(Subscription.room_id).distinct().order_by(Subscription.room_id)
    )
    return [int(item) for item in result]


async def followers_of_room(session: AsyncSession, room_id: int) -> list[Subscription]:
    result = await session.scalars(
        select(Subscription).where(Subscription.room_id == int(room_id))
    )
    return list(result)


async def get_room_state(session: AsyncSession, room_id: int) -> RoomState | None:
    return await session.get(RoomState, int(room_id))


async def upsert_room_state(
    session: AsyncSession,
    room_id: int,
    *,
    live_status: int,
    title: str = "",
    cover_url: str = "",
    area_name: str = "",
    online: int = 0,
    live_time: datetime | None = None,
) -> RoomState:
    row = await session.get(RoomState, int(room_id))
    if row is None:
        row = RoomState(room_id=int(room_id))
        session.add(row)
    row.live_status = int(live_status)
    row.title = title or row.title
    row.cover_url = cover_url or row.cover_url
    row.area_name = area_name or row.area_name
    row.online = int(online or 0)
    if live_time is not None:
        row.live_time = live_time
    row.checked_at = _now()
    return row

