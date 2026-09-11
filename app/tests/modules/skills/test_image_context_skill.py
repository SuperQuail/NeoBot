"""Native image-context transport, source resolution, limits and registration."""
from __future__ import annotations

import base64
import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from PIL import Image

import neobot_app.skills.image_context_skill as context_module
from neobot_app.image.source import ImageSourceResolver, read_image_ref
from neobot_app.image_pool import ImageStagingPool
from neobot_app.skills import build_all_skills
from neobot_app.skills.base import SkillManager
from neobot_app.skills.image_context_skill import ImageContextResult, ImageContextSkill


def image_bytes(fmt="PNG", size=(8, 6)):
    output = io.BytesIO()
    Image.new("RGB", size, "red").save(output, format=fmt)
    return output.getvalue()


@pytest.fixture
def png():
    return image_bytes()


@pytest.fixture
def image_path(tmp_path, png):
    path = tmp_path / "图片 with spaces.wrong-extension"
    path.write_bytes(png)
    return path


def assert_image(result, raw=None, mime="image/png"):
    assert isinstance(result, str)
    assert isinstance(result, ImageContextResult)
    metadata = json.loads(result)
    assert metadata["ok"], metadata
    assert len(result.image_parts) == metadata["count"]
    assert "base64," not in result
    assert "image_parts" not in metadata
    part = result.image_parts[0]
    assert part["type"] == "image_url"
    url = part["image_url"]["url"]
    assert url.startswith(f"data:{mime};base64,")
    if raw:
        assert base64.b64decode(url.partition(",")[2], validate=True) == raw
        assert base64.b64encode(raw).decode() not in result
    return metadata


def assert_failure(result):
    assert not json.loads(result)["ok"]
    assert result.image_parts == []


@pytest.mark.parametrize("prefix", ["", "base64://", "data:image/png;base64,"])
async def test_base64_forms_and_out_of_band_payload(png, prefix):
    result = await ImageContextSkill().execute("add_image", {"image_base64": prefix + base64.b64encode(png).decode()})
    metadata = assert_image(result, png)
    assert metadata["images"][0]["width"] == 8
    assert metadata["images"][0]["height"] == 6
    assert metadata["images"][0]["size_bytes"] == len(png)
    assert len(metadata["images"][0]["sha256"]) == 64
    assert not hasattr(str(result), "image_parts")


@pytest.mark.parametrize("source", ["image_path", "file_url", "source", "file_ref", "image"])
async def test_paths_and_file_urls(image_path, png, source):
    if source == "file_url":
        args = {"image_url": image_path.as_uri()}
    elif source == "file_ref":
        args = {"source": f"file:{image_path}"}
    else:
        args = {source: str(image_path)}
    assert_image(await ImageContextSkill().execute("add_image", args), png)


@pytest.mark.parametrize(
    "fmt,mime",
    [
        ("JPEG", "image/jpeg"),
        ("WEBP", "image/webp"),
        # 无透明通道的重编码统一走 JPEG：PNG 会让内联 base64 膨胀到数 MB，
        # 而这段 base64 会在管线内每一次模型调用里重复发送。
        ("BMP", "image/jpeg"),
        ("GIF", "image/jpeg"),
    ],
)
async def test_sniffs_actual_format_and_normalizes(fmt, mime):
    raw = image_bytes(fmt)
    # Deliberately wrong MIME: normalization trusts decoded content, not hints.
    result = await ImageContextSkill().execute("add_image", {"image_url": "data:image/jpeg;base64," + base64.b64encode(raw).decode()})
    assert_image(result, mime=mime)


async def test_transparent_image_keeps_png_when_small_enough():
    """有透明通道且体积可控时保留 PNG，不能为了压体积丢掉透明度。"""
    output = io.BytesIO()
    Image.new("RGBA", (9000, 9), (255, 0, 0, 128)).save(output, format="PNG")
    result = await ImageContextSkill().execute(
        "add_image", {"image_base64": base64.b64encode(output.getvalue()).decode()}
    )
    metadata = assert_image(result, mime="image/png")["images"][0]
    assert metadata["mime_type"] == "image/png"
    assert metadata["resized"] is True


