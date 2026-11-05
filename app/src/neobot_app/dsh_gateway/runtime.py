"""网关运行期封装：按配置装配 service + server，并挂到应用生命周期。

``enabled=False`` 时 :func:`build_gateway_runtime` 直接返回 None：不创建服务、
不监听端口，插件读宿主服务 ``dsh_gateway`` 也只会拿到 None。
"""

from __future__ import annotations

from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

from .server import DshGatewayServer
from .service import DshGatewayService


class DshGatewayRuntime:
    """把网关服务端挂到 ``NeoBotApplication`` 启动/关闭步骤上的轻量封装。"""

    def __init__(
        self,
        *,
        config: Any,
        service: DshGatewayService,
        server: DshGatewayServer,
        logger: Logger | None = None,
    ) -> None:
        self._config = config
        self._service = service
        self._server = server
        self._logger = logger or NullLogger()
        self._started = False

    @property
    def service(self) -> DshGatewayService:
        """注册进宿主服务 ``dsh_gateway`` 的对象。"""
        return self._service

    @property
    def server(self) -> DshGatewayServer:
        return self._server

    @property
    def port(self) -> int:
        return self._server.port

    @property
    def running(self) -> bool:
        return self._server.running

    @property
    def started(self) -> bool:
        return self._started

    async def start(self) -> None:
        if self._started:
            return
        try:
            await self._server.start()
        except OSError as exc:
            # 端口被占用/无权限等：网关是可选增强，不能拖垮 bot 主流程启动。
            self._logger.error(
                "DSH 网关启动失败，本次不监听（bot 其它功能不受影响）",
                event="dsh_gateway.start_failed",
                host=self._server.host,
                port=self._server.port,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return
        self._started = True

    async def close(self) -> None:
        self._started = False
        await self._server.close()


def build_gateway_runtime(
    *,
    config: Any,
    logger: Logger | None = None,
) -> DshGatewayRuntime | None:
    """按 ``agent.dsh.gateway`` 配置创建网关；关闭或配置不完整时返回 None。"""
    log = logger or NullLogger()
    if config is None or not bool(getattr(config, "enabled", False)):
        return None
    token = str(getattr(config, "token", "") or "").strip()
    if not token:
        log.error(
            "DSH 网关已启用但 token 为空，拒绝启动网关（不监听端口）",
            event="dsh_gateway.no_token",
        )
        return None
    service = DshGatewayService(logger=log)
    try:
        server = DshGatewayServer(config=config, service=service, logger=log)
    except ValueError as exc:
        log.error(
            "DSH 网关 allow_ips 配置非法，拒绝启动网关",
            event="dsh_gateway.bad_allow_ips",
            error=str(exc),
        )
        return None
    log.info(
        "DSH 网关已装配",
        event="dsh_gateway.configured",
        host=getattr(config, "host", ""),
        port=getattr(config, "port", 0),
        allow_ips=list(getattr(config, "allow_ips", []) or ()),
        max_body_bytes=getattr(config, "max_body_bytes", 0),
        poll_wait_seconds=getattr(config, "poll_wait_seconds", 0),
    )
    return DshGatewayRuntime(config=config, service=service, server=server, logger=log)


__all__ = ["DshGatewayRuntime", "build_gateway_runtime"]
