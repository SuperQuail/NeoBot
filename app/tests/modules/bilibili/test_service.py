"""BilibiliService：休眠、登录态校验、扫码登录与动态发布门面。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from neobot_app.bilibili.cookie_provider import BilibiliCookieStore
from neobot_app.bilibili.errors import BilibiliAuthError
from neobot_app.bilibili.qr_login import QrCodeLogin, QrPollResult
from neobot_app.bilibili.service import BilibiliService

from ._fakes import FakeClient

_CONFIG = SimpleNamespace(cookie_file="data/bilibili/cookies.json", login_timeout_seconds=30)
_COOKIES = {
    "SESSDATA": "sess",
    "bili_jct": "jct",
    "DedeUserID": "42",
    "buvid3": "buvid",
}


def _make_service(
    tmp_path,
    *,
    info: dict | None = None,
) -> tuple[BilibiliService, FakeClient, object]:
    fake_client = FakeClient(info=info or {})
    created: list[tuple[tuple, dict]] = []

    def factory(*args, **kwargs):
        created.append((args, kwargs))
        return fake_client

    service = BilibiliService(
        _CONFIG,
        data_dir=tmp_path / "data",
        client_factory=factory,
    )
    return service, fake_client, created


def _cookie_path(tmp_path):
    return tmp_path / "data" / "bilibili" / "cookies.json"


async def test_start_without_cookie_stays_dormant(tmp_path) -> None:
    service, fake_client, created = _make_service(tmp_path)
    await service.start()

    assert service.available is False
    assert service.is_dormant is True
    assert service.client is None
    assert created == []
    status = service.status()
    assert set(status) == {"available", "valid", "uid", "uname", "face", "login_at", "error"}
    assert status["valid"] is False
    assert status["uid"] == 0
    assert status["login_at"] is None

    with pytest.raises(BilibiliAuthError):
        await service.publish_dynamic("hello")

    await service.stop()
    assert fake_client.closed is False


async def test_start_with_saved_cookie_verifies_and_activates(tmp_path) -> None:
    BilibiliCookieStore(_cookie_path(tmp_path)).save(_COOKIES)
    service, fake_client, created = _make_service(
        tmp_path,
        info={"isLogin": True, "mid": 42, "uname": "tester", "face": "https://x/f.png"},
    )
    await service.start()

    assert service.available is True
    assert len(created) == 1
    args, kwargs = created[0]
    assert args == ("sess", "jct", 42)
    assert kwargs["buvid3"] == "buvid"
    status = service.status()
    assert status["available"] is True
    assert status["valid"] is True
    assert status["uid"] == 42
    assert status["uname"] == "tester"
    assert status["face"] == "https://x/f.png"
    assert status["login_at"] is not None
    assert status["error"] == ""

    assert await service.publish_dynamic("hello") == 99
    assert fake_client.published == [("hello", None)]

    await service.stop()
    assert fake_client.closed is True
    assert service.available is False


async def test_start_with_expired_cookie_stays_dormant(tmp_path) -> None:
    BilibiliCookieStore(_cookie_path(tmp_path)).save(_COOKIES)
    service, _, _ = _make_service(tmp_path, info={"isLogin": False, "mid": 0})
    await service.start()

    assert service.available is False
    status = service.status()
    assert status["valid"] is False
    assert "过期" in status["error"]


async def test_verify_refreshes_login_state(tmp_path) -> None:
    BilibiliCookieStore(_cookie_path(tmp_path)).save(_COOKIES)
    service, fake_client, _ = _make_service(tmp_path, info={"isLogin": True, "mid": 42})
    await service.start()
    assert service.available is True

    fake_client.info = {"isLogin": False, "mid": 0}
    assert await service.verify() is False
    assert service.available is False


async def test_login_with_qr_saves_cookies_and_activates(tmp_path, monkeypatch) -> None:
    service, fake_client, _ = _make_service(
        tmp_path,
        info={"isLogin": True, "mid": 42, "uname": "扫码用户"},
    )
    qr_events: list[QrCodeLogin] = []
    status_events: list[QrPollResult] = []

    async def fake_login(self, *, on_qr=None, on_status=None, interval=2.0, timeout=180.0):
        qr_info = QrCodeLogin(
            url="https://account.bilibili.com/h5/scan", qrcode_key="key", png_bytes=b"png"
        )
        if on_qr is not None:
            await on_qr(qr_info)
        result = QrPollResult(
            state="success",
            raw_code=0,
            message="ok",
            cookies=dict(_COOKIES),
            refresh_token="refresh-token",
        )
        if on_status is not None:
            await on_status(result)
        return result

    monkeypatch.setattr("neobot_app.bilibili.service.BilibiliQrLogin.login", fake_login)

    async def on_qr(info: QrCodeLogin) -> None:
        qr_events.append(info)

    async def on_status(result: QrPollResult) -> None:
        status_events.append(result)

    assert await service.login_with_qr(on_qr=on_qr, on_status=on_status) is True

    assert qr_events[0].qrcode_key == "key"
    assert status_events[-1].state == "success"
    saved = BilibiliCookieStore(_cookie_path(tmp_path)).load()
    assert saved is not None
    assert saved["SESSDATA"] == "sess"
    assert saved["refresh_token"] == "refresh-token"
    assert service.available is True
    status = service.status()
    assert status["uid"] == 42
    assert status["uname"] == "扫码用户"
    assert status["login_at"] is not None
    assert fake_client.published == []  # 登录只拉资料，不发动态


async def test_login_with_qr_expired_keeps_dormant(tmp_path, monkeypatch) -> None:
    service, _, _ = _make_service(tmp_path)

    async def fake_login(self, *, on_qr=None, on_status=None, interval=2.0, timeout=180.0):
        return QrPollResult(state="expired", raw_code=86038, message="二维码已失效")

    monkeypatch.setattr("neobot_app.bilibili.service.BilibiliQrLogin.login", fake_login)

    assert await service.login_with_qr() is False
    assert service.available is False
    error = service.status()["error"]
    assert "二维码已失效" in error  # 保留原始错误文本
    assert "重新扫码" in error  # 可读中文原因
    assert not _cookie_path(tmp_path).exists()


async def test_login_with_qr_error_returns_false(tmp_path, monkeypatch) -> None:
    service, _, _ = _make_service(tmp_path)

    async def fake_login(self, *, on_qr=None, on_status=None, interval=2.0, timeout=180.0):
        raise BilibiliAuthError("网络错误")

    monkeypatch.setattr("neobot_app.bilibili.service.BilibiliQrLogin.login", fake_login)

    assert await service.login_with_qr() is False
    error = service.status()["error"]
    assert "B站扫码登录失败" in error  # 可读中文前缀
    assert "网络错误" in error  # 保留原始错误文本


async def test_login_with_qr_save_failure_keeps_memory_login(tmp_path, monkeypatch) -> None:
    service, fake_client, created = _make_service(
        tmp_path, info={"isLogin": True, "mid": 42, "uname": "扫码用户"}
    )

    async def fake_login(self, **_kwargs):
        return QrPollResult(
            state="success",
            raw_code=0,
            cookies=dict(_COOKIES),
            refresh_token="refresh-token",
        )

    def broken_save(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("neobot_app.bilibili.service.BilibiliQrLogin.login", fake_login)
    monkeypatch.setattr(BilibiliCookieStore, "save", broken_save)

    assert await service.login_with_qr() is True
    assert service.available is True
    assert len(created) == 1  # 内存 cookie 仍然激活了客户端
    status = service.status()
    assert "凭证保存失败" in status["error"]
    assert "disk full" in status["error"]  # 保留原始错误文本
    assert status["uid"] == 42  # uid 由 nav 接口补齐
    assert not _cookie_path(tmp_path).exists()


async def test_login_with_qr_without_dedeuserid_uses_nav_uid(tmp_path, monkeypatch) -> None:
    service, _, created = _make_service(
        tmp_path, info={"isLogin": True, "mid": 42, "uname": "扫码用户"}
    )
    cookies = {"SESSDATA": "sess", "bili_jct": "jct", "buvid3": "buvid"}

    async def fake_login(self, **_kwargs):
        return QrPollResult(state="success", raw_code=0, cookies=dict(cookies))

    monkeypatch.setattr("neobot_app.bilibili.service.BilibiliQrLogin.login", fake_login)

    # DedeUserID 缺失也能登录成功：uid 由 nav 接口（get_my_info）补齐。
    assert await service.login_with_qr() is True
    assert created[0][0] == ("sess", "jct", 0)
    status = service.status()
    assert status["available"] is True
    assert status["uid"] == 42
    assert BilibiliCookieStore(_cookie_path(tmp_path)).load() is not None


async def test_login_with_qr_failure_but_account_already_logged_in(tmp_path, monkeypatch) -> None:
    BilibiliCookieStore(_cookie_path(tmp_path)).save(_COOKIES)
    service, _, _ = _make_service(tmp_path, info={"isLogin": True, "mid": 42})
    await service.start()
    assert service.available is True

    async def fake_login(self, **_kwargs):
        raise BilibiliAuthError("网络错误")

    monkeypatch.setattr("neobot_app.bilibili.service.BilibiliQrLogin.login", fake_login)

    # 轮询失败但账号实际已登录：先 verify 一次，按成功处理。
    assert await service.login_with_qr() is True
    assert service.available is True
