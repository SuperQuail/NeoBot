"""QQ 官方富媒体上传：URL 直传、分片上传与 file_info 缓存。

官方要求先把媒体上传成 file_info，再带 media 字段发消息；URL 来源只走官方
URL 转存，本地/Base64 来源走分片上传。上传失败直接报错，不做下载回退。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, unquote_to_bytes, urlparse

from neobot_contracts.ports.logging import Logger, NullLogger

#: OneBot 消息段类型 → 官方 file_type（1 图片 / 2 视频 / 3 语音 / 4 文件）。
_FILE_TYPES = {"image": 1, "video": 2, "record": 3, "voice": 3, "file": 4}
#: 官方接口明确支持的扩展名；其它扩展名在发送前失败，不赌平台转码。
_ALLOWED_EXTENSIONS = {
    1: frozenset({"png", "jpg", "jpeg", "gif", "webp", "bmp"}),
    2: frozenset({"mp4"}),
    3: frozenset({"silk", "slk", "mp3", "wav", "ogg"}),
}
_ENDPOINTS = {"group": "/v2/groups/{openid}", "private": "/v2/users/{openid}"}
#: 40093001 是官方分片接口的临时错误，可重试；40093002 是当日配额用尽。
_RETRYABLE_CODE = 40093001
_QUOTA_CODE = 40093002
_RETRY_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 1.0
_MD5_10M_BYTES = 10_002_432
_PUT_TIMEOUT_SECONDS = 300.0
_MAX_MEDIA_BYTES = 200 * 1024 * 1024
_CACHE_MAX_ENTRIES = 128


class MediaUploadError(RuntimeError):
    """官方富媒体上传失败；消息可直接展示给用户。"""

    def __init__(self, message: str, *, code: int | str | None = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class MediaFile:
    """一次上传的结果；发送消息时放进 media 字段。"""

    file_info: str
    file_uuid: str = ""
    ttl: int = 0


def api_data(body: dict[str, Any]) -> dict[str, Any]:
    """官方 HTTP 响应取 data 段；部分接口直接返回对象本身。"""
    data = body.get("data")
    return data if isinstance(data, dict) else body


def _validate_extension(source: str, file_name: str, file_type: int) -> None:
    """有扩展名时按官方支持列表预检；无扩展名/任意文件交给平台。"""
    allowed = _ALLOWED_EXTENSIONS.get(file_type)
    if not allowed:
        return
    suffix = Path(file_name).suffix if file_name else ""
    if not suffix:
        candidate = urlparse(source).path if source.startswith(("http://", "https://")) else source
        suffix = Path(unquote(candidate)).suffix
    ext = suffix.lstrip(".").strip().casefold()
    if ext and ext not in allowed:
        raise MediaUploadError(
            f"官方富媒体不支持 .{ext} 格式（file_type={file_type}，允许：{', '.join(sorted(allowed))}）"
        )



class MediaUploader:
    """按目标会话上传媒体；同一来源在 ttl 内复用 file_info。"""

    def __init__(
        self,
        logger: Logger | None = None,
        *,
        clock: Any = time.monotonic,
    ) -> None:
        self._logger = logger if logger is not None else NullLogger()
        self._clock = clock
        self._cache: dict[tuple[str, str, int, str], tuple[MediaFile, float]] = {}

    async def upload(
        self,
        api: Any,
        *,
        kind: str,
        openid: str,
        segment_type: str,
        source: str,
        file_name: str = "",
        timeout: float = _PUT_TIMEOUT_SECONDS,
    ) -> MediaFile:
        """上传一个消息段里的媒体来源（http(s)/file:///base64:///data:/本地路径）。"""
        file_type = _FILE_TYPES.get(str(segment_type or "").strip().casefold())
        if file_type is None:
            raise MediaUploadError(f"官方协议不支持发送该消息段: {segment_type}")
        if kind not in _ENDPOINTS:
            raise MediaUploadError(f"官方协议不支持发送到该会话类型: {kind}")
        if not openid:
            raise MediaUploadError("官方协议缺少目标 openid，无法上传富媒体")
        source = str(source or "").strip()
        if not source:
            raise MediaUploadError("富媒体来源为空")
        _validate_extension(source, file_name, file_type)

        if source.startswith(("http://", "https://")):
            # 官方只认它能访问到的 URL；拉不到就报错，不下载后改走分片。
            cache_key = (kind, openid, file_type, source)
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached
            result = await self._upload_url(api, kind, openid, file_type, source, file_name, timeout)
        else:
            data, name = _read_source(source, file_name)
            # 本地/内联来源按内容哈希缓存：app 的卡片图用固定文件名覆写
            # （help-{perm}-{page}.png / reload.png），Windows 上快速覆写时
            # st_mtime_ns 可能同毫秒不变，只有内容才能可靠区分新旧图。
            digest = hashlib.sha1(data, usedforsecurity=False).hexdigest()
            cache_key = (kind, openid, file_type, f"{source}|{digest}")
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached
            result = await self._upload_bytes(api, kind, openid, file_type, data, name, timeout)
        self._cache_put(cache_key, result)
        return result

    # ── URL 直传 ────────────────────────────────────────────────────

    async def _upload_url(
        self,
        api: Any,
        kind: str,
        openid: str,
        file_type: int,
        url: str,
        file_name: str,
        timeout: float,
    ) -> MediaFile:
        body: dict[str, Any] = {"file_type": file_type, "url": url, "srv_send_msg": False}
        if file_name:
            body["file_name"] = file_name
        payload = await _post(api, _base_path(kind, openid), "/files", body, timeout)
        return _media_from_payload(payload)

    # ── 分片上传 ────────────────────────────────────────────────────

    async def _upload_bytes(
        self,
        api: Any,
        kind: str,
        openid: str,
        file_type: int,
        data: bytes,
        file_name: str,
        timeout: float,
    ) -> MediaFile:
        if len(data) > _MAX_MEDIA_BYTES:
            raise MediaUploadError("富媒体超过 200MB 上限，官方协议无法发送")
        base_path = _base_path(kind, openid)
        prepare_body = {
            "file_type": file_type,
            "file_size": str(len(data)),
            "file_name": file_name or "media",
            **_hash_bytes(data),
        }
        prepare = await _post(api, base_path, "/upload_prepare", prepare_body, timeout)
        try:
            upload_id = str(prepare.get("upload_id") or "")
            block_size = int(prepare.get("block_size") or 0)
            parts = prepare.get("parts")
        except (TypeError, ValueError) as exc:
            raise MediaUploadError("官方分片上传响应格式异常") from exc
        if not upload_id or block_size <= 0 or not isinstance(parts, list) or not parts:
            raise MediaUploadError("官方分片上传准备响应缺少 upload_id/block_size/parts")

        indexes: list[int] = []
        for part in parts:
            if not isinstance(part, dict):
                raise MediaUploadError("官方分片上传准备响应含非法分片")
            try:
                indexes.append(int(part.get("index", part.get("part_index"))))
            except (TypeError, ValueError) as exc:
                raise MediaUploadError("官方分片上传准备响应含非法分片号") from exc
        base_index = min(indexes)
        for part in parts:
            assert isinstance(part, dict)
            part_index = int(part.get("index", part.get("part_index")))
            part_size = int(part.get("block_size") or block_size)
            offset = (part_index - base_index) * block_size
            chunk = data[offset : offset + part_size]
            if not chunk:
                raise MediaUploadError(f"官方分片 {part_index} 超出媒体长度")
            presigned_url = str(part.get("presigned_url") or "")
            if not presigned_url:
                raise MediaUploadError(f"官方分片 {part_index} 缺少上传地址")
            await _put_part(presigned_url, chunk)
            finish_body = {
                "upload_id": upload_id,
                "part_index": part_index,
                "block_size": str(len(chunk)),
                "md5": hashlib.md5(chunk, usedforsecurity=False).hexdigest(),
            }
            await _post(api, base_path, "/upload_part_finish", finish_body, timeout)

        merge_body = {
            "file_type": file_type,
            "srv_send_msg": False,
            "file_name": file_name or "media",
            "upload_id": upload_id,
        }
        merged = await _post(api, base_path, "/files", merge_body, timeout)
        media = _media_from_payload(merged)
        self._logger.info("官方富媒体分片上传完成", file_name=file_name, bytes=len(data))
        return media

    # ── file_info 缓存 ──────────────────────────────────────────────

    def _cache_get(self, key: tuple[str, str, int, str]) -> MediaFile | None:
        cached = self._cache.get(key)
        if cached is None:
            return None
        media, expires_at = cached
        if self._clock() >= expires_at:
            self._cache.pop(key, None)
            return None
        return media

    def _cache_put(self, key: tuple[str, str, int, str], media: MediaFile) -> None:
        if media.ttl <= 0:
            return
        self._cache[key] = (media, self._clock() + media.ttl)
        while len(self._cache) > _CACHE_MAX_ENTRIES:
            self._cache.pop(next(iter(self._cache)))


