from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from neobot_app.emoji.service import EmojiService
from neobot_storage import create_engine, make_uow_factory
from neobot_storage.models import Base


def _png_bytes(color: str = "red") -> bytes:
    output = BytesIO()
    Image.new("RGB", (2, 2), color=color).save(output, format="PNG")
    return output.getvalue()


def _engine_factory(tmp_path):
    engine = create_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'emoji.sqlite3').as_posix()}"
    )

    async def _setup():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    return engine, _setup


class _FakeFileServer:
    _enabled = False

    def register_file(self, file_path):
        raise AssertionError("file_server._enabled=False 时不应调用 register_file")


class _FakeAdapter:
    def __init__(self) -> None:
        self.sent: list[tuple] = []

    async def send(self, conversation, segments):
        self.sent.append((conversation, segments))
        return "sent"


@pytest.mark.asyncio
async def test_emoji_scan_and_rename_preserve_database_metadata(tmp_path):
    engine, setup = _engine_factory(tmp_path)
    await setup()
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


@pytest.mark.asyncio
async def test_send_sticker_sends_image_and_records_usage(tmp_path):
    engine, setup = _engine_factory(tmp_path)
    await setup()
    uow_factory = make_uow_factory(engine)
    adapter = _FakeAdapter()
    service = EmojiService(
        data_dir=tmp_path,
        uow_factory=uow_factory,
        adapter=adapter,
        file_server=_FakeFileServer(),
    )

    try:
        imported = await service.add_image_bytes(
            _png_bytes(),
            file_name="sticker.png",
            analysis_text="测试表情",
        )

        resp = await service.send_sticker(imported.number, text="来咯", group_id="123456")
        assert resp == "sent"
        assert len(adapter.sent) == 1
        conv, segments = adapter.sent[0]
        assert conv.kind == "group"
        assert conv.id == "123456"
        assert segments[0]["type"] == "text"
        assert segments[0]["data"]["text"] == "来咯"
        assert segments[1]["type"] == "image"
        assert service.get_entry(imported.number).use_count == 1

        await service.send_sticker(imported.number, user_id="88888")
        conv, segments = adapter.sent[1]
        assert conv.kind == "private"
        assert conv.id == "88888"
        assert segments[0]["type"] == "image"
        assert service.get_entry(imported.number).use_count == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_send_sticker_validates_inputs(tmp_path):
    engine, setup = _engine_factory(tmp_path)
    await setup()
    uow_factory = make_uow_factory(engine)
    adapter = _FakeAdapter()
    service = EmojiService(
        data_dir=tmp_path,
        uow_factory=uow_factory,
        adapter=adapter,
        file_server=_FakeFileServer(),
    )

    try:
        with pytest.raises(LookupError):
            await service.send_sticker(999, group_id="123456")
        imported = await service.add_image_bytes(
            _png_bytes(),
            file_name="target.png",
            analysis_text="目标表情",
        )
        with pytest.raises(ValueError):
            await service.send_sticker(imported.number, text="缺目标")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_send_sticker_without_send_dependencies_raises(tmp_path):
    engine, setup = _engine_factory(tmp_path)
    await setup()
    uow_factory = make_uow_factory(engine)
    service = EmojiService(data_dir=tmp_path, uow_factory=uow_factory)

    try:
        with pytest.raises(RuntimeError, match="发送能力未注入"):
            await service.send_sticker(1, group_id="123456")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_send_sticker_prefers_group_when_both_targets_given(tmp_path):
    """Arrange: 同时注入群与私聊目标的表情包服务；Act: send_sticker 同时传 group_id 与 user_id；Assert: 发送目标优先为群聊。"""
    engine, setup = _engine_factory(tmp_path)
    await setup()
    uow_factory = make_uow_factory(engine)
    adapter = _FakeAdapter()
    service = EmojiService(
        data_dir=tmp_path,
        uow_factory=uow_factory,
        adapter=adapter,
        file_server=_FakeFileServer(),
    )

    try:
        imported = await service.add_image_bytes(
            _png_bytes(),
            file_name="dual.png",
            analysis_text="双目标表情",
        )
        await service.send_sticker(imported.number, group_id="111", user_id="222")

        conv, segments = adapter.sent[0]
        assert conv.kind == "group"
        assert conv.id == "111"
        assert segments[-1]["type"] == "image"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_record_usage_increments_use_count_and_missing_number_is_noop(tmp_path):
    """Arrange: 已导入表情的服务；Act: 对有效编号 record_usage 两次、对无效编号一次；Assert: 内存与数据库计数递增 2、无效编号无副作用。"""
    engine, setup = _engine_factory(tmp_path)
    await setup()
    uow_factory = make_uow_factory(engine)
    service = EmojiService(data_dir=tmp_path, uow_factory=uow_factory)

    try:
        imported = await service.add_image_bytes(
            _png_bytes(),
            file_name="usage.png",
            analysis_text="计数测试",
        )
        await service.record_usage(imported.number)
        await service.record_usage(imported.number)
        await service.record_usage(999)

        assert service.get_entry(imported.number).use_count == 2
        async with uow_factory() as uow:
            record = await uow.emojis.get_by_hash(imported.entry.file_hash)
        assert record is not None
        assert record.use_count == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_number_assignment_sequential_and_not_reused_after_delete(tmp_path):
    """Arrange: 空表情目录；Act: 依次导入 A/B、删除 A 后再导入 C；Assert: 编号连续分配、删除后编号不复用而是取最大值+1。"""
    engine, setup = _engine_factory(tmp_path)
    await setup()
    uow_factory = make_uow_factory(engine)
    service = EmojiService(data_dir=tmp_path, uow_factory=uow_factory)

    try:
        first = await service.add_image_bytes(
            _png_bytes("red"),
            file_name="a.png",
            analysis_text="A",
        )
        second = await service.add_image_bytes(
            _png_bytes("blue"),
            file_name="b.png",
            analysis_text="B",
        )
        assert first.number == 1
        assert second.number == 2

        assert await service.delete_entry(1) is True
        assert service.get_entry(1) is None
        assert service.emoji_count == 1

        third = await service.add_image_bytes(
            _png_bytes("green"),
            file_name="c.png",
            analysis_text="C",
        )
        assert third.number == 3
        assert service.get_entry(2) is not None
        assert service.emoji_count == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_send_sticker_missing_file_raises_file_not_found(tmp_path):
    """Arrange: 导入后删除实体文件的服务；Act: send_sticker；Assert: 抛出 FileNotFoundError 且不调用 adapter。"""
    engine, setup = _engine_factory(tmp_path)
    await setup()
    uow_factory = make_uow_factory(engine)
    adapter = _FakeAdapter()
    service = EmojiService(
        data_dir=tmp_path,
        uow_factory=uow_factory,
        adapter=adapter,
        file_server=_FakeFileServer(),
    )

    try:
        imported = await service.add_image_bytes(
            _png_bytes(),
            file_name="gone.png",
            analysis_text="即将删除",
        )
        imported.entry.file_path.unlink()

        with pytest.raises(FileNotFoundError):
            await service.send_sticker(imported.number, group_id="123")
        assert adapter.sent == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_entries_sorted_by_use_count_ascending(tmp_path):
    """Arrange: 导入两个表情并只使用其中一个；Act: list_entries；Assert: 使用次数少的排在前面。"""
    engine, setup = _engine_factory(tmp_path)
    await setup()
    uow_factory = make_uow_factory(engine)
    service = EmojiService(data_dir=tmp_path, uow_factory=uow_factory)

    try:
        used = await service.add_image_bytes(
            _png_bytes("red"),
            file_name="a_used.png",
            analysis_text="热图",
        )
        cold = await service.add_image_bytes(
            _png_bytes("blue"),
            file_name="b_cold.png",
            analysis_text="冷图",
        )
        await service.record_usage(used.number)

        entries = service.list_entries()
        assert [number for number, _ in entries] == [cold.number, used.number]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_add_image_bytes_with_filename_sorting_before_existing_assigns_number(tmp_path):
    """Arrange: 已存在 z.png 的服务；Act: 新增文件名排序更早的 a.png；Assert: 两个表情都能获得不冲突的编号。"""
    engine, setup = _engine_factory(tmp_path)
    await setup()
    uow_factory = make_uow_factory(engine)
    service = EmojiService(data_dir=tmp_path, uow_factory=uow_factory)

    try:
        await service.add_image_bytes(
            _png_bytes("red"),
            file_name="z.png",
            analysis_text="旧表情",
        )
        imported = await service.add_image_bytes(
            _png_bytes("blue"),
            file_name="a.png",
            analysis_text="新表情",
        )

        assert service.get_entry(imported.number) is not None
        assert service.emoji_count == 2
        assert {entry.file_name for _, entry in service.list_entries()} == {"a.png", "z.png"}
    finally:
        await engine.dispose()
