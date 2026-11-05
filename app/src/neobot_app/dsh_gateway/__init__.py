"""核心最小 DSH daemon 网关。

开发机 daemon 出站轮询：上报语义事件（reports）、带走待执行命令（commands）。
插件通过宿主服务 ``ctx.plugin_host.services.get("dsh_gateway")`` 拿到
:class:`DshGatewayService` 并注册 handler。

默认关闭（``agent.dsh.gateway.enabled = false``）；关闭时不会创建服务、也不监听
端口。本包只做传输与去重，不包含 dsh_router 插件业务逻辑。
"""

from .models import (
    DaemonCommand,
    GatewayProtocolError,
    SyncReport,
    SyncRequest,
    SyncResponse,
    parse_sync_request,
)
from .runtime import DshGatewayRuntime, build_gateway_runtime
from .server import HEALTH_PATH, SYNC_PATH, DshGatewayServer
from .service import DaemonHandler, DshGatewayService

__all__ = [
    "DaemonCommand",
    "DaemonHandler",
    "DshGatewayRuntime",
    "DshGatewayServer",
    "DshGatewayService",
    "GatewayProtocolError",
    "HEALTH_PATH",
    "SYNC_PATH",
    "SyncReport",
    "SyncRequest",
    "SyncResponse",
    "build_gateway_runtime",
    "parse_sync_request",
]