async def test_oversized_inline_image_is_recompressed():
    """原图体积超过内联上限时必须重编码，否则每轮调用都要重发十几 MB base64。"""
    output = io.BytesIO()
    noise = Image.effect_noise((1600, 1200), 100).convert("RGB")
    noise.save(output, format="PNG")
    raw = output.getvalue()
    assert len(raw) > context_module.MAX_INLINE_IMAGE_BYTES

    result = await ImageContextSkill().execute(
        "add_image", {"image_base64": base64.b64encode(raw).decode()}
    )
    metadata = assert_image(result, mime="image/jpeg")["images"][0]
    assert metadata["size_bytes"] <= context_module.MAX_INLINE_IMAGE_BYTES


async def test_long_narrow_image_resizes_for_native_provider():
    raw = image_bytes(size=(9000, 9))
    result = await ImageContextSkill().execute("add_image", {"image_base64": base64.b64encode(raw).decode()})
    metadata = assert_image(result, mime="image/jpeg")["images"][0]
    assert metadata["original_width"] == 9000
    assert metadata["original_height"] == 9
    assert metadata["width"] == 4096
    assert 1 <= metadata["height"] <= 5
    assert metadata["resized"] is True
    decoded = base64.b64decode(result.image_parts[0]["image_url"]["url"].partition(",")[2])
    with Image.open(io.BytesIO(decoded)) as image:
        assert image.size == (metadata["width"], metadata["height"])


async def test_animated_gif_first_frame_metadata():
    output = io.BytesIO()
    Image.new("RGB", (8, 6), "red").save(output, format="GIF", save_all=True, append_images=[Image.new("RGB", (8, 6), "blue")])
    result = await ImageContextSkill().execute("add_image", {"image_base64": base64.b64encode(output.getvalue()).decode()})
    metadata = assert_image(result, mime="image/jpeg")
    assert metadata["images"][0]["first_frame_only"] is True


def mock_http(monkeypatch, handler):
    original = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=transport, **kwargs))


@pytest.mark.parametrize("args", [{"image_url": "https://images.test/image"}, {"source": "url:https://images.test/image"}, {"source": "https://images.test/image"}])
async def test_url_download_validates_body(monkeypatch, png, args):
    mock_http(monkeypatch, lambda request: httpx.Response(200, content=png, headers={"content-type": "text/plain"}))
    assert_image(await ImageContextSkill().execute("add_image", args), png)


async def test_url_redirect(monkeypatch, png):
    def handler(request):
        if request.url.path == "/redirect":
            return httpx.Response(302, headers={"location": "/actual"})
        return httpx.Response(200, content=png)
    mock_http(monkeypatch, handler)
    assert_image(await ImageContextSkill().execute("add_image", {"image_url": "https://images.test/redirect"}), png)


@pytest.mark.parametrize("status,body", [(404, b"missing"), (200, b"<html>not an image</html>"), (200, b"")])
async def test_url_failures(monkeypatch, status, body):
    mock_http(monkeypatch, lambda request: httpx.Response(status, content=body))
    assert_failure(await ImageContextSkill().execute("add_image", {"image_url": "https://images.test/image"}))


class Queue:
    def __init__(self, message):
        self.message = message

    def find_by_message_id(self, conv_id, message_id):
        return self.message if self.message.message_id == message_id else None

    def iterate_from_newest(self, conv_id):
        yield self.message

    def entries(self, conv_id):
        return []


@pytest.mark.parametrize("args", [
    {"msg_number": 7, "pipeline_key": "group:123", "_numbering_mapping": {7: 42}},
    {"msg_number": 7, "pipeline_key": "private:123", "_numbering_mapping": {"7": "42"}},
    {"chat_flow_id": "Group_123"}, {"chat_flow_id": "Friend_123"},
    {"message_id": 42},
    {"source": "chat:7:1", "pipeline_key": "group:123", "_numbering_mapping": {7: 42}},
])
async def test_chat_sources_reuse_resolver(png, args):
    message = SimpleNamespace(message_id=42, message=[{"type": "image", "data": {"file": "base64://" + base64.b64encode(png).decode()}}])
    queue = Queue(message)
    adapter = SimpleNamespace(get_msg=AsyncMock(return_value={"data": {"message": message.message}}))
    skill = ImageContextSkill(adapter=adapter, group_message_queue=queue, friend_message_queue=queue)
    assert isinstance(skill._resolver, ImageSourceResolver)
    assert_image(await skill.execute("add_image", args), png)


