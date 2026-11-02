"""DSH daemon 网关的 aiohttp 服务端：认证、同步端点与长轮询。

路由（v1）：

- ``POST /dsh/daemon/sync``：上报 reports、取回 commands；没有命令时按
  ``poll_wait_seconds`` 挂起长轮询。
- ``GET  /dsh/daemon/health``：daemon 连接/游标快照（同样要求 token）。

认证顺序固定为「来源 IP 白名单 → Bearer token」，失败分别返回 403 / 401；
请求体非法返回 400，超过 ``max_body_bytes`` 返回 413。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable

from aiohttp import web
from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.config.schemas.bot_parts.dsh import DshGatewayConfig

from .auth import IpAllowList, is_loopback_host, resolve_client_ip, token_matches
from .models import PROTOCOL_VERSION, GatewayProtocolError, SyncResponse, parse_sync_request
from .service import DshGatewayService

SYNC_PATH = "/dsh/daemon/sync"
HEALTH_PATH = "/dsh/daemon/health"


def error_response(code: str, message: str, *, status: int) -> web.Response:
    """线协议错误体：``{"v": 1, "error": {"code", "message"}}``。"""
    return web.json_response(
        {"v": PROTOCOL_VERSION, "error": {"code": code, "message": message}},
        status=status,
    )


class DshGatewayServer:
    """一个最小 aiohttp 应用的生命周期封装（start/close 幂等）。"""

    def __init__(
        self,
        *,
        config: DshGatewayConfig,
        service: DshGatewayService,
        logger: Logger | None = None,
    ) -> None:
        self._config = config
        self._service = service
        self._logger = logger or NullLogger()
        self._token = str(config.token or "").strip()
        self._allow_ips = IpAllowList(config.allow_ips)
        self._poll_wait_seconds = max(0.0, float(config.poll_wait_seconds))
        self._port = int(config.port)
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    # ── 只读状态 ────────────────────────────────────────────────

    @property
    def port(self) -> int:
        """实际监听端口（配置 ``port=0`` 时是系统分配的端口）。"""
        return self._port

    @property
    def host(self) -> str:
        return self._config.host

    @property
    def running(self) -> bool:
        return self._site is not None

    @property
    def app(self) -> web.Application | None:
        """当前 aiohttp 应用（未启动时为 None）。"""
        return self._app

    # ── 应用与生命周期 ──────────────────────────────────────────

    def make_app(self) -> web.Application:
        """构建 aiohttp 应用；测试可直接交给 ``TestServer`` 使用。"""
        app = web.Application(
            client_max_size=max(1, int(self._config.max_body_bytes)),
            middlewares=[self._auth_middleware],
        )
        app.router.add_post(SYNC_PATH, self._handle_sync)
        app.router.add_get(HEALTH_PATH, self._handle_health)
        return app

    async def start(self) -> None:
        if self._site is not None:
            return
        app = self.make_app()
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, host=self._config.host, port=int(self._config.port))
        try:
            await site.start()
        except BaseException:
            await runner.cleanup()
            raise
        self._app = app
        self._runner = runner
        self._site = site
        self._port = self._bound_port(site, fallback=int(self._config.port))
        if not is_loopback_host(self._config.host):
            # 不拒绝启动：部署方可能已在前面放了 HTTPS 反代；这里只把风险说清楚。
            self._logger.warning(
                "DSH 网关监听非回环地址且未启用 TLS：token 会以明文传输，请确认前面有反向代理 + HTTPS",
                event="dsh_gateway.non_loopback",
                host=self._config.host,
                port=self._port,
            )
        self._logger.info(
            "DSH 网关已启动",
            event="dsh_gateway.started",
            host=self._config.host,
            port=self._port,
            path=SYNC_PATH,
            poll_wait_seconds=self._poll_wait_seconds,
        )

    async def close(self) -> None:
        site, runner = self._site, self._runner
        self._site = None
        self._runner = None
        self._app = None
        if site is not None:
            try:
                await site.stop()
            except Exception as exc:  # noqa: BLE001 - 收尾失败只报告，不中断关闭链
                self._logger.warning(
                    "DSH 网关停止监听失败",
                    event="dsh_gateway.stop_failed",
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
        if runner is not None:
            try:
                await runner.cleanup()
            except Exception as exc:  # noqa: BLE001
                self._logger.warning(
                    "DSH 网关清理失败",
                    event="dsh_gateway.cleanup_failed",
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
        if site is not None:
            self._logger.info("DSH 网关已关闭", event="dsh_gateway.closed")

    @staticmethod
    def _bound_port(site: web.TCPSite, *, fallback: int) -> int:
        server = getattr(site, "_server", None)
        sockets = getattr(server, "sockets", None) or ()
        if not sockets:
            return fallback
        try:
            return int(sockets[0].getsockname()[1])
        except (OSError, IndexError, TypeError, ValueError):
            return fallback

    # ── 认证 ────────────────────────────────────────────────────

    @web.middleware
    async def _auth_middleware(
        self,
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
    ) -> web.StreamResponse:
        remote_ip = resolve_client_ip(request)
        if not self._allow_ips.allows(remote_ip):
            self._logger.warning(
                "DSH 网关拒绝了白名单外的来源",
                event="dsh_gateway.ip_rejected",
                remote_ip=remote_ip,
                path=request.path,
            )
            return error_response("ip_not_allowed", "来源 IP 不在白名单内", status=403)
        if not token_matches(request.headers.get("Authorization"), self._token):
            response = error_response("unauthorized", "缺少或无效的 Bearer token", status=401)
            response.headers["WWW-Authenticate"] = 'Bearer realm="dsh-gateway"'
            return response
        return await handler(request)

    # ── 处理函数 ────────────────────────────────────────────────

    async def _handle_sync(self, request: web.Request) -> web.StreamResponse:
        try:
            payload = await request.json()
        except web.HTTPRequestEntityTooLarge:
            return error_response(
                "payload_too_large",
                f"请求体超过 {self._config.max_body_bytes} 字节上限",
                status=413,
            )
        except (json.JSONDecodeError, UnicodeDecodeError):
            return error_response("invalid_json", "请求体必须是合法 JSON", status=400)
        try:
            sync_request = parse_sync_request(payload)
        except GatewayProtocolError as exc:
            return error_response(exc.code, exc.message, status=400)
        try:
            response = await self._service.sync(sync_request)
            if not response.commands and self._poll_wait_seconds > 0:
                commands = await self._service.wait_for_commands(
                    sync_request.daemon_id,
                    self._poll_wait_seconds,
                )
                response = SyncResponse(
                    daemon_id=response.daemon_id,
                    cursor=response.cursor,
                    commands=commands,
                )
        except asyncio.CancelledError:
            # 客户端断开 / 服务端关闭时会取消 handler：安静退出，别再写响应。
            raise
        except Exception as exc:  # noqa: BLE001 - 插件 handler 失败统一转 500
            self._logger.error(
                "DSH 网关处理同步请求失败",
                event="dsh_gateway.sync_failed",
                daemon_id=sync_request.daemon_id,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return error_response("internal_error", "网关处理同步请求失败", status=500)
        return web.json_response(response.to_dict())

    async def _handle_health(self, request: web.Request) -> web.StreamResponse:
        daemons = self._service.health_snapshot()
        return web.json_response(
            {
                "v": PROTOCOL_VERSION,
                "gateway": {"host": self._config.host, "port": self._port},
                "connected": sum(1 for item in daemons if item["connected"]),
                "daemons": daemons,
            }
        )


__all__ = ["DshGatewayServer", "HEALTH_PATH", "SYNC_PATH", "error_response"]
