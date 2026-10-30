"""Agent 段：子 Agent、沙箱、自修复与共享工具配置。"""

from dataclasses import dataclass, field
from typing import List, Optional

from .media import ImageCreationConfig, VisionDetect
from .memory import AgentMemory


@dataclass
class AgentSystem:
    """System Agent 配置。"""

    allowed_work_dirs: List[str] = field(
        default_factory=lambda: ["./Data/"],
        metadata={"description": "System Agent 允许操作的工作目录"},
    )


@dataclass
class AgentProblemSolver:
    """Problem Solver Agent 配置。

    模型路由由 agent_model.problem_solver 编号控制，无需在子 agent 配置中指定模型名。
    """

    enabled: bool = field(
        default=True,
        metadata={"description": "是否启用解题 Agent"},
    )
    timeout_seconds: Optional[float] = field(
        default=600.0,
        metadata={"description": "解题超时时间（秒），默认 10 分钟"},
    )
    max_tokens: Optional[int] = field(
        default=20480,
        metadata={"description": "最大输出 Token 数，默认 20K"},
    )
    notification_retry_seconds: int = field(
        default=30,
        metadata={"description": "解题完成后通知重试间隔（秒）"},
    )
    allow_sandbox_output: Optional[bool] = field(
        default=True,
        metadata={"description": "是否允许解题结果保存到沙箱并返回文件路径"},
    )
    max_retries: int = field(
        default=1,
        metadata={"description": "通知最大重试次数（不含首次）"},
    )
    startup_grace_seconds: float = field(
        default=3.0,
        metadata={"description": "后台解题启动宽限期（秒）"},
    )
    max_tasks_per_pipeline: int = field(
        default=5,
        metadata={"description": "每个聊天流最多保留的后台解题任务数"},
    )
    reasoning_effort: Optional[str] = field(
        default="max",
        metadata={"description": "推理强度：high 或 max"},
    )


@dataclass
class AgentBrowser:
    """浏览器 Agent 配置。"""

    enabled: bool = field(
        default=True,
        metadata={"description": "是否启用浏览器 Agent"},
    )
    hold_max_minutes: Optional[int] = field(
        default=120,
        metadata={"description": "浏览器页面保活最大分钟数，默认 120（2 小时）"},
    )
    auto_close_idle_seconds: Optional[int] = field(
        default=600,
        metadata={"description": "空闲自动关闭秒数，默认 600（10 分钟）"},
    )
    data_dir: Optional[str] = field(
        default="./data/browser/",
        metadata={"description": "浏览器数据目录"},
    )
    browser_path: Optional[str] = field(
        default="",
        metadata={"description": "Chrome/Chromium 可执行路径，留空则自动检测"},
    )


@dataclass
class SandboxMaintenance:
    """沙箱持久化文件定时维护配置。"""

    enabled: bool = field(
        default=True,
        metadata={"description": "是否启用定时维护"},
    )
    interval_seconds: Optional[int] = field(
        default=10800,
        metadata={"description": "维护间隔秒数，默认 10800（3 小时）"},
    )


