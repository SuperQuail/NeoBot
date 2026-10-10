"""拉不到的图片：进程内登记表 + 不再重复拉取 + 过期文案（issue #80）。

语料分四层：
* 引用键推导与登记表本身（LRU、命中计数）；
* 取图解析器：命中登记表不发请求、判定过期时登记、非过期故障不登记；
* 自动解析（ImageParseService）：过期时正文占位、并回显库里留过的描述；
* 工具面：过期说明不带原始 URL / file id。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from neobot_app.image import unavailable
from neobot_app.image.parser import ImageParseService
from neobot_app.image.source import ImageSourceResolver
from neobot_app.image.unavailable import (
    EXPIRED_INLINE,
    EXPIRED_NOTICE,
    ImageUnavailableRegistry,
    clean_expired_text,
    image_ref_key,
    is_expired_message,
    ref_digest,
)
from neobot_app.skills.image_context_skill import ImageContextSkill
from neobot_app.skills.image_parse_skill import ImageParseSkill


# ── 引用键与登记表 ──────────────────────────────────────────────


def test_ref_key_prefers_file_and_skips_inline_content() -> None:
    assert image_ref_key({"file": "abc", "url": "https://x/y.png"}) == "file:abc"
    assert image_ref_key({"url": "https://x/y.png"}) == "url:https://x/y.png"
    assert image_ref_key({"file": "base64://AAAA"}) is None, "内联内容不会过期，不进登记表"
    assert image_ref_key({"url": "data:image/png;base64,AAAA"}) is None
    assert image_ref_key({}, message_id=42, image_index=1) == "msg:42:1"
    assert image_ref_key({}) is None


def test_ref_digest_is_stable_and_short() -> None:
    digest = ref_digest("file:secret-token")
    assert digest and len(digest) == 32
    assert digest == ref_digest("file:secret-token")
    assert "secret-token" not in digest
    assert ref_digest(None) is None


def test_registry_is_lru_bounded() -> None:
    registry = ImageUnavailableRegistry(capacity=2)
    registry.mark("a")
    registry.mark("b")
    assert registry.notice("a") == EXPIRED_NOTICE
    registry.mark("c")  # 挤掉最久未命中的 "b"（"a" 刚命中过）
    assert registry.is_marked("a")
    assert not registry.is_marked("b")
    assert registry.is_marked("c")
    assert len(registry) == 2
    assert registry.notice("nope") is None
    registry.clear()
    assert len(registry) == 0


def test_clean_expired_text_drops_raw_refs() -> None:
    clean = clean_expired_text(
        "图片已过期，无法获取（可能原因：清理过历史聊天记录 / 时间太久）；"
        "Adapter 回源失败：get_image API 异常(file=secret-token)"
    )
    assert clean == EXPIRED_NOTICE
    assert "secret-token" not in clean


# ── 取图解析器 ──────────────────────────────────────────────────


async def test_resolver_skips_marked_ref_without_any_request(monkeypatch) -> None:
    """登记过的引用：直接返回过期说明，HTTP 与 get_image 都不发。"""

    def _no_http(**_kwargs):
        raise AssertionError("命中登记表后不应再发 HTTP 请求")

    get_image = AsyncMock(side_effect=AssertionError("命中登记表后不应再调用 get_image"))
    monkeypatch.setattr("neobot_app.image.source.image_http_client", _no_http)
    monkeypatch.setattr("neobot_adapter.request.message.get_image", get_image)

    registry = ImageUnavailableRegistry()
    segment = {"file": "gone-file", "url": "https://images.test/gone.png"}
    registry.mark(image_ref_key(segment))

    resolver = ImageSourceResolver(adapter=SimpleNamespace(), unavailable_registry=registry)
    raw, error = await resolver._download_image_segment(segment)
    assert raw is None
    assert error == EXPIRED_NOTICE
    get_image.assert_not_awaited()


async def test_resolver_marks_expired_get_image_and_stops_retrying(monkeypatch) -> None:
    get_image = AsyncMock(return_value={"data": {}})  # OneBot 已解析不出这个 file id
    monkeypatch.setattr("neobot_adapter.request.message.get_image", get_image)
    registry = ImageUnavailableRegistry()
    resolver = ImageSourceResolver(adapter=SimpleNamespace(), unavailable_registry=registry)

    raw, error = await resolver._download_image_segment({"file": "gone-file"})
    assert raw is None and is_expired_message(error)
    assert registry.is_marked("file:gone-file"), "明确「图没了」的信号要登记"

    get_image.reset_mock()
    raw, error = await resolver._download_image_segment({"file": "gone-file"})
    assert raw is None and error == EXPIRED_NOTICE
    # 第二次不该再问 OneBot
    get_image.assert_not_awaited()


async def test_resolver_does_not_mark_transient_failures(monkeypatch) -> None:
    """断线一类的瞬时故障不登记：否则会把还能拉的图一并废掉。"""
    get_image = AsyncMock(side_effect=RuntimeError("adapter disconnected"))
    monkeypatch.setattr("neobot_adapter.request.message.get_image", get_image)
    registry = ImageUnavailableRegistry()
    resolver = ImageSourceResolver(adapter=SimpleNamespace(), unavailable_registry=registry)

    raw, error = await resolver._download_image_segment({"file": "flaky-file"})
    assert raw is None and not is_expired_message(error)
    assert len(registry) == 0

    await resolver._download_image_segment({"file": "flaky-file"})
    assert get_image.await_count == 2, "非过期故障仍应重试"


async def test_resolver_falls_back_to_get_image_after_url_404(monkeypatch) -> None:
    """URL 过期但 get_image 仍能取到：必须成功，且不得登记。"""
    import httpx

    monkeypatch.setattr(
        "neobot_app.image.source.image_http_client",
        lambda **_kwargs: _response_client(httpx.Response(404)),
    )
    get_image = AsyncMock(return_value={"data": {"file": "base64://" + _png_base64()}})
    monkeypatch.setattr("neobot_adapter.request.message.get_image", get_image)
    registry = ImageUnavailableRegistry()
    resolver = ImageSourceResolver(adapter=SimpleNamespace(), unavailable_registry=registry)

    raw, error = await resolver._download_image_segment(
        {"url": "https://images.test/expired.png", "file": "onebot-file-token"}
    )
    assert error is None and raw
    assert len(registry) == 0


class _response_client:
    """把固定响应包成 image_http_client 的异步上下文。"""

    def __init__(self, response) -> None:
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc) -> bool:
        return False

    async def get(self, _url):
        return self._response


def _png_base64() -> str:
    import base64
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (255, 0, 0)).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


# ── 自动解析（ImageParseService）─────────────────────────────────


def _parse_service(monkeypatch, registry: ImageUnavailableRegistry) -> ImageParseService:
    """独立登记表的解析服务：模块级单例是进程共享的，用例之间必须隔离。"""
    monkeypatch.setattr("neobot_app.image.parser.REGISTRY", registry)
    return ImageParseService()


async def test_expired_image_placeholder_and_no_second_attempt(monkeypatch) -> None:
    get_image = AsyncMock(return_value={"data": {}})
    monkeypatch.setattr("neobot_adapter.request.message.get_image", get_image)
    registry = ImageUnavailableRegistry()
    service = _parse_service(monkeypatch, registry)
    segment = {"type": "image", "data": {"file": "gone-file"}}

    assert await service._parse_single_image(segment) == f"[图片：{EXPIRED_INLINE}]"
    get_image.reset_mock()
    assert await service._parse_single_image(segment) == f"[图片：{EXPIRED_INLINE}]"
    get_image.assert_not_awaited()


async def test_expired_image_echoes_description_from_registry_lookup(monkeypatch) -> None:
    """库里留过描述时，过期占位里带上它 —— 模型仍知道这张图大概是什么。"""
    monkeypatch.setattr(
        "neobot_adapter.request.message.get_image",
        AsyncMock(return_value={"data": {}}),
    )
    key = image_ref_key({"file": "gone-file"})
    digest = ref_digest(key)
    seen: list[str] = []

    async def lookup(source_ref: str):
        seen.append(source_ref)
        return "一只橘猫趴在键盘上" if source_ref == digest else None

    unavailable.install_description_lookup(lookup)
    try:
        service = _parse_service(monkeypatch, ImageUnavailableRegistry())
        text = await service._parse_single_image({"type": "image", "data": {"file": "gone-file"}})
    finally:
        unavailable.install_description_lookup(None)

    assert "一只橘猫趴在键盘上" in text
    assert text.startswith(f"[图片：{EXPIRED_INLINE}")
    assert seen == [digest], "落库/查询用引用摘要，不落原文"


async def test_parse_service_records_ref_description(monkeypatch) -> None:
    """解析成功后记下「引用摘要 -> 描述」，供以后过期时回显。"""
    stored: dict[str, str] = {}

    class _Analysis:
        async def get(self, _file_hash):
            return None

        async def set(self, *_args, **_kwargs):
            return SimpleNamespace(analysis_text="一只橘猫")

        async def remember_ref(self, source_ref, analysis_text):
            stored[source_ref] = analysis_text

    monkeypatch.setattr(
        "neobot_adapter.request.message.get_image",
        AsyncMock(return_value={"data": {"file": "base64://" + _png_base64()}}),
    )
    service = _parse_service(monkeypatch, ImageUnavailableRegistry())
    service._analysis = _Analysis()
    service._vision_provider = SimpleNamespace(chat=AsyncMock(return_value={"content": "一只橘猫"}))

    text = await service._parse_single_image({"type": "image", "data": {"file": "ok-file"}})
    assert text == "[图片：一只橘猫]"
    assert stored == {ref_digest("file:ok-file"): "一只橘猫"}


# ── 工具面 ──────────────────────────────────────────────────────


async def test_image_context_tool_reports_expiry_without_raw_ref() -> None:
    adapter = SimpleNamespace(
        get_msg=AsyncMock(return_value={"data": {"message": [{"type": "image", "data": {"file": "secret-token"}}]}})
    )
    skill = ImageContextSkill(adapter=adapter)
    skill._resolver._unavailable.mark("file:secret-token")

    payload = json.loads(await skill.execute("add_image", {"message_id": 42}))
    assert payload["ok"] is False
    assert payload["error"] == EXPIRED_NOTICE
    assert "secret-token" not in json.dumps(payload, ensure_ascii=False)


async def test_image_context_eager_loader_reports_expiry() -> None:
    skill = ImageContextSkill()
    skill._resolver._unavailable.mark("file:secret-token")

    payload = json.loads(await skill.load_message({"message": [{"type": "image", "data": {"file": "secret-token"}}]}))
    assert payload["ok"] is False
    assert payload["error"] == EXPIRED_NOTICE
    assert "secret-token" not in json.dumps(payload, ensure_ascii=False)


async def test_image_parse_skill_skips_marked_ref_without_request(monkeypatch) -> None:
    get_image = AsyncMock(side_effect=AssertionError("命中登记表后不应再调用 get_image"))
    monkeypatch.setattr("neobot_adapter.request.message.get_image", get_image)
    registry = ImageUnavailableRegistry()
    monkeypatch.setattr("neobot_app.skills.image_parse_skill.REGISTRY", registry)
    registry.mark("file:gone-file")

    skill = ImageParseSkill(adapter=SimpleNamespace())
    raw, error = await skill._download_image_segment({"file": "gone-file"})
    assert raw is None and error == EXPIRED_NOTICE
    get_image.assert_not_awaited()


async def test_image_parse_skill_marks_expired_ref(monkeypatch) -> None:
    monkeypatch.setattr(
        "neobot_adapter.request.message.get_image",
        AsyncMock(return_value={"data": {}}),
    )
    registry = ImageUnavailableRegistry()
    monkeypatch.setattr("neobot_app.skills.image_parse_skill.REGISTRY", registry)

    skill = ImageParseSkill(adapter=SimpleNamespace())
    raw, error = await skill._download_image_segment({"file": "gone-file"})
    assert raw is None and is_expired_message(error)
    assert registry.is_marked("file:gone-file")