async def test_chat_replied_message_number_and_api_fallback(png):
    message = SimpleNamespace(message_id=42, message=[{"type": "text", "data": {"text": "[图片：旧描述]"}}])
    adapter = SimpleNamespace(get_msg=AsyncMock(return_value=SimpleNamespace(data={"message": [{"type": "image", "data": {"file": "base64://" + base64.b64encode(png).decode()}}]})))
    skill = ImageContextSkill(adapter=adapter, group_message_queue=Queue(message))
    result = await skill.execute("add_image", {"msg_number": 1, "pipeline_key": "group:123", "_numbering_mapping": {1: 42}})
    assert_image(result, png)
    adapter.get_msg.assert_awaited_once_with(42)


async def test_chat_indices_preserve_order(png):
    other = image_bytes("JPEG")
    message = SimpleNamespace(message_id=42, message=[{"type": "image", "data": {"file": "base64://" + base64.b64encode(raw).decode()}} for raw in (png, other)])
    result = await ImageContextSkill(group_message_queue=Queue(message)).execute("add_image", {"chat_flow_id": "Group_123", "image_indices": [1, 0]})
    metadata = assert_image(result, other, "image/jpeg")
    assert metadata["count"] == 2
    assert result.image_parts[1]["image_url"]["url"].startswith("data:image/png;")


@pytest.mark.parametrize("field", ["pool_key", "image_id", "source"])
async def test_pool_ids_are_session_scoped_and_do_not_consume(image_path, png, field):
    pool = ImageStagingPool()
    key = pool.put("group:123", image_path)
    args = {field: f"pool:{key}" if field == "source" else key, "pipeline_key": "group:123"}
    skill = ImageContextSkill(image_pool=pool)
    assert_image(await skill.execute("add_image", args), png)
    assert pool.get("group:123", key) is not None
    args["pipeline_key"] = "group:456"
    assert_failure(await skill.execute("add_image", args))


async def test_expired_pool_image(image_path):
    pool = ImageStagingPool(ttl_seconds=-1)
    key = pool.put("group:123", image_path)
    result = await ImageContextSkill(image_pool=pool).execute("add_image", {"pool_key": key, "pipeline_key": "group:123"})
    assert_failure(result)
    assert "过期" in result


@pytest.mark.parametrize("args", [{"gallery_id": 2}, {"source": "gallery:2"}, {"source": "2"}, {"image_id": "g_test"}, {"image": "tmp_test"}])
async def test_gallery_numbers_and_persistent_ids(image_path, png, args):
    # Exercise actual existing gallery reference and image-ID lookup code.
    from neobot_app.drawing.service import CreatorImageService
    service = object.__new__(CreatorImageService)
    record = SimpleNamespace(file_path=str(image_path))
    service._get_reference_by_gallery_no = AsyncMock(return_value=record)
    service._get_existing = AsyncMock(return_value=record)
    skill = ImageContextSkill(creator_image_service=service)
    assert_image(await skill.execute("add_image", args), png)
    if "g_test" in args.values() or "tmp_test" in args.values():
        service._get_existing.assert_awaited_once()
    else:
        service._get_reference_by_gallery_no.assert_awaited_once_with(2)


@pytest.mark.parametrize("args", [{"emoji_id": 3}, {"source": "emoji:3"}, {"source": "e:3"}])
async def test_emoji_pool(image_path, png, args):
    service = SimpleNamespace(get_entry=lambda number: SimpleNamespace(file_path=image_path) if number == 3 else None)
    assert_image(await ImageContextSkill(emoji_service=service).execute("add_image", args), png)