@dataclass
class AgentSandbox:
    """沙箱文件系统配置。"""

    enabled: bool = field(
        default=True,
        metadata={"description": "是否启用沙箱系统"},
    )
    max_total_size_bytes: Optional[int] = field(
        default=2 * 1024 * 1024 * 1024,
        metadata={"description": "沙箱整体最大总容量（字节），默认 2GB。写入前检查，超出则拒绝"},
    )
    temp_max_age_seconds: Optional[int] = field(
        default=1800,
        metadata={"description": "临时文件最大存活秒数，默认 1800（30 分钟）"},
    )
    temp_hold_max_minutes: Optional[int] = field(
        default=120,
        metadata={"description": "临时文件保活最大分钟数，默认 120（2 小时）"},
    )
    scan_interval_seconds: Optional[int] = field(
        default=300,
        metadata={"description": "临时文件清理扫描间隔秒数，默认 300（5 分钟）"},
    )
    allowed_read_dirs: Optional[list[str]] = field(
        default_factory=lambda: ["./data/emoji/", "./data/creator/gallery/"],
        metadata={"description": "允许文件操作 agent 只读访问的目录列表（相对路径按数据目录的父目录解析）"},
    )
    excluded_workspaces: Optional[list[str]] = field(
        default_factory=list,
        metadata={
            "description": (
                "不受沙箱限制的工作区（绝对路径列表，支持 ~）：目录内文件读写、编辑、删除、移动全部放行，"
                "且不计入沙箱容量（目录本身位于沙箱根内时仍计入）；相对路径会在装配时直接报错"
            )
        },
    )
    maintenance: SandboxMaintenance = field(
        default_factory=SandboxMaintenance,
        metadata={"description": "沙箱持久化文件定时维护配置"},
    )


@dataclass
class AgentOneBot:
    """OneBot 通用动作的安全审查配置。"""

    auto_review: bool = field(
        default=True,
        metadata={
            "description": (
                "是否默认用 AI 自动审查 yellow/red 的 onebot__call 动作。"
                "true=审查通过直接执行，拒绝时提示申请管理员凭据；"
                "false=回到旧行为，所有非绿色动作都必须先申请凭据。"
            )
        },
    )
    review_timeout_seconds: float = field(
        default=30.0,
        metadata={"description": "自动审查单次模型调用超时（秒）"},
    )


@dataclass
class AgentSkill:
    """Skill 系统全局配置。"""

    disabled_skills: Optional[list[str]] = field(
        default_factory=list,
        metadata={"description": "禁用的 skill 名称列表（黑名单模式），空列表表示全部启用"},
    )


@dataclass
class AgentFileOperation:
    """文件操作 Agent 配置。"""

    enabled: bool = field(
        default=True,
        metadata={"description": "是否启用文件操作 Agent"},
    )


@dataclass
class AgentSelfHeal:
    """自修复 Agent 配置。

    通过 loguru ERROR sink 累积异常，触发后自动唤起 Agent 进行诊断、
    尝试安全修复并写 debug 报告，最终通过通知系统向管理员私聊推送。
    """

    enabled: bool = field(
        default=True,
        metadata={"description": "是否启用自修复 Agent"},
    )
    admin_account: Optional[str] = field(
        default="",
        metadata={
            "description": (
                "接收自修复通知的管理员 QQ；留空时回退到 chat.admin_accounts[0]。"
                "若两者都未配置则不会触发自修复任务"
            )
        },
    )
    traceback_threshold: Optional[int] = field(
        default=3,
        metadata={"description": "累积带 traceback 的异常数阈值；满足后立即触发"},
    )
    rate_threshold: Optional[int] = field(
        default=10,
        metadata={"description": "60 秒内错误速率阈值；满足后立即触发"},
    )
    rate_window_seconds: Optional[int] = field(
        default=60,
        metadata={"description": "错误速率统计窗口（秒）"},
    )
    min_interval_seconds: Optional[int] = field(
        default=300,
        metadata={"description": "两次自动触发的最小间隔（秒），避免短期内重复唤起；手动触发不受此限制"},
    )
    buffer_size: Optional[int] = field(
        default=200,
        metadata={"description": "异常环形缓冲区大小"},
    )
    timeout_seconds: float = field(
        default=300.0,
        metadata={"description": "自修复 Agent 单次诊断超时（秒）"},
    )
    max_tokens: int = field(
        default=8192,
        metadata={"description": "自修复 Agent 最大输出 Token 数"},
    )
    reasoning_effort: str = field(
        default="high",
        metadata={"description": "推理强度：high 或 max"},
    )
    sandbox_debug_dir: Optional[str] = field(
        default="debug/self_heal",
        metadata={"description": "沙箱内 debug 报告子目录（相对沙箱根）"},
    )
    daily_limit: Optional[int] = field(
        default=5,
        metadata={
            "description": (
                "自修复任务每日（自然日，进程内计数）最大触发次数；默认 5，"
                "防止异常风暴导致 LLM 费用失控"
            )
        },
    )


