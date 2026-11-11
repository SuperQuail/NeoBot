"""QQ 官方机器人 WebSocket 网关（v2 协议）。

职责：换 access token、GET /gateway 取 wss 地址、维护 Hello/Identify/Resume
与心跳，把 op0 dispatch 原样交给 on_event。事件到 OneBot 形状的映射在上层做，
本模块不认识任何具体事件类型。
"""

from __future__ import annotations

import asyncio
import inspect
import json
import random
from contextlib import suppress
from typing import Any, Awaitable, Callable

import websockets
from websockets.exceptions import ConnectionClosed

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_adapter.official.auth import OfficialAuthError, TokenProvider, http_scope
from neobot_adapter.official.settings import OfficialSettings

_OP_DISPATCH = 0
_OP_HEARTBEAT = 1
_OP_IDENTIFY = 2
_OP_RESUME = 6
_OP_RECONNECT = 7
_OP_INVALID_SESSION = 9
_OP_HELLO = 10
_OP_HEARTBEAT_ACK = 11

#: 群聊与 C2C 消息事件（1 << 25）：C2C_MESSAGE_CREATE、GROUP_AT_MESSAGE_CREATE、
#: GROUP_MESSAGE_CREATE 都在这个 intent 下。
_INTENTS = (1 << 25) | (1 << 24)  # GROUP_AND_C2C_EVENT | GROUP_MEMBER_EVENT
#: 心跳按 Hello 给的间隔的 80% 发送，留出网络抖动余量。
_HEARTBEAT_RATIO = 0.8
_DEFAULT_HEARTBEAT_INTERVAL_MS = 30000.0
_BACKOFF_BASE_SECONDS = 1.0
_BACKOFF_MAX_SECONDS = 60.0
_MAX_BACKOFF_EXPONENT = 6

#: 不可重试：机器人已下架 / 已封禁，重连只会一直失败。
_FATAL_CLOSE_CODES = frozenset({4914, 4915})
#: token 失效：刷新 token 后重新 Identify。
_TOKEN_CLOSE_CODES = frozenset({4004})
#: session_id/seq 失效：清空会话后重新 Identify。
_SESSION_CLOSE_CODES = frozenset({4006, 4007, 4009})

EventHandler = Callable[[dict[str, Any]], Awaitable[None] | None]


