"""增强聊天段：EnhancedChat（在基础 Chat 上追加回复管线相关字段）。"""

from dataclasses import dataclass, field
from typing import List, Optional

from .core import Chat


@dataclass
class EnhancedChat(Chat):
    """支持消息队列时间戳的聊天配置。"""

    message_timestamp_interval_seconds: Optional[int] = field(
        default=300,
        metadata={"description": "消息队列时间戳插入间隔，单位秒"},
    )
    enable_periodic_user_info_update: Optional[bool] = field(
        default=True,
        metadata={"description": "是否定时更新用户信息"},
    )
    user_info_update_interval_days: Optional[int] = field(
        default=7,
        metadata={"description": "用户信息更新时间，单位天"},
    )
    reply_mode: Optional[str] = field(
        default="agent",
        metadata={"description": "回复模式：common(只有基础回复功能,不推荐) 或 agent(推荐)"},
    )
    at_mention_guaranteed_reply: Optional[bool] = field(
        default=True,
        metadata={"description": "@ 时是否必回"},
    )
    at_mention_reply_delay_seconds: Optional[float] = field(
        default=0.0,
        metadata={
            "description": (
                "@ 提及时的回复延迟秒数。**默认 0：不延迟，被 @ 后立即开始回复** —— "
                "「对方还没说要我做什么」的兜底改由提示词分区 [at_mention_wait] 交给模型自己 "
                "wait 五秒（说清了就直接做）。大于 0 时回到旧行为：本体先等这么多秒收集后续"
                "群消息再生成回复；正文命中插件登记的玩法关键词（漂流瓶 / 签到 / 抽签 等）时"
                "跳过该等待，直接触发回复事件"
            )
        },
    )
    willing_global_coefficient: Optional[float] = field(
        default=1.0,
        metadata={"description": "common 模式全局回复概率系数"},
    )
    willing_agent_global_coefficient: Optional[float] = field(
        default=1.0,
        metadata={"description": "agent 模式全局回复概率系数"},
    )
    enable_group_startup_history_warmup: Optional[bool] = field(
        default=False,
        metadata={"description": "是否在启动时读取群聊历史消息预热队列"},
    )
    enable_friend_startup_history_warmup: Optional[bool] = field(
        default=False,
        metadata={"description": "是否在启动时读取私聊历史消息预热队列"},
    )
    startup_history_group_whitelist: Optional[List[str]] = field(
        default_factory=list,
        metadata={"description": "启动历史预热群聊白名单"},
    )
    startup_history_friend_whitelist: Optional[List[str]] = field(
        default_factory=list,
        metadata={"description": "启动历史预热私聊白名单"},
    )
    reply_cooldown_seconds: Optional[int] = field(
        default=0,
        metadata={"description": "回复冷却时间，单位秒；距上次回复结束不足此时间则不触发新回复"},
    )
    reply_sentence_cooldown_seconds: Optional[float] = field(
        default=2.0,
        metadata={"description": "群聊每条回复短句之间的冷却时间，单位秒；用于模拟打字间隔"},
    )
    private_chat_sentence_cooldown_seconds: Optional[float] = field(
        default=2.0,
        metadata={"description": "私聊每条回复短句之间的冷却时间，单位秒"},
    )
    agent_wait_max_seconds: Optional[int] = field(
        default=60,
        metadata={"description": "Agent wait 工具单次最大等待秒数"},
    )
    agent_max_iterations: Optional[int] = field(
        default=200,
        metadata={"description": "Agent 模式单轮回复最大工具调用迭代次数"},
    )
    group_agent_silent_timeout_seconds: Optional[float] = field(
        default=120.0,
        metadata={
            "description": "群聊 agent 回复管线最长静默时间；超过后强制关闭管线。wait 工具等待时间不计入静默时间，0 表示禁用"
        },
    )
    silent_nudge_enabled: Optional[bool] = field(
        default=True,
        metadata={"description": "长任务沉默提醒：模型长时间只调用工具不回复时注入一条系统提醒；关闭后回到原行为"},
    )
    silent_nudge_first_rounds: Optional[int] = field(
        default=5,
        metadata={"description": "首次沉默提醒需要的连续工具调用轮数；0表示关闭轮次触发"},
    )
    silent_nudge_repeat_rounds: Optional[int] = field(
        default=10,
        metadata={"description": "首次提醒之后，每次再累积多少轮工具调用才再次提醒"},
    )
    silent_nudge_seconds: Optional[float] = field(
        default=45.0,
        metadata={"description": "自本轮开始(或上次提醒)起超过此秒数仍未使用回复工具即提醒；0表示关闭时间触发"},
    )
    silent_nudge_max: Optional[int] = field(
        default=3,
        metadata={"description": "单次回复事件内最多注入的沉默提醒次数"},
    )
    chat_flow_prompt_history_enabled: Optional[bool] = field(
        default=True,
        metadata={"description": "是否记录完整提示词历史供面板查看；纯内存(逐份diff)+重启清空，不落盘；图片只留sha256哈希不留base64"},
    )
    chat_flow_prompt_history_limit: Optional[int] = field(
        default=100,
        metadata={"description": "完整提示词历史的全局保留份数；纯内存且逐份只存diff，100份常驻约1~2MB(旧落盘实现的单份体积是0.5~1.2MB)"},
    )
    random_sticker_probability: Optional[float] = field(
        default=0.1,
        metadata={"description": "回复事件中随机触发聊天互动agent发送表情包的概率，范围0.0~1.0"},
    )
    ai_reply_check: Optional[bool] = field(
        default=False,
        metadata={"description": "AI回复检查；开启后 send_reply 会先返回切分结果供主Agent确认"},
    )
    ai_reply_check_lightweight: Optional[bool] = field(
        default=True,
        metadata={
            "description": "AI回复轻量检查；仅在回复触发过长/过多拦截时才提示AI检查切分结果。"
            "当 ai_reply_check 全量检查开启后，此开关被忽略"
        },
    )
    long_reply_max_length: Optional[int] = field(
        default=300,
        metadata={"description": "回复最大字符数，超过此长度将触发 fallback 回复"},
    )
    long_reply_max_sentence_count: Optional[int] = field(
        default=12,
        metadata={"description": "回复自动切分后允许的最大消息条数，超过此数量将触发 fallback 回复"},
    )
    enable_ai_reply_regenerate_on_length_limit: Optional[bool] = field(
        default=True,
        metadata={
            "description": "当回复超过长度/句数限制时，是否让 AI 重新生成更简短的版本，"
            "而非直接使用 fallback 模板"
        },
    )
    emoji_page_size: Optional[int] = field(
        default=50,
        metadata={"description": "表情包列表每页显示数量；总数超过此值时分页展示，agent 可使用翻页参数查看"},
    )
    emoji_random_candidate_count: Optional[int] = field(
        default=10,
        metadata={
            "description": "每轮表情包选择注入的随机候选数量；从使用次数最少（真实发送+候选曝光）"
            "的非爱用表情包中取，爱用表情包不占这些槽位"
        },
    )
    emoji_favorite_limit: Optional[int] = field(
        default=10,
        metadata={
            "description": "爱用表情包数量上限；爱用表情包每轮固定进入候选池，"
            "设置爱用时最多可选这么多张"
        },
    )
    enable_last_reply_tracking: Optional[bool] = field(
        default=True,
        metadata={"description": "是否启用'上次回复到'位置追踪；开启后每次回复会记录最后位置"},
    )
    show_last_reply_markers: Optional[bool] = field(
        default=False,
        metadata={
            "description": "调试开关：是否在提示词中显示'以上是上次对话回复过的内容'等边界标记。"
            "正常情况应保持关闭；仅在新版提示词表现异常时开启用于排查"
        },
    )
    archive_fetch_window: Optional[int] = field(
        default=20,
        metadata={"description": "群成员列表窗口；只列出消息队列中最新的此数量消息的发送者，戳一戳等同0.2条消息"},
    )
    tool_result_full_keep: Optional[int] = field(
        default=10,
        metadata={
            "description": "工具输出压缩:重新构建提示词后保留完整内容的最近工具返回条数,其余压缩"
        },
    )
    tool_result_summary_chars: Optional[int] = field(
        default=200,
        metadata={"description": "工具输出压缩:非基础工具压缩后保留的结果摘要字符数"},
    )
    inject_member_archives: Optional[bool] = field(
        default=False,
        metadata={
            "description": "群聊提示词是否注入群成员的个人档案；默认 false（只注入群档案），"
            "群员档案由 agent 用 archive_crud__read_archive 按需读取"
        },
    )
    gentle_language_enabled: Optional[bool] = field(
        default=True,
        metadata={
            "description": "是否在群聊/私聊 system 提示词的人设之后插入 [gentle_language] "
            "温和语言风格提示词；默认开启。关闭也可在提示词分区里写 enabled = false"
        },
    )
    poke_weight: Optional[float] = field(
        default=0.2,
        metadata={"description": "戳一戳事件在消息队列中的权重，结算队列长度时按此权重计算（0.2表示5个戳一戳等同1条消息）"},
    )
    reaction_weight: Optional[float] = field(
        default=0.2,
        metadata={"description": "表情回应事件在消息队列中的权重，结算队列长度时按此权重计算（0.2表示5个表情回应等同1条消息）"},
    )
    self_sent_message_weight: Optional[float] = field(
        default=0.1,
        metadata={
            "description": "Bot 自身发言（含实时入队与历史灌入两个来源）与后台通知在消息队列中的权重；"
            "0.1 表示 10 条自身发言才等同 1 条用户消息，基本不挤占观测窗口与上下文窗口"
        },
    )
    official_bot_reply_coefficient: Optional[float] = field(
        default=0.05,
        metadata={"description": "官方Bot回复概率系数，识别到消息发送者为官方Bot时，基础概率乘以此系数"},
    )
    private_chat_suspend_wait_seconds: Optional[int] = field(
        default=300,
        metadata={"description": "私聊回复后挂起等待秒数；超时无新消息则结束会话，默认300秒（5分钟）"},
    )
    private_chat_max_tokens: Optional[int] = field(
        default=250000,
        metadata={"description": "私聊会话最大token数；超过后重启聊天管线（默认 250K）"},
    )
    private_chat_dynamic_warmup: Optional[bool] = field(
        default=True,
        metadata={"description": "首次收到私聊消息时是否动态预热历史消息"},
    )
    private_chat_warmup_history_count: Optional[int] = field(
        default=100,
        metadata={"description": "私聊动态预热时拉取的历史消息条数"},
    )
    private_chat_new_message_collect_seconds: Optional[float] = field(
        default=5.0,
        metadata={"description": "私聊挂起期间收到首条新消息后继续收集新消息的时间窗口（秒）"},
    )
    private_chat_reply_delay_seconds: Optional[float] = field(
        default=5.0,
        metadata={"description": "私聊收到消息后延迟多少秒再触发回复（在此期间收集后续消息）"},
    )
    post_reply_message_timeout_seconds: Optional[float] = field(
        default=60.0,
        metadata={"description": "群聊回复期间收集的消息超时秒数；超过此时间的消息不触发回复意愿判断"},
    )
    forward_message_display_threshold: Optional[int] = field(
        default=50,
        metadata={"description": "合并转发消息节点数阈值；小于此值直接显示内容，大于等于此值仅显示ID并提供读取工具"},
    )
    forward_message_queue_weight: Optional[int] = field(
        default=2,
        metadata={"description": "合并转发消息在队列中的容量权重；一个合并转发消息占用此数量的队列位置"},
    )
    forward_message_max_nesting: Optional[int] = field(
        default=10,
        metadata={"description": "合并转发消息最大嵌套层级；支持最多10层转发嵌套"},
    )
    wait_cooldown_seconds: Optional[int] = field(
        default=60,
        metadata={"description": "wait 工具调用冷却秒数；同一会话在一次 wait 调用后需等待此秒数才可再次调用"},
    )
    group_chat_reply_lifespan: Optional[int] = field(
        default=5,
        metadata={
            "description": "群聊回复管线寿命；每次回复-1，归零则销毁管线。设为0禁用寿命机制，回复结束后立即销毁管线"
        },
    )
    cost_pipeline_enabled: Optional[bool] = field(
        default=True,
        metadata={
            "description": "成本计算管线系统开关；开启后聊天管线在基础寿命耗尽时，"
            "若计算缓存命中后的继续成本低于重启一个聊天管线的输入成本，"
            "则复用继续使用管线（总寿命不超过 基础寿命+成本管线阈值）。"
            "关闭后缓存计算不启用，不占用性能。只对聊天管线生效（记忆总结/子Agent/非聊天模型不接入）"
        },
    )
    cost_pipeline_threshold: Optional[int] = field(
        default=20,
        metadata={
            "description": "成本管线阈值；基础寿命之上最多可额外续用的回复次数。"
            "默认 20，即群聊默认寿命 5 时总寿命上限为 5+20=25"
        },
    )
    cache_retention_seconds: Optional[int] = field(
        default=1800,
        metadata={
            "description": "缓存前缀保存时间（秒），默认 1800（30 分钟）；"
            "超过后缓存前缀单元失效，需重新落盘"
        },
    )
    cache_hit_price_difference: Optional[int] = field(
        default=120,
        metadata={
            "description": "缓存命中成本与未命中成本的差价（倍），默认 120；"
            "成本估算与成本管线续用决策使用（命中部分按 1/差价 计费）"
        },
    )
    group_chat_suspend_wait_seconds: Optional[int] = field(
        default=3600,
        metadata={"description": "群聊回复后挂起等待秒数；超时无新消息则结束会话，默认3600秒（1小时）"},
    )
    enable_balance_check: Optional[bool] = field(
        default=False,
        metadata={"description": "是否启用DeepSeek余额检查与低余额预警；仅在主模型使用DeepSeek且配置了管理员账户时生效"},
    )
    balance_threshold: Optional[float] = field(
        default=1.0,
        metadata={"description": "余额预警阈值（CNY），低于此值时发送私聊通知；默认1.0"},
    )
    admin_accounts: Optional[List[str]] = field(
        default_factory=list,
        metadata={
            "description": "超级管理员QQ号列表，用于接收余额不足等系统通知；仅可通过配置增减。"
            "留空也能正常启动，但相关系统通知无人接收；面板首页会给出提示"
        },
    )
    sub_admin_accounts: List[str] = field(
        default_factory=list,
        metadata={"description": "次级管理员QQ号列表；超级管理员可通过 /add_admin、/del_admin 命令增删"},
    )
    balance_check_cooldown_seconds: Optional[int] = field(
        default=300,
        metadata={"description": "余额检查冷却秒数；每次检查后至少间隔此秒数才会再次查询；默认300秒"},
    )
