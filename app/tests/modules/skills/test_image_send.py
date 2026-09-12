"""ImageSendSkill 测试 — 图片发送（file_path/pool_key/image_id 三种来源与异常响应）。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import neobot_app.core as core_module
from neobot_app.skills.image_send import ImageSendSkill


class FakeAdapter:
    """记录 send 调用并可配置响应/异常的假适配器。"""

    _NO_RESPONSE = object()

    def __init__(self, response: Any = _NO_RESPONSE, error: Exception | None = None) -> None:
        self.calls: list[tuple[Any, list[dict]]] = []
        self._response = response
        self._error = error

    async def send(
        self, conv_ref, segments: list[dict], wait_response: bool = True
    ) -> Any:
        self.calls.append((conv_ref, segments))
        if self._error is not None:
            raise self._error
        if self._response is self._NO_RESPONSE:
            return SimpleNamespace(status="ok", retcode=0)
        return self._response


class FakeFileServer:
    """仅暴露 _enabled 与 register_file 的假文件服务器（本地路径模式）。"""

    _enabled = False

    def register_file(self, path: Path) -> str:
        return f"file:///{path.as_posix()}"


class FakeImagePool:
    """记录 get 调用并可配置缓存条目的假图片池。"""

    def __init__(self, staged: Any = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self._staged = staged

    def get(self, pipeline_key: str, pool_key: str) -> Any:
        self.calls.append((pipeline_key, pool_key))
        return self._staged


def _parse(text: str) -> dict:
    return json.loads(text)


def _make_skill(adapter: FakeAdapter | None = None, file_server=None, pool=None) -> ImageSendSkill:
    return ImageSendSkill(adapter=adapter, file_server=file_server, image_pool=pool)


async def test_send_image_by_file_path_to_group(tmp_path):
    """正常路径：send_image 用 file_path 发送到群应构造 group 会话并返回路径。"""
    img = tmp_path / "pic.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    adapter = FakeAdapter()
    skill = _make_skill(adapter=adapter, file_server=FakeFileServer())

    result = _parse(await skill.execute("send_image", {"file_path": str(img), "group_id": "888"}))

    assert result["ok"] is True
    assert result["path"] == str(img)
    conv_ref, segments = adapter.calls[0]
    assert conv_ref.kind == "group"
    assert conv_ref.id == "888"
    assert segments[0]["type"] == "image"


async def test_send_image_by_file_path_to_private(tmp_path):
    """正常路径：send_image 用 file_path 发送到私聊应构造 private 会话。"""
    img = tmp_path / "pic.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    adapter = FakeAdapter()
    skill = _make_skill(adapter=adapter, file_server=FakeFileServer())

    result = _parse(await skill.execute("send_image", {"file_path": str(img), "user_id": "42"}))

    assert result["ok"] is True
    assert adapter.calls[0][0].kind == "private"
    assert adapter.calls[0][0].id == "42"


async def test_send_image_missing_target_rejected(tmp_path):
    """异常路径：缺少 group_id 与 user_id 时应拒绝发送。"""
    img = tmp_path / "pic.png"
    img.write_bytes(b"png")
    skill = _make_skill(adapter=FakeAdapter(), file_server=FakeFileServer())

    result = _parse(await skill.execute("send_image", {"file_path": str(img)}))

    assert result["ok"] is False
    assert "缺少 group_id 或 user_id" in result["error"]


async def test_send_image_missing_source_rejected():
    """异常路径：image_id/file_path/pool_key 全缺时应拒绝发送。"""
    skill = _make_skill(adapter=FakeAdapter(), file_server=FakeFileServer())

    result = _parse(await skill.execute("send_image", {"group_id": "888"}))

    assert result["ok"] is False
    assert "缺少 image_id、file_path 或 pool_key" in result["error"]


async def test_send_image_file_not_found_rejected(tmp_path):
    """异常路径：file_path 文件不存在时应拒绝且不调用适配器。"""
    adapter = FakeAdapter()
    skill = _make_skill(adapter=adapter, file_server=FakeFileServer())

    result = _parse(await skill.execute("send_image", {"file_path": str(tmp_path / "nope.png"), "group_id": "888"}))

    assert result["ok"] is False
    assert "文件不存在" in result["error"]
    assert adapter.calls == []


async def test_send_image_from_pool_requires_pipeline_key():
    """异常路径：使用 pool_key 但缺少/格式错误的 pipeline_key 时应拒绝。"""
    adapter = FakeAdapter()
    skill = _make_skill(adapter=adapter, file_server=FakeFileServer(), pool=FakeImagePool())

    no_key = _parse(await skill.execute("send_image", {"pool_key": "k1", "group_id": "888"}))
    bad_format = _parse(await skill.execute("send_image", {"pool_key": "k1", "pipeline_key": "nogroup", "group_id": "888"}))

    assert no_key["ok"] is False
    assert "pipeline_key" in no_key["error"]
    assert bad_format["ok"] is False
    assert "格式 kind:id" in bad_format["error"]


async def test_send_image_from_pool_missing_entry(tmp_path):
    """异常路径：缓存池中不存在 pool_key 时应提示可能已过期。"""
    adapter = FakeAdapter()
    skill = _make_skill(adapter=adapter, file_server=FakeFileServer(), pool=FakeImagePool(staged=None))

    result = _parse(await skill.execute("send_image", {"pool_key": "gone", "pipeline_key": "group:1", "group_id": "888"}))

    assert result["ok"] is False
    assert "缓存池中不存在" in result["error"]
    assert "过期" in result["error"]


async def test_send_image_from_pool_success(tmp_path):
    """正常路径：pool_key 命中缓存时应发送 staged.file_path 指向的图片。"""
    img = tmp_path / "staged.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    staged = SimpleNamespace(file_path=img)
    adapter = FakeAdapter()
    skill = _make_skill(adapter=adapter, file_server=FakeFileServer(), pool=FakeImagePool(staged=staged))

    result = _parse(await skill.execute("send_image", {"pool_key": "k1", "pipeline_key": "group:1", "group_id": "888"}))

    assert result["ok"] is True
    assert result["path"] == str(img)
    assert adapter.calls[0][1][0]["data"]["file"].startswith("file:///")


async def test_send_image_by_image_id_from_gallery(tmp_path, monkeypatch):
    """正常路径：image_id 应从 DATA_DIR/creator/gallery 找到对应图片文件。"""
    gallery_dir = tmp_path / "creator" / "gallery"
    gallery_dir.mkdir(parents=True)
    img = gallery_dir / "42.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    monkeypatch.setattr(core_module, "DATA_DIR", tmp_path)
    adapter = FakeAdapter()
    skill = _make_skill(adapter=adapter, file_server=FakeFileServer())

    result = _parse(await skill.execute("send_image", {"image_id": 42, "group_id": "888"}))

    assert result["ok"] is True
    assert result["path"] == str(img)


async def test_send_image_by_image_id_not_found(tmp_path, monkeypatch):
    """异常路径：图库中不存在 image_id 时应提示图库不存在。"""
    monkeypatch.setattr(core_module, "DATA_DIR", tmp_path)
    skill = _make_skill(adapter=FakeAdapter(), file_server=FakeFileServer())

    result = _parse(await skill.execute("send_image", {"image_id": 999, "group_id": "888"}))

    assert result["ok"] is False
    assert "图库不存在 image_id=999" in result["error"]


async def test_send_image_adapter_failed_dict_response(tmp_path):
    """异常路径：适配器返回 failed 字典时应透传 retcode 与原因。"""
    img = tmp_path / "pic.png"
    img.write_bytes(b"png")
    adapter = FakeAdapter(response={"status": "failed", "retcode": 100, "message": "no permission"})
    skill = _make_skill(adapter=adapter, file_server=FakeFileServer())

    result = _parse(await skill.execute("send_image", {"file_path": str(img), "group_id": "888"}))

    assert result["ok"] is False
    assert "发送失败(retcode=100)" in result["error"]
    assert "no permission" in result["error"]


async def test_send_image_adapter_failed_object_response(tmp_path):
    """异常路径：适配器返回 failed 对象时应透传 retcode 与 wording。"""
    img = tmp_path / "pic.png"
    img.write_bytes(b"png")
    adapter = FakeAdapter(response=SimpleNamespace(status="failed", retcode=101, message=None, wording="被禁言"))
    skill = _make_skill(adapter=adapter, file_server=FakeFileServer())

    result = _parse(await skill.execute("send_image", {"file_path": str(img), "group_id": "888"}))

    assert result["ok"] is False
    assert "发送失败(retcode=101)" in result["error"]
    assert "被禁言" in result["error"]


async def test_send_image_timeout_no_response(tmp_path):
    """边界：适配器返回 None（超时无响应）时应提示发送超时。"""
    img = tmp_path / "pic.png"
    img.write_bytes(b"png")
    adapter = FakeAdapter(response=None)
    skill = _make_skill(adapter=adapter, file_server=FakeFileServer())

    result = _parse(await skill.execute("send_image", {"file_path": str(img), "group_id": "888"}))

    assert result["ok"] is False
    assert "发送超时" in result["error"]


async def test_send_image_adapter_exception_reported(tmp_path):
    """异常路径：适配器抛异常时应返回发送失败且不崩溃。"""
    img = tmp_path / "pic.png"
    img.write_bytes(b"png")
    adapter = FakeAdapter(error=RuntimeError("network broken"))
    skill = _make_skill(adapter=adapter, file_server=FakeFileServer())

    result = _parse(await skill.execute("send_image", {"file_path": str(img), "group_id": "888"}))

    assert result["ok"] is False
    assert "发送失败" in result["error"]
    assert "network broken" in result["error"]


async def test_send_image_missing_adapter_or_file_server():
    """异常路径：adapter 或 file_server 未配置时应返回对应配置错误。"""
    no_adapter = _make_skill(adapter=None, file_server=FakeFileServer())
    no_fs = _make_skill(adapter=FakeAdapter(), file_server=None)

    r1 = _parse(await no_adapter.execute("send_image", {"group_id": "888", "image_id": 1}))
    r2 = _parse(await no_fs.execute("send_image", {"group_id": "888", "image_id": 1}))

    assert r1["ok"] is False and "adapter 未配置" in r1["error"]
    assert r2["ok"] is False and "file_server 未配置" in r2["error"]


async def test_unknown_tool_returns_error():
    """异常路径：未知工具名应返回明确错误。"""
    skill = _make_skill()

    result = _parse(await skill.execute("no_such_tool", {}))

    assert result["ok"] is False
    assert "unknown image_send tool" in result["error"]
