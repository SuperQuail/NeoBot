"""二维码登录：状态机、cookie 提取、PNG 渲染与异步轮询。"""

from __future__ import annotations

import importlib.util

import pytest

from neobot_app.bilibili.errors import BilibiliApiError, BilibiliAuthError
from neobot_app.bilibili.qr_login import (
    QR_STATE_EXPIRED,
    QR_STATE_PENDING,
    QR_STATE_REJECTED,
    QR_STATE_SCANNED,
    QR_STATE_SUCCESS,
    BilibiliQrLogin,
    QrCodeLogin,
    QrLoginCookieError,
    QrPollResult,
    make_qr_png,
)
from neobot_contracts.ports.logging import NullLogger

from ._fakes import FakeResponse, FakeSession

_GENERATE_PAYLOAD = {
    "code": 0,
    "data": {
        "url": "https://account.bilibili.com/h5/account-h5/auth/scan-web?qrcode_key=key-1",
        "qrcode_key": "key-1",
    },
}


def _login(session: FakeSession) -> BilibiliQrLogin:
    return BilibiliQrLogin(session=session)


def test_generate_parses_qrcode() -> None:
    session = FakeSession([FakeResponse(_GENERATE_PAYLOAD)])
    info = _login(session).generate()
    assert isinstance(info, QrCodeLogin)
    assert info.qrcode_key == "key-1"
    assert info.url.startswith("https://account.bilibili.com/")
    assert session.calls[0]["method"] == "GET"
    assert session.calls[0]["url"].endswith("/x/passport-login/web/qrcode/generate")
    assert session.headers["User-Agent"]


def test_generate_without_required_fields_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("neobot_app.bilibili.qr_login.time.sleep", lambda _delay: None)
    # 缺字段也算失败，会重试满 3 次后才抛。
    session = FakeSession([FakeResponse({"code": 0, "data": {}})] * 3)
    with pytest.raises(BilibiliApiError):
        _login(session).generate()


def test_generate_retries_twice_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("neobot_app.bilibili.qr_login.time.sleep", sleeps.append)
    session = FakeSession(
        [
            FakeResponse({"code": -412, "message": "请求被拦截"}),
            FakeResponse({"code": -352, "message": "风控校验失败"}),
            FakeResponse(_GENERATE_PAYLOAD),
        ]
    )
    info = _login(session).generate()
    assert info.qrcode_key == "key-1"
    assert sleeps == [0.5, 1.0]
    assert len(session.calls) == 3


def test_generate_raises_after_retries_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("neobot_app.bilibili.qr_login.time.sleep", lambda _delay: None)
    session = FakeSession([FakeResponse({"code": -412, "message": "请求被拦截"})] * 3)
    with pytest.raises(BilibiliApiError, match="-412"):
        _login(session).generate()
    assert len(session.calls) == 3


def test_make_qr_png_matches_dependency_state() -> None:
    png = make_qr_png("https://example.com")
    if importlib.util.find_spec("qrcode") is None:
        assert png is None
    else:
        assert png is not None
        assert png.startswith(b"\x89PNG")


@pytest.mark.parametrize(
    ("code", "state"),
    [
        (86101, QR_STATE_PENDING),
        (86090, QR_STATE_SCANNED),
        (86038, QR_STATE_EXPIRED),
        (86083, QR_STATE_REJECTED),
    ],
)
def test_poll_maps_bilibili_states(code: int, state: str) -> None:
    session = FakeSession([FakeResponse({"code": 0, "data": {"code": code, "message": state}})])
    result = _login(session).poll("key-1")
    assert result.state == state
    assert result.raw_code == code
    assert result.success is False
    assert session.calls[0]["params"] == {"qrcode_key": "key-1"}


def test_poll_success_extracts_cookies_from_redirect_url() -> None:
    cross_domain = (
        "https://passport.biligame.com/x/passport-login/web/crossDomain"
        "?DedeUserID=42&SESSDATA=sd%2Cvalue&bili_jct=jct-token"
    )
    response = FakeResponse(
        {"code": 0, "data": {"code": 0, "url": cross_domain, "refresh_token": "refresh-1"}}
    )
    spi = FakeResponse({"code": 0, "data": {"b_3": "buvid-from-spi"}})
    session = FakeSession([response, spi])
    result = _login(session).poll("key-1")
    assert result.success is True
    assert result.cookies == {
        "SESSDATA": "sd,value",
        "bili_jct": "jct-token",
        "DedeUserID": "42",
        "buvid3": "buvid-from-spi",
    }
    assert result.refresh_token == "refresh-1"
    assert session.calls[-1]["url"].endswith("/x/frontend/finger/spi")


