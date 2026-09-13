"""小游戏插件独立数据库模型（spec(5) §4.4 的六张表）。

表结构以 :mod:`.migrations` 的 DDL 为准（迁移随插件走，不动本体迁移）；
本模块用 SQLAlchemy 声明同一份结构，供 ORM 风格读取与结构一致性测试使用。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Profile(Base):
    """统一积分账户与战绩（与 mg_record 的聚合口径一致）。"""

    __tablename__ = "mg_profile"

    user_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    score: Mapped[int] = mapped_column(Integer, default=0)
    best_score: Mapped[int] = mapped_column(Integer, default=0)
    plays: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Bottle(Base):
    """漂流瓶：瓶池与瓶档同表（status 区分 pooled / picked / expired）。"""

    __tablename__ = "mg_bottle"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sender_id: Mapped[str] = mapped_column(String(32), default="")
    sender_name: Mapped[str] = mapped_column(String(128), default="")
    sender_avatar: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    anonymous: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    picked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    picked_by: Mapped[str] = mapped_column(String(32), default="")
    status: Mapped[str] = mapped_column(String(16), default="pooled")
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Daily(Base):
    """每日次数上限（game_id 形如 bottle:send / bottle:pick）。"""

    __tablename__ = "mg_daily"

    user_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    game_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    plays: Mapped[int] = mapped_column(Integer, default=0)


class Checkin(Base):
    """签到与连续天数。"""

    __tablename__ = "mg_checkin"

    user_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    score: Mapped[int] = mapped_column(Integer, default=0)
    streak: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Fortune(Base):
    """每日抽签结果（user_id + day 联合主键 => 当日幂等）。"""

    __tablename__ = "mg_fortune"

    user_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    result_key: Mapped[str] = mapped_column(String(32), default="")
    result_text: Mapped[str] = mapped_column(Text, default="")
    drawn_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Record(Base):
    """战绩流水（审计与排行榜；按 record_keep_days 清理）。"""

    __tablename__ = "mg_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(32), default="")
    game_id: Mapped[str] = mapped_column(String(32), default="")
    score: Mapped[int] = mapped_column(Integer, default=0)
    conversation_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


#: 表名 -> 模型（结构一致性测试与文档使用）
TABLES: dict[str, type[Base]] = {
    "mg_profile": Profile,
    "mg_bottle": Bottle,
    "mg_daily": Daily,
    "mg_checkin": Checkin,
    "mg_fortune": Fortune,
    "mg_record": Record,
}


__all__ = [
    "Base",
    "Bottle",
    "Checkin",
    "Daily",
    "Fortune",
    "Profile",
    "Record",
    "TABLES",
]
