"""B 站服务生命周期：cookie 加载、登录态校验、休眠状态与 async 门面。

设计分层：
- BilibiliClient：同步原子操作（requests）；
- BilibiliService：async 门面 + 登录态/休眠状态，调用 client 时用 asyncio.to_thread。

没有 cookie 或登录态失效时服务进入休眠（dormant）：start() 不抛错，available 为
False，其余功能等同关闭；扫码登录成功后自动激活。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from neobot_app.core import DATA_DIR
from neobot_contracts.ports.logging import Logger, NullLogger

from .client import BilibiliClient
from .cookie_provider import BilibiliCookieStore
from .errors import BilibiliAuthError, BilibiliError
from .qr_login import (
    QR_STATE_EXPIRED,
    QR_STATE_REJECTED,
    BilibiliQrLogin,
    QrCodeLogin,
    QrPollResult,
)

_DEFAULT_COOKIE_FILE = "data/bilibili/cookies.json"

#: 扫码终态里「不是成功」的那些 → 给用户看的中文原因。
_LOGIN_STATE_REASONS = {
    QR_STATE_EXPIRED: "二维码已失效或登录超时，请重新扫码",
    QR_STATE_REJECTED: "已在手机上取消登录，请重新扫码",
}


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _format_login_at(raw: Any) -> str | None:
    """秒级时间戳 → 本地 ISO 时间字符串。"""
    try:
        return datetime.fromtimestamp(float(raw)).astimezone().isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError):
        return None


class BilibiliService:
    """B 站功能的服务门面。"""

    def __init__(
        self,
        config: Any = None,
        *,
        data_dir: Path = DATA_DIR,
        logger: Logger | None = None,
        client_factory: Callable[..., BilibiliClient] | None = None,
    ) -> None:
        self._logger = logger or NullLogger()
        self._config = config
        cookie_file = str(getattr(config, "cookie_file", "") or _DEFAULT_COOKIE_FILE)
        cookie_path = Path(cookie_file)
        if not cookie_path.is_absolute():
            # 配置默认值形如 data/bilibili/cookies.json，相对应用根目录解析。
            cookie_path = Path(data_dir).parent / cookie_path
        self._store = BilibiliCookieStore(cookie_path)
        self._login_timeout = float(getattr(config, "login_timeout_seconds", 0) or 180)
        self._client_factory = client_factory or BilibiliClient
        self._client: BilibiliClient | None = None
        self._started = False
        self._valid = False
        self._uid = 0
        self._uname = ""
        self._face = ""
        self._login_at: str | None = None
        self._error = ""

    # ── 状态 ──

    @property
    def client(self) -> BilibiliClient | None:
        return self._client

    @property
    def available(self) -> bool:
        """已启动且登录态有效时才算可用；否则等同关闭（dormant）。"""
        return self._started and self._valid and self._client is not None

    @property
    def is_dormant(self) -> bool:
        return not self.available

    def status(self) -> dict[str, Any]:
        """状态摘要：是否可用/有效、uid、昵称、登录时间、最近错误。"""
        return {
            "available": self.available,
            "valid": self._valid,
            "uid": self._uid,
            "uname": self._uname,
            "face": self._face,
            "login_at": self._login_at,
            "error": self._error,
        }

    # ── 生命周期 ──

    async def start(self) -> None:
        """加载已保存的 cookie 并校验登录态；没有 cookie 时静默休眠。"""
        if self._started:
            return
        self._started = True
        cookies = await asyncio.to_thread(self._store.load)
        if not cookies:
            self._logger.info("B站未登录（无 cookie），B站功能休眠；扫码登录后自动启用")
            return
        self._apply_cookies(cookies)
        self._client = self._make_client(cookies)
        self._logger.info(f"B站服务启动，校验登录态（uid={self._uid}）")
        await self.verify()

    async def stop(self) -> None:
        """关闭客户端并回到未启动状态（cookie 保留，重启后自动恢复）。"""
        if self._client is not None:
            await asyncio.to_thread(self._client.close)
        self._client = None
        self._started = False
        self._valid = False

    async def verify(self) -> bool:
        """重新校验登录态并刷新昵称等信息。"""
        if self._client is None:
            self._valid = False
            return False
        info = await asyncio.to_thread(self._client.get_my_info)
        valid = bool(info.get("isLogin")) and _to_int(info.get("mid")) > 0
        self._valid = valid
        if valid:
            self._update_from_info(info)
            self._error = ""
            self._logger.info(f"B站登录态有效: uid={self._uid} uname={self._uname}")
        else:
            self._error = "B站登录态无效或已过期，请重新扫码登录"
            self._logger.warning(self._error)
        return valid

    # ── 扫码登录 ──

    async def login_with_qr(
        self,
        *,
        on_qr: Callable[[QrCodeLogin], Any] | None = None,
        on_status: Callable[[QrPollResult], Any] | None = None,
        timeout: float | None = None,
    ) -> bool:
        """走完整二维码登录；成功时保存 cookie 并激活客户端。

        落盘失败不算登录失败：用内存 cookie 激活客户端，error 里提示重启后需重新登录。
        """
        qr_login = BilibiliQrLogin(logger=self._logger)
        try:
            result = await qr_login.login(
                on_qr=on_qr,
                on_status=on_status,
                timeout=timeout if timeout is not None else self._login_timeout,
            )
        except BilibiliError as exc:
            return await self._login_failed(f"B站扫码登录失败: {exc}")
        if not result.success:
            reason = _LOGIN_STATE_REASONS.get(result.state, "B站扫码登录未完成")
            detail = result.message.strip()
            return await self._login_failed(f"{reason}（{detail}）" if detail else reason)
        save_error: Exception | None = None
        try:
            await asyncio.to_thread(
                self._store.save, result.cookies, refresh_token=result.refresh_token
            )
        except (OSError, ValueError) as exc:
            save_error = exc
            self._logger.warning(f"B站 cookie 保存失败: {exc}")
        if self._client is not None:
            await asyncio.to_thread(self._client.close)
        self._apply_cookies(result.cookies)
        self._client = self._make_client(result.cookies)
        self._started = True
        self._valid = True
        self._login_at = datetime.now().astimezone().isoformat(timespec="seconds")
        if save_error is None:
            self._error = ""
        else:
            self._error = f"登录成功，但凭证保存失败，重启后需重新登录（{save_error}）"
            self._logger.warning(self._error)
        self._logger.info(f"B站扫码登录完成: uid={self._uid}")
        # 昵称等资料拉取失败不影响登录成功；DedeUserID 缺失时这里也能补上 uid。
        info = await asyncio.to_thread(self._client.get_my_info)
        if info:
            self._update_from_info(info)
        return True

    async def _login_failed(self, reason: str) -> bool:
        """记录可读失败原因；账号其实已登录（如轮询被提前打断）时按成功处理。"""
        self._error = reason
        self._logger.warning(reason)
        if await self.verify():
            self._logger.info("B站扫码登录未完成，但当前账号已登录，按成功处理")
            return True
        # verify 失败会覆盖成它自己的错误，这里恢复登录流程的真实原因。
        self._error = reason
        return False

    # ── 对外动作 ──

    async def publish_dynamic(
        self, text: str, images: Sequence[str | Path] | None = None
    ) -> int:
        """发布动态；休眠时抛 BilibiliAuthError。"""
        if not self.available or self._client is None:
            raise BilibiliAuthError("B站未登录（功能休眠），无法发布动态")
        return await asyncio.to_thread(self._client.publish_dynamic, text, images)

    # ── 内部 ──

    def _make_client(self, cookies: dict[str, str]) -> BilibiliClient:
        return self._client_factory(
            cookies.get("SESSDATA", ""),
            cookies.get("bili_jct", ""),
            self._uid,
            buvid3=cookies.get("buvid3", ""),
            logger=self._logger,
        )

    def _apply_cookies(self, cookies: dict[str, str]) -> None:
        self._uid = _to_int(cookies.get("DedeUserID"))
        self._login_at = _format_login_at(cookies.get("saved_at")) or self._login_at

    def _update_from_info(self, info: dict[str, Any]) -> None:
        mid = _to_int(info.get("mid"))
        if mid:
            self._uid = mid
        self._uname = str(info.get("uname") or "")
        self._face = str(info.get("face") or "")