class _Reconnect(Exception):
    """服务端要求重建连接（op7），或会话失效（op9）。"""

    def __init__(self, reason: str, *, clear_session: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.clear_session = clear_session


class _GatewayClosed(Exception):
    """连接关闭，携带用于分类的 close code。"""

    def __init__(self, code: int | None, reason: str = "") -> None:
        super().__init__(f"{code}: {reason}")
        self.code = code
        self.reason = reason


class OfficialGateway:
    """独立后台任务维护的上行网关；start() 立即返回，等待用 wait_connected。"""

    def __init__(
        self,
        settings: OfficialSettings,
        token_provider: TokenProvider,
        on_event: EventHandler,
        logger: Logger | None = None,
        *,
        http: Any | None = None,
        ws_connect: Callable[[str], Awaitable[Any]] | None = None,
    ) -> None:
        self._settings = settings
        self._token_provider = token_provider
        self._on_event = on_event
        self._logger = logger if logger is not None else NullLogger()
        self._http = http
        self._ws_connect = ws_connect if ws_connect is not None else websockets.connect
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()
        self._connected = asyncio.Event()
        self._ws: Any = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._heartbeat_interval = 0.0
        self._session_id = ""
        self._last_seq: int | None = None
        self._ready = False

    @property
    def connected(self) -> bool:
        """是否已收到 READY/RESUMED（只开 WebSocket 还不算就绪）。"""
        return self._connected.is_set()

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stopping = asyncio.Event()
        self._connected.clear()
        self._task = asyncio.create_task(self._run(), name="qq-official-gateway")

    async def stop(self) -> None:
        self._stopping.set()
        await self._cancel_heartbeat()
        await self._close_ws()
        task = self._task
        self._task = None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._connected.clear()
        self._reset_session()

    async def wait_connected(self, timeout: float | None = None) -> bool:
        try:
            await asyncio.wait_for(self._connected.wait(), timeout)
        except asyncio.TimeoutError:
            return False
        return True

    # ── 连接循环 ────────────────────────────────────────────────────

    async def _run(self) -> None:
        attempt = 0
        while not self._stopping.is_set():
            fatal_code: int | None = None
            clear_session = False
            try:
                await self._connect_once()
                reason = "网关连接已关闭"
            except asyncio.CancelledError:
                raise
            except _Reconnect as exc:
                reason = exc.reason
                clear_session = exc.clear_session
            except _GatewayClosed as exc:
                reason = f"网关连接关闭（code={exc.code}）"
                action = self._classify_close(exc.code)
                self._logger.warning(
                    "官方网关连接断开",
                    code=exc.code,
                    detail=exc.reason,
                    action=action,
                )
                if action == "fatal":
                    fatal_code = exc.code
                elif action == "token":
                    # token 失效时旧 session 也一并作废：刷新后重新 Identify。
                    self._token_provider.invalidate()
                    clear_session = True
                elif action == "session":
                    clear_session = True
            except OfficialAuthError as exc:
                reason = f"官方网关鉴权失败: {exc}"
                self._logger.warning(reason)
            except Exception as exc:
                reason = f"官方网关异常: {type(exc).__name__}: {exc}"
                self._logger.warning(reason)
            if self._ready:
                # 上一轮确实就绪过：退避从 1 秒重新开始。
                attempt = 0
                self._ready = False
            if self._stopping.is_set():
                break
            if fatal_code is not None:
                self._logger.error(
                    "QQ 官方机器人不可用（已下架或封禁），停止重连",
                    code=fatal_code,
                )
                break
            if clear_session:
                self._logger.info("官方网关会话状态失效，下次连接重新 Identify")
                self._reset_session()
            delay = self._backoff_delay(attempt)
            attempt += 1
            self._logger.info(
                "官方网关将在重连前等待",
                seconds=round(delay, 2),
                reason=reason,
            )
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=delay)
            except asyncio.TimeoutError:
                continue
            break

    async def _connect_once(self) -> None:
        self._ready = False
        token = await self._token_provider.get_token()
        ws_url = await self._fetch_gateway_url(token)
        self._logger.info("正在连接 QQ 官方网关", url=ws_url)
        ws = await self._ws_connect(ws_url)
        self._ws = ws
        try:
            async for raw in ws:
                await self._handle_frame(ws, raw)
        except ConnectionClosed as exc:
            raise _GatewayClosed(
                getattr(exc, "code", None),
                str(getattr(exc, "reason", "") or ""),
            ) from exc
        finally:
            self._ws = None
            # 连接结束（正常关闭/异常/重连）立即视为不可用，避免重连退避期间
            # 面板与双通道路由继续按 connected 选路。
            self._connected.clear()
            self._ready = False
            # 每次连接结束都要停掉本轮心跳，否则旧心跳会跟随旧 ws 残留。
            await self._cancel_heartbeat()
            with suppress(Exception):
                await ws.close()

    async def _fetch_gateway_url(self, token: str) -> str:
        url = f"{self._settings.base_url.rstrip('/')}/gateway"
        headers = {"Authorization": f"QQBot {token}", "Accept": "application/json"}
        async with http_scope(self._http) as http:
            try:
                async with http.get(url, headers=headers) as response:
                    status = int(getattr(response, "status", 0) or 0)
                    data = await response.json(content_type=None)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                raise OfficialAuthError(f"获取官方网关地址失败: {type(exc).__name__}: {exc}") from exc
        if not isinstance(data, dict) or status != 200:
            raise OfficialAuthError(f"获取官方网关地址失败：HTTP {status}")
        ws_url = str(data.get("url") or "").strip()
        if not ws_url:
            raise OfficialAuthError("获取官方网关地址失败：响应缺少 url")
        return ws_url

    # ── 帧处理 ──────────────────────────────────────────────────────

    async def _handle_frame(self, ws: Any, raw: Any) -> None:
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            self._logger.warning("收到畸形网关帧，已跳过")
            return
        if not isinstance(payload, dict):
            self._logger.warning("收到非对象网关帧，已跳过")
            return
        op = payload.get("op")
        data = payload.get("d")
        if op == _OP_HELLO:
            await self._handle_hello(ws, data if isinstance(data, dict) else {})
        elif op == _OP_DISPATCH:
            self._track_dispatch(payload, data if isinstance(data, dict) else {})
            await self._emit(payload)
        elif op == _OP_HEARTBEAT_ACK:
            self._logger.debug("官方网关心跳已确认", seq=self._last_seq)
        elif op == _OP_RECONNECT:
            raise _Reconnect("服务端要求重连（op7）")
        elif op == _OP_INVALID_SESSION:
            raise _Reconnect("服务端判定会话失效（op9）", clear_session=True)
        else:
            self._logger.debug("收到未处理的网关操作码", op=op)

    def _track_dispatch(self, payload: dict[str, Any], data: dict[str, Any]) -> None:
        seq = payload.get("s")
        if isinstance(seq, int) and not isinstance(seq, bool):
            self._last_seq = seq
        event_type = str(payload.get("t") or "")
        if event_type == "READY":
            session_id = str(data.get("session_id") or "").strip()
            if session_id:
                self._session_id = session_id
            self._ready = True
            self._connected.set()
            self._logger.info("QQ 官方机器人网关就绪", session_id=self._session_id)
        elif event_type == "RESUMED":
            self._ready = True
            self._connected.set()
            self._logger.info("QQ 官方机器人网关已恢复连接")

    async def _handle_hello(self, ws: Any, data: dict[str, Any]) -> None:
        interval_ms = _positive_float(data.get("heartbeat_interval"), _DEFAULT_HEARTBEAT_INTERVAL_MS)
        self._heartbeat_interval = interval_ms / 1000.0 * _HEARTBEAT_RATIO
        token = await self._token_provider.get_token()
        if self._session_id and self._last_seq is not None:
            payload = self._resume_payload(token)
            self._logger.info(
                "官方网关发送 Resume",
                session_id=self._session_id,
                seq=self._last_seq,
            )
        else:
            payload = self._identify_payload(token)
            self._logger.info("官方网关发送 Identify", intents=_INTENTS)
        await ws.send(json.dumps(payload, ensure_ascii=False))
        self._start_heartbeat(ws)

    def _identify_payload(self, token: str) -> dict[str, Any]:
        return {
            "op": _OP_IDENTIFY,
            "d": {
                "token": f"QQBot {token}",
                "intents": _INTENTS,
                "shard": [0, 1],
            },
        }

    def _resume_payload(self, token: str) -> dict[str, Any]:
        return {
            "op": _OP_RESUME,
            "d": {
                "token": f"QQBot {token}",
                "session_id": self._session_id,
                "seq": self._last_seq,
            },
        }

    async def _emit(self, payload: dict[str, Any]) -> None:
        try:
            result = self._on_event(payload)
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            # 单条事件处理失败不能拖垮整个网关连接。
            self._logger.error(
                "官方事件回调失败，已跳过该事件",
                error_type=type(exc).__name__,
                error=str(exc),
            )

    # ── 心跳 ────────────────────────────────────────────────────────

    def _start_heartbeat(self, ws: Any) -> None:
        if self._heartbeat_task is not None and not self._heartbeat_task.done():
            return
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws), name="qq-official-heartbeat")

    async def _heartbeat_loop(self, ws: Any) -> None:
        try:
            while True:
                await asyncio.sleep(self._heartbeat_interval or 30.0)
                await ws.send(
                    json.dumps(
                        {"op": _OP_HEARTBEAT, "d": self._last_seq},
                        ensure_ascii=False,
                    )
                )
                self._logger.debug("官方网关心跳已发送", seq=self._last_seq)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # 心跳写不出去说明连接已经坏了：主动关闭，让 _run 走重连流程。
            self._logger.warning("官方网关心跳发送失败，主动断开重连", error=str(exc))
            with suppress(Exception):
                await ws.close()

    async def _cancel_heartbeat(self) -> None:
        task = self._heartbeat_task
        self._heartbeat_task = None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _close_ws(self) -> None:
        ws = self._ws
        self._ws = None
        if ws is not None:
            with suppress(Exception):
                await ws.close()

    def _reset_session(self) -> None:
        self._session_id = ""
        self._last_seq = None

    # ── 重连策略 ────────────────────────────────────────────────────

    def _classify_close(self, code: int | None) -> str:
        """close code -> 动作：fatal / token / session / retry。"""
        if code in _FATAL_CLOSE_CODES:
            return "fatal"
        if code in _TOKEN_CLOSE_CODES:
            return "token"
        if code in _SESSION_CLOSE_CODES:
            return "session"
        return "retry"

    def _backoff_delay(self, attempt: int) -> float:
        """指数退避 + 抖动；attempt 越大等待越久，上限 60 秒。"""
        exponent = min(max(attempt, 0), _MAX_BACKOFF_EXPONENT)
        base = min(_BACKOFF_MAX_SECONDS, _BACKOFF_BASE_SECONDS * (2**exponent))
        return base * (0.5 + random.random() / 2)


def _positive_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
