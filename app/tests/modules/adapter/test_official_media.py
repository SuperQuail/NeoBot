"""官方富媒体上传：URL 直传、分片上传、配额错误与 file_info 缓存。

URL 直传失败不再下载后改走分片：直接报错，由发送层返回 failed。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest


from neobot_contracts.ports.logging import NullLogger

from neobot_adapter.official import media as media_module
from neobot_adapter.official.media import MediaFile, MediaUploadError, MediaUploader
from neobot_adapter.official.send import OfficialApiError


@pytest.fixture
def workdir():
    """隔离落盘目录；pytest 的 tmp_path 用 0o700 建目录，本机沙箱下会拒绝访问。"""
    path = Path(tempfile.gettempdir()) / f"neobot-official-{uuid.uuid4().hex}"
    os.mkdir(path)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


_OK_FILE = {"code": 0, "data": {"file_info": "FILE-INFO", "file_uuid": "FILE-UUID", "ttl": 60}}


class _FakeApi:
    """按路径后缀返回预设响应；用来观察上传请求体。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.handlers: dict[str, list] = {}

    def on(self, suffix: str, *results) -> None:
        self.handlers[suffix] = list(results)

    async def request(self, method: str, path: str, *, body=None, timeout: float = 10.0) -> dict:
        self.calls.append({"method": method, "path": path, "body": dict(body or {})})
        for suffix in sorted(self.handlers, key=len, reverse=True):
            if path.endswith(suffix):
                queue = self.handlers[suffix]
                result = queue.pop(0) if len(queue) > 1 else queue[0]
                if isinstance(result, Exception):
                    raise result
                return result
        raise AssertionError(f"unexpected path: {path}")


def _prepare_payload(*, block_size: int = 4, indexes=(0, 1)) -> dict:
    return {
        "code": 0,
        "data": {
            "upload_id": "upload-1",
            "block_size": block_size,
            "parts": [
                {
                    "index": index,
                    "block_size": block_size,
                    "presigned_url": f"https://cos.example/{index}",
                }
                for index in indexes
            ],
        },
    }


async def test_url_source_uploads_by_url(workdir) -> None:
    api = _FakeApi()
    api.on("/files", _OK_FILE)
    uploader = MediaUploader(NullLogger())

    result = await uploader.upload(
        api,
        kind="group",
        openid="group-openid",
        segment_type="image",
        source="https://example.com/a.png",
    )

    assert result.file_info == "FILE-INFO"
    assert result.file_uuid == "FILE-UUID"
    assert api.calls[0]["path"] == "/v2/groups/group-openid/files"
    assert api.calls[0]["body"] == {
        "file_type": 1,
        "url": "https://example.com/a.png",
        "srv_send_msg": False,
    }


async def test_url_upload_failure_is_not_retried_as_chunked_upload(workdir) -> None:
    api = _FakeApi()
    api.on("/files", OfficialApiError("url not reachable", code=850026))
    uploader = MediaUploader(NullLogger())

    with pytest.raises(MediaUploadError) as excinfo:
        await uploader.upload(
            api,
            kind="private",
            openid="user-openid",
            segment_type="image",
            source="http://127.0.0.1:8099/files/a.png",
        )

    assert excinfo.value.code == 850026
    # 只尝试了一次 URL 转存，没有下载/分片请求。
    assert len(api.calls) == 1
    assert api.calls[0]["path"] == "/v2/users/user-openid/files"
    assert api.calls[0]["body"]["url"] == "http://127.0.0.1:8099/files/a.png"


