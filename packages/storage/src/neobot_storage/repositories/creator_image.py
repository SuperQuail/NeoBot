"""SqlAlchemy 创作者图片仓库。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import case, delete as sql_delete, func, or_, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from neobot_contracts.models.memory import CreatorImageRecord
from neobot_contracts.time_context import now_utc, to_utc
from neobot_contracts.ports.creator_image_access import CreatorImageAccess

from neobot_storage.models import CreatorImageData, CreatorImageSequenceData

#: 图库编号的序列键（只有 source=gallery 的记录参与编号）
GALLERY_SEQUENCE_NAME = "gallery"


class SqlAlchemyCreatorImageAccess:
    """CreatorImageAccess 协议的 SqlAlchemy 实现。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, image_id: str) -> Optional[CreatorImageRecord]:
        row = await self._get_optional_row(image_id)
        if row is None:
            return None
        return self._to_domain(row)

    async def get_by_hash(self, file_hash: str) -> Optional[CreatorImageRecord]:
        stmt = select(CreatorImageData).where(CreatorImageData.file_hash == file_hash)
        result = await self._session.execute(stmt)
        row = result.scalars().first()
        if row is None:
            return None
        return self._to_domain(row)

    async def get_by_gallery_no(self, gallery_no: int) -> Optional[CreatorImageRecord]:
        stmt = select(CreatorImageData).where(CreatorImageData.gallery_no == gallery_no)
        result = await self._session.execute(stmt)
        row = result.scalars().first()
        if row is None:
            return None
        return self._to_domain(row)

    async def set(
        self,
        image_id: str,
        *,
        source: str,
        file_hash: str,
        file_path: str,
        prompt: Optional[str] = None,
        description: Optional[str] = None,
        mime_type: Optional[str] = None,
        original_width: Optional[int] = None,
        original_height: Optional[int] = None,
        image_source: Optional[str] = None,
        gallery_no: Optional[int] = None,
    ) -> CreatorImageRecord:
        now = now_utc()

        if self._session.bind is not None and self._session.bind.dialect.name == "sqlite":
            stmt = sqlite_insert(CreatorImageData).values(
                image_id=image_id,
                source=source,
                file_hash=file_hash,
                file_path=file_path,
                prompt=prompt,
                description=description,
                mime_type=mime_type,
                original_width=original_width,
                original_height=original_height,
                image_source=image_source,
                gallery_no=gallery_no,
                created_at=now,
                updated_at=now,
                version=1,
            )
            # 更新只在当前编号为空时补号（迁移前遗留/外部导入的图），
            # 已分配的编号不会被覆盖——编号一旦确定就固定。
            stmt = stmt.on_conflict_do_update(
                index_elements=["image_id"],
                set_={
                    "gallery_no": case(
                        (CreatorImageData.gallery_no.is_(None), gallery_no),
                        else_=CreatorImageData.gallery_no,
                    ),
                    "source": source,
                    "file_hash": file_hash,
                    "file_path": file_path,
                    "prompt": prompt,
                    "description": description,
                    "mime_type": mime_type,
                    "original_width": original_width,
                    "original_height": original_height,
                    "image_source": image_source,
                    "updated_at": now,
                    "version": CreatorImageData.version + 1,
                },
            )
            await self._session.execute(stmt)
            row = await self._get_row(image_id)
        else:
            row = await self._get_optional_row(image_id)
            if row is None:
                row = CreatorImageData(
                    image_id=image_id,
                    source=source,
                    file_hash=file_hash,
                    file_path=file_path,
                    prompt=prompt,
                    description=description,
                    mime_type=mime_type,
                    original_width=original_width,
                    original_height=original_height,
                    image_source=image_source,
                    gallery_no=gallery_no,
                    created_at=now,
                    updated_at=now,
                    version=1,
                )
                self._session.add(row)
            else:
                row.source = source
                row.file_hash = file_hash
                row.file_path = file_path
                row.prompt = prompt
                row.description = description
                row.mime_type = mime_type
                row.original_width = original_width
                row.original_height = original_height
                row.image_source = image_source
                if row.gallery_no is None and gallery_no is not None:
                    # 只为历史遗留（编号为空）的记录补号，已分配的编号不动
                    row.gallery_no = gallery_no
                row.updated_at = now
                row.version += 1

        await self._session.flush()
        return self._to_domain(row)

    async def delete(self, image_id: str) -> bool:
        row = await self._get_optional_row(image_id)
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True

    async def delete_by_source(self, source: str) -> int:
        stmt = sql_delete(CreatorImageData).where(CreatorImageData.source == source)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount

    async def rename(self, image_id: str, new_file_path: str) -> CreatorImageRecord:
        row = await self._get_optional_row(image_id)
        if row is None:
            raise LookupError(f"creator image not found for image_id={image_id}")
        row.file_path = new_file_path
        row.updated_at = now_utc()
        row.version += 1
        await self._session.flush()
        return self._to_domain(row)

    async def count(self, *, source: Optional[str] = None) -> int:
        stmt = select(func.count()).select_from(CreatorImageData)
        if source is not None:
            stmt = stmt.where(CreatorImageData.source == source)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def allocate_gallery_no(self) -> int:
        """分配下一个图库编号：持久化高水位 + 1。

        - 删除不回收：已分配过的编号永不再次发出，历史引用不会指到新图片；
        - 并发安全：单条 UPDATE ... RETURNING / UPDATE + SELECT 原子自增，
          不再出现"两个事务读到同一个 MAX 后撞唯一索引"；
        - 必须与 set() 在同一个 UnitOfWork 事务内调用：事务回滚会浪费一个号
          （允许空洞），但不会发出重号。

        （SQLite < 3.35 不支持 RETURNING 时退回同事务内的 UPDATE + SELECT，
        UPDATE 已持有写锁，读到的是本事务刚写入的值。）
        """
        await self._ensure_gallery_sequence()
        statement = (
            update(CreatorImageSequenceData)
            .where(CreatorImageSequenceData.name == GALLERY_SEQUENCE_NAME)
            .values(last_no=CreatorImageSequenceData.last_no + 1)
        )
        if self._dialect_name() == "sqlite" and not self._sqlite_supports_returning():
            await self._session.execute(statement)
            result = await self._session.execute(
                select(CreatorImageSequenceData.last_no).where(
                    CreatorImageSequenceData.name == GALLERY_SEQUENCE_NAME
                )
            )
            return int(result.scalar_one())
        result = await self._session.execute(
            statement.returning(CreatorImageSequenceData.last_no)
        )
        return int(result.scalar_one())

    async def _ensure_gallery_sequence(self) -> None:
        """保证序列行存在；缺失时以现有最大编号为高水位回填。

        生产路径由迁移 0024 建立并回填；这里同时兼容直接用 metadata.create_all
        建库的测试/全新库。并发首次调用由 ON CONFLICT DO NOTHING / savepoint
        兜底，不会写出两条序列行。
        """
        seed = select(func.coalesce(func.max(CreatorImageData.gallery_no), 0)).scalar_subquery()
        if self._dialect_name() == "sqlite":
            statement = (
                sqlite_insert(CreatorImageSequenceData)
                .values(name=GALLERY_SEQUENCE_NAME, last_no=seed)
                .on_conflict_do_nothing(index_elements=["name"])
            )
            await self._session.execute(statement)
            return
        if await self._session.get(CreatorImageSequenceData, GALLERY_SEQUENCE_NAME) is not None:
            return
        current = await self._session.execute(
            select(func.coalesce(func.max(CreatorImageData.gallery_no), 0))
        )
        row = CreatorImageSequenceData(
            name=GALLERY_SEQUENCE_NAME, last_no=int(current.scalar_one())
        )
        try:
            async with self._session.begin_nested():
                self._session.add(row)
        except IntegrityError:
            # 并发首次分配：另一事务已建行，使用它的高水位
            pass

    def _dialect_name(self) -> str:
        bind = self._session.bind
        return bind.dialect.name if bind is not None else ""

    def _sqlite_supports_returning(self) -> bool:
        bind = self._session.bind
        version = getattr(bind.dialect, "server_version_info", None) if bind is not None else None
        return bool(version and version >= (3, 35))

    async def list(
        self,
        *,
        source: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CreatorImageRecord]:
        stmt = select(CreatorImageData)
        if source is not None:
            stmt = stmt.where(CreatorImageData.source == source)
        stmt = (
            stmt.order_by(CreatorImageData.updated_at.desc(), CreatorImageData.id.desc())
            .offset(max(offset, 0))
            .limit(max(limit, 0))
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars().all()]

    async def search(
        self,
        keyword: str,
        *,
        source: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CreatorImageRecord]:
        pattern = f"%{keyword}%"
        stmt = select(CreatorImageData).where(
            or_(
                CreatorImageData.description.like(pattern),
                CreatorImageData.prompt.like(pattern),
            )
        )
        if source is not None:
            stmt = stmt.where(CreatorImageData.source == source)
        stmt = (
            stmt.order_by(CreatorImageData.updated_at.desc(), CreatorImageData.id.desc())
            .offset(max(offset, 0))
            .limit(max(limit, 0))
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars().all()]

    async def _get_optional_row(self, image_id: str) -> Optional[CreatorImageData]:
        stmt = select(CreatorImageData).where(CreatorImageData.image_id == image_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_row(self, image_id: str) -> CreatorImageData:
        row = await self._get_optional_row(image_id)
        if row is None:
            raise LookupError(f"creator image entry not found for image_id={image_id}")
        return row

    @staticmethod
    def _to_domain(row: CreatorImageData) -> CreatorImageRecord:
        return CreatorImageRecord(
            id=row.id,
            image_id=row.image_id,
            source=row.source,
            file_hash=row.file_hash,
            file_path=row.file_path,
            prompt=row.prompt,
            description=row.description,
            mime_type=row.mime_type,
            original_width=row.original_width,
            original_height=row.original_height,
            created_at=SqlAlchemyCreatorImageAccess._normalize_datetime(row.created_at),
            updated_at=SqlAlchemyCreatorImageAccess._normalize_datetime(row.updated_at),
            version=row.version,
            image_source=row.image_source,
            gallery_no=row.gallery_no,
        )

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        return to_utc(value)


_: CreatorImageAccess = SqlAlchemyCreatorImageAccess  # type: ignore
