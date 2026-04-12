"""SQLAlchemy ORM models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserData(Base):
    __tablename__ = "user_data"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    nick_name: Mapped[str | None] = mapped_column(Text)
    relation_ship: Mapped[str | None] = mapped_column(Text)
    profile: Mapped[str | None] = mapped_column(Text)
    known_gender: Mapped[str | None] = mapped_column(Text)
    birthday: Mapped[str | None] = mapped_column(Text)
    sex: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)
    labs: Mapped[str | None] = mapped_column(Text)
    remark: Mapped[str | None] = mapped_column(Text)
    age: Mapped[int | None] = mapped_column(Integer)
    long_nick: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GroupData(Base):
    __tablename__ = "group_data"

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
    __tablename__ = "event_data"

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


class ArchiveMemoryData(Base):
    __tablename__ = "archive_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    table_name: Mapped[str] = mapped_column(String, nullable=False)
    key: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[str | None] = mapped_column(Text)  # 逗号分隔的标签
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # 在表名和键上创建唯一约束
    __table_args__ = (
        UniqueConstraint("table_name", "key", name="uq_archive_memories_table_key"),
        Index("ix_archive_memories_table_name_updated_at", "table_name", "updated_at"),
    )


class ImageAnalysisData(Base):
    __tablename__ = "images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    source: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(String)
    original_width: Mapped[int | None] = mapped_column(Integer)
    original_height: Mapped[int | None] = mapped_column(Integer)
    processed_width: Mapped[int | None] = mapped_column(Integer)
    processed_height: Mapped[int | None] = mapped_column(Integer)
    analysis_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        Index("ix_images_updated_at", "updated_at"),
        Index("ix_images_source", "source"),
    )
