"""运行时服务段：回复意愿、插件、消息、文件服务器、调试、待机与定时任务配置。"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Willing:
    """回复意愿管理器配置。"""

    manager_name: Optional[str] = field(
        default="Quail",
        metadata={"description": "回复意愿管理器名称"},
    )
    observe_window: Optional[int] = field(
        default=5,
        metadata={"description": "意愿计算观察窗口"},
    )


@dataclass
class Plugins:
    """插件配置。"""

    enabled: bool = field(default=True, metadata={"description": "是否启用插件"})
    dir: str = field(default="./plugins", metadata={"description": "插件目录"})
    watch: bool = field(
        default=False,
        metadata={"description": "监听已加载插件源码并自动热重载（开发用，修改此项需重启）"},
    )
    proxy_mode: str = field(
        default="system",
        metadata={
            "description": "插件下载代理模式：system 跟随系统/环境变量代理，none 直连，custom 使用自定义 HTTP 代理"
        },
    )
    proxy_host: str = field(
        default="127.0.0.1",
        metadata={"description": "自定义代理地址（proxy_mode=custom 时生效）"},
    )
    proxy_port: int = field(
        default=7890,
        metadata={"description": "自定义代理端口（proxy_mode=custom 时生效）"},
    )


@dataclass
class Message:
    """消息处理配置。"""

    max_length: Optional[int] = field(
        default=1000,
        metadata={"description": "消息最大长度"},
    )
    enable_group: Optional[bool] = field(
        default=True,
        metadata={"description": "是否处理群消息"},
    )
    enable_private: Optional[bool] = field(
        default=True,
        metadata={"description": "是否处理私聊消息"},
    )


@dataclass
class FileServer:
    """文件服务器配置。"""

    port: int = field(default=8765, metadata={"description": "文件服务器端口"})
    host: str = field(
        default="127.0.0.1",
        metadata={"description": "文件服务器主机地址"},
    )
    public_url: Optional[str] = field(
        default=None,
        metadata={"description": "访问地址"},
    )
    enabled: bool = field(default=True, metadata={"description": "是否启用文件服务器"})


@dataclass
class Debug:
    """调试配置。"""

    enabled: bool = field(
        default=False,
        metadata={"description": "是否启用 Debug 模式"},
    )
    retention_days: int = field(
        default=10,
        metadata={"description": "调试数据保留天数（默认 10）：data/debug/log 下更早的分片与回复事件明细会被自动清理"},
    )


@dataclass
class Standby:
    """待机状态配置。

    待机 = 只启动最基本的服务（面板、配置、命令），bot 运行时整体停掉；
    面板可改任意配置并软重启运行，不必重启进程。
    """

    start_in_standby: Optional[bool] = field(
        default=False,
        metadata={
            "description": "启动时直接进入待机（只启动面板等核心服务，不启动 bot 运行时）；适合先开面板补配置再启动运行"
        },
    )
    connect_onebot: Optional[bool] = field(
        default=True,
        metadata={
            "description": "待机时是否保持与 OneBot 的连接（默认保持：QQ 命令仍可用，"
            "便于随时恢复运行；关闭后待机期只有面板可用）"
        },
    )
    shutdown_timeout_seconds: Optional[float] = field(
        default=300.0,
        metadata={
            "description": "进入待机/软重启时等待优雅关闭的窗口(秒)。关闭要跑记忆总结"
            "这类收尾，单次总结预算默认 300 秒，所以窗口必须能装下它，否则会误判成"
            "「关闭卡住」；窗口到点只是记日志并继续等，不会中断关闭。调大它不会让"
            "关闭变慢，只是放宽判定"
        },
    )
    resume_timeout_seconds: Optional[float] = field(
        default=600.0,
        metadata={
            "description": "软重启运行的总窗口(秒)，必须大于 shutdown_timeout_seconds"
            "（关闭 + 按当前配置重建运行时）；到点仍未完成才判失败并停在待机"
        },
    )


@dataclass
class ScheduledTask:
    """定时任务系统配置。"""

    enabled: Optional[bool] = field(
        default=True,
        metadata={"description": "是否启用定时任务系统；关闭后定时任务 agent 不会注册"},
    )
    reminder_cooldown_seconds: Optional[int] = field(
        default=300,
        metadata={"description": "同一定时任务在触发时间窗口内重复提醒的冷却秒数，默认300秒"},
    )
    poll_interval_seconds: Optional[int] = field(
        default=10,
        metadata={"description": "定时任务扫描间隔秒数，默认 10 秒"},
    )
    default_window_seconds: Optional[int] = field(
        default=3600,
        metadata={"description": "任务未指定时间窗口时使用的默认窗口秒数"},
    )
    max_repeating_tasks: Optional[int] = field(
        default=15,
        metadata={"description": "重复定时任务数量上限；一次性任务不计入此上限"},
    )
    default_one_shot_notification: Optional[bool] = field(
        default=True,
        metadata={
            "description": "新建定时任务默认是否使用一次性通知；一次性通知指每个触发窗口只通知一次并自动完成该窗口，不等同于 once 一次性任务"
        },
    )
    missed_window_grace_seconds: Optional[int] = field(
        default=300,
        metadata={
            "description": "错过窗口的补发宽限期（秒）：窗口结束超过该秒数才被扫描到的任务视为停机期间错过，不再补发提醒（默认 300 秒）。没有上限时进程重启会把早已过期的任务补发一遍"
        },
    )
