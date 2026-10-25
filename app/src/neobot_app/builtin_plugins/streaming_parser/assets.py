"""头像/封面等图片资源的下载与本地缓存。

渲染卡片需要主播头像与直播封面，都是 B 站 CDN 上的图片。这里做四件事：
1. 走本插件统一的请求头（Referer 指向直播间，避免被 CDN 拒绝）；
2. 落盘缓存，避免每次推送都重复下载、也避免平台抖动导致卡片缺图；
3. 转成 data URI 直接嵌进 HTML，渲染时不需要任何外部网络请求；
4. 失败重试 + 记日志：CDN 偶发失败会让卡片上出现一个空头像，必须能自己恢复。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from .bilibili.headers import DEFAULT_UA
from .logs import log_at

#: 常见图片格式的魔数探测（够用即可，B 站头像/封面只有这几种）
_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF8", "image/gif"),
    (b"RIFF", "image/webp"),
)

DEFAULT_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 0.4

#: 下载器签名：(url, headers, timeout) -> (status, body)
Downloader = Callable[[str, dict[str, str], float], Awaitable[tuple[int, bytes]]]


def sniff_mime(data: bytes) -> str:
    """按魔数判断图片类型；识别不了就按 jpeg 处理。"""
    for magic, mime in _MAGIC:
        if data.startswith(magic):
            return mime
    return "image/jpeg"


#: 重试没有意义的 4xx：URL 失效、被拒绝、内容已删除
_NON_RETRYABLE_STATUS = frozenset({400, 401, 403, 404, 405, 410, 451})


def is_retryable_status(status: int) -> bool:
    """3xx 重定向、408 超时、425 过早、429 限流与 5xx 都是暂时性失败。

    只有明确的「URL 没了 / 被拒绝」类 4xx 才值得直接放弃；把 3xx 与限流当成
    永久失败会让一张卡片永远缺图，直到缓存过期。
    """
    return status not in _NON_RETRYABLE_STATUS and status >= 300


class HttpxDownloader:
    """默认下载器：复用一个 httpx.AsyncClient，由 AssetCache.aclose 关闭。

    每次请求都新建 AsyncClient 等于每次重新建连（代理下尤其慢）：一次推送要拉
    头像 + 封面，还可能重试。这里按实例复用，插件 shutdown 时统一关掉。
    """

    def __init__(self, *, follow_redirects: bool = True, client: Any = None) -> None:
        self._follow_redirects = follow_redirects
        self._client = client

    def _ensure_client(self) -> Any:
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient()
        return self._client

    async def __call__(self, url: str, headers: dict[str, str], timeout: float) -> tuple[int, bytes]:
        client = self._ensure_client()
        # B 站 CDN 的图片地址会 302 到真实节点：跟随重定向，别把 302 当失败
        response = await client.get(
            url, headers=headers, timeout=timeout, follow_redirects=self._follow_redirects
        )
        return response.status_code, response.content

    async def aclose(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()


class AssetCache:
    """按 URL 哈希落盘的图片缓存，返回 data URI。"""

    def __init__(
        self,
        root: Path,
        *,
        timeout: float = 15.0,
        user_agent: str | None = None,
        ttl_days: int = 14,
        max_bytes: int = 8 * 1024 * 1024,
        attempts: int = DEFAULT_ATTEMPTS,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
        logger: Any = None,
        downloader: Downloader | None = None,
    ) -> None:
        self.root = Path(root)
        self.timeout = timeout
        self.user_agent = user_agent or DEFAULT_UA
        self.ttl_seconds = max(0, int(ttl_days)) * 86400
        self.max_bytes = max_bytes
        self.attempts = max(1, int(attempts))
        self.backoff_seconds = max(0.0, float(backoff_seconds))
        self._logger = logger
        # 注入的下载器由注入方负责关闭，只有自建的那个归本对象管
        self._owns_downloader = downloader is None
        self._download = downloader or HttpxDownloader()

    async def aclose(self) -> None:
        """关闭自建的下载器（可重复调用）；注入的下载器由调用方自己收尾。"""
        close = getattr(self._download, "aclose", None)
        if self._owns_downloader and callable(close):
            await close()

    def path_for(self, url: str) -> Path:
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
        return self.root / digest[:2] / digest

    def _read_cache(self, url: str) -> bytes | None:
        path = self.path_for(url)
        try:
            stat = path.stat()
        except OSError:
            return None
        if self.ttl_seconds and time.time() - stat.st_mtime > self.ttl_seconds:
            return None
        try:
            return path.read_bytes()
        except OSError:
            return None

    def _write_cache(self, url: str, data: bytes) -> None:
        path = self.path_for(url)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except OSError as exc:
            # 缓存写失败不影响本次使用：图片已经在内存里了
            log_at(self._logger, "debug", f"写入图片缓存失败: {exc!r}")

    def purge_expired(self) -> int:
        """删除过期缓存文件，返回删除数量。"""
        if not self.ttl_seconds or not self.root.exists():
            return 0
        removed = 0
        cutoff = time.time() - self.ttl_seconds
        for item in self.root.rglob("*"):
            if not item.is_file():
                continue
            try:
                if item.stat().st_mtime < cutoff:
                    item.unlink()
                    removed += 1
            except OSError:
                continue
        return removed

    def _headers(self) -> dict[str, str]:
        return {
            "user-agent": self.user_agent,
            "referer": "https://live.bilibili.com/",
            "accept": "image/webp,image/png,image/jpeg,image/*;q=0.8",
        }

    async def fetch_bytes(self, url: str) -> bytes | None:
        """取图片字节；命中缓存直接返回，失败按次数退避重试。"""
        if not url:
            return None
        cached = self._read_cache(url)
        if cached is not None:
            return cached
        headers = self._headers()
        last_error = ""
        for attempt in range(1, self.attempts + 1):
            try:
                status, data = await self._download(url, headers, self.timeout)
            except Exception as exc:
                last_error = repr(exc)
                status, data = 0, b""
            else:
                if status == 200 and data and len(data) <= self.max_bytes:
                    self._write_cache(url, data)
                    return data
                if status == 200:
                    # 200 却空/超限：可能是被截断的响应，重试一次有意义
                    last_error = "响应为空或超过大小上限"
                elif not is_retryable_status(status):
                    # 404/403 之类重试没有意义（URL 失效/被拒绝），直接放弃
                    log_at(self._logger, "debug", f"图片下载被拒绝 ({status})，不再重试: {url}")
                    return None
                else:
                    # 3xx / 408 / 429 / 5xx：重定向与限流都是暂时性的，继续退避重试
                    last_error = "HTTP " + str(status)
            if attempt < self.attempts:
                await asyncio.sleep(self.backoff_seconds * attempt)
        log_at(
            self._logger,
            "warning",
            "图片下载失败（已重试 " + str(self.attempts) + " 次）: " + url
            + "；最后一次错误: " + (last_error or "未知"),
        )
        return None

    async def fetch_data_uri(self, url: str) -> str:
        """取图片并转成 data URI；失败返回空串（渲染端自行降级）。"""
        data = await self.fetch_bytes(url)
        if not data:
            return ""
        mime = sniff_mime(data)
        encoded = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{encoded}"

