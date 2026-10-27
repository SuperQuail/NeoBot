"""适配器段：OneBot / 本地适配器监听与鉴权配置。"""

from dataclasses import dataclass, field


@dataclass
class Adapter:
    """适配器配置。"""

    mode: str = field(
        default="onebot",
        metadata={"description": "适配器模式：onebot 或 local"},
    )
    local_host: str = field(
        default="127.0.0.1",
        metadata={"description": "本地适配器 HTTP/WebSocket 监听地址"},
    )
    local_port: int = field(
        default=8090,
        metadata={"description": "本地适配器 HTTP/WebSocket 监听端口"},
    )
    local_auth_token: str = field(
        default="",
        metadata={
            "description": (
                "本地适配器（local 模式）的 Bearer token：留空表示不校验，"
                "此时若监听非回环地址会在启动日志告警。也可用环境变量 "
                "NEOBOT_LOCAL_ADAPTER_TOKEN 配置"
            )
        },
    )
    reverse_ws_host: str = field(
        default="",
        metadata={
            "description": (
                "OneBot 反向 WebSocket 服务端监听地址（onebot 模式）；"
                "留空则读环境变量 NEO_BOT_ADAPTER_HOST（兼容回退 NEOBOT_LOCAL_ADAPTER_HOST），"
                "再缺省 0.0.0.0"
            )
        },
    )
    reverse_ws_port: int = field(
        default=0,
        metadata={
            "description": (
                "OneBot 反向 WebSocket 服务端监听端口（onebot 模式）；"
                "0 表示未配置，读环境变量 NEO_BOT_ADAPTER_PORT（兼容回退 "
                "NEOBOT_LOCAL_ADAPTER_PORT），再缺省 8080"
            )
        },
    )
    reverse_ws_access_token: str = field(
        default="",
        metadata={
            "description": (
                "OneBot 反向 WebSocket 握手鉴权的 access token（onebot 模式，"
                "OneBot 11 规范）：框架侧在握手请求头带 Authorization: Bearer <token>，"
                "本端校验一致才接受连接。留空表示不校验（此时监听非回环地址会告警）。"
                "也可用环境变量 NEO_BOT_ADAPTER_TOKEN / NEOBOT_ADAPTER_TOKEN 配置"
            )
        },
    )
