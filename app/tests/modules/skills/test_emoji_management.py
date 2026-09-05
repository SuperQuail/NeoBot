"""EmojiManagementSkill 测试 — 表情包列/搜/增/改/改名（依赖注入 Fake 表情服务）。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from neobot_app.skills.emoji_management import EmojiManagementSkill


def _entry(file_name: str = "cat.png", analysis_text: str = "猫猫", use_count: int = 3):
    return SimpleNamespace(
        file_name=file_name,
        analysis_text=analysis_text,
        use_count=use_count,
        file_path=f"/emoji/{file_name}",
    )


class FakeEmojiService:
    """记录表情服务调用并返回可配置结果的假服务。"""

    def __init__(self) -> None:
        self.list_calls: list[tuple[int, int]] = []
        self.search_calls: list[str] = []
        self.add_calls: list[dict] = []
        self.update_calls: list[tuple[int, str]] = []
        self.rename_calls: list[tuple[int, str]] = []
        self.entries: list[tuple[int, Any]] = []
        self.total = 0
        self.has_more = False
        self.add_error: ValueError | None = None

    def list_entries_paginated(self, offset: int, limit: int) -> tuple[list[tuple[int, Any]], int, bool]:
        self.list_calls.append((offset, limit))
        return self.entries, self.total, self.has_more

    def search_entries(self, keyword: str) -> list[tuple[int, Any]]:
        self.search_calls.append(keyword)
        return self.entries

    async def add_image_bytes(self, image_bytes: bytes, file_name: str, analysis_text: Any, image_source: str) -> Any:
        self.add_calls.append({
            "image_bytes": image_bytes,
            "file_name": file_name,
            "analysis_text": analysis_text,
            "image_source": image_source,
        })
        if self.add_error is not None:
            raise self.add_error
        return SimpleNamespace(number=7, entry=_entry(file_name=file_name, analysis_text=analysis_text or ""))

    async def update_entry_description(self, emoji_id: int, description: str) -> Any:
        self.update_calls.append((emoji_id, description))
        return SimpleNamespace(analysis_text=description)

    async def rename_entry(self, emoji_id: int, name: str) -> Any:
        self.rename_calls.append((emoji_id, name))
        return SimpleNamespace(file_name=name)


def _parse(text: str) -> dict:
    return json.loads(text)


def _make_skill(service: FakeEmojiService | None = None) -> EmojiManagementSkill:
    return EmojiManagementSkill(emoji_service=service)


async def test_emoji_list_paginates_and_reports_has_more():
    """正常路径：emoji_list 应按分页参数计算 offset 并透传总数与 has_more。"""
    service = FakeEmojiService()
    service.entries = [(1, _entry()), (2, _entry("dog.png", "狗"))]
    service.total = 12
    service.has_more = True
    skill = _make_skill(service)

    result = _parse(await skill.execute("emoji_list", {"page": 2, "page_size": 5}))

    assert result["ok"] is True
    assert service.list_calls == [(5, 5)]
    assert result["total"] == 12
    assert result["has_more"] is True
    assert result["items"][0]["number"] == 1
    assert result["items"][0]["file_name"] == "cat.png"
    assert result["items"][0]["use_count"] == 3


async def test_emoji_list_include_paths():
    """边界：return_paths=True 时条目应包含文件路径。"""
    service = FakeEmojiService()
    service.entries = [(1, _entry())]
    skill = _make_skill(service)

    result = _parse(await skill.execute("emoji_list", {"return_paths": True}))

    assert result["ok"] is True
    assert result["items"][0]["path"] == "/emoji/cat.png"


async def test_emoji_search_by_keyword():
    """正常路径：emoji_search 应把关键词传给服务并返回条目。"""
    service = FakeEmojiService()
    service.entries = [(3, _entry("cat.png", "猫猫"))]
    skill = _make_skill(service)

    result = _parse(await skill.execute("emoji_search", {"keyword": "猫"}))

    assert result["ok"] is True
    assert service.search_calls == ["猫"]
    assert result["items"][0]["description"] == "猫猫"
    assert result["total"] == 1


async def test_emoji_add_uploads_file_bytes(tmp_path):
    """正常路径：emoji_add 应读取本地图片字节并带来源标记入库。"""
    img = tmp_path / "cat.png"
    img.write_bytes(b"png-bytes")
    service = FakeEmojiService()
    skill = _make_skill(service)

    result = _parse(await skill.execute("emoji_add", {"image_path": str(img), "description": "可爱的猫"}))

    assert result["ok"] is True
    assert result["number"] == 7
    assert service.add_calls == [{
        "image_bytes": b"png-bytes",
        "file_name": "cat.png",
        "analysis_text": "可爱的猫",
        "image_source": "skill_import",
    }]


async def test_emoji_add_missing_file_rejected(tmp_path):
    """异常路径：emoji_add 文件不存在时应拒绝且不调用服务。"""
    service = FakeEmojiService()
    skill = _make_skill(service)

    result = _parse(await skill.execute("emoji_add", {"image_path": str(tmp_path / "nope.png")}))

    assert result["ok"] is False
    assert "下载/解码失败" in result["error"]
    assert service.add_calls == []


async def test_emoji_add_missing_source_param_rejected():
    """异常路径：emoji_add 无任何图片来源参数时应返回缺少来源错误。"""
    skill = _make_skill(FakeEmojiService())

    result = _parse(await skill.execute("emoji_add", {}))

    assert result["ok"] is False
    assert "缺少图片来源参数" in result["error"]


async def test_emoji_add_from_base64():
    """emoji_add 应支持 base64 来源(与图片解析工具一致)。"""
    import base64

    service = FakeEmojiService()
    skill = _make_skill(service)

    result = _parse(await skill.execute(
        "emoji_add",
        {"image_base64": base64.b64encode(b"png-bytes").decode(), "description": "base64图"},
    ))

    assert result["ok"] is True
    assert service.add_calls[0]["image_bytes"] == b"png-bytes"
    assert service.add_calls[0]["file_name"] is None


async def test_emoji_add_from_data_url():
    """emoji_add 应支持 data URL 来源。"""
    import base64

    service = FakeEmojiService()
    skill = _make_skill(service)

    payload = base64.b64encode(b"png-bytes").decode()
    result = _parse(await skill.execute(
        "emoji_add",
        {"image_url": f"data:image/png;base64,{payload}", "description": "data图"},
    ))

    assert result["ok"] is True
    assert service.add_calls[0]["image_bytes"] == b"png-bytes"


async def test_emoji_add_value_error_passthrough(tmp_path):
    """异常路径：服务抛 ValueError（如图片超限）时应透传其提示。"""
    img = tmp_path / "big.png"
    img.write_bytes(b"x")
    service = FakeEmojiService()
    service.add_error = ValueError("图片超过 5MB 限制")
    skill = _make_skill(service)

    result = _parse(await skill.execute("emoji_add", {"image_path": str(img)}))

    assert result["ok"] is False
    assert "图片超过 5MB 限制" in result["error"]
    assert "添加失败" not in result["error"]


async def test_emoji_update_description():
    """正常路径：emoji_update 应更新描述并返回新描述。"""
    service = FakeEmojiService()
    skill = _make_skill(service)

    result = _parse(await skill.execute("emoji_update", {"emoji_id": 5, "description": "新的描述"}))

    assert result["ok"] is True
    assert result["description"] == "新的描述"
    assert service.update_calls == [(5, "新的描述")]


async def test_emoji_update_missing_params_rejected():
    """异常路径：emoji_id 为 0 或 description 为空时应拒绝更新。"""
    service = FakeEmojiService()
    skill = _make_skill(service)

    zero_id = _parse(await skill.execute("emoji_update", {"emoji_id": 0, "description": "x"}))
    empty_desc = _parse(await skill.execute("emoji_update", {"emoji_id": 5, "description": ""}))

    assert zero_id["ok"] is False
    assert empty_desc["ok"] is False
    assert "缺少 emoji_id 或 description" in zero_id["error"]
    assert service.update_calls == []


async def test_emoji_rename():
    """正常路径：emoji_rename 应调用服务改名并返回新文件名。"""
    service = FakeEmojiService()
    skill = _make_skill(service)

    result = _parse(await skill.execute("emoji_rename", {"emoji_id": 5, "name": "new_name.png"}))

    assert result["ok"] is True
    assert result["file_name"] == "new_name.png"
    assert service.rename_calls == [(5, "new_name.png")]


async def test_emoji_rename_missing_params_rejected():
    """异常路径：emoji_rename 缺少 emoji_id 或 name 时应拒绝。"""
    service = FakeEmojiService()
    skill = _make_skill(service)

    result = _parse(await skill.execute("emoji_rename", {"emoji_id": 5}))

    assert result["ok"] is False
    assert "缺少 emoji_id 或 name" in result["error"]
    assert service.rename_calls == []


async def test_missing_service_rejected():
    """异常路径：emoji_service 未配置时所有工具应返回配置错误。"""
    skill = _make_skill(service=None)

    for tool, args in (
        ("emoji_list", {}),
        ("emoji_search", {"keyword": "猫"}),
        ("emoji_add", {"image_path": "x.png"}),
        ("emoji_update", {"emoji_id": 1, "description": "x"}),
        ("emoji_rename", {"emoji_id": 1, "name": "y"}),
    ):
        result = _parse(await skill.execute(tool, args))

        assert result["ok"] is False
        assert "emoji_service 未配置" in result["error"]


async def test_unknown_tool_returns_error():
    """异常路径：未知工具名应返回明确错误。"""
    skill = _make_skill(FakeEmojiService())

    result = _parse(await skill.execute("no_such_tool", {}))

    assert result["ok"] is False
    assert "unknown emoji_management tool" in result["error"]