@dataclass
class AgentToolsConfig:
    """DSH 风格共享工具；执行工具仍需现有管理员凭据。"""

    enabled: bool = field(default=True, metadata={"description": "启用共享 agent 工具"})
    mode: str = field(default="native", metadata={"description": "任务工具模式：native（精简普通模式，默认）/ ptc（程序编排）"})
    ptc_enabled: bool = field(default=True, metadata={"description": "启用可选PTC能力；不改变默认普通模式"})
    shell_enabled: bool = field(default=True, metadata={"description": "提供需凭据的 Python/命令工具"})
    terminal_enabled: bool = field(default=True, metadata={"description": "提供需凭据的持久管道终端（非 PTY）"})
    web_enabled: bool = field(default=True, metadata={"description": "提供联网搜索和网页读取"})
    lsp_enabled: bool = field(default=True, metadata={"description": "默认启用项目依赖内的Python语言服务器（按需启动）"})
    lsp_servers: dict = field(default_factory=dict, metadata={"description": "覆盖/扩展默认Python LSP：扩展名映射到command数组及language_id；关闭使用lsp_enabled=false"})
    max_agent_iterations: int = field(default=20, metadata={"description": "每个子 agent 的工具调用轮数上限"})
    max_goal_rounds: int = field(default=8, metadata={"description": "同一目标的最大自动轮数"})
    max_child_agents: int = field(default=8, metadata={"description": "每个 owner 的子 agent 数量上限"})
    max_output_bytes: int = field(default=262144, metadata={"description": "单次共享工具输出的最大 UTF-8 字节数"})
    auto_review: bool = field(
        default=True,
        metadata={"description": "沙箱/宿主执行等敏感工具默认 AI 自动审查；false=回到旧凭据门控"},
    )
    admin_self_authorize: bool = field(
        default=False,
        metadata={
            "description": (
                "管理员本人发起的请求视为已授权：跳过凭据申请与自动审查；"
                "其他人发起的请求仍需管理员签发凭据。默认只信任与超管的私聊，"
                "群聊需另配 admin_self_authorize_chats。默认 false（所有人一律走审查/凭据）"
            )
        },
    )
    admin_self_authorize_chats: Optional[list[str]] = field(
        default_factory=list,
        metadata={
            "description": (
                "额外的受信会话（如 group:12345）：管理员本人发起的请求在这些会话里也免审批。"
                "受信群里的其他成员可能通过 wait 插话搭上同一条回复管线，只填只有可信成员的群"
            )
        },
    )
    review_timeout_seconds: float = field(
        default=30.0,
        metadata={"description": "敏感工具自动审查单次模型调用超时（秒）"},
    )


@dataclass
class Agent:
    """Agent 配置。"""

    creator: ImageCreationConfig = field(default_factory=ImageCreationConfig)
    system: AgentSystem = field(default_factory=AgentSystem)
    memory: AgentMemory = field(default_factory=AgentMemory)
    problem_solver: AgentProblemSolver = field(default_factory=AgentProblemSolver)
    browser: AgentBrowser = field(default_factory=AgentBrowser)
    sandbox: AgentSandbox = field(default_factory=AgentSandbox)
    skill: AgentSkill = field(default_factory=AgentSkill)
    onebot: AgentOneBot = field(default_factory=AgentOneBot)
    file_operation: AgentFileOperation = field(default_factory=AgentFileOperation)
    self_healing: AgentSelfHeal = field(default_factory=AgentSelfHeal)
    vision_detect: VisionDetect = field(default_factory=VisionDetect)
    tools: AgentToolsConfig = field(default_factory=AgentToolsConfig)