def test_poll_success_collects_cookies_from_response_headers() -> None:
    response = FakeResponse(
        {"code": 0, "data": {"code": 0, "url": "", "refresh_token": "rt"}},
        cookies={
            "SESSDATA": "sd",
            "bili_jct": "jct",
            "DedeUserID": "7",
            "buvid3": "buvid-from-cookie",
        },
    )
    session = FakeSession([response])
    result = _login(session).poll("key-1")
    assert result.cookies["DedeUserID"] == "7"
    assert result.cookies["buvid3"] == "buvid-from-cookie"
    # 已有 buvid3，不应再请求 spi 接口。
    assert len(session.calls) == 1


def test_poll_success_without_required_cookies_raises() -> None:
    session = FakeSession(
        [FakeResponse({"code": 0, "data": {"code": 0, "url": "", "refresh_token": "rt"}})]
    )
    with pytest.raises(BilibiliApiError, match="SESSDATA"):
        _login(session).poll("key-1")


def test_poll_success_allows_missing_dedeuserid() -> None:
    response = FakeResponse(
        {"code": 0, "data": {"code": 0, "url": "", "refresh_token": "rt"}},
        cookies={"SESSDATA": "sd", "bili_jct": "jct", "buvid3": "b3"},
    )
    session = FakeSession([response])
    result = _login(session).poll("key-1")
    assert result.success is True
    assert "DedeUserID" not in result.cookies
    assert result.cookies["SESSDATA"] == "sd"


_CROSS_DOMAIN_URL = "https://passport.biligame.com/x/passport-login/web/crossDomain"


def test_poll_success_gets_cookies_from_cross_domain_url() -> None:
    poll = FakeResponse(
        {"code": 0, "data": {"code": 0, "url": _CROSS_DOMAIN_URL, "refresh_token": "rt"}}
    )
    redirect = FakeResponse(
        cookies={"SESSDATA": "sd", "bili_jct": "jct", "DedeUserID": "7", "buvid3": "b3"}
    )
    session = FakeSession([poll, redirect])
    result = _login(session).poll("key-1")
    assert result.cookies["SESSDATA"] == "sd"
    assert result.cookies["bili_jct"] == "jct"
    assert result.cookies["DedeUserID"] == "7"
    # 必须按 crossDomain 流程真的 GET 了 data.url（同一 session）。
    assert [call["url"] for call in session.calls] == [
        "https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
        _CROSS_DOMAIN_URL,
    ]


def test_poll_success_missing_required_cookies_after_cross_domain_raises() -> None:
    poll = FakeResponse(
        {"code": 0, "data": {"code": 0, "url": _CROSS_DOMAIN_URL, "refresh_token": "rt"}}
    )
    session = FakeSession([poll, FakeResponse()])
    with pytest.raises(BilibiliApiError, match="SESSDATA"):
        _login(session).poll("key-1")
    assert session.calls[-1]["url"] == _CROSS_DOMAIN_URL


def test_poll_root_auth_error_raises_auth_error() -> None:
    session = FakeSession([FakeResponse({"code": -101, "message": "账号未登录"})])
    with pytest.raises(BilibiliAuthError):
        _login(session).poll("key-1")


def test_poll_unknown_state_raises_api_error() -> None:
    session = FakeSession([FakeResponse({"code": 0, "data": {"code": 12345, "message": "?"}})])
    with pytest.raises(BilibiliApiError):
        _login(session).poll("key-1")