def _base_path(kind: str, openid: str) -> str:
    return _ENDPOINTS[kind].format(openid=openid)


async def _post(
    api: Any,
    base_path: str,
    suffix: str,
    body: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    """带 40093001/40093002 语义的官方文件接口 POST。"""
    last_error: Exception | None = None
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            payload = await api.request("POST", base_path + suffix, body=body, timeout=timeout)
        except Exception as exc:
            code = getattr(exc, "code", None)
            if code == _QUOTA_CODE:
                raise MediaUploadError(
                    "QQ 官方文件上传今日配额已用尽（40093002），请明天再试",
                    code=code,
                ) from exc
            last_error = exc
            if code == _RETRYABLE_CODE and attempt < _RETRY_ATTEMPTS - 1:
                await asyncio.sleep(_RETRY_DELAY_SECONDS)
                continue
            raise MediaUploadError(f"上传官方富媒体失败：{exc}", code=code) from exc
        return api_data(payload)
    raise MediaUploadError(f"上传官方富媒体失败：{last_error}")


async def _put_part(presigned_url: str, data: bytes) -> None:
    """把一片数据 PUT 到官方给的预签名地址（该地址不要带鉴权头）。"""
    import aiohttp

    try:
        timeout = aiohttp.ClientTimeout(total=_PUT_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.put(
                presigned_url,
                data=data,
                headers={"Content-Length": str(len(data))},
            ) as response:
                if not 200 <= int(response.status) < 300:
                    text = (await response.text(errors="replace"))[:200]
                    raise MediaUploadError(f"官方分片上传地址返回 HTTP {response.status}: {text}")
    except MediaUploadError:
        raise
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        raise MediaUploadError(f"官方分片上传失败: {type(exc).__name__}: {exc}") from exc


def _read_source(source: str, file_name: str) -> tuple[bytes, str]:
    """解析 file:///、base64://、data: 与本地路径，返回字节和文件名。"""
    if source.startswith("file://"):
        path = _path_from_file_uri(source)
        return _read_local(path, file_name), file_name or path.name
    if source.startswith("base64://"):
        try:
            data = base64.b64decode(source[len("base64://") :], validate=True)
        except Exception as exc:
            raise MediaUploadError("base64 富媒体解码失败") from exc
        return data, file_name or "media"
    if source.startswith("data:"):
        header, _, payload = source.partition(",")
        if not payload:
            raise MediaUploadError("data: 富媒体缺少内容")
        try:
            if ";base64" in header:
                data = base64.b64decode(payload, validate=True)
            else:
                data = unquote_to_bytes(payload)
        except Exception as exc:
            raise MediaUploadError("data: 富媒体解码失败") from exc
        return data, file_name or "media"
    path = Path(source).expanduser()
    if path.is_file():
        return _read_local(path, file_name), file_name or path.name
    raise MediaUploadError(f"无法读取富媒体来源: {source}")


def _path_from_file_uri(source: str) -> Path:
    path = Path(unquote(urlparse(source).path))
    text = str(path)
    # Windows 的 file:///D:/x 解析后是 /D:/x（Path 转成 \D:\x），去掉盘符前的分隔符。
    if len(text) >= 3 and text[0] in ("/", "\\") and text[2] == ":":
        return Path(text[1:])
    return path


def _read_local(path: Path, file_name: str) -> bytes:
    if not path.is_file():
        raise MediaUploadError(f"本地富媒体文件不存在: {path}")
    size = path.stat().st_size
    if size > _MAX_MEDIA_BYTES:
        raise MediaUploadError("富媒体超过 200MB 上限，官方协议无法发送")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise MediaUploadError(f"读取本地富媒体失败: {path}: {exc}") from exc


def _hash_bytes(data: bytes) -> dict[str, str]:
    prefix = data[:_MD5_10M_BYTES]
    return {
        "md5": hashlib.md5(data, usedforsecurity=False).hexdigest(),
        "sha1": hashlib.sha1(data, usedforsecurity=False).hexdigest(),
        "md5_10m": hashlib.md5(prefix, usedforsecurity=False).hexdigest(),
    }


def _media_from_payload(payload: dict[str, Any]) -> MediaFile:
    file_info = str(payload.get("file_info") or "")
    if not file_info:
        raise MediaUploadError("官方富媒体上传响应缺少 file_info")
    try:
        ttl = int(payload.get("ttl") or 0)
    except (TypeError, ValueError):
        ttl = 0
    return MediaFile(
        file_info=file_info,
        file_uuid=str(payload.get("file_uuid") or ""),
        ttl=ttl,
    )
