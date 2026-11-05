"""客户端核心：构造、登录态校验、线程 Session 与 HTTP 请求/重试/限速。"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

import requests

from neobot_contracts.ports.logging import Logger, NullLogger

from ..errors import BilibiliApiError, BilibiliAuthError, BilibiliError
from .common import (
    DEFAULT_USER_AGENT,
    _IDEMPOTENT_METHODS,
    _NAV_URL,
    _RISK_CONTROL_STATUS,
    _WRITE_RETRY_CODES,
    _to_int,
    parse_video_id,
)


class _ClientCoreMixin:
    """客户端核心：构造、登录态、HTTP 请求与限速/重试。"""

    _MAX_RETRIES = 2
    _RETRY_DELAY_SECONDS = 0.5
    _DEFAULT_WRITE_INTERVAL_SECONDS = 1.0
    _MAX_WRITE_INTERVAL_SECONDS = 60.0
    #: WBI 密钥有效期；过期后重新从 nav 接口取，避免长期用失效密钥被 -352。
    _WBI_KEY_TTL_SECONDS = 1800.0

    def __init__(
        self,
        sessdata: str,
        bili_jct: str,
        uid: int = 0,
        *,
        buvid3: str = "",
        logger: Logger | None = None,
        session: requests.Session | None = None,
        timeout: float = 10.0,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        if not sessdata or not bili_jct:
            raise ValueError("SESSDATA 和 bili_jct 不能为空")
        self._sessdata = sessdata
        self._bili_jct = bili_jct
        self._my_uid = int(uid or 0)
        self._buvid3 = buvid3
        self._logger = logger or NullLogger()
        self._timeout = timeout
        # 外部传入的 session 归调用方所有，close() 不关它。
        self._session = session if session is not None else requests.Session()
        self._owns_session = session is None
        self._session.headers.update(
            {
                "User-Agent": user_agent,
                "Referer": "https://www.bilibili.com/",
                "Origin": "https://www.bilibili.com",
                "Accept": "application/json, text/plain, */*",
            }
        )
        jar = self._session.cookies
        jar.set("SESSDATA", sessdata, domain=".bilibili.com", path="/")
        jar.set("bili_jct", bili_jct, domain=".bilibili.com", path="/")
        if self._my_uid:
            jar.set("DedeUserID", str(self._my_uid), domain=".bilibili.com", path="/")
        if buvid3:
            jar.set("buvid3", buvid3, domain=".bilibili.com", path="/")

        # 并发安全：任务模块可能从多个线程调用同一个客户端。锁只保护 cookie/限速状态，
        # 不包网络 I/O；requests.Session 不保证跨线程安全，所以每个线程用自己的 Session
        # （创建线程继续用 self._session，其余线程复制一份）。
        self._lock = threading.Lock()
        self._local = threading.local()
        self._local.session = self._session
        # 限速：写操作之间的最小间隔，命中风控后自适应放大，风控过去后逐步回落。
        self._write_interval = self._DEFAULT_WRITE_INTERVAL_SECONDS
        self._last_write_at = 0.0
        # WBI 签名密钥缓存（带有效期）。
        self._wbi_mixin_key = ""
        self._wbi_key_at = 0.0
        # 私信去重缓存。
        self._seen_msg_keys: set[str] = set()
        self._last_msg_times: dict[int, int] = defaultdict(int)

    # ── 认证 ──

    @property
    def my_uid(self) -> int:
        """自己的 UID；构造时未给则尝试从 nav 接口取一次（取不到返回 0）。"""
        if self._my_uid > 0:
            return self._my_uid
        try:
            self._my_uid = _to_int(self.get_my_info().get("mid"))
        except BilibiliError as exc:
            self._log_read_error("UID 读取", exc)
            self._my_uid = 0
        return self._my_uid

    def get_my_info(self) -> dict[str, Any]:
        """nav 接口的 data 原样返回（mid/uname/face/isLogin/wbi_img 等）。

        登录失效（-101 或 isLogin=False）抛 BilibiliAuthError；网络/5xx/非法 JSON
        抛 BilibiliApiError —— 调用方必须能区分「接口失败」和「未登录」，不能靠空 dict。
        """
        payload = self._fetch("GET", _NAV_URL)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise BilibiliApiError(-1, "B站账号信息接口没有返回 data")
        wbi_img = data.get("wbi_img")
        if isinstance(wbi_img, dict):
            self._cache_wbi_keys(wbi_img)
        if not data.get("isLogin"):
            raise BilibiliAuthError("B站未登录或登录态已过期")
        mid = _to_int(data.get("mid"))
        if mid <= 0:
            raise BilibiliAuthError("B站账号信息缺少 mid，登录态无效")
        self._my_uid = mid
        return data

    def verify_auth(self) -> bool:
        """当前 cookie 是否仍处于登录态（网络异常也按 False 处理，bool 没有第三态）。"""
        try:
            self.get_my_info()
        except BilibiliError as exc:
            self._log_read_error("登录态校验", exc)
            return False
        return True

    # ── 生命周期 ──

    def close(self) -> None:
        """关闭本客户端自建的 HTTP 会话（外部传入的 session 归调用方所有，不关）。"""
        if not self._owns_session:
            return
        self._session.close()
        session = getattr(self._local, "session", None)
        if session is not None and session is not self._session:
            session.close()

    # ── 内部：ID 解析 ──

    def _resolve_video_aid(self, identifier: str) -> int:
        """BV/av/URL -> aid；BV 需要查一次 view 接口，解析失败返回 0。"""
        bvid, aid = parse_video_id(identifier)
        if aid:
            return aid
        if not bvid:
            return 0
        return _to_int(self.get_video_info(bvid).get("aid"))

    def _resolve_comment_oid(self, identifier: str) -> int:
        """BV/av/URL -> aid；动态/专栏/opus 的数字 ID 直接当 oid。"""
        text = str(identifier or "").strip()
        bvid, aid = parse_video_id(text)
        if aid:
            return aid
        if bvid:
            return _to_int(self.get_video_info(bvid).get("aid"))
        return _to_int(text)

    def _resolve_live_room_id(self, room_id: int) -> int:
        """短号/房间号 -> 真实房间号；查不到时原样返回输入值。"""
        room_id = _to_int(room_id)
        if room_id <= 0:
            return 0
        room = self.get_live_room_info(room_id).get("room_info")
        real_room_id = _to_int(room.get("room_id")) if isinstance(room, dict) else 0
        return real_room_id or room_id

    # ── 内部：HTTP / 错误处理 ──

    @property
    def _http(self) -> requests.Session:
        """当前线程的 Session；没有就复制一份（requests.Session 不保证跨线程安全）。"""
        session = getattr(self._local, "session", None)
        if session is None:
            session = self._clone_session()
            self._local.session = session
        return session

    def _clone_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(self._session.headers)
        # 按 Cookie 对象复制，保留 domain/path，避免 cookie 被当成全局 cookie 发出去。
        for cookie in self._session.cookies:
            session.cookies.set_cookie(cookie)
        return session

    def _fetch(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
        json_body: Any = None,
        files: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        allow_redirects: bool | None = None,
        retry: bool = False,
    ) -> dict[str, Any]:
        response = self._request(
            method,
            url,
            params=params,
            data=data,
            json_body=json_body,
            files=files,
            headers=headers,
            allow_redirects=allow_redirects,
            retry=retry,
        )
        if response is None:
            raise BilibiliApiError(-1, "B站网络请求失败")
        if response.status_code in _RISK_CONTROL_STATUS:
            self._on_risk_control(response.status_code)
            raise BilibiliApiError(-response.status_code, f"B站风控拦截（HTTP {response.status_code}）")
        try:
            return self._decode(response)
        except BilibiliApiError as exc:
            if exc.code != -352 or method.upper() != "GET" or "w_rid" not in (params or {}):
                raise
            # -352：B 站判定 WBI 签名失效。清空密钥、重取后重签一次再试。
            self._invalidate_wbi_keys()
            self._logger.warning("B站 WBI 签名失效（-352），重取密钥后重试一次")
            retried = self._request(
                method,
                url,
                params=self._sign_wbi(
                    {
                        key: value
                        for key, value in params.items()
                        if key not in ("wts", "w_rid")
                    }
                ),
                data=data,
                json_body=json_body,
                files=files,
                headers=headers,
            )
            if retried is None:
                raise BilibiliApiError(-1, "B站网络请求失败") from exc
            return self._decode(retried)

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
        json_body: Any = None,
        files: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        allow_redirects: bool | None = None,
        retry: bool = False,
    ) -> requests.Response | None:
        """发一次请求；只有幂等的 GET/HEAD（或显式 retry 安全写）会重试。

        评论/私信/弹幕/投币等写请求重发会造成重复操作，一律只发一次。
        """
        options: dict[str, Any] = {
            "params": params,
            "data": data,
            "json": json_body,
            "files": files,
            "headers": headers,
            "timeout": self._timeout,
        }
        if allow_redirects is not None:
            options["allow_redirects"] = allow_redirects
        idempotent = retry or method.upper() in _IDEMPOTENT_METHODS
        attempts = self._MAX_RETRIES + 1 if idempotent else 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                response = self._http.request(method, url, **options)
            except requests.RequestException as exc:
                last_error = exc
            else:
                if response.status_code < 500:
                    return response
                last_error = BilibiliApiError(-1, f"B站服务异常 HTTP {response.status_code}")
            if attempt + 1 < attempts:
                time.sleep(self._RETRY_DELAY_SECONDS * (attempt + 1))
        self._logger.warning(f"B站请求失败: {method} {url}（{last_error}）")
        return None

    @staticmethod
    def _decode(response: requests.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise BilibiliApiError(-1, "B站响应不是合法 JSON") from exc
        if not isinstance(payload, dict):
            raise BilibiliApiError(-1, "B站响应不是 JSON 对象")
        try:
            code = int(payload.get("code") or 0)
        except (TypeError, ValueError) as exc:
            raise BilibiliApiError(-1, f"B站响应 code 不合法: {payload.get('code')!r}") from exc
        if code == 0:
            return payload
        message = str(payload.get("message") or payload.get("msg") or "")
        if code == -101:
            raise BilibiliAuthError(f"B站登录态失效: {message}")
        raise BilibiliApiError(code, message)

    def _require_login(self, action: str) -> bool:
        """需要登录态的操作前检查：缺 cookie 时直接失败，避免请求打到风控。"""
        if self._sessdata and self._bili_jct:
            return True
        return False

    def _rate_limit_wait(self) -> None:
        """在锁内预约下一个写操作时隙，锁外 sleep —— 并发写不会挤在同一个时隙。"""
        with self._lock:
            now = time.monotonic()
            if now - self._last_write_at > self._write_interval * 3:
                # 距上次写很久说明风控期已过，冷却逐步回落到默认间隔。
                self._write_interval = max(
                    self._DEFAULT_WRITE_INTERVAL_SECONDS, self._write_interval * 0.5
                )
            wait = self._last_write_at + self._write_interval - now
            self._last_write_at = max(now, self._last_write_at + self._write_interval)
        if wait > 0:
            time.sleep(wait)

    def _bump_write_cooldown(self) -> None:
        with self._lock:
            self._write_interval = min(
                self._write_interval * 1.5, self._MAX_WRITE_INTERVAL_SECONDS
            )

    def _on_risk_control(self, status_code: int) -> None:
        """HTTP 412/429 是风控拦截（不是业务错误），同样放大写冷却。"""
        self._bump_write_cooldown()
        self._logger.warning(
            f"B站请求命中风控（HTTP {status_code}），写操作冷却提升到 {self._write_interval:.1f}s"
        )

    def _on_write_error(self, action: str, error: Exception) -> None:
        if isinstance(error, BilibiliApiError) and error.code in _WRITE_RETRY_CODES:
            self._bump_write_cooldown()
            self._logger.warning(
                f"B站{action}命中风控/限流（{error.code}），写操作冷却提升到 {self._write_interval:.1f}s"
            )
            return
        if isinstance(error, BilibiliAuthError):
            self._logger.warning(f"B站{action}失败: {error}")
            return
        self._logger.warning(f"B站{action}失败: {error}")

    def _log_read_error(self, action: str, error: Exception) -> None:
        if isinstance(error, BilibiliAuthError):
            self._logger.warning(f"B站{action}失败: {error}")
        else:
            self._logger.debug(f"B站{action}失败: {error}")