async def test_async_wait_polls_until_success() -> None:
    login = _login(FakeSession())
    results = [
        QrPollResult(state=QR_STATE_PENDING, raw_code=86101),
        QrPollResult(state=QR_STATE_SCANNED, raw_code=86090),
        QrPollResult(
            state=QR_STATE_SUCCESS,
            raw_code=0,
            message="ok",
            cookies={"SESSDATA": "s", "bili_jct": "j", "DedeUserID": "1"},
            refresh_token="rt",
        ),
    ]
    login.poll = lambda _key: results.pop(0)  # type: ignore[method-assign]
    seen: list[str] = []

    async def on_status(result: QrPollResult) -> None:
        seen.append(result.state)

    final = await login.async_wait("key-1", on_status=on_status, interval=0, timeout=5)
    assert final.success is True
    assert seen == [QR_STATE_PENDING, QR_STATE_SCANNED, QR_STATE_SUCCESS]
    assert results == []


async def test_async_wait_timeout_returns_expired() -> None:
    login = _login(FakeSession())
    login.poll = lambda _key: QrPollResult(state=QR_STATE_PENDING, raw_code=86101)  # type: ignore[method-assign]
    result = await login.async_wait("key-1", interval=0, timeout=0.02)
    assert result.state == QR_STATE_EXPIRED
    assert "超时" in result.message


async def test_login_emits_qr_and_status_callbacks() -> None:
    session = FakeSession(
        [
            FakeResponse(_GENERATE_PAYLOAD),
            FakeResponse(
                {"code": 0, "data": {"code": 0, "url": "", "refresh_token": "rt"}},
                cookies={
                    "SESSDATA": "s",
                    "bili_jct": "j",
                    "DedeUserID": "7",
                    "buvid3": "b3",
                },
            ),
        ]
    )
    login = _login(session)
    qr_codes: list[QrCodeLogin] = []
    statuses: list[str] = []

    def on_qr(info: QrCodeLogin) -> None:
        qr_codes.append(info)

    async def on_status(result: QrPollResult) -> None:
        statuses.append(result.state)

    result = await login.login(on_qr=on_qr, on_status=on_status, interval=0, timeout=5)
    assert result.success is True
    assert [info.qrcode_key for info in qr_codes] == ["key-1"]
    assert statuses == [QR_STATE_SUCCESS]


async def test_async_wait_keeps_polling_after_poll_error() -> None:
    login = _login(FakeSession())
    outcomes: list = [
        BilibiliApiError(-412, "请求被风控拦截"),
        QrPollResult(state=QR_STATE_PENDING, raw_code=86101),
        QrPollResult(
            state=QR_STATE_SUCCESS,
            raw_code=0,
            cookies={"SESSDATA": "s", "bili_jct": "j"},
        ),
    ]
    calls: list[int] = []

    def flaky_poll(_key: str) -> QrPollResult:
        calls.append(1)
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    login.poll = flaky_poll  # type: ignore[method-assign]
    seen: list[str] = []

    async def on_status(result: QrPollResult) -> None:
        seen.append(result.state)

    final = await login.async_wait("key-1", on_status=on_status, interval=0, timeout=5)
    assert final.success is True
    assert len(calls) == 3  # 第一次抛错后没有提前退出
    assert seen == [QR_STATE_PENDING, QR_STATE_SUCCESS]
    assert outcomes == []


async def test_async_wait_retries_unknown_state_code() -> None:
    session = FakeSession(
        [
            FakeResponse({"code": 0, "data": {"code": 99999, "message": "?"}}),
            FakeResponse(
                {"code": 0, "data": {"code": 0, "url": "", "refresh_token": "rt"}},
                cookies={"SESSDATA": "s", "bili_jct": "j", "buvid3": "b3"},
            ),
        ]
    )
    result = await _login(session).async_wait("key-1", interval=0, timeout=5)
    assert result.success is True
    assert len(session.calls) == 2


async def test_async_wait_returns_rejected() -> None:
    login = _login(FakeSession())
    login.poll = lambda _key: QrPollResult(  # type: ignore[method-assign]
        state=QR_STATE_REJECTED, raw_code=86083, message="用户拒绝登录"
    )
    result = await login.async_wait("key-1", interval=0, timeout=5)
    assert result.state == QR_STATE_REJECTED


async def test_async_wait_timeout_when_poll_keeps_failing() -> None:
    login = _login(FakeSession())

    def failing_poll(_key: str) -> QrPollResult:
        raise BilibiliApiError(-1, "网络错误")

    login.poll = failing_poll  # type: ignore[method-assign]
    result = await login.async_wait("key-1", interval=0, timeout=0.02)
    assert result.state == QR_STATE_EXPIRED
    assert "超时" in result.message


