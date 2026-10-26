"""弹幕 WebSocket：连接、收包分发、事件回调与每房间任务生命周期。"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import time
from collections import deque
from typing import Any

import aiohttp

from neobot_app.bilibili._compat import call_client, get_field, resolve_client
from neobot_app.bilibili.live_parts.constants import (
    _DANMU_MAX_PENDING,
    _MAX_RECENT_EVENTS,
    _WS_AUTH_MAX_FAILURES,
    _WS_HEALTHY_SECONDS,
    _WS_OP_AUTH,
    _WS_OP_AUTH_REPLY,
    _WS_OP_HEARTBEAT,
    _WS_OP_MESSAGE,
    _WS_RECEIVE_TIMEOUT_SECONDS,
    _WS_RECONNECT_MAX_SECONDS,
)
from neobot_app.bilibili.live_parts.helpers import _client_user_agent, _to_int, _with_jitter
from neobot_app.bilibili.live_protocol import (
    LiveAuthError,
    LiveEvent,
    check_auth_reply,
    decode_packets,
    encode_packet,
    event_key,
    parse_events,
)


class _WebSocketMixin:
    """连接弹幕服务器、分发收包、把事件转给回调，并管理每房间监听任务。"""

    async def _room_loop(self, room_id: str) -> None:
        backoff = 1.0
        attempt = 0
        auth_failures = 0
        while self._running:
            started = time.monotonic()
            try:
                authenticated = await self._connect_once(room_id, attempt)
                if authenticated:
                    auth_failures = 0
                if time.monotonic() - started >= _WS_HEALTHY_SECONDS:
                    backoff = 1.0
            except asyncio.CancelledError:
                raise
            except LiveAuthError as exc:
                auth_failures += 1
                self._logger.warning(
                    f"B站直播弹幕认证失败（连续 {auth_failures}/{_WS_AUTH_MAX_FAILURES} 次）："
                    f"房间 {room_id}，错误 {exc}"
                )
                if auth_failures >= _WS_AUTH_MAX_FAILURES:
                    # token 连续被拒多半是登录态失效，继续重连只会刷接口：停掉本房间监听。
                    self._logger.error(
                        f"B站直播弹幕认证连续失败，已停止监听该房间：房间 {room_id}，"
                        "请检查B站登录态后重新开启直播互动"
                    )
                    return
            except Exception as exc:
                self._logger.warning(
                    f"B站直播弹幕连接失败，准备重连：房间 {room_id}，"
                    f"错误 {type(exc).__name__}: {exc}"
                )
            if not self._running:
                return
            # host_list 按尝试次数轮换，避免一直撞同一个故障节点。
            attempt += 1
            await asyncio.sleep(_with_jitter(backoff))
            backoff = min(backoff * 2, _WS_RECONNECT_MAX_SECONDS)

    async def _connect_once(self, room_id: str, attempt: int = 0) -> bool:
        """连一次弹幕服务器并收包；正常断开返回是否成功认证过，异常向上抛给 _room_loop。"""
        client = self._get_client()
        if client is None:
            raise RuntimeError("B站未登录或客户端不可用")
        rid = _to_int(room_id)
        room = self._rooms.get(room_id) or {}
        real_room_id = _to_int(room.get("real_room_id")) or rid
        info = await call_client(client.get_live_danmu_info, rid)
        if not isinstance(info, dict):
            raise RuntimeError("弹幕服务器信息为空")
        token = str(info.get("token") or "")
        hosts = [item for item in info.get("host_list") or [] if isinstance(item, dict) and item.get("host")]
        if not token or not hosts:
            raise RuntimeError("弹幕服务器信息缺少 token/host_list")
        server = hosts[attempt % len(hosts)]
        host = str(server["host"])
        port = _to_int(server.get("wss_port")) or 443
        url = f"wss://{host}:{port}/sub"
        uid = await self._resolve_my_uid(client)
        buvid = str(get_field(client, "buvid3", "") or get_field(client, "_buvid3", "") or "")
        auth = {
            "uid": uid,
            "roomid": real_room_id,
            "protover": 3,
            "platform": "web",
            "type": 2,
            "buvid": buvid,
            "key": token,
        }
        # token 与 UA 绑定：与 getDanmuInfo 用同一个 UA。
        headers = {
            "User-Agent": _client_user_agent(client),
            "Origin": "https://live.bilibili.com",
            "Referer": f"https://live.bilibili.com/{real_room_id}",
        }
        authenticated = False
        async with aiohttp.ClientSession() as session:
            # receive_timeout：2×心跳收不到任何包就认为连接僵死，让收包循环抛超时去重连。
            async with session.ws_connect(
                url, headers=headers, receive_timeout=_WS_RECEIVE_TIMEOUT_SECONDS
            ) as ws:
                await ws.send_bytes(encode_packet(_WS_OP_AUTH, json.dumps(auth).encode("utf-8")))
                heartbeat = asyncio.create_task(self._heartbeat(ws))
                try:
                    async for message in ws:
                        if message.type == aiohttp.WSMsgType.BINARY:
                            for op, body in decode_packets(message.data):
                                if await self._handle_packet(room_id, op, body):
                                    authenticated = True
                                    # 认证成功后立即补一次心跳，随后交给 30s 定时器。
                                    await ws.send_bytes(encode_packet(_WS_OP_HEARTBEAT))
                        elif message.type in (
                            aiohttp.WSMsgType.ERROR,
                            aiohttp.WSMsgType.CLOSED,
                            aiohttp.WSMsgType.CLOSING,
                        ):
                            break
                except TimeoutError:
                    raise RuntimeError(
                        f"超过 {_WS_RECEIVE_TIMEOUT_SECONDS:.0f} 秒未收到弹幕数据包，主动断开重连"
                    ) from None
                finally:
                    heartbeat.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await heartbeat
        return authenticated

    async def _handle_packet(self, room_id: str, op: int, body: bytes) -> bool:
        """处理一个业务包；返回 True 表示认证成功，需要立即补心跳。"""
        if op == _WS_OP_AUTH_REPLY:
            check_auth_reply(body)
            return True
        if op != _WS_OP_MESSAGE or not body:
            return False
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return False
        for event in parse_events(payload, _to_int(room_id)):
            if event.kind == "danmaku":
                # 生成回复可能耗时 90s；不能阻塞 WebSocket 收包，否则后续弹幕
                # 连历史都记不上。
                self._schedule_danmu(
                    room_id,
                    {
                        "uid": event.uid,
                        "name": event.name,
                        "text": event.text,
                        "reply_mid": getattr(event, "reply_mid", 0),
                        "dmid": getattr(event, "dmid", ""),
                        # 收包时刻：排队超过 _DANMU_STALE_SECONDS 就不再自动回复。
                        "recv_at": time.monotonic(),
                    },
                )
                continue
            await self._handle_event(room_id, event)
        return False

    def _schedule_danmu(self, room_id: str, danmu: dict[str, Any]) -> None:
        """把弹幕处理丢进后台任务；每房间排队数有上限，刷屏时丢弃新的（历史也一并放弃）。"""
        pending = self._pending_danmu.get(room_id, 0)
        if pending >= _DANMU_MAX_PENDING:
            self._logger.debug(
                f"B站直播弹幕处理积压已达 {_DANMU_MAX_PENDING} 条，丢弃新弹幕：房间 {room_id}"
            )
            return
        self._pending_danmu[room_id] = pending + 1
        task = asyncio.create_task(self._handle_danmu(room_id, danmu))
        self._reply_tasks.add(task)
        task.add_done_callback(lambda done: self._danmu_task_done(room_id, done))

    def _danmu_task_done(self, room_id: str, task: asyncio.Task[None]) -> None:
        self._reply_tasks.discard(task)
        pending = self._pending_danmu.get(room_id, 0) - 1
        if pending > 0:
            self._pending_danmu[room_id] = pending
        else:
            self._pending_danmu.pop(room_id, None)

    async def _handle_event(self, room_id: str, event: LiveEvent) -> None:
        """统一事件入口：弹幕走历史/自动回复，其余进 recent_events + on_event。"""
        if event.kind == "danmaku":
            await self._handle_danmu(room_id, {"uid": event.uid, "name": event.name, "text": event.text})
            return
        key = event_key(event)
        if key and not self._event_keys.add(f"{room_id}:{key}"):
            return
        events = self._recent.get(room_id)
        if events is None:
            events = self._recent[room_id] = deque(maxlen=_MAX_RECENT_EVENTS)
        events.append(event)
        self._emit_event(event)

    def _emit_event(self, event: LiveEvent) -> None:
        """把事件交给可选回调；异步回调只排任务，不阻塞收包。"""
        if self._on_event is None:
            return
        try:
            result = self._on_event(event)
        except Exception as exc:
            self._logger.warning(f"B站直播事件回调失败：错误 {type(exc).__name__}: {exc}")
            return
        if inspect.isawaitable(result):
            task = asyncio.create_task(self._await_event_callback(result))
            self._event_tasks.add(task)
            task.add_done_callback(self._event_tasks.discard)

    async def _await_event_callback(self, awaitable: Any) -> None:
        try:
            await awaitable
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._logger.warning(f"B站直播事件回调失败：错误 {type(exc).__name__}: {exc}")

    def _get_client(self) -> Any | None:
        """取当前可用 client；service 不可用时 resolve_client 返回 None。"""
        client = resolve_client(self._service)
        return client if callable(getattr(client, "send_danmaku", None)) else None

    async def _resolve_my_uid(self, client: Any) -> int:
        """解析并缓存自己的 UID：client.my_uid 是属性，未缓存时会打 nav 接口，必须丢线程池。"""
        if self._my_uid:
            return self._my_uid
        try:
            uid = _to_int(await call_client(lambda: getattr(client, "my_uid", 0)))
        except Exception as exc:
            self._logger.warning(f"B站直播账号 UID 解析失败：{type(exc).__name__}: {exc}")
            return 0
        if uid > 0:
            self._my_uid = uid
        return self._my_uid

    def _start_task(self, room_id: str) -> None:
        if not self._running:
            return
        task = self._tasks.get(room_id)
        if task is not None and not task.done():
            return
        self._tasks[room_id] = asyncio.create_task(self._room_loop(room_id), name=f"bilibili-live-{room_id}")

    async def _cancel_task(self, room_id: str) -> None:
        task = self._tasks.pop(room_id, None)
        if task is None:
            return
        task.cancel()
        if task is not asyncio.current_task():
            with contextlib.suppress(asyncio.CancelledError):
                await task