@pytest.mark.parametrize("args", [
    {}, {"image_path": "missing-image.png"}, {"image_base64": ""},
    {"image_base64": "!!!!"}, {"image_base64": "aGVsbG8="},
    {"image_url": "data:text/html;base64,aGVsbG8="},
    {"image_path": []}, {"image_base64": 123},
    {"image_path": "x", "image_url": "y"},
    {"image_path": "x", "image_index": -1}, {"image_path": "x", "image_index": True},
    {"message_id": "not-a-number"}, {"message_id": 1.5},
    {"msg_number": 7}, {"chat_flow_id": "bad-format"},
    {"pool_key": "missing"}, {"gallery_id": 0}, {"gallery_id": 2},
    {"image_id": "g_missing"}, {"emoji_id": 3},
    {"source": "chat:1:0"}, {"source": "chat:1:2:3"},
    {"image_path": "x", "detail": "bad"}, {"image_path": "x", "timeout_seconds": 0},
    {"image_path": "x", "timeout_seconds": 121},
    {"sources": []}, {"sources": "x"},
    {"sources": ["x"], "image_path": "y"}, {"image_url_list": ["x"], "sources": ["y"]},
    {"image_indices": [0], "image_path": "x"}, {"message_id": 42, "image_index": 0, "image_indices": [0]},
])
async def test_invalid_inputs_return_metadata_without_payload(args):
    assert_failure(await ImageContextSkill().execute("add_image", args))


async def test_strict_base64_rejects_trailing_garbage(png):
    for ref in ("base64://", "data:image/png;base64,"):
        result = await ImageContextSkill().execute("add_image", {"image_url": ref + base64.b64encode(png).decode() + "!!!"})
        assert_failure(result)
        assert base64.b64encode(png).decode() not in result


async def test_truncated_image_rejected(png):
    result = await ImageContextSkill().execute("add_image", {"image_base64": base64.b64encode(png[:45]).decode()})
    assert_failure(result)


async def test_input_byte_limit_before_read(image_path, png, monkeypatch):
    monkeypatch.setattr(context_module, "MAX_IMAGE_BYTES", len(png) - 1)
    skill = ImageContextSkill()
    assert_failure(await skill.execute("add_image", {"image_path": str(image_path)}))
    assert_failure(await skill.execute("add_image", {"image_base64": base64.b64encode(png).decode()}))


async def test_pixel_limit_before_full_decode(png, monkeypatch):
    monkeypatch.setattr(context_module, "MAX_IMAGE_PIXELS", 47)
    result = await ImageContextSkill().execute("add_image", {"image_base64": base64.b64encode(png).decode()})
    assert_failure(result)
    assert "像素" in result


async def test_total_limit_is_atomic(image_path, png, monkeypatch):
    monkeypatch.setattr(context_module, "MAX_TOTAL_BYTES", len(png))
    result = await ImageContextSkill().execute("add_image", {"image_path_list": [str(image_path)] * 2})
    assert_failure(result)
    assert "合计" in result


async def test_batch_failure_never_returns_partial_parts(image_path):
    result = await ImageContextSkill().execute("add_image", {"sources": [str(image_path), "missing.png"]})
    assert_failure(result)


@pytest.mark.parametrize("batch", ["sources", "image_path_list", "image_url_list"])
async def test_batch_success(image_path, png, batch):
    value = image_path.as_uri() if batch == "image_url_list" else str(image_path)
    result = await ImageContextSkill().execute("add_image", {batch: [value] * 2, "detail": "low"})
    metadata = assert_image(result, png)
    assert metadata["count"] == 2
    assert all(part["image_url"]["detail"] == "low" for part in result.image_parts)


async def test_failure_does_not_echo_resolver_payload():
    skill = ImageContextSkill()
    skill._resolver.resolve = AsyncMock(return_value=(None, "data:image/png;base64,SECRET_PAYLOAD"))
    result = await skill.execute("add_image", {"image_url": "https://images.test/x"})
    assert_failure(result)
    assert "SECRET_PAYLOAD" not in result


async def test_timeout_is_metadata_only():
    skill = ImageContextSkill()
    skill._resolver.resolve = AsyncMock(side_effect=TimeoutError)
    result = await skill.execute("add_image", {"image_path": "x"})
    assert_failure(result)
    assert "超时" in result