async def test_async_wait_treats_cookie_error_as_terminal() -> None:
    login = _login(FakeSession())

    def failing_poll(_key: str) -> QrPollResult:
        raise QrLoginCookieError(-1, "登录成功但未取到 cookie: SESSDATA")

    login.poll = failing_poll  # type: ignore[method-assign]
    # 已经确认登录但拿不到凭证：直接作为终态失败，不要等到超时再报"二维码失效"。
    with pytest.raises(QrLoginCookieError):
        await login.async_wait("key-1", interval=0, timeout=5)


class _RecordingLogger(NullLogger):
    """记录 warning 文案，用来断言日志里不带凭证。"""

    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warning(self, msg: str, **kw) -> None:  # type: ignore[override]
        self.warnings.append(msg)


def test_poll_success_prefers_response_cookie_over_url_parameter() -> None:
    response = FakeResponse(
        {
            "code": 0,
            "data": {
                "code": 0,
                "url": (
                    "https://passport.biligame.com/x/passport-login/web/crossDomain"
                    "?SESSDATA=from-url&bili_jct=url-jct"
                ),
                "refresh_token": "rt",
            },
        },
        cookies={"SESSDATA": "from-set-cookie", "bili_jct": "jct", "buvid3": "b3"},
    )
    result = _login(FakeSession([response])).poll("key-1")
    assert result.cookies["SESSDATA"] == "from-set-cookie"
    assert result.cookies["bili_jct"] == "jct"


def test_poll_success_fills_missing_cookie_from_session_jar() -> None:
    session = FakeSession()
    session.cookies.set("DedeUserID", "9", domain=".bilibili.com")
    session.cookies.set("buvid3", "b3", domain=".bilibili.com")
    session.queue(
        FakeResponse(
            {
                "code": 0,
                "data": {
                    "code": 0,
                    "url": "https://passport.biligame.com/x?SESSDATA=sd&bili_jct=jct",
                    "refresh_token": "",
                },
            }
        )
    )
    result = _login(session).poll("key-1")
    assert result.cookies["SESSDATA"] == "sd"
    assert result.cookies["DedeUserID"] == "9"
    assert result.cookies["buvid3"] == "b3"


def test_poll_success_jar_conflict_is_treated_as_missing_field() -> None:
    """跨域登录过的会话里同名 cookie 并存：jar.get 抛 CookieConflictError，不能向上冒。"""
    session = FakeSession()
    session.cookies.set("SESSDATA", "old-bili", domain=".bilibili.com")
    session.cookies.set("SESSDATA", "old-game", domain=".biligame.com")
    session.queue(
        FakeResponse({"code": 0, "data": {"code": 0, "url": "", "refresh_token": ""}})
    )
    with pytest.raises(QrLoginCookieError, match="SESSDATA"):
        _login(session).poll("key-1")


def test_close_keeps_external_session_open() -> None:
    own = BilibiliQrLogin()
    own.close()
    own.close()  # 重复关闭不抛错

    external = FakeSession()
    BilibiliQrLogin(session=external).close()
    assert external.closed is False


def test_untrusted_cross_domain_warning_hides_url_query() -> None:
    logger = _RecordingLogger()
    session = FakeSession(
        [
            FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "code": 0,
                        "url": (
                            "https://evil.example/crossDomain"
                            "?SESSDATA=&bili_jct=jct&refresh_token=secret-token"
                        ),
                        "refresh_token": "",
                    },
                }
            )
        ]
    )
    with pytest.raises(QrLoginCookieError):
        BilibiliQrLogin(session=session, logger=logger).poll("key-1")
    assert any("evil.example" in message for message in logger.warnings)
    assert all("secret-token" not in message for message in logger.warnings)


def test_poll_skips_untrusted_cross_domain_url() -> None:
    session = FakeSession(
        [
            FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "code": 0,
                        "url": "https://evil.example/crossDomain?SESSDATA=",
                        "refresh_token": "",
                    },
                }
            )
        ]
    )
    login = _login(session)
    with pytest.raises(QrLoginCookieError):
        login.poll("key-1")
    # 远端给的 URL 不可信时不去请求，避免 SSRF。
    assert len(session.calls) == 1

