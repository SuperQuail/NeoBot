"""客户端行为：请求头、解析、重试与退避（离线，全部走假传输层）。"""

from __future__ import annotations

import pytest
from conftest import json_response, text_response

from bilibili.client import BilibiliLiveClient, HttpxTransport
from bilibili.errors import BilibiliAPIError, BilibiliTransportError


def make_client(fake_transport, responses, slept, sleep, **kwargs):
    transport = fake_transport(responses)
    client = BilibiliLiveClient(transport, sleep=sleep, **kwargs)
    return client, transport


class TestSuccessPath:
    async def test_fetch_live_room_init(self, load_fixture, fake_transport, sleep_recorder):
        slept, sleep = sleep_recorder
        payload = load_fixture("live_room_init.json")
        client, transport = make_client(fake_transport, [json_response(payload)], slept, sleep)

        init = await client.fetch_live_room_init(5440)

        assert init.room_id == 21452505
        assert len(transport.calls) == 1
        call = transport.calls[0]
        assert call["method"] == "GET"
        assert call["url"].endswith("/room/v1/Room/room_init?id=5440")
        assert call["headers"]["referer"] == "https://live.bilibili.com/5440"
        assert call["timeout"] == 10.0
        assert slept == []

    async def test_fetch_user_live_status(self, load_fixture, fake_transport, sleep_recorder):
        slept, sleep = sleep_recorder
        payload = load_fixture("user_live_status.json")
        client, transport = make_client(fake_transport, [json_response(payload)], slept, sleep)

        status = await client.fetch_user_live_status(401742377)

        assert status.room_id == 21452505
        assert status.is_living is True
        assert transport.calls[0]["url"].endswith("getRoomInfoOld?mid=401742377")
        assert transport.calls[0]["headers"]["referer"] == "https://live.bilibili.com/"

    async def test_fetch_live_room_info(self, load_fixture, fake_transport, sleep_recorder):
        slept, sleep = sleep_recorder
        payload = load_fixture("live_room_info.json")
        client, transport = make_client(fake_transport, [json_response(payload)], slept, sleep)

        info = await client.fetch_live_room_info(21452505)

        assert info.title == "测试直播间标题"
        assert info.cover.startswith("https://example.invalid/user_cover")
        assert transport.calls[0]["url"].endswith("get_info?room_id=21452505")

    async def test_cookie_is_forwarded(self, load_fixture, fake_transport, sleep_recorder):
        slept, sleep = sleep_recorder
        payload = load_fixture("live_room_init.json")
        client, transport = make_client(
            fake_transport, [json_response(payload)], slept, sleep, cookie="SESSDATA=abc"
        )

        await client.fetch_live_room_init(1)

        assert transport.calls[0]["headers"]["cookie"] == "SESSDATA=abc"


