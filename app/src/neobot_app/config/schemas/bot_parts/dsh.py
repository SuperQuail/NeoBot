"""DSH 段：Router/Worker 集成的网关与工具面配置。

默认全部关闭。打开 ``router.enabled`` 只代表允许插件启用 Router 模式；
某个聊天流是否真的进入 Router 模式由插件在用户确认后调用
``RouterModeService.activate()`` 决定，普通会话行为不受影响。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


def _default_router_tools() -> List[str]:
    """Router 模式默认保留的工具（只读 + 回复基础设施）。

    ``dsh_router__*`` 由代码自动放行；``agents__delegate`` 刻意不在默认名单里，
    避免 Router 通过子 Agent 绕开工具面裁剪。
    """
    return [
        "read",
        "glob",
        "grep",
        "read_image",
        "send_reply",
        "split_reply",
        "send_long_reply",
        "wait",
        "check_background_tasks",
        "cancel_task",
        "skills__read_manifest",
        "skills__read_resource",
        "skills__view_instructions",
        "skills__load_tools",
    ]


@dataclass
class DshGatewayConfig:
    """核心最小网关：给开发机 daemon 出站轮询用。"""

    enabled: bool = field(
        default=False,
        metadata={
            "description": (
                "启用 DSH daemon 网关。默认关闭；开启后只监听本机回环地址，"
                "由 daemon 携带 token 出站轮询。"
            )
        },
    )
    host: str = field(
        default="127.0.0.1",
        metadata={
            "description": (
                "网关监听地址。默认 127.0.0.1；改成非回环地址前请确认前面有"
                "反向代理 + HTTPS，否则 token 会以明文传输"
            )
        },
    )
    port: int = field(
        default=8791,
        metadata={"description": "网关监听端口（默认 8791）"},
    )
    token: str = field(
        default="",
        metadata={
            "description": (
                "daemon 认证 token。网关与开发机 daemon 必须配置同一个值；"
                "留空时网关拒绝启动"
            )
        },
    )
    allow_ips: List[str] = field(
        default_factory=list,
        metadata={
            "description": (
                "允许的来源 IP / CIDR 白名单。留空表示不限制来源 IP，"
                "只靠 token 认证"
            )
        },
    )
    max_body_bytes: int = field(
        default=1_048_576,
        metadata={"description": "单次同步请求体上限（字节，默认 1 MiB）"},
    )
    poll_wait_seconds: int = field(
        default=25,
        metadata={"description": "daemon 长轮询最长挂起秒数（默认 25）"},
    )


@dataclass
class DshRouterConfig:
    """Router 模式：启用方式与工具面。"""

    enabled: bool = field(
        default=False,
        metadata={
            "description": (
                "允许 dsh_router 插件启用 Router 模式。关闭时插件工具不注册，"
                "所有会话保持原有工具面"
            )
        },
    )
    ask_before_enable: bool = field(
        default=True,
        metadata={
            "description": (
                "启用 Router 模式前先向用户确认。插件会按此开关决定是否允许"
                "直接 activate；默认必须确认"
            )
        },
    )
    allowed_tools: List[str] = field(
        default_factory=_default_router_tools,
        metadata={
            "description": (
                "Router 模式下额外保留的工具名（dsh_router__* 始终保留）。"
                "写文件、执行命令、委托子 Agent 等工具不在默认名单里"
            )
        },
    )
    inject_task_table: bool = field(
        default=True,
        metadata={
            "description": (
                "Router 模式激活时，每次模型调用前注入一行「活跃任务表」"
                "（由插件提供内容）"
            )
        },
    )
    auto_exit_idle_minutes: int = field(
        default=30,
        metadata={
            "description": (
                "没有活跃任务后自动退出 Router 模式的分钟数；"
                "0 表示不自动退出，只能由用户或插件显式关闭"
            )
        },
    )


@dataclass
class DshConfig:
    """DSH 桥接配置。"""

    gateway: DshGatewayConfig = field(default_factory=DshGatewayConfig)
    router: DshRouterConfig = field(default_factory=DshRouterConfig)