async def test_manager_preserves_str_subclass_and_non_session_transport(png):
    manager = SkillManager()
    manager.register(ImageContextSkill())
    assert not manager.is_session_tool("image_context__add_image")
    assert manager.get_tools()[0]["function"]["name"] == "image_context__add_image"
    result = await manager.execute("image_context__add_image", {"image_base64": base64.b64encode(png).decode()})
    assert_image(result, png)
    assert_failure(await manager.get("image_context").execute("unknown", {}))


def test_factory_registers_without_any_vision_provider():
    manager = build_all_skills(vision_provider=None)
    assert isinstance(manager.get("image_context"), ImageContextSkill)
    assert manager.get("image_parse") is not None  # old non-native behavior retained
    assert not manager.is_session_tool("image_context__add_image")
    assert manager.is_session_tool("image_parse__parse_image")
    assert build_all_skills(disabled_skills=["image_context"]).get("image_context") is None


def test_bootstrap_assembly_forwards_native_context_dependencies(monkeypatch):
    import inspect
    import neobot_app.bootstrap._skills as bootstrap

    captured = {}
    def capture(**kwargs):
        captured.update(kwargs)
        return "manager"
    monkeypatch.setattr(bootstrap, "build_all_skills", capture)
    kwargs = {
        name: None for name, parameter in inspect.signature(bootstrap.build_skill_manager).parameters.items()
        if parameter.default is inspect.Parameter.empty
    }
    dependencies = {name: object() for name in ("image_pool", "creator_image_service", "group_message_queue", "friend_message_queue", "emoji_service", "adapter")}
    kwargs.update(dependencies)
    kwargs["config"] = SimpleNamespace(agent=SimpleNamespace(skill=SimpleNamespace(disabled_skills=[])))
    assert bootstrap.build_skill_manager(**kwargs) == "manager"
    assert captured["vision_provider"] is None
    assert all(captured[name] is value for name, value in dependencies.items())


async def test_factory_forwards_pool_gallery_and_queues(image_path, png):
    pool = ImageStagingPool()
    key = pool.put("group:123", image_path)
    queue = Queue(SimpleNamespace(message_id=42, message=[]))
    service = SimpleNamespace(resolve_source_to_path=AsyncMock(return_value=image_path))
    manager = build_all_skills(image_pool=pool, creator_image_service=service, group_message_queue=queue)
    skill = manager.get("image_context")
    assert skill._resolver._group_queue is queue
    assert_image(await manager.execute("image_context__add_image", {"pool_key": key, "pipeline_key": "group:123"}), png)
    assert_image(await manager.execute("image_context__add_image", {"gallery_id": 1}), png)


async def test_manual_loading_has_no_image_count_limit(png):
    source = "data:image/png;base64," + base64.b64encode(png).decode()
    skill = ImageContextSkill()
    result = await skill.execute("add_image", {"sources": [source] * 20})
    assert assert_image(result, png)["count"] == 20
    parameters = skill.get_tools()[0]["function"]["parameters"]["properties"]
    assert all("maxItems" not in parameters[name] for name in ("sources", "image_indices", "image_path_list", "image_url_list"))


async def test_eager_loading_zero_disables_without_downloading(png):
    skill = ImageContextSkill()
    skill._resolver._download_image_segment = AsyncMock()
    result = await skill.load_message({"message": [{"type": "image", "data": {"file": "anything"}}]}, max_images=0)
    assert json.loads(result)["ok"]
    assert result.image_parts == []
    skill._resolver._download_image_segment.assert_not_awaited()


async def test_eager_message_loading_current_and_reply_images(png):
    segments = [{"type": "image", "data": {"file": "base64://" + base64.b64encode(png).decode()}}]
    adapter = SimpleNamespace(get_msg=AsyncMock(return_value={"data": {"message": segments}}))
    skill = ImageContextSkill(adapter=adapter)
    message = SimpleNamespace(message=segments + [{"type": "reply", "data": {"id": "42"}}])
    result = await skill.load_message(message, pipeline_key="group:123", numbering_mapping={7: 42})
    metadata = assert_image(result, png)
    assert metadata["count"] == 2
    assert metadata["images"][1]["message_id"] == 42
    assert metadata["images"][1]["image_index"] == 0
    assert "42" in metadata["images"][1]["label"]
    adapter.get_msg.assert_awaited_once_with(42)