class TestRetry:
    async def test_risk_control_then_success(self, load_fixture, fake_transport, sleep_recorder):
        slept, sleep = sleep_recorder
        payload = load_fixture("live_room_init.json")
        client, transport = make_client(
            fake_transport,
            [json_response({"code": -412, "message": "请求被拦截"}), json_response(payload)],
            slept,
            sleep,
        )

        init = await client.fetch_live_room_init(5440)

        assert init.room_id == 21452505
        assert len(transport.calls) == 2
        assert slept == [1.0]
        assert client.retry_count == 1

    async def test_risk_control_gives_up_after_four_attempts(
        self, fake_transport, sleep_recorder
    ):
        slept, sleep = sleep_recorder
        client, transport = make_client(
            fake_transport,
            [json_response({"code": -412, "message": "请求被拦截"})] * 4,
            slept,
            sleep,
        )

        with pytest.raises(BilibiliAPIError) as excinfo:
            await client.fetch_live_room_init(5440)

        error = excinfo.value
        assert error.retryable is True
        assert error.kind == "risk"
        assert error.platform_code == -412
        assert len(transport.calls) == 4
        # amagi transport/retry.ts:94-95 的退避：1s / 2s / 4s
        assert slept == [1.0, 2.0, 4.0]

    async def test_not_logged_in_does_not_retry(self, fake_transport, sleep_recorder):
        slept, sleep = sleep_recorder
        client, transport = make_client(
            fake_transport,
            [json_response({"code": -101, "message": "账号未登录"})],
            slept,
            sleep,
        )

        with pytest.raises(BilibiliAPIError) as excinfo:
            await client.fetch_live_room_init(5440)

        assert excinfo.value.code == "COOKIE_EXPIRED"
        assert len(transport.calls) == 1
        assert slept == []

    async def test_antibot_page_retries_then_raises(self, fake_transport, sleep_recorder):
        slept, sleep = sleep_recorder
        client, transport = make_client(
            fake_transport,
            [text_response("<html>waf</html>")] * 4,
            slept,
            sleep,
        )

        with pytest.raises(BilibiliAPIError) as excinfo:
            await client.fetch_user_live_status(1)

        assert excinfo.value.code == "ANTIBOT_PAGE"
        assert len(transport.calls) == 4

    async def test_transport_error_is_not_retried_by_client(
        self, fake_transport, sleep_recorder
    ):
        """传输层异常由传输层自己决定重试；客户端不再叠加一层。"""
        slept, sleep = sleep_recorder
        client, transport = make_client(
            fake_transport, [BilibiliTransportError("boom")], slept, sleep
        )

        with pytest.raises(BilibiliTransportError):
            await client.fetch_live_room_init(5440)

        assert len(transport.calls) == 1
        assert slept == []

    async def test_max_attempts_is_configurable(self, fake_transport, sleep_recorder):
        slept, sleep = sleep_recorder
        client, transport = make_client(
            fake_transport,
            [json_response({"code": -412})] * 2,
            slept,
            sleep,
            max_retries=0,
        )

        with pytest.raises(BilibiliAPIError):
            await client.fetch_live_room_init(5440)

        assert len(transport.calls) == 1
        assert slept == []


class TestRequestValidation:
    async def test_invalid_room_id_fails_before_any_request(
        self, fake_transport, sleep_recorder
    ):
        slept, sleep = sleep_recorder
        client, transport = make_client(fake_transport, [], slept, sleep)

        with pytest.raises(ValueError):
            await client.fetch_live_room_init("abc")

        assert transport.calls == []


class StubHttpResponse:
    status_code = 200
    text = '{"code": 0, "data": {}}'
    headers: dict[str, str] = {}
    url = "https://api.live.bilibili.com/"

    def __init__(self) -> None:
        self.closed = False


class StubHttpClient:
    """替身 httpx.AsyncClient：记录调用，验证连接被复用而不是每次重建。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, float | None]] = []
        self.closed = 0

    async def request(self, method, url, *, headers=None, timeout=None):  # noqa: ANN001
        self.calls.append((method, url, timeout))
        return StubHttpResponse()

    async def aclose(self) -> None:
        self.closed += 1


class TestTransportReuse:
    async def test_one_client_is_reused_across_requests(self):
        stub = StubHttpClient()
        transport = HttpxTransport(client=stub)

        first = await transport.request(method="GET", url="https://x/1", headers={}, timeout=3.0)
        second = await transport.request(method="GET", url="https://x/2", headers={}, timeout=7.0)

        assert first.status == second.status == 200
        assert [call[1] for call in stub.calls] == ["https://x/1", "https://x/2"]
        # 超时按请求传，复用客户端不改变 per-request 超时
        assert [call[2] for call in stub.calls] == [3.0, 7.0]
        await transport.aclose()
        assert stub.closed == 1

    async def test_aclose_is_idempotent(self):
        stub = StubHttpClient()
        transport = HttpxTransport(client=stub)

        await transport.aclose()
        await transport.aclose()

        assert stub.closed == 1

    async def test_bilibili_client_aclose_delegates_to_transport(self):
        class ClosingTransport:
            def __init__(self) -> None:
                self.closed = 0

            async def request(self, **kwargs):  # noqa: ANN003
                raise AssertionError("不该发请求")

            async def aclose(self) -> None:
                self.closed += 1

        transport = ClosingTransport()
        client = BilibiliLiveClient(transport)

        await client.aclose()

        assert transport.closed == 1

