"""BilibiliService：休眠、登录态校验、扫码登录与动态发布门面。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from neobot_app.bilibili.cookie_provider import BilibiliCookieStore
from neobot_app.bilibili.errors import BilibiliApiError, BilibiliAuthError
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
    assert "重启后需重新登录" in status["error"]
    # 服务器绝对路径与原始异常只进日志，不给用户看。
    assert "disk full" not in status["error"]
    assert str(tmp_path) not in status["error"]
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


async def test_verify_network_failure_keeps_client_and_refresh_recovers(tmp_path) -> None:
    """启动时 nav 校验网络异常不能把登录态钉死成「未登录」。"""
    BilibiliCookieStore(_cookie_path(tmp_path)).save(_COOKIES)
    service, fake_client, _ = _make_service(tmp_path)

    def _boom() -> dict:
        raise RuntimeError("网络未就绪")

    fake_client.get_my_info = _boom  # type: ignore[method-assign]
    await service.start()  # 不向外抛
    assert service.available is False
    assert "网络异常" in service.status()["error"]
    assert service.client is fake_client

    fake_client.get_my_info = lambda: {"isLogin": True, "mid": 42, "uname": "tester"}  # type: ignore[method-assign]
    assert await service.refresh() is True
    assert service.available is True
    assert service.status()["uname"] == "tester"
    await service.stop()


async def test_refresh_starts_service_and_verifies(tmp_path) -> None:
    BilibiliCookieStore(_cookie_path(tmp_path)).save(_COOKIES)
    service, _, created = _make_service(tmp_path, info={"isLogin": True, "mid": 42})
    assert service.available is False  # 尚未 start

    assert await service.refresh() is True
    assert len(created) == 1
    assert service.status()["uid"] == 42
    await service.stop()


async def test_refresh_loads_cookie_file_that_appeared_later(tmp_path) -> None:
    """无凭证启动后 cookie 文件才出现（另一进程登录）：refresh 自愈补加载。"""
    service, _, created = _make_service(tmp_path, info={"isLogin": True, "mid": 42})
    await service.start()
    assert service.available is False
    assert created == []

    BilibiliCookieStore(_cookie_path(tmp_path)).save(_COOKIES)
    assert await service.refresh() is True
    assert len(created) == 1
    assert service.status()["uid"] == 42
    await service.stop()


async def test_verify_network_failure_keeps_last_valid_state(tmp_path) -> None:
    """已登录后遇到网络异常：保留 valid=True，只把 error 写成「网络异常」。"""
    BilibiliCookieStore(_cookie_path(tmp_path)).save(_COOKIES)
    service, fake_client, _ = _make_service(
        tmp_path, info={"isLogin": True, "mid": 42, "uname": "tester"}
    )
    await service.start()
    assert service.available is True

    def _boom() -> dict:
        raise BilibiliApiError(-1, "B站请求失败: 连接超时")

    fake_client.get_my_info = _boom  # type: ignore[method-assign]
    assert await service.verify() is True
    assert service.available is True
    assert service.status()["uname"] == "tester"
    assert "网络异常" in service.status()["error"]
    assert "暂未确认" in service.status()["error"]
    await service.stop()


async def test_verify_auth_error_marks_invalid(tmp_path) -> None:
    """只有明确的登录失效（BilibiliAuthError）才判为 valid=False。"""
    BilibiliCookieStore(_cookie_path(tmp_path)).save(_COOKIES)
    service, fake_client, _ = _make_service(tmp_path, info={"isLogin": True, "mid": 42})
    await service.start()
    assert service.available is True

    def _denied() -> dict:
        raise BilibiliAuthError("B站登录态失效: 账号未登录")

    fake_client.get_my_info = _denied  # type: ignore[method-assign]
    assert await service.verify() is False
    assert service.available is False
    assert "失效" in service.status()["error"]
    await service.stop()


async def test_login_with_qr_succeeds_when_profile_fetch_fails(tmp_path, monkeypatch) -> None:
    """登录已成功时，nav 资料接口失败不能把结果翻成失败。"""
    service, fake_client, _ = _make_service(tmp_path, info={"isLogin": True, "mid": 42})

    async def fake_login(self, **_kwargs):
        return QrPollResult(state="success", raw_code=0, cookies=dict(_COOKIES))

    def _boom() -> dict:
        raise BilibiliApiError(-1, "B站请求失败: 连接超时")

    monkeypatch.setattr("neobot_app.bilibili.service.BilibiliQrLogin.login", fake_login)
    fake_client.get_my_info = _boom  # type: ignore[method-assign]

    assert await service.login_with_qr() is True
    assert service.available is True
    assert service.status()["uid"] == 42  # uid 来自 cookie 的 DedeUserID
    await service.stop()


async def test_concurrent_login_keeps_single_qr_flow(tmp_path, monkeypatch) -> None:
    """面板与聊天同时发起扫码：只跑一路二维码，后到的一路复用结果。"""
    service, _, created = _make_service(
        tmp_path, info={"isLogin": True, "mid": 42, "uname": "扫码用户"}
    )
    calls: list[int] = []
    release = asyncio.Event()

    async def fake_login(self, **_kwargs):
        calls.append(1)
        await release.wait()
        return QrPollResult(state="success", raw_code=0, cookies=dict(_COOKIES))

    monkeypatch.setattr("neobot_app.bilibili.service.BilibiliQrLogin.login", fake_login)

    first = asyncio.create_task(service.login_with_qr())
    second = asyncio.create_task(service.login_with_qr())
    for _ in range(100):
        if calls:
            break
        await asyncio.sleep(0)
    release.set()

    assert await first is True
    assert await second is True
    assert len(calls) == 1  # 第二路没有另开一张二维码
    assert len(created) == 1
    await service.stop()


async def test_login_cancel_releases_single_flight(tmp_path, monkeypatch) -> None:
    """登录流程被取消后锁与单飞占位都要释放，下一次登录还能正常跑。"""
    service, _, _ = _make_service(tmp_path, info={"isLogin": True, "mid": 42})
    entered = asyncio.Event()

    async def hanging_login(self, **_kwargs):
        entered.set()
        await asyncio.sleep(3600)

    monkeypatch.setattr("neobot_app.bilibili.service.BilibiliQrLogin.login", hanging_login)
    task = asyncio.create_task(service.login_with_qr())
    await asyncio.wait_for(entered.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    async def ok_login(self, **_kwargs):
        return QrPollResult(state="success", raw_code=0, cookies=dict(_COOKIES))

    monkeypatch.setattr("neobot_app.bilibili.service.BilibiliQrLogin.login", ok_login)
    assert await asyncio.wait_for(service.login_with_qr(), timeout=5) is True
    await service.stop()
