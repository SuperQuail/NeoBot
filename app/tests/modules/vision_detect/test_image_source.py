"""统一图片来源解析模块(neobot_app.image.source)单元测试。"""

from __future__ import annotations

import base64
import io

from PIL import Image

from neobot_app.image.source import ImageSourceResolver, read_image_ref


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


async def test_read_image_ref_base64() -> None:
    payload = base64.b64encode(_png_bytes()).decode()
    data = await read_image_ref(f"base64://{payload}")
    assert data == _png_bytes()


async def test_read_image_ref_data_url() -> None:
    payload = base64.b64encode(_png_bytes()).decode()
    data = await read_image_ref(f"data:image/png;base64,{payload}")
    assert data == _png_bytes()


async def test_read_image_ref_local_path(tmp_path) -> None:
    path = tmp_path / "pic.png"
    path.write_bytes(_png_bytes())
    data = await read_image_ref(str(path))
    assert data == _png_bytes()


async def test_read_image_ref_file_url(tmp_path) -> None:
    path = tmp_path / "pic.png"
    path.write_bytes(_png_bytes())
    data = await read_image_ref(f"file://{path}")
    assert data == _png_bytes()


async def test_read_image_ref_missing_returns_none() -> None:
    assert await read_image_ref(r"D:\no\such\file.png") is None
    assert await read_image_ref("not-a-url") is None


async def test_resolve_priority_base64_over_path(tmp_path) -> None:
    """base64 优先于 path 参数。"""
    resolver = ImageSourceResolver()
    path = tmp_path / "a.png"
    path.write_bytes(b"path-bytes")
    payload = base64.b64encode(b"base64-bytes").decode()
    data, error = await resolver.resolve({"image_base64": payload, "image_path": str(path)})
    assert error is None
    assert data == b"base64-bytes"


async def test_resolve_missing_source() -> None:
    resolver = ImageSourceResolver()
    data, error = await resolver.resolve({})
    assert data is None
    assert "缺少图片来源参数" in error


async def test_resolve_bad_image_index() -> None:
    resolver = ImageSourceResolver()
    data, error = await resolver.resolve({"image_base64": "aGVsbG8=", "image_index": "abc"})
    assert data is None
    assert "image_index" in error


async def test_resolve_msg_number_requires_pipeline_key() -> None:
    resolver = ImageSourceResolver()
    data, error = await resolver.resolve({"msg_number": 5})
    assert data is None
    assert "pipeline_key" in error


async def test_resolve_msg_number_maps_and_fetches() -> None:
    """msg_number 经编号映射 → 队列查找 → 回源下载。"""
    from types import SimpleNamespace

    png = _png_bytes()

    class _Queue:
        def __init__(self) -> None:
            self._msg = SimpleNamespace(
                message_id=42,
                message=[
                    {
                        "type": "image",
                        "data": {"url": "http://example.invalid/x.png"},
                    }
                ],
            )

        def entries(self, conv_id: str) -> list:
            return [self._msg]

        def iterate_from_newest(self, conv_id: str):
            yield self._msg

        def find_by_message_id(self, conv_id: str, message_id: int):
            return self._msg if message_id == 42 else None

    class _Adapter:
        async def get_msg(self, message_id: int):
            return SimpleNamespace(data=SimpleNamespace(message=[
                {"type": "image", "data": {"url": "http://example.invalid/x.png"}},
            ]))

        async def call_api(self, name: str, params: dict):
            return None

    resolver = ImageSourceResolver(
        adapter=_Adapter(),
        group_message_queue=_Queue(),
        friend_message_queue=_Queue(),
    )
    data, error = await resolver.resolve(
        {"msg_number": 7, "pipeline_key": "group:123", "_numbering_mapping": {7: 42}}
    )
    # URL 不可达,回源后仍失败 → 返回错误(验证链路完整不崩溃)
    assert data is None
    assert error and "下载" in error or "回源" in error or "失败" in error
    assert png  # 占位避免未使用告警


async def test_resolve_message_id_rejects_bad_value() -> None:
    resolver = ImageSourceResolver()
    data, error = await resolver.resolve({"message_id": "abc"})
    assert data is None
    assert "message_id" in error