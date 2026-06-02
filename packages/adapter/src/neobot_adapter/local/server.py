from __future__ import annotations

from typing import Any

from aiohttp import web


class LocalAdapterServer:
    def __init__(
        self,
        *,
        core: Any,
        host: str = "127.0.0.1",
        port: int = 8090,
        auth_token: str = "",
    ) -> None:
        self._core = core
        self._host = host
        self._port = int(port)
        self._auth_token = auth_token or ""
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._running = False

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> None:
        if self._running:
            return
        self._app = web.Application(middlewares=[self._error_middleware, self._auth_middleware])
        self._app.router.add_get("/health", self._handle_health)
        self._app.router.add_post("/v1/messages", self._handle_create_message)
        self._app.router.add_post("/v1/events", self._handle_create_event)
        self._app.router.add_get("/v1/conversations", self._handle_list_conversations)
        self._app.router.add_get(
            "/v1/conversations/{kind}/{id}/messages",
            self._handle_list_messages,
        )
        self._app.router.add_post("/v1/send", self._handle_send)
        self._app.router.add_post("/v1/actions/{action}", self._handle_action)
        self._app.router.add_post("/v1/test/reset", self._handle_test_reset)
        self._app.router.add_get("/v1/test/export", self._handle_test_export)
        self._app.router.add_post("/v1/test/import", self._handle_test_import)
        self._app.router.add_post("/v1/test/friends", self._handle_test_upsert_friend)
        self._app.router.add_delete("/v1/test/friends/{user_id}", self._handle_test_delete_friend)
        self._app.router.add_post("/v1/test/groups", self._handle_test_upsert_group)
        self._app.router.add_post(
            "/v1/test/groups/{group_id}/members",
            self._handle_test_upsert_group_member,
        )
        self._app.router.add_delete(
            "/v1/test/groups/{group_id}/members/{user_id}",
            self._handle_test_delete_group_member,
        )
        self._app.router.add_post("/v1/test/media", self._handle_test_media)
        self._app.router.add_post("/v1/test/forward-messages", self._handle_test_forward)
        self._app.router.add_post("/v1/test/friend-requests", self._handle_test_friend_request)
        self._app.router.add_post("/v1/test/group-requests", self._handle_test_group_request)
        self._app.router.add_post("/v1/test/notices", self._handle_test_notice)
        self._app.router.add_get("/ws", self._core.websocket_handler)
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._host, self._port)
        await self._site.start()
        if self._port == 0 and self._site._server is not None:
            sockets = self._site._server.sockets or []
            if sockets:
                self._port = int(sockets[0].getsockname()[1])
        self._running = True

    async def stop(self) -> None:
        self._running = False
        if self._runner is not None:
            await self._runner.cleanup()
        self._site = None
        self._runner = None
        self._app = None

    def public_http_url(self) -> str:
        return f"http://{self._host}:{self._port}"

    def public_ws_url(self) -> str:
        return f"ws://{self._host}:{self._port}/ws"

    @web.middleware
    async def _error_middleware(self, request: web.Request, handler):
        try:
            return await handler(request)
        except web.HTTPException:
            raise
        except ValueError as exc:
            return self._error("invalid_request", str(exc), status=400)
        except Exception as exc:
            return self._error("internal_error", str(exc), status=500)

    @web.middleware
    async def _auth_middleware(self, request: web.Request, handler):
        if self._auth_token:
            header = request.headers.get("Authorization", "")
            expected = f"Bearer {self._auth_token}"
            query_token = request.query.get("token") if request.path == "/ws" else None
            if header != expected and query_token != self._auth_token:
                return self._error("unauthorized", "Authorization token is invalid", status=401)
        return await handler(request)

    async def _handle_health(self, request: web.Request) -> web.Response:
        return self._ok(self._core.health())

    async def _handle_create_message(self, request: web.Request) -> web.Response:
        data = await self._read_json(request)
        result = await self._core.create_message(data)
        return self._ok(result)

    async def _handle_create_event(self, request: web.Request) -> web.Response:
        data = await self._read_json(request)
        result = await self._core.create_event(data)
        return self._ok(result)

    async def _handle_list_conversations(self, request: web.Request) -> web.Response:
        return self._ok(self._core.list_conversations())

    async def _handle_list_messages(self, request: web.Request) -> web.Response:
        try:
            limit = int(request.query.get("limit", "50"))
        except ValueError:
            limit = 50
        before_raw = request.query.get("before_message_id")
        before_message_id = None
        if before_raw:
            try:
                before_message_id = int(before_raw)
            except ValueError:
                before_message_id = None
        result = self._core.list_messages(
            kind=request.match_info["kind"],
            conversation_id=request.match_info["id"],
            limit=limit,
            before_message_id=before_message_id,
        )
        return self._ok(result)

    async def _handle_send(self, request: web.Request) -> web.Response:
        data = await self._read_json(request)
        result = await self._core.create_outgoing(data)
        return self._ok(result)

    async def _handle_action(self, request: web.Request) -> web.Response:
        data = await self._read_json(request)
        action = request.match_info["action"]
        params = data.get("params", {}) if isinstance(data, dict) else {}
        timeout = float(data.get("timeout", 5.0)) if isinstance(data, dict) else 5.0
        result = await self._core.call_api(action, params, timeout)
        await self._core.broadcast_action(action, params, result)
        return self._ok(result)

    async def _handle_test_reset(self, request: web.Request) -> web.Response:
        return self._ok(await self._core.reset_sandbox())

    async def _handle_test_export(self, request: web.Request) -> web.Response:
        return self._ok(await self._core.export_sandbox_state())

    async def _handle_test_import(self, request: web.Request) -> web.Response:
        return self._ok(await self._core.import_sandbox_state(await self._read_json(request)))

    async def _handle_test_upsert_friend(self, request: web.Request) -> web.Response:
        return self._ok(await self._core.upsert_friend(await self._read_json(request)))

    async def _handle_test_delete_friend(self, request: web.Request) -> web.Response:
        return self._ok(await self._core.delete_friend(request.match_info["user_id"]))

    async def _handle_test_upsert_group(self, request: web.Request) -> web.Response:
        return self._ok(await self._core.upsert_group(await self._read_json(request)))

    async def _handle_test_upsert_group_member(self, request: web.Request) -> web.Response:
        data = await self._read_json(request)
        return self._ok(await self._core.upsert_group_member(request.match_info["group_id"], data))

    async def _handle_test_delete_group_member(self, request: web.Request) -> web.Response:
        return self._ok(
            await self._core.remove_group_member(
                request.match_info["group_id"],
                request.match_info["user_id"],
            )
        )

    async def _handle_test_media(self, request: web.Request) -> web.Response:
        return self._ok(await self._core.register_media(await self._read_json(request)))

    async def _handle_test_forward(self, request: web.Request) -> web.Response:
        return self._ok(await self._core.create_forward_message(await self._read_json(request)))

    async def _handle_test_friend_request(self, request: web.Request) -> web.Response:
        return self._ok(await self._core.create_friend_request(await self._read_json(request)))

    async def _handle_test_group_request(self, request: web.Request) -> web.Response:
        return self._ok(await self._core.create_group_request(await self._read_json(request)))

    async def _handle_test_notice(self, request: web.Request) -> web.Response:
        return self._ok(await self._core.create_notice(await self._read_json(request)))

    async def _read_json(self, request: web.Request) -> dict[str, Any]:
        try:
            data = await request.json()
        except Exception as exc:
            raise web.HTTPBadRequest(
                text=self._error_text("invalid_json", f"Invalid JSON: {exc}"),
                content_type="application/json",
            ) from exc
        if not isinstance(data, dict):
            raise web.HTTPBadRequest(
                text=self._error_text("invalid_request", "JSON body must be an object"),
                content_type="application/json",
            )
        return data

    @staticmethod
    def _ok(data: Any) -> web.Response:
        return web.json_response({"ok": True, "data": data, "error": None})

    @staticmethod
    def _error(code: str, message: str, *, status: int = 400) -> web.Response:
        return web.json_response(
            {
                "ok": False,
                "data": None,
                "error": {"code": code, "message": message},
            },
            status=status,
        )

    @staticmethod
    def _error_text(code: str, message: str) -> str:
        import json

        return json.dumps(
            {
                "ok": False,
                "data": None,
                "error": {"code": code, "message": message},
            },
            ensure_ascii=False,
        )
