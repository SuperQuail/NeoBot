"""GallerySkill 测试 — 图库列/搜/增/改/删/改名/批量导入（依赖注入 Fake 图库服务）。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from neobot_app.skills.gallery_skill import GallerySkill


class FakeImageService:
    """记录图库操作调用并返回可配置结果的假图库服务。"""

    def __init__(self) -> None:
        self.list_calls: list[tuple[int, int]] = []
        self.search_calls: list[str] = []
        self.add_calls: list[tuple[str, Any]] = []
        self.update_calls: list[tuple[str, str]] = []
        self.delete_calls: list[str] = []
        self.rename_calls: list[tuple[str, str]] = []
        self.import_calls: list[dict] = []
        self.images: list[Any] = []
        self.delete_result = True
        self.import_result: list[dict] = [{"ok": True}]

    async def list_images(self, limit: int, offset: int) -> list[Any]:
        self.list_calls.append((limit, offset))
        return self.images

    async def search_images(self, keyword: str) -> list[Any]:
        self.search_calls.append(keyword)
        return self.images

    async def gallery_add(self, image_id: str, description: Any) -> Any:
        self.add_calls.append((image_id, description))
        return SimpleNamespace(image_id=image_id, file_path="/tmp/g1.png")

    async def update_image_description(self, image_id: str, description: str) -> Any:
        self.update_calls.append((image_id, description))
        return SimpleNamespace(image_id=image_id, description=description)

    async def gallery_delete(self, image_id: str) -> bool:
        self.delete_calls.append(image_id)
        return self.delete_result

    async def gallery_rename(self, image_id: str, new_name: str) -> Any:
        self.rename_calls.append((image_id, new_name))
        return SimpleNamespace(image_id=image_id)

    async def import_chat_images(self, **kwargs) -> list[dict]:
        self.import_calls.append(kwargs)
        return self.import_result


def _record(image_id: str, description: str = "测试图"):
    return SimpleNamespace(
        image_id=image_id,
        description=description,
        prompt="a cat",
        source="gallery",
        created_at=None,
        file_path=f"/tmp/{image_id}.png",
    )


def _parse(text: str) -> dict:
    return json.loads(text)


async def test_gallery_list_paginates_with_offset():
    """正常路径：gallery_list 应按 page/page_size 计算 offset 传给服务。"""
    service = FakeImageService()
    service.images = [_record("g1"), _record("g2")]
    skill = GallerySkill(creator_image_service=service)

    result = _parse(await skill.execute("gallery_list", {"page": 3, "page_size": 10}))

    assert result["ok"] is True
    assert service.list_calls == [(10, 20)]
    assert result["total"] == 2
    assert result["items"][0]["image_id"] == "g1"


async def test_gallery_list_include_paths():
    """边界：return_paths=True 时条目应包含文件路径。"""
    service = FakeImageService()
    service.images = [_record("g1")]
    skill = GallerySkill(creator_image_service=service)

    with_paths = _parse(await skill.execute("gallery_list", {"return_paths": True}))
    without_paths = _parse(await skill.execute("gallery_list", {"return_paths": False}))

    assert with_paths["items"][0]["path"] == "/tmp/g1.png"
    assert "path" not in without_paths["items"][0]


async def test_gallery_search_by_keyword():
    """正常路径：gallery_search 应把关键词传给服务并返回条目。"""
    service = FakeImageService()
    service.images = [_record("g1", "夕阳大海")]
    skill = GallerySkill(creator_image_service=service)

    result = _parse(await skill.execute("gallery_search", {"keyword": "夕阳"}))

    assert result["ok"] is True
    assert service.search_calls == ["夕阳"]
    assert result["items"][0]["description"] == "夕阳大海"


async def test_gallery_add_imports_local_image(monkeypatch, tmp_path):
    """正常路径：gallery_add 应预处理本地图片后以 hash 入库。"""
    img = tmp_path / "photo.png"
    img.write_bytes(b"fake png bytes")
    fake_prepared = SimpleNamespace(file_hash="hash-abc")
    monkeypatch.setattr(
        "neobot_app.message.image_pipeline.prepare_local_image",
        lambda p, max_pixels=0: fake_prepared,
    )
    service = FakeImageService()
    skill = GallerySkill(creator_image_service=service)

    result = _parse(await skill.execute("gallery_add", {"image_path": str(img), "description": "海边"}))

    assert result["ok"] is True
    assert result["image_id"] == "hash-abc"
    assert service.add_calls == [("hash-abc", "海边")]


async def test_gallery_add_missing_file_rejected(tmp_path):
    """异常路径：gallery_add 文件不存在时应拒绝且不调用服务。"""
    service = FakeImageService()
    skill = GallerySkill(creator_image_service=service)

    result = _parse(await skill.execute("gallery_add", {"image_path": str(tmp_path / "nope.png")}))

    assert result["ok"] is False
    assert "文件不存在" in result["error"]
    assert service.add_calls == []


async def test_gallery_add_missing_path_param_rejected():
    """异常路径：gallery_add 缺少 image_path 时应返回缺少参数错误。"""
    skill = GallerySkill(creator_image_service=FakeImageService())

    result = _parse(await skill.execute("gallery_add", {}))

    assert result["ok"] is False
    assert "缺少 image_path" in result["error"]


async def test_gallery_update_description():
    """正常路径：gallery_update 应更新描述并返回新描述。"""
    service = FakeImageService()
    skill = GallerySkill(creator_image_service=service)

    result = _parse(await skill.execute("gallery_update", {"image_id": "g1", "description": "新描述"}))

    assert result["ok"] is True
    assert result["description"] == "新描述"
    assert service.update_calls == [("g1", "新描述")]


async def test_gallery_update_missing_params_rejected():
    """异常路径：gallery_update 缺少 image_id 或 description 时应拒绝。"""
    skill = GallerySkill(creator_image_service=FakeImageService())

    result = _parse(await skill.execute("gallery_update", {"image_id": "g1"}))

    assert result["ok"] is False
    assert "缺少 image_id 或 description" in result["error"]


async def test_gallery_delete_success():
    """正常路径：gallery_delete 应透传服务的删除结果布尔值。"""
    service = FakeImageService()
    skill = GallerySkill(creator_image_service=service)

    ok = _parse(await skill.execute("gallery_delete", {"image_id": "g1"}))
    service.delete_result = False
    failed = _parse(await skill.execute("gallery_delete", {"image_id": "g1"}))

    assert ok["ok"] is True
    assert failed["ok"] is False
    assert service.delete_calls == ["g1", "g1"]


async def test_gallery_rename():
    """正常路径：gallery_rename 应调用服务改名并返回新名称。"""
    service = FakeImageService()
    skill = GallerySkill(creator_image_service=service)

    result = _parse(await skill.execute("gallery_rename", {"image_id": "g1", "name": "sunset_ocean"}))

    assert result["ok"] is True
    assert result["name"] == "sunset_ocean"
    assert service.rename_calls == [("g1", "sunset_ocean")]


async def test_batch_add_translates_msg_number_via_mapping():
    """正常路径：带 msg_number 与编号映射时应翻译成真实消息 ID 再批量导入。"""
    service = FakeImageService()
    skill = GallerySkill(creator_image_service=service)

    result = _parse(await skill.execute("gallery_batch_add_from_chat", {
        "msg_number": 75,
        "image_indices": [1, 2],
        "name_prefix": "sakura",
        "_numbering_mapping": {"75": 9999},
    }))

    assert result["ok"] is True
    assert result["imported"] == 1
    assert result["total"] == 1
    assert service.import_calls == [{
        "message_id": 9999,
        "image_indices": [1, 2],
        "target": "gallery",
        "description": None,
        "name": "sakura",
    }]


async def test_batch_add_msg_number_unresolvable_rejected():
    """异常路径：msg_number 无法从映射取得真实 ID 时应拒绝且不导入。"""
    service = FakeImageService()
    skill = GallerySkill(creator_image_service=service)

    result = _parse(await skill.execute("gallery_batch_add_from_chat", {
        "msg_number": 75, "_numbering_mapping": {"74": 1},
    }))

    assert result["ok"] is False
    assert "无法从编号映射" in result["error"]
    assert service.import_calls == []


async def test_batch_add_neither_source_rejected():
    """异常路径：既无 msg_number 也无 message_id 时应拒绝。"""
    skill = GallerySkill(creator_image_service=FakeImageService())

    result = _parse(await skill.execute("gallery_batch_add_from_chat", {}))

    assert result["ok"] is False
    assert "请提供 msg_number 或 message_id" in result["error"]


async def test_batch_add_with_direct_message_id():
    """正常路径：提供 message_id 时应直接使用并过滤非正索引。"""
    service = FakeImageService()
    skill = GallerySkill(creator_image_service=service)

    result = _parse(await skill.execute("gallery_batch_add_from_chat", {
        "message_id": 555, "image_indices": [0, -1, 3],
    }))

    assert result["ok"] is True
    assert service.import_calls[0]["message_id"] == 555
    assert service.import_calls[0]["image_indices"] == [3]


async def test_gallery_unknown_tool_returns_error():
    """异常路径：未知工具名应返回明确错误。"""
    skill = GallerySkill()

    result = _parse(await skill.execute("no_such_tool", {}))

    assert result["ok"] is False
    assert "unknown gallery tool" in result["error"]
