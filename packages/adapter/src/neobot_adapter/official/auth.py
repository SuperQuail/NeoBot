"""官方机器人鉴权：access token 缓存、扫码绑定与凭据落盘。

凭据来自 QQ 机器人门户的扫码绑定（AES-256-GCM 加密返回），落盘为
<DATA_DIR>/qqbot/credentials.json；access token 由 AppID/AppSecret 换取，
只在内存里缓存到 expires_in 的 80%，到期或失效后重新获取。
"""

from __future__ import annotations

import asyncio
import base64
import inspect
import json
import os
import secrets
import tempfile
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_adapter.official.settings import OfficialSettings

_CREDENTIALS_DIR_NAME = "qqbot"
_CREDENTIALS_FILE_NAME = "credentials.json"
_HTTP_TIMEOUT_SECONDS = 10.0
#: 门户轮询节奏；绑定接口在扫码前只会返回「继续等待」。
_POLL_INTERVAL_SECONDS = 2.0
#: 提前到 expires_in 的 80% 刷新，避免请求正卡在过期边界上。
_TOKEN_TTL_RATIO = 0.8
_DEFAULT_TOKEN_TTL_SECONDS = 7200.0
_BIND_PENDING = 1
_BIND_COMPLETED = 2
_BIND_EXPIRED = 3
_JSON_HEADERS = {"Accept": "application/json"}


class OfficialAuthError(RuntimeError):
    """官方协议鉴权/绑定失败；消息可直接展示给用户。"""


@dataclass(frozen=True, slots=True)
class Credentials:
    app_id: str
    client_secret: str


@asynccontextmanager
async def http_scope(http: Any | None):
    """复用注入的 HTTP 会话，或临时建一个 aiohttp 会话并及时关闭。"""
    if http is not None:
        yield http
        return
    import aiohttp

    session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=_HTTP_TIMEOUT_SECONDS))
    try:
        yield session
    finally:
        await session.close()


