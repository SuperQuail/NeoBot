"""B 站直播客户端（传输层可注入，便于离线测试）。

对照参考：amagi packages/core/src/runtime/execute.ts:389-428 的重试语义 ——
端点声明 retryOn 后，最多 DEFAULT_MAX_RETRIES + 1 = 4 次尝试，退避 1s / 2s / 4s。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from .errors import BilibiliAPIError, BilibiliTransportError
from .headers import live_room_headers
from .judge import judge
from .models import LiveRoomInfo, LiveRoomInit, UserCard, UserLiveStatus
from .urls import (
    live_room_info_url,
    live_room_init_url,
    user_card_url,
    user_live_status_url,
)

#: transport/retry.ts:43,46：默认重试 3 次（共 4 次尝试），退避基数 1s
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BASE_DELAY = 1.0
DEFAULT_TIMEOUT = 10.0


@dataclass(frozen=True)
class RawResponse:
    """传输层返回的原始响应。body 是解析后的 JSON 对象，或原始文本。"""

    status: int
    body: Any
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)


@runtime_checkable
class Transport(Protocol):
    async def request(
        self, *, method: str, url: str, headers: dict[str, str], timeout: float
    ) -> RawResponse: ...


class HttpxTransport:
    """基于 httpx 的默认传输实现（httpx 已是 NeoBot 本体依赖）。

    复用一个 AsyncClient：轮询每轮要打 N 个房间，每次请求都新建客户端等于丢掉
    连接池与 TLS 会话（代理下尤其慢）。插件 shutdown 时由 aclose() 关闭。
    """

    def __init__(self, *, follow_redirects: bool = False, client: Any = None) -> None:
        self._follow_redirects = follow_redirects
        self._client = client

    def _ensure_client(self) -> Any:
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(follow_redirects=self._follow_redirects)
        return self._client

    async def aclose(self) -> None:
        """关闭复用的客户端；可重复调用（插件 shutdown 会调用一次）。"""
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()

    async def request(
        self, *, method: str, url: str, headers: dict[str, str], timeout: float
    ) -> RawResponse:
        import httpx

        client = self._ensure_client()
        try:
            response = await client.request(method, url, headers=headers, timeout=timeout)
        except httpx.HTTPError as exc:  # 连接/超时/TLS 等
            raise BilibiliTransportError(f"请求失败: {exc}") from exc

        text = response.text
        body: Any = text
        stripped = text.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                body = json.loads(text)
            except json.JSONDecodeError:
                body = text
        return RawResponse(
            status=response.status_code,
            body=body,
            url=str(response.url),
            headers=dict(response.headers),
        )


class BilibiliLiveClient:
    """直播间 HTTP 接口封装（对应 amagi 的 bilibili live 三条端点）。"""

    def __init__(
        self,
        transport: Transport,
        *,
        cookie: str = "",
        user_agent: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_base_delay: float = DEFAULT_RETRY_BASE_DELAY,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._transport = transport
        self._cookie = cookie
        self._user_agent = user_agent
        self._timeout = timeout
        self._max_attempts = max(1, int(max_retries) + 1)
        self._retry_base_delay = retry_base_delay
        self._sleep = sleep
        self.retry_count = 0

    async def _get(self, url: str, *, room_id: int | str | None = None) -> RawResponse:
        headers = live_room_headers(
            room_id, cookie=self._cookie, user_agent=self._user_agent
        )
        attempt = 0
        while True:
            attempt += 1
            raw = await self._transport.request(
                method="GET", url=url, headers=headers, timeout=self._timeout
            )
            verdict = judge(raw.body, http_status=raw.status)
            if verdict.ok:
                return raw
            error = BilibiliAPIError(
                kind=verdict.kind,
                code=verdict.code,
                message=verdict.message,
                retryable=verdict.retryable,
                platform_code=verdict.platform_code,
                platform_message=verdict.platform_message,
                http_status=raw.status,
                raw=raw.body,
            )
            if not verdict.retryable or attempt >= self._max_attempts:
                raise error
            self.retry_count += 1
            await self._sleep(self._retry_base_delay * (2 ** (attempt - 1)))

    async def fetch_user_live_status(self, host_mid: int | str) -> UserLiveStatus:
        """uid → 直播状态 / 房间号（轮询开播最省流的接口）。"""
        raw = await self._get(user_live_status_url(host_mid))
        return UserLiveStatus.from_payload(raw.body)

    async def fetch_live_room_init(self, room_id: int | str) -> LiveRoomInit:
        """短号或真实房间号 → 房间基本信息（含真实 room_id / short_id / uid）。"""
        raw = await self._get(live_room_init_url(room_id), room_id=room_id)
        return LiveRoomInit.from_payload(raw.body)

    async def fetch_live_room_info(self, room_id: int | str) -> LiveRoomInfo:
        """真实房间号 → 直播间展示信息。"""
        raw = await self._get(live_room_info_url(room_id), room_id=room_id)
        return LiveRoomInfo.from_payload(raw.body)

    async def fetch_user_card(self, host_mid: int | str) -> UserCard:
        """uid → 主播昵称与头像（卡片渲染用）。"""
        raw = await self._get(user_card_url(host_mid))
        return UserCard.from_payload(raw.body)

    async def aclose(self) -> None:
        """释放传输层持有的连接（传输层没实现 aclose 就什么都不做）。"""
        close = getattr(self._transport, "aclose", None)
        if callable(close):
            await close()