@pytest.mark.parametrize(
    "source_builder",
    [
        lambda path: "base64://YWJjZA==",
        lambda path: "data:image/png;base64,YWJjZA==",
        lambda path: path.as_uri(),
    ],
    ids=["base64", "data-uri", "file-uri"],
)
async def test_bytes_sources_use_chunked_upload(workdir, monkeypatch, source_builder) -> None:
    local_file = workdir / "a.png"
    local_file.write_bytes(b"abcd")
    api = _FakeApi()
    api.on("/upload_prepare", _prepare_payload(block_size=100, indexes=(0,)))
    api.on("/upload_part_finish", {"code": 0, "data": {}})
    api.on("/files", _OK_FILE)
    puts: list[bytes] = []

    async def fake_put(url: str, data: bytes) -> None:
        puts.append(data)

    monkeypatch.setattr(media_module, "_put_part", fake_put)
    uploader = MediaUploader(NullLogger())

    result = await uploader.upload(
        api,
        kind="group",
        openid="group-openid",
        segment_type="image",
        source=source_builder(local_file),
    )

    assert result.file_info == "FILE-INFO"
    assert puts == [b"abcd"]
    prepare = next(call for call in api.calls if call["path"].endswith("/upload_prepare"))
    assert prepare["body"]["file_size"] == "4"
    assert prepare["body"]["md5"] == hashlib.md5(b"abcd", usedforsecurity=False).hexdigest()
    assert prepare["body"]["sha1"] == hashlib.sha1(b"abcd", usedforsecurity=False).hexdigest()


async def test_quota_error_reports_chinese_reason(workdir) -> None:
    api = _FakeApi()
    api.on("/files", OfficialApiError("quota", code=40093002))
    uploader = MediaUploader(NullLogger())

    with pytest.raises(MediaUploadError) as excinfo:
        await uploader.upload(
            api,
            kind="group",
            openid="group-openid",
            segment_type="image",
            source="https://example.com/a.png",
        )

    assert "配额" in str(excinfo.value)
    assert excinfo.value.code == 40093002
    assert len(api.calls) == 1


async def test_retryable_40093001_is_retried(workdir, monkeypatch) -> None:
    api = _FakeApi()
    api.on("/files", OfficialApiError("transient", code=40093001), _OK_FILE)
    monkeypatch.setattr(media_module, "_RETRY_DELAY_SECONDS", 0.0)
    uploader = MediaUploader(NullLogger())

    result = await uploader.upload(
        api,
        kind="group",
        openid="group-openid",
        segment_type="image",
        source="https://example.com/a.png",
    )

    assert result.file_info == "FILE-INFO"
    assert len(api.calls) == 2


async def test_file_info_is_cached_until_ttl_expires(workdir) -> None:
    now = [0.0]
    api = _FakeApi()
    api.on("/files", dict(_OK_FILE))
    uploader = MediaUploader(NullLogger(), clock=lambda: now[0])

    kwargs = {
        "kind": "group",
        "openid": "group-openid",
        "segment_type": "image",
        "source": "https://example.com/a.png",
    }
    first = await uploader.upload(api, **kwargs)
    second = await uploader.upload(api, **kwargs)

    assert first == second
    assert len(api.calls) == 1

    now[0] = 61.0
    await uploader.upload(api, **kwargs)
    assert len(api.calls) == 2


async def test_missing_file_info_is_an_error(workdir) -> None:
    api = _FakeApi()
    api.on("/files", {"code": 0, "data": {}})
    uploader = MediaUploader(NullLogger())

    with pytest.raises(MediaUploadError):
        await uploader.upload(
            api,
            kind="group",
            openid="group-openid",
            segment_type="image",
            source="https://example.com/a.png",
        )


async def test_unsupported_segment_type_is_an_error(workdir) -> None:
    uploader = MediaUploader(NullLogger())

    with pytest.raises(MediaUploadError):
        await uploader.upload(
            _FakeApi(),
            kind="group",
            openid="group-openid",
            segment_type="face",
            source="https://example.com/a.png",
        )


async def test_missing_local_file_is_an_error(workdir) -> None:
    uploader = MediaUploader(NullLogger())

    with pytest.raises(MediaUploadError):
        await uploader.upload(
            _FakeApi(),
            kind="group",
            openid="group-openid",
            segment_type="image",
            source=str(workdir / "missing.png"),
        )


def test_media_file_is_frozen() -> None:
    media = MediaFile(file_info="FI", file_uuid="FU", ttl=1)
    assert media == MediaFile(file_info="FI", file_uuid="FU", ttl=1)