async def _post_json(http: Any, url: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST JSON 并统一收敛错误；非 200 或非对象响应一律抛 OfficialAuthError。"""
    try:
        async with http.post(url, json=payload, headers=_JSON_HEADERS) as response:
            status = int(getattr(response, "status", 0) or 0)
            data = await response.json(content_type=None)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        raise OfficialAuthError(f"请求官方接口失败: {type(exc).__name__}: {exc}") from exc
    if not isinstance(data, dict):
        raise OfficialAuthError("官方接口响应格式异常")
    if status != 200:
        message = str(data.get("message") or data.get("msg") or "").strip()
        raise OfficialAuthError(f"官方接口返回 HTTP {status}" + (f"：{message}" if message else ""))
    return data


def _checked_data(data: dict[str, Any], action: str) -> dict[str, Any]:
    """校验门户接口的 retcode 并取出 data 段；业务失败也转成可读中文。"""
    retcode = data.get("retcode")
    if retcode not in (None, 0, "0"):
        message = str(data.get("msg") or data.get("message") or "").strip() or "未知错误"
        raise OfficialAuthError(f"{action}失败：{message}（retcode={retcode}）")
    payload = data.get("data")
    return payload if isinstance(payload, dict) else {}


def _positive_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class CredentialStore:
    """<data_dir>/qqbot/credentials.json：0600、原子写。"""

    def __init__(self, data_dir: str | Path) -> None:
        self._path = Path(data_dir) / _CREDENTIALS_DIR_NAME / _CREDENTIALS_FILE_NAME

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> Credentials | None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            return None
        if not isinstance(raw, dict):
            return None
        app_id = str(raw.get("app_id") or "").strip()
        client_secret = str(raw.get("client_secret") or "").strip()
        if not app_id or not client_secret:
            return None
        return Credentials(app_id=app_id, client_secret=client_secret)

    def save(self, app_id: str, secret: str) -> None:
        app_id = str(app_id or "").strip()
        secret = str(secret or "").strip()
        if not app_id or not secret:
            raise OfficialAuthError("扫码结果缺少机器人 AppID 或 AppSecret")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"app_id": app_id, "client_secret": secret},
            ensure_ascii=False,
        )
        # mkstemp 创建的文件在 POSIX 上就是 0600，os.replace 保留权限；
        # 这样既保证原子写，也不会留下先宽后紧的权限窗口。
        fd, temp_path = tempfile.mkstemp(
            dir=self._path.parent,
            prefix=f".{self._path.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self._path)
        except BaseException:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise

    def delete(self) -> None:
        try:
            self._path.unlink()
        except FileNotFoundError:
            pass


class TokenProvider:
    """access token 的单飞缓存。

    并发 get_token 共享同一次刷新；force=True 用于「API 返回 401 后重取一次」。
    """

    def __init__(self, settings: OfficialSettings, http: Any | None = None) -> None:
        self._settings = settings
        self._http = http
        self._lock = asyncio.Lock()
        self._token = ""
        self._expires_at = 0.0

    async def get_token(self, *, force: bool = False) -> str:
        async with self._lock:
            if not force and self._token and time.monotonic() < self._expires_at:
                return self._token
            token, ttl = await self._fetch_token()
            self._token = token
            self._expires_at = time.monotonic() + ttl * _TOKEN_TTL_RATIO
            return token

    def invalidate(self) -> None:
        self._token = ""
        self._expires_at = 0.0

    async def _fetch_token(self) -> tuple[str, float]:
        if not self._settings.app_id or not self._settings.client_secret:
            raise OfficialAuthError("未配置 QQ 官方机器人 AppID/AppSecret，请先在面板扫码绑定")
        async with http_scope(self._http) as http:
            data = await _post_json(
                http,
                self._settings.token_url,
                {
                    "appId": self._settings.app_id,
                    "clientSecret": self._settings.client_secret,
                },
            )
        token = str(data.get("access_token") or "").strip()
        if not token:
            message = str(data.get("message") or data.get("msg") or "").strip()
            raise OfficialAuthError(
                "获取 access token 失败" + (f"：{message}" if message else "：响应缺少 access_token")
            )
        ttl = _positive_float(data.get("expires_in"), _DEFAULT_TOKEN_TTL_SECONDS)
        return token, ttl


def decrypt_secret(encrypted_secret: str, bind_key: str) -> str:
    """解密扫码返回的 AppSecret：base64(IV12 + 密文 + GCM tag16)。

    bind_key 是发起绑定任务时 POST 的 base64 32 字节 AES-256 key。密文与 key
    只在本进程内存在，不落盘。
    """
    try:
        key = base64.b64decode(bind_key)
        raw = base64.b64decode(encrypted_secret)
    except Exception as exc:
        raise OfficialAuthError("QQ 机器人凭据解码失败") from exc
    if len(key) != 32 or len(raw) <= 28:
        raise OfficialAuthError("QQ 机器人凭据密文格式异常")
    try:
        # 末尾 16 字节是 GCM tag，AESGCM 会把它与密文一起校验。
        plaintext = AESGCM(key).decrypt(raw[:12], raw[12:], None)
    except Exception as exc:
        raise OfficialAuthError("QQ 机器人凭据解密失败") from exc
    try:
        return plaintext.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OfficialAuthError("QQ 机器人凭据解密结果不是文本") from exc


@dataclass
class BindState:
    """扫码绑定对外暴露的状态快照（面板与适配器只读）。"""

    phase: str = "idle"
    url: str = ""
    svg: str = ""
    expires_at: float = 0.0
    error: str = ""


class QrBindFlow:
    """一次完整的扫码绑定：创建任务 → 轮询 → 解密 → 写凭据。"""

    def __init__(
        self,
        settings: OfficialSettings,
        logger: Logger | None = None,
        http: Any | None = None,
    ) -> None:
        self._settings = settings
        self._logger = logger if logger is not None else NullLogger()
        self._http = http
        self._state = BindState()
        self._announced = False

    @property
    def state(self) -> BindState:
        return self._state

    async def start(
        self,
        on_update: Callable[[BindState], Any] | None = None,
    ) -> BindState:
        """跑完整个绑定流程并返回终态；预期失败也放在 BindState 里返回。"""
        deadline = time.time() + max(0.0, float(self._settings.bind_timeout_seconds))
        key = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
        async with http_scope(self._http) as http:
            try:
                task_id = await self._create_task(http, key)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                return await self._fail(exc, on_update)
            await self._show_pending(task_id, deadline, on_update)
            while True:
                remaining = deadline - time.time()
                if remaining <= 0:
                    return await self._expire("扫码绑定超时，请重新发起", on_update)
                await asyncio.sleep(min(_POLL_INTERVAL_SECONDS, remaining))
                try:
                    payload = await self._poll_task(http, task_id)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    # 单次轮询失败（网络抖动/5xx）不停绑定：下一轮再试，直到超时。
                    self._logger.warning(
                        "扫码绑定轮询失败，将重试",
                        error_type=type(exc).__name__,
                        error=str(exc),
                    )
                    continue
                status = _int_value(payload.get("status"), _BIND_PENDING)
                if status == _BIND_COMPLETED:
                    return await self._complete(payload, key, deadline, on_update)
                if status == _BIND_EXPIRED:
                    # 二维码过期但总时长未到：同一把 AES key 重新申请任务。
                    try:
                        task_id = await self._create_task(http, key)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        return await self._fail(exc, on_update)
                    await self._show_pending(task_id, deadline, on_update)

    async def _show_pending(
        self,
        task_id: str,
        deadline: float,
        on_update: Callable[[BindState], Any] | None,
    ) -> None:
        url = self._connect_url(task_id)
        self._state = BindState(
            phase="pending",
            url=url,
            svg=_qr_svg(url),
            expires_at=deadline,
        )
        if not self._announced:
            self._announced = True
            _print_ascii_qr(url)
        self._logger.info("QQ 官方机器人扫码绑定：请打开链接或用手机 QQ 扫码", url=url)
        await self._notify(on_update, self._state)

    async def _create_task(self, http: Any, key: str) -> str:
        data = await _post_json(
            http,
            f"https://{self._settings.portal_host}/lite/create_bind_task",
            {"key": key},
        )
        payload = _checked_data(data, "创建扫码绑定任务")
        task_id = str(payload.get("task_id") or "").strip()
        if not task_id:
            raise OfficialAuthError("创建扫码绑定任务失败：响应缺少 task_id")
        return task_id

    async def _poll_task(self, http: Any, task_id: str) -> dict[str, Any]:
        data = await _post_json(
            http,
            f"https://{self._settings.portal_host}/lite/poll_bind_result",
            {"task_id": task_id},
        )
        return _checked_data(data, "轮询扫码绑定结果")

    def _connect_url(self, task_id: str) -> str:
        return (
            f"https://{self._settings.portal_host}/qqbot/openclaw/connect.html"
            f"?task_id={quote(task_id, safe='')}&_wv=2&source=neobot"
        )

    async def _complete(
        self,
        payload: dict[str, Any],
        key: str,
        deadline: float,
        on_update: Callable[[BindState], Any] | None,
    ) -> BindState:
        app_id = str(payload.get("bot_appid") or "").strip()
        encrypted_secret = str(payload.get("bot_encrypt_secret") or "").strip()
        try:
            if not app_id or not encrypted_secret:
                raise OfficialAuthError("扫码成功但未返回完整的机器人凭据")
            secret = decrypt_secret(encrypted_secret, key)
            CredentialStore(self._settings.data_dir).save(app_id, secret)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return await self._fail(exc, on_update)
        self._state = BindState(phase="success", expires_at=deadline)
        self._logger.info("QQ 官方机器人绑定成功", app_id=app_id)
        await self._notify(on_update, self._state)
        return self._state

    async def _fail(
        self,
        exc: Exception,
        on_update: Callable[[BindState], Any] | None,
    ) -> BindState:
        message = str(exc) or "扫码绑定失败"
        self._state = BindState(
            phase="error",
            expires_at=self._state.expires_at,
            error=message,
        )
        self._logger.error(
            "QQ 官方机器人扫码绑定失败",
            error_type=type(exc).__name__,
            error=message,
        )
        await self._notify(on_update, self._state)
        return self._state

    async def _expire(
        self,
        message: str,
        on_update: Callable[[BindState], Any] | None,
    ) -> BindState:
        self._state = BindState(
            phase="expired",
            expires_at=self._state.expires_at,
            error=message,
        )
        self._logger.warning("QQ 官方机器人扫码绑定已过期", error=message)
        await self._notify(on_update, self._state)
        return self._state

    async def _notify(
        self,
        on_update: Callable[[BindState], Any] | None,
        state: BindState,
    ) -> None:
        if on_update is None:
            return
        try:
            result = on_update(state)
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            # 展示层回调失败不应中断绑定流程。
            self._logger.warning(
                "扫码绑定状态回调失败",
                error_type=type(exc).__name__,
                error=str(exc),
            )


def _qr_svg(url: str) -> str:
    """渲染二维码 SVG；面板内联显示，不依赖 Pillow。"""
    import io

    import qrcode
    import qrcode.image.svg

    image = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage)
    buffer = io.BytesIO()
    image.save(buffer)
    return buffer.getvalue().decode("utf-8")


def _print_ascii_qr(url: str) -> None:
    """控制台二维码；只在一次绑定流程开始时打印一次。"""
    try:
        import qrcode

        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        print(f"\n[QQBot] 扫码绑定链接: {url}")
        qr.print_ascii(invert=True)
    except Exception as exc:
        # 终端编码不支持方块字符等情况不能阻断绑定，链接已经先打印出来了。
        print(f"[QQBot] 控制台渲染二维码失败（请使用上面打印的链接）：{exc}")