@pytest.mark.parametrize("max_images", [None, 2, 9])
async def test_eager_message_loading_cardimage_and_max_images(png, max_images):
    segment = {"type": "cardimage", "data": {"file": "base64://" + base64.b64encode(png).decode()}}
    kwargs = {} if max_images is None else {"max_images": max_images}
    result = await ImageContextSkill().load_message({"message_id": 99, "content": [segment] * 10}, **kwargs)
    metadata = assert_image(result, png)
    assert metadata["count"] == (max_images if max_images is not None else 4)
    assert metadata["images"][0]["message_id"] == 99
    assert metadata["images"][0]["image_index"] == 0
    assert metadata["images"][1]["image_index"] == 1
    assert "99" in metadata["images"][0]["label"]
    assert metadata["truncated"] is True
    assert "尚未查看" in metadata["message"]


@pytest.mark.parametrize("message", [None, {"content": "plain text"}, SimpleNamespace(message=[{"type": "text", "data": {"text": "hello"}}])])
async def test_eager_loading_text_only_returns_empty_success(message):
    result = await ImageContextSkill().load_message(message)
    assert json.loads(result) == {"ok": True, "count": 0, "images": []}
    assert result.image_parts == []


async def test_eager_reply_without_image_is_not_failure():
    adapter = SimpleNamespace(get_msg=AsyncMock(return_value={"data": {"message": [{"type": "text", "data": {"text": "quoted text"}}]}}))
    result = await ImageContextSkill(adapter=adapter).load_message({"message": [{"type": "reply", "data": {"id": 42}}]})
    assert json.loads(result)["ok"]
    assert result.image_parts == []


@pytest.mark.parametrize("response", [None, {"data": {"message": [{"type": "image", "data": {"file": "missing-file"}}]}}])
async def test_eager_reply_fetch_and_download_failures_are_explicit(response):
    adapter = SimpleNamespace(get_msg=AsyncMock(return_value=response))
    skill = ImageContextSkill(adapter=adapter)
    skill._resolver._download_image_segment = AsyncMock(return_value=(None, "download failed"))
    result = await skill.load_message({"message": [{"type": "reply", "data": {"id": 42}}]})
    assert_failure(result)


async def test_eager_invalid_inline_image_never_attaches():
    result = await ImageContextSkill().load_message({"message": [{"type": "image", "data": {"file": "base64://aGVsbG8="}}]})
    assert_failure(result)


async def test_bounded_reader_content_length_rejects_early(monkeypatch):
    mock_http(monkeypatch, lambda request: httpx.Response(200, headers={"content-length": "1000"}, content=b"x"))
    assert await read_image_ref("https://images.test/x", max_bytes=10) is None


async def test_bounded_reader_stream_limit_without_content_length(monkeypatch):
    class Stream(httpx.AsyncByteStream):
        yielded = 0
        async def __aiter__(self):
            for _ in range(10):
                self.yielded += 1
                yield b"x" * 65536
    stream = Stream()
    mock_http(monkeypatch, lambda request: httpx.Response(200, stream=stream))
    assert await read_image_ref("https://images.test/x", max_bytes=100_000) is None
    assert stream.yielded == 2


async def test_bounded_chat_url_and_get_image_fallback(monkeypatch, png):
    mock_http(monkeypatch, lambda request: httpx.Response(404))
    fallback = AsyncMock(return_value={"data": {"file": "base64://" + base64.b64encode(png).decode()}})
    monkeypatch.setattr("neobot_adapter.request.message.get_image", fallback)
    resolver = ImageSourceResolver(adapter=object(), max_bytes=1024)
    raw, error = await resolver._download_image_segment({"url": "https://images.test/expired", "file": "onebot-file-token"})
    assert error is None
    assert raw == png
    fallback.assert_awaited_once()
