"""Agent 记忆段：触发、档案、好感度与物品档案配置。"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AgentMemoryTrigger:
    group_interval: Optional[int] = field(
        default=500,
        metadata={"description": "群聊每N条消息触发一次记忆处理；0表示禁用"},
    )
    private_interval: Optional[int] = field(
        default=200,
        metadata={"description": "私聊每N条消息触发一次记忆处理；0表示禁用"},
    )
    prompt_snippet_chars: Optional[int] = field(
        default=120,
        metadata={
            "description": "总结提示词中每条消息的最大展示字符数；超出部分截断，"
            "模型可用 archive_crud__read_pending_messages 按需读取全文；0表示不截断"
        },
    )
    max_tool_rounds: Optional[int] = field(
        default=20,
        metadata={"description": "单次记忆总结最多允许的工具调用轮次，防止工具失败时反复重试烧token"},
    )
    max_summary_seconds: Optional[float] = field(
        default=300.0,
        metadata={
            "description": "单次记忆总结的总时长预算(秒)；超过即中止本轮并进入失败冷却，"
            "避免多轮工具调用把一次总结拖成数十分钟。至少要能装下两轮完整调用"
            "(第一轮工具调用 + 第二轮收尾)，否则思考模型会在收尾时被腰斩"
        },
    )
    model_call_timeout_seconds: Optional[float] = field(
        default=0.0,
        metadata={
            "description": "记忆总结单次模型调用的超时(秒)；0 表示自动跟随总结模型自身的"
            "请求超时(settings.timeout_seconds)并留 15 秒余量。开启思考/推理强度 max 的模型"
            "单次调用常超过 60 秒，此处不应小于该模型的请求超时，否则会在正常推理中被掐断"
        },
    )


@dataclass
class AgentMemoryArchive:
    allow_delete: bool = field(
        default=False,
        metadata={"description": "是否允许 delete_archive 删除档案记忆"},
    )
    allowed_tables: Optional[List[str]] = field(
        default_factory=list,
        metadata={"description": "允许访问的档案表名列表；留空表示不限制"},
    )
    auto_compact_chars: Optional[int] = field(
        default=200,
        metadata={"description": "单条档案超过此字符数时触发一次 AI 自动精简；0表示禁用"},
    )
    max_chars: Optional[int] = field(
        default=500,
        metadata={"description": "个人记忆渲染进提示词时的展示长度上限(截取开头部分)；超出部分由模型用 archive_crud 分页查阅；user_summary 条目也以此为准"},
    )
    group_profile_max_chars: Optional[int] = field(
        default=1500,
        metadata={"description": "群聊记忆渲染进提示词时的展示长度上限(截取开头部分)；超出部分由模型用 archive_crud 分页查阅；group_summary 条目也以此为准"},
    )
    max_total_chars: Optional[int] = field(
        default=15000,
        metadata={"description": "单条档案的存储硬上限(字符)；超过后按 overflow_action 处理，自动压缩目标固定为 10000（留出余量）；0表示禁用(不限制)。与渲染上限 max_chars 无关"},
    )
    overflow_action: Optional[str] = field(
        default="summarize",
        metadata={"description": "档案超过 max_total_chars 时的动作：summarize(异步自动压缩)或reject(拒绝写入并返回错误)"},
    )
    overflow_summary_cooldown_seconds: Optional[int] = field(
        default=600,
        metadata={"description": "同一档案两次自动压缩之间的最小间隔(秒)，用于防抖"},
    )


@dataclass
class AgentMemoryFavorability:
    """好感度系统配置。"""

    max_change_per_summary: Optional[int] = field(
        default=5,
        metadata={"description": "每次档案总结时好感度单次变更上限"},
    )
    min_value: Optional[int] = field(
        default=-1000,
        metadata={"description": "好感度下限"},
    )
    max_value: Optional[int] = field(
        default=1000,
        metadata={"description": "好感度上限"},
    )


@dataclass
class AgentMemoryItemArchive:
    """物品/事件关键词档案配置。

    允许 Agent 以关键词为键建立独立数据表，记录对特定物品、事件或话题的
    长期信息档案。该表与 user_profile / group_profile 的摘要长度控制
    （由 AgentMemoryArchive 配置）独立。
    自动记忆总结系统也会同步向该表写入。
    """

    enabled: bool = field(
        default=True,
        metadata={"description": "是否启用物品/事件关键词档案"},
    )
    table_name: Optional[str] = field(
        default="item_archive",
        metadata={"description": "物品/事件档案表名；Agent 使用此表名存储和检索关键词档案"},
    )


@dataclass
class AgentMemory:
    trigger: AgentMemoryTrigger = field(default_factory=AgentMemoryTrigger)
    archive: AgentMemoryArchive = field(default_factory=AgentMemoryArchive)
    favorability: AgentMemoryFavorability = field(default_factory=AgentMemoryFavorability)
    item_archive: AgentMemoryItemArchive = field(default_factory=AgentMemoryItemArchive)
    adaptive_prompt_enabled: bool = field(
        default=True,
        metadata={"description": "是否启用自适应提示词（agent 可自主维护的永久记忆）"},
    )
    adaptive_prompt_max_chars: int = field(
        default=200,
        metadata={"description": "自适应提示词最大字符数，超出自动截断"},
    )
