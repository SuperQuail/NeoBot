"""星舰插件独立数据库模型（成绩、成就、航行记录）。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class ScoreRecord(Base):
    """一条小游戏成绩。"""

    __tablename__ = "starship_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game: Mapped[str] = mapped_column(String(64), index=True)
    score: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    player: Mapped[str] = mapped_column(String(64), default="")
    user_id: Mapped[str] = mapped_column(String(32), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )


class AchievementRecord(Base):
    """舰船成就 / 统计计数（按 key 唯一，重复解锁只累加计数）。"""

    __tablename__ = "starship_achievements"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    first_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    detail: Mapped[str] = mapped_column(Text, default="")
