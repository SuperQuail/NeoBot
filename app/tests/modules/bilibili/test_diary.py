"""BilibiliDiaryService / BilibiliDiarySkill 测试：素材、生成、预览、发布、开关。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from neobot_app.bilibili.diary import BilibiliDiaryService, BilibiliDiarySkill


class FakeProvider:
    def __init__(self, content: str = "今天也在打游戏") -> None:
        self.content = content
        self.calls: list[list[dict]] = []
        self.model = "fake-model"

    async def chat(self, messages, tools=None):
        self.calls.append(messages)
        if self.content.strip().upper() == "[SKIP]":
            name, arguments = "cancel", {}
        else:
            name, arguments = "send_dynamic", {"text": self.content}
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
                }
            ],
        }


class FakeClient:
    def __init__(self, dynamic_id: int = 42, *, error: Exception | None = None) -> None:
        self.dynamic_id = dynamic_id
        self.error = error
        self.published: list[str] = []

    def publish_dynamic(self, text, images=None):
        if self.error is not None:
            raise self.error
        self.published.append(text)
        return self.dynamic_id


class FakeAsyncService:
    def __init__(self, dynamic_id: int = 7) -> None:
        self.dynamic_id = dynamic_id
        self.published: list[str] = []

    async def publish_dynamic(self, text, images=None):
        self.published.append(text)
        return self.dynamic_id


class FakeArchive:
    def __init__(self, items=None) -> None:
        self.items = list(items or [])
        self.calls: list[str] = []

    async def list(self, table_name, *, key_query=None, limit=50, offset=0):
        self.calls.append(table_name)
        return [item for item in self.items if item.table_name == table_name][:limit]


def _item(key: str, value: str, *, updated_at=None) -> SimpleNamespace:
    return SimpleNamespace(
        table_name="group_summary",
        key=key,
        value=value,
        tags=[],
        updated_at=updated_at or datetime.now(timezone.utc),
    )


def _service(provider=None, client=None, **kwargs) -> BilibiliDiaryService:
    values = {"bot_name": "Neo", "enabled": True}
    values.update(kwargs)
    return BilibiliDiaryService(provider or FakeProvider(), client, **values)


async def test_disabled_diary_refuses() -> None:
    service = _service(FakeProvider(), FakeClient(), enabled=False)

    result = await service.run()

    assert result["ok"] is False
    assert "未启用" in result["error"]


async def test_preview_generates_without_publishing() -> None:
    client = FakeClient()
    service = _service(FakeProvider("今天很开心"), client)

    result = await service.run(preview=True)

    assert result["ok"] is True
    assert result["text"] == "今天很开心"
    assert client.published == []


async def test_publish_calls_client_and_returns_dynamic_id() -> None:
    client = FakeClient(dynamic_id=123)
    service = _service(FakeProvider("今天很开心"), client)

    result = await service.run()

    assert result["ok"] is True
    assert result["dynamic_id"] == 123
    assert client.published == ["今天很开心"]


async def test_async_service_client_is_supported() -> None:
    service = _service(FakeProvider("动态"), FakeAsyncService(dynamic_id=7))

    result = await service.run()

    assert result["ok"] is True
    assert result["dynamic_id"] == 7


async def test_publish_error_is_reported() -> None:
    service = _service(FakeProvider("动态"), FakeClient(error=RuntimeError("风控")))

    result = await service.run()

    assert result["ok"] is False
    assert "风控" in result["error"]


async def test_material_provider_is_not_used_for_private_content() -> None:
    provider = FakeProvider()
    seen: list[str] = []

    async def material():
        seen.append("called")
        return "私聊内容不应进入日记"

    service = _service(provider, FakeClient(), material_provider=material)
    await service.generate()

    assert seen == []


async def test_archive_material_fallback() -> None:
    archive = FakeArchive([_item("123", "群里在聊游戏")])
    provider = FakeProvider()
    service = _service(provider, FakeClient(), archive_service=archive)
    material = await service.collect_material()

    assert "群里在聊游戏" in material
    assert archive.calls == ["group_summary"]


async def test_archive_material_skips_yesterdays_items() -> None:
    old = datetime(2020, 1, 1, tzinfo=timezone.utc)
    archive = FakeArchive([_item("123", "旧档案", updated_at=old)])
    service = _service(FakeProvider(), FakeClient(), archive_service=archive)

    assert await service.collect_material() == ""


async def test_generate_failure_returns_error() -> None:
    service = _service(FakeProvider("[SKIP]"), FakeClient())

    result = await service.run()

    assert result["ok"] is False


def test_diary_skill_requires_service() -> None:
    assert BilibiliDiarySkill(None).get_tools() == []


async def test_diary_skill_executes() -> None:
    service = _service(FakeProvider("动态正文"), FakeClient())
    skill = BilibiliDiarySkill(service)

    result = json.loads(await skill.execute("publish_bilibili_diary", {}))

    assert result["ok"] is True
    assert result["text"] == "动态正文"


async def test_diary_skill_unknown_tool() -> None:
    skill = BilibiliDiarySkill(_service())
    result = json.loads(await skill.execute("nope", {}))
    assert result["ok"] is False



async def test_collect_material_diff_is_only_consumed_after_publish(tmp_path) -> None:
    archive = FakeArchive([_item("123", "群里在聊游戏")])
    service = _service(
        FakeProvider("动态正文"), FakeClient(), archive_service=archive, data_dir=tmp_path
    )

    first = await service.collect_material()
    second = await service.collect_material()

    assert "+ [群:123] 群里在聊游戏" in first
    # 只收集/预览不消费 diff：快照要等发布成功才落盘。
    assert second == first
    assert archive.calls == ["group_summary", "group_summary"]

    assert (await service.run())["ok"] is True
    assert await service.collect_material() == ""


async def test_preview_keeps_diff_until_publish(tmp_path) -> None:
    archive = FakeArchive([_item("123", "群里在聊游戏")])
    service = _service(
        FakeProvider("草稿"), FakeClient(), archive_service=archive, data_dir=tmp_path
    )

    preview = await service.run(preview=True)
    assert preview["ok"] is True
    assert preview["preview"] is True
    assert "+ [群:123] 群里在聊游戏" in await service.collect_material()

    assert (await service.run())["ok"] is True
    assert await service.collect_material() == ""
    assert (tmp_path / "bilibili" / "diary_material.json").exists()


async def test_publish_failure_keeps_diff(tmp_path) -> None:
    archive = FakeArchive([_item("123", "群里在聊游戏")])
    service = _service(
        FakeProvider("动态"),
        FakeClient(error=RuntimeError("风控")),
        archive_service=archive,
        data_dir=tmp_path,
    )

    result = await service.run()

    assert result["ok"] is False
    assert not (tmp_path / "bilibili" / "diary_material.json").exists()
    assert "+ [群:123] 群里在聊游戏" in await service.collect_material()


class _LengthCheckingProvider(FakeProvider):
    """第一次提交超长正文（应被工具拒绝），之后提交合规正文。"""

    def __init__(self) -> None:
        super().__init__()
        self.sent = 0

    async def chat(self, messages, tools=None):
        self.calls.append(messages)
        self.sent += 1
        text = "长" * 100 if self.sent == 1 else "短动态"
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "send_dynamic",
                        "arguments": json.dumps({"text": text}, ensure_ascii=False),
                    },
                }
            ],
        }


async def test_overlong_dynamic_is_rejected_and_retried() -> None:
    provider = _LengthCheckingProvider()
    service = _service(provider, FakeClient(), max_chars=10)

    result = await service.run(preview=True)

    assert result["ok"] is True
    assert result["text"] == "短动态"
