"""SQLAlchemy ORM models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserData(Base):
    __tablename__ = "USER_DATA"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    nick_name: Mapped[str | None] = mapped_column(Text)
    relation_ship: Mapped[str | None] = mapped_column(Text)
    profile: Mapped[str | None] = mapped_column(Text)
    birthday: Mapped[str | None] = mapped_column(Text)
    sex: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)
    labs: Mapped[str | None] = mapped_column(Text)
    remark: Mapped[str | None] = mapped_column(Text)
    age: Mapped[int | None] = mapped_column(Integer)
    long_nick: Mapped[str | None] = mapped_column(Text)


class GroupData(Base):
    __tablename__ = "GROUP_DATA"

    group_id: Mapped[str] = mapped_column(String, primary_key=True)
    group_name: Mapped[str | None] = mapped_column(Text)
    profile: Mapped[str | None] = mapped_column(Text)
    is_quite: Mapped[bool] = mapped_column(Boolean, default=False)


class MessageData(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    conversation_kind: Mapped[str] = mapped_column(String, nullable=False)  # "private" | "group"
    conversation_id: Mapped[str] = mapped_column(String, nullable=False)
    sender_id: Mapped[str] = mapped_column(String, nullable=False)
    sender_name: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class EventData(Base):
    __tablename__ = "EVENT_DATA"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    event_message: Mapped[str | None] = mapped_column(Text)
    embedded_data: Mapped[str | None] = mapped_column(Text)


class MemoryData(Base):
    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_kind: Mapped[str] = mapped_column(String, nullable=False)
    conversation_id: Mapped[str] = mapped_column(String, nullable=False)
    speaker_id: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
