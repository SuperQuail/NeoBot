from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from neobot_app.emoji.service import EmojiService
from neobot_storage import create_engine, make_uow_factory
from neobot_storage.models import Base


def _png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (2, 2), color="red").save(output, format="PNG")
    return output.getvalue()


@pytest.mark.asyncio
async def test_emoji_scan_and_rename_preserve_database_metadata(tmp_path):
    engine = create_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'emoji.sqlite3').as_posix()}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    uow_factory = make_uow_factory(engine)
    service = EmojiService(data_dir=tmp_path, uow_factory=uow_factory)

    try:
        imported = await service.add_image_bytes(
            _png_bytes(),
            file_name="original.png",
            analysis_text="红色方块",
            image_source="用户上传",
        )
        assert imported.entry.file_hash
        assert imported.entry.image_source == "用户上传"

        await service._scan_folder()
        rescanned = service.get_entry(imported.number)
        assert rescanned is not None
        assert rescanned.file_hash == imported.entry.file_hash
        assert rescanned.image_source == "用户上传"

        renamed = await service.rename_entry(imported.number, "renamed.png")
        assert renamed.file_hash == imported.entry.file_hash
        assert renamed.image_source == "用户上传"
        assert renamed.created_at is not None
        assert renamed.updated_at is not None

        async with uow_factory() as uow:
            persisted = await uow.emojis.get_by_hash(imported.entry.file_hash)
        assert persisted is not None
        assert persisted.file_name == "renamed.png"
        assert persisted.image_source == "用户上传"
    finally:
        await engine.dispose()
