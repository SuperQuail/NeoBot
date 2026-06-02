from __future__ import annotations

import json
import time
from itertools import count
from typing import Any

from aiohttp import WSMsgType, web


class LocalWebSocketHub:
    def __init__(self) -> None:
        self._clients: set[web.WebSocketResponse] = set()
        self._session_ids = count(1)
        self._event_ids = count(1)

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def handle(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)
        self._clients.add(ws)
        session_id = f"ws_{int(time.time())}_{next(self._session_ids)}"
        await ws.send_json(
            {
                "type": "hello",
                "version": 1,
                "session_id": session_id,
                "server_time": int(time.time()),
            }
        )
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    await self._handle_text(ws, msg.data)
                elif msg.type == WSMsgType.ERROR:
                    break
        finally:
            self._clients.discard(ws)
        return ws

    async def broadcast(self, event_type: str, payload: dict[str, Any]) -> None:
        envelope = {
            "type": event_type,
            "id": f"evt_{int(time.time())}_{next(self._event_ids)}",
            "time": int(time.time()),
            "payload": payload,
        }
        stale: list[web.WebSocketResponse] = []
        for ws in list(self._clients):
            if ws.closed:
                stale.append(ws)
                continue
            try:
                await ws.send_json(envelope)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self._clients.discard(ws)

    async def close(self) -> None:
        for ws in list(self._clients):
            await ws.close(code=1001, message=b"Local adapter shutting down")
        self._clients.clear()

    async def _handle_text(self, ws: web.WebSocketResponse, data: str) -> None:
        try:
            packet = json.loads(data)
        except json.JSONDecodeError:
            await ws.send_json(
                {
                    "type": "error",
                    "id": "",
                    "time": int(time.time()),
                    "payload": {
                        "code": "invalid_json",
                        "message": "WebSocket message must be valid JSON",
                    },
                }
            )
            return
        if packet.get("type") == "ping":
            await ws.send_json(
                {
                    "type": "pong",
                    "id": str(packet.get("id") or ""),
                    "time": int(time.time()),
                }
            )
