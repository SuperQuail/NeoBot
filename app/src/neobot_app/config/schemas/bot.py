from dataclasses import dataclass, field, fields as dataclass_fields
from typing import Dict, Iterator, List, Optional, TypedDict


class KeyWordRule(TypedDict, total=False):
    """关键词规则类型。"""

    enabled: bool
    keywords: List[str]
    prompt_list: List[str]
    ignore_case: bool
    match_mode: str
    min_depth: int
    max_depth: int
    description: str


@dataclass
class Bot:
    """机器人基础配置。"""

    account: int = field(
        default=0,
        metadata={"description": "机器人QQ号", "placeholder": True},
    )
    nick_name: str = field(default="Neo Bot", metadata={"description": "Bot昵称"})
    alias_name: Optional[List[str]] = field(
        default_factory=lambda: ["Neo", "铸币bot"],
        metadata={"description": "Bot别称"},
    )
    bot_data: str = field(
        default="你是一个可爱的机器人",
        metadata={"description": "描述机器人的人设"},
    )
    enable_bot_get_married: bool = field(
        default=False,
        metadata={"description": "是否允许bot与好友结婚"},
    )


@dataclass
class Chat:
    group_prompt_template: str = field(
        default=(
            "<当前时间>{current_time}</当前时间>\n"
            "<群聊>{group_name}[群号:{group_id}]{group_description}\n"
            "<群聊档案>\n{group_info}\n</群聊档案>\n"
            "</群聊>\n"
            "<聊天记录>\n{message_list}\n</聊天记录>\n"
            "<群友信息>\n{member_list}\n</群友信息>\n"
            "<你是谁>\n"
            "你的名字是{bot_name},你的QQ号是{bot_account}{other_name}.\n"
            "{bot_data}\n"
            "</你是谁>\n"
            "<回复要求>请注意把握聊天内容,不要回复的太有条理,可以有个性.请回复的平淡一些，简短一些,不要刻意突出自身学科背景，尽量不要说你说过的话.不要输出多余内容(包括前后缀，冒号和引号，括号，表情包，at或 @等 ),不要使用markdown,和正常聊天一样,回复短句即可.当有人让你使用工具时,你可以先告诉对方你打算这么做再去调用工具,但不要在对话中提及你调用的具体工具.如果工具调用失败且你无法让其正常工作,你可以在聊天中告知你操作失败了,如果成功,在对方没有要求你成功后告知的情况下不需要再告诉对方你完成了.只有在有人询问你说的是哪句的时候,或者有明显歧义可能的情况下,使用回复语句功能;只有在提醒通知某人时,使用@功能,否则尽可能不要使用这两个功能.如果有人要求你做什么事情,你不一定要答应,如果你觉得可以答应,使用你可用的工具/agent来实现,不要只表示去做而不使用工具/agent完成,如果你发现你没有合适的工具/agent或者工具/agent无法完成任务,则回复你做不到如果你不确定你的工具/agent能否完成指定任务,不要先回复做不到,先回复试试看,然后询问对应的agent,再根据agent的回复来决定完成任务或告知无法实现.不需要重复回复你之前回复过的消息,优先回复比较新的消息,如果你觉得没有你需要回复的消息,则使用工具取消回复.</回复要求>\n"
            "<任务处理要求>如果委托子Agent后,对方回复表示缺少信息、需要确认、无法访问、建议下一步、结果不完整或明显误解任务,不要把这类中间回复当成最终结果;应继续调用delegate,保持同一个session_id,把子Agent上次回复填入previous_response,并在task里补充上下文、纠正误解或要求继续执行,直到任务完成或确定无法完成。结束事件前检查是否仍有未完成且尚未确定无法完成的任务;如果有,先继续使用工具/agent完成再发送最终回复或取消。如果任务需要其他人提供更多信息才能继续,使用wait等待新消息,不要直接结束事件。</任务处理要求>\n"
            "<回复样例>\n回复1:好哦\n回复2:我这就去看看\n注意,短句分开回复,而不是以整段回复\n</回复样例>\n"
            "<你的印象>\n"
            "{key_word_reaction_list}\n"
            "你想起来之前:\n"
            "{memory_list}\n"
            "</你的印象>"
        ),
        metadata={"description": "群聊提示词模板，非开发者不建议修改"},
    )
    max_group_chat_observations: int = field(
        default=100,
        metadata={"description": "群聊观察上限"},
    )
    group_chat_chance: float = field(
        default=0.5,
        metadata={"description": "群聊基础回复概率"},
    )
    group_use_black_list: bool = field(
        default=True,
        metadata={"description": "群聊名单是否使用黑名单模式"},
    )
    group_list: Optional[List[str]] = field(
        default_factory=lambda: ["111111", "222222"],
        metadata={"description": "群名单"},
    )
    group_response_coefficient: Optional[Dict[str, float]] = field(
        default_factory=lambda: {"111111": 0.5, "222222": 0.5},
        metadata={"description": "群聊回复系数", "aliases": ("group_Response_coefficient",)},
    )
    group_description: Optional[Dict[str, str]] = field(
        default_factory=lambda: {"111111": "这是不知道谁不知道干什么的群"},
        metadata={"description": "群描述"},
    )
    friend_prompt_template: str = field(
        default=(
            "<当前时间>{current_time}</当前时间>\n"
            "<聊天对象>{friend_name}(你的备注:{remark})</聊天对象>\n"
            "<你对ta的印象>{profile}</你对ta的印象>\n"
            "<对方信息>\n{friend_info}\n</对方信息>\n"
            "<你的记忆>\n你想起来{memory_list}\n</你的记忆>\n"
            "<聊天记录>\n{message_list}\n</聊天记录>\n"
            "<你是谁>\n"
            "你的名字是{bot_name},你的QQ号是{bot_account}{other_name}.\n"
            "{bot_data}\n"
            "</你是谁>"
            "<回复要求>请注意把握聊天内容,不要回复的太有条理,可以有个性.请回复的平淡一些，简短一些,不要刻意突出自身学科背景，尽量不要说你说过的话.不要输出多余内容(包括前后缀，冒号和引号，括号，表情包，at或 @等 ),不要使用markdown,和正常聊天一样,回复短句即可.当有人让你使用工具时,你可以先告诉对方你打算这么做再去调用工具,但不要在对话中提及你调用的具体工具.如果工具调用失败且你无法让其正常工作,你可以在聊天中告知你操作失败了,如果成功,在对方没有要求你成功后告知的情况下不需要再告诉对方你完成了.只有在有人询问你说的是哪句的时候,或者有明显歧义可能的情况下,使用回复语句功能;只有在提醒通知某人时,使用@功能,否则尽可能不要使用这两个功能.如果有人要求你做什么事情,你不一定要答应,如果你觉得可以答应,使用你可用的工具/agent来实现,不要只表示去做而不使用工具/agent完成,如果你发现你没有合适的工具/agent或者工具/agent无法完成任务,则回复你做不到如果你不确定你的工具/agent能否完成指定任务,不要先回复做不到,先回复试试看,然后询问对应的agent,再根据agent的回复来决定完成任务或告知无法实现.</回复要求>\n"
            "<任务处理要求>如果委托子Agent后,对方回复表示缺少信息、需要确认、无法访问、建议下一步、结果不完整或明显误解任务,不要把这类中间回复当成最终结果;应继续调用delegate,保持同一个session_id,把子Agent上次回复填入previous_response,并在task里补充上下文、纠正误解或要求继续执行,直到任务完成或确定无法完成。结束事件前检查是否仍有未完成且尚未确定无法完成的任务;如果有,先继续使用工具/agent完成再发送最终回复或取消。如果任务需要其他人提供更多信息才能继续,使用wait等待新消息,不要直接结束事件。</任务处理要求>\n"
            "<回复样例>\n回复1:好哦\n回复2:我这就去看看\n注意,短句分开回复,而不是以整段回复\n</回复样例>\n"
            "<工具与agent指南>当你使用工具/agent时,确认你使用的工具是否是正确职能的工具/agent,如果agent询问你问题,你需要回复agent帮助其完成任务,如果你缺失信息,需要先发送消息询问,注意:群友看不到agent发给你的消息,你应该先把agent的话转述,然后再询问需要的额外信息,最后再调用wait等待群友告诉你信息</工具与agent指南>\n"
        ),
        metadata={"description": "私聊提示词模板，非开发者不建议修改"},
    )
    max_friend_chat_observations: int = field(
        default=100,
        metadata={"description": "私聊观察上限"},
    )
    friend_chat_chance: float = field(
        default=0.5,
        metadata={"description": "私聊基础回复概率"},
    )
    friend_use_black_list: bool = field(
        default=True,
        metadata={"description": "私聊名单是否使用黑名单模式"},
    )
    friend_list: Optional[List[str]] = field(
        default_factory=lambda: ["111111", "222222"],
        metadata={"description": "好友名单"},
    )
    friend_description: Optional[Dict[str, str]] = field(
        default_factory=lambda: {"111111": "这是不知道谁不知道干什么的人"},
        metadata={"description": "好友描述"},
    )
    key_word: Optional[List[KeyWordRule]] = field(
        default_factory=lambda: [
            {
                "enabled": True,
                "keywords": ["妈妈", "妈"],
                "prompt_list": ["你可以反问对方是不是叫夏亚"],
                "ignore_case": True,
                "match_mode": "any",
                "min_depth": -1,
                "max_depth": 0,
            },
            {
                "enabled": False,
                "keywords": ["测试"],
                "prompt_list": ["Test"],
                "ignore_case": True,
                "match_mode": "any",
                "min_depth": -1,
                "max_depth": -1,
            },
        ],
        metadata={"description": "关键词规则列表"},
    )


@dataclass
class ModelPricing:
    """模型价格配置。"""

    input_price_per_mtokens: float = field(
        default=0.0,
        metadata={"description": "输入价格，单位为每百万Tokens"},
    )
    output_price_per_mtokens: float = field(
        default=0.0,
        metadata={"description": "输出价格，单位为每百万Tokens"},
    )
    billing_metric: str = field(
        default="",
        metadata={"description": "非Token计费模型的平台计费标识"},
    )


@dataclass
class ModelSettings:
    """模型运行设置。"""

    temperature: float = field(
        default=1.0,
        metadata={"description": "采样温度"},
    )
    max_output_tokens: int = field(
        default=2048,
        metadata={"description": "单次最大回复Tokens"},
    )
    timeout_seconds: float = field(
        default=120.0,
        metadata={"description": "请求超时时间，单位秒"},
    )
    top_p: float = field(
        default=1.0,
        metadata={"description": "Top P 采样参数"},
    )
    frequency_penalty: float = field(
        default=0.0,
        metadata={"description": "频率惩罚"},
    )
    presence_penalty: float = field(
        default=0.0,
        metadata={"description": "存在惩罚"},
    )


@dataclass
class DeepSeekModelSettings(ModelSettings):
    """DeepSeek 模型运行设置（包含思考模式相关配置）。
    注意：思考模式配置统一采用 OpenAI 样式作为参考填写，程序会自动根据实际 API 提供方进行样式转换。
    """

    deepseek_thinking_mode: str = field(
        default="enabled",
        metadata={
            "description": "思考模式开关（OpenAI 样式）：enabled 开启（默认），disabled 关闭，random 按概率随机开启"
        },
    )
    deepseek_reasoning_effort: str = field(
        default="high",
        metadata={
            "description": "思考强度控制（OpenAI 样式）：low/medium 映射为 high，xhigh 映射为 max，可选 high（默认）或 max"
        },
    )
    deepseek_random_thinking_probability: float = field(
        default=0.6,
        metadata={
            "description": "随机思考开启概率，范围 0.0 到 1.0，仅在思考模式为 random 时生效"
        },
    )


@dataclass
class ModelRegistration:
    """单个模型注册配置。"""

    description: str = field(
        default="主对话模型",
        metadata={"description": "模型用途说明"},
    )
    provider: str = field(
        default="DeepSeek",
        metadata={"description": "模型供应商"},
    )
    model_name: str = field(
        default="deepseek-chat",
        metadata={"description": "模型名"},
    )
    pricing: ModelPricing = field(default_factory=ModelPricing)
    settings: ModelSettings = field(default_factory=ModelSettings)


def _default_primary_chat_model() -> "ModelRegistration":
    return ModelRegistration(
        description="主对话模型",
        provider="DeepSeek",
        model_name="deepseek-v4-flash",
        settings=DeepSeekModelSettings(
            temperature=1.0,
            max_output_tokens=2048,
            timeout_seconds=120.0,
            top_p=1.0,
            frequency_penalty=0.0,
            presence_penalty=0.0,
            deepseek_thinking_mode="enabled",
            deepseek_reasoning_effort="high",
            deepseek_random_thinking_probability=0.6,
        ),
        pricing=ModelPricing(
            input_price_per_mtokens=0.0,
            output_price_per_mtokens=0.0,
        ),
    )


def _default_vision_model() -> "ModelRegistration":
    return ModelRegistration(
        description="图像识别模型",
        provider="硅基流动",
        model_name="Qwen/Qwen2.5-VL-32B-Instruct",
        settings=ModelSettings(
            temperature=0.7,
            max_output_tokens=2048,
            timeout_seconds=120.0,
            top_p=1.0,
        ),
        pricing=ModelPricing(
            input_price_per_mtokens=1.89,
            output_price_per_mtokens=1.89,
        ),
    )


def _default_tts_model() -> "ModelRegistration":
    return ModelRegistration(
        description="语音模型",
        provider="硅基流动",
        model_name="FunAudioLLM/CosyVoice2-0.5B",
        settings=ModelSettings(
            temperature=1.0,
            timeout_seconds=120.0,
        ),
        pricing=ModelPricing(
            input_price_per_mtokens=0.0,
            output_price_per_mtokens=0.0,
            billing_metric="funaudiollm/cosyvoice2-0.5b.utf8-bytes",
        ),
    )


def _default_creator_image_model() -> "ModelRegistration":
    return ModelRegistration(
        description="创作者Agent生图模型",
        provider="SiliconFlow",
        model_name="black-forest-labs/FLUX.1-schnell",
        settings=ModelSettings(
            temperature=1.0,
            timeout_seconds=120.0,
        ),
        pricing=ModelPricing(
            input_price_per_mtokens=0.0,
            output_price_per_mtokens=0.0,
        ),
    )


@dataclass
class Models:
    """模型注册配置集合。"""

    primary_chat_model: ModelRegistration = field(
        default_factory=_default_primary_chat_model,
        metadata={"description": "主对话模型"},
    )
    vision_model: ModelRegistration = field(
        default_factory=_default_vision_model,
        metadata={"description": "图像识别模型"},
    )
    tts_model: ModelRegistration = field(
        default_factory=_default_tts_model,
        metadata={"description": "语音模型"},
    )
    creator_image_model: ModelRegistration = field(
        default_factory=_default_creator_image_model,
        metadata={"description": "创作者Agent生图模型"},
    )

    def iter_registrations(self) -> Iterator[tuple[str, ModelRegistration]]:
        for config_field in dataclass_fields(self):
            model = getattr(self, config_field.name)
            if isinstance(model, ModelRegistration):
                yield config_field.name, model


@dataclass
class TTSReferenceVoice:
    """TTS 参考音频上传配置。"""

    enabled: bool = field(
        default=False,
        metadata={"description": "是否启用参考音频上传"},
    )
    audio_file: str = field(
        default="./data/tts/reference.mp3",
        metadata={"description": "参考音频文件路径"},
    )
    custom_name: str = field(
        default="neo-default-voice",
        metadata={"description": "上传到平台后的声音名称"},
    )
    reference_text: str = field(
        default="慢工出细活，再给我两分钟，你马上就能见识到超梦分析的厉害了",
        metadata={"description": "参考音频对应文本"},
    )
    disable_tts_on_upload_failure: bool = field(
        default=True,
        metadata={"description": "参考音频上传失败时是否自动禁用TTS"},
    )


@dataclass
class TTS:
    """TTS 功能配置。"""

    enabled: bool = field(
        default=True,
        metadata={"description": "是否启用TTS功能"},
    )
    response_format: str = field(
        default="mp3",
        metadata={"description": "TTS输出格式"},
    )
    stream: bool = field(
        default=True,
        metadata={"description": "是否使用流式语音生成"},
    )
    output_dir: str = field(
        default="./data/tts",
        metadata={"description": "生成语音文件保存目录"},
    )
    reference_voice: TTSReferenceVoice = field(default_factory=TTSReferenceVoice)


@dataclass
class Willing:
    """回复意愿管理器配置。"""

    manager_name: str = field(
        default="Quail",
        metadata={"description": "回复意愿管理器名称"},
    )
    observe_window: int = field(
        default=5,
        metadata={"description": "意愿计算观察窗口"},
    )
    reply_threshold: float = field(
        default=0.5,
        metadata={"description": "建议回复阈值"},
    )


@dataclass
class Plugins:
    """插件配置。"""

    enabled: bool = field(default=True, metadata={"description": "是否启用插件"})
    dir: str = field(default="./plugins", metadata={"description": "插件目录"})


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


@dataclass
class Debug:
    """调试配置。"""

    enabled: bool = field(
        default=False,
        metadata={"description": "是否启用 Debug 模式"},
    )


@dataclass
class AgentCreatorGallery:
    """Creator Agent 图库配置。"""

    capacity: int = field(
        default=10,
        metadata={"description": "图库容量上限；为0时禁用图库管理工具"},
    )
    page_size: int = field(
        default=50,
        metadata={"description": "图库列表每页显示数量；图片总数超过此值时分页展示"},
    )


@dataclass
class AgentCreatorEmoji:
    """Creator Agent 表情包管理配置。"""

    allow_add: bool = field(
        default=False,
        metadata={"description": "是否允许 Creator Agent 增加表情包"},
    )
    allow_delete: bool = field(
        default=False,
        metadata={"description": "是否允许 Creator Agent 删除表情包"},
    )
    page_size: int = field(
        default=50,
        metadata={"description": "表情包列表每页显示数量；总数超过此值时分页展示"},
    )


@dataclass
class AgentCreator:
    """Creator Agent 配置。"""

    enabled: bool = field(
        default=False,
        metadata={"description": "是否启用Creator Agent"},
    )
    gallery: AgentCreatorGallery = field(default_factory=AgentCreatorGallery)
    emoji: AgentCreatorEmoji = field(default_factory=AgentCreatorEmoji)


@dataclass
class AgentSystem:
    """System Agent 配置。"""

    allowed_work_dirs: List[str] = field(
        default_factory=lambda: ["./Data/"],
        metadata={"description": "System Agent 允许操作的工作目录"},
    )


@dataclass
class AgentMemoryTrigger:
    group_interval: int = field(
        default=50,
        metadata={"description": "群聊每N条消息触发一次记忆处理；0表示禁用"},
    )
    private_interval: int = field(
        default=50,
        metadata={"description": "私聊每N条消息触发一次记忆处理；0表示禁用"},
    )


@dataclass
class AgentMemoryArchive:
    allow_delete: bool = field(
        default=False,
        metadata={"description": "是否允许 delete_archive 删除档案记忆"},
    )
    allowed_tables: List[str] = field(
        default_factory=list,
        metadata={"description": "允许访问的档案表名列表；留空表示不限制"},
    )
    auto_compact_chars: int = field(
        default=500,
        metadata={"description": "单条档案超过此字符数时触发一次 AI 自动精简；0表示禁用"},
    )
    max_chars: int = field(
        default=600,
        metadata={"description": "单条档案最大字符数；超过后截断写入"},
    )


@dataclass
class AgentMemoryFavorability:
    """好感度系统配置。"""

    max_change_per_summary: int = field(
        default=5,
        metadata={"description": "每次档案总结时好感度单次变更上限"},
    )
    min_value: int = field(
        default=-1000,
        metadata={"description": "好感度下限"},
    )
    max_value: int = field(
        default=1000,
        metadata={"description": "好感度上限"},
    )


@dataclass
class AgentMemory:
    trigger: AgentMemoryTrigger = field(default_factory=AgentMemoryTrigger)
    archive: AgentMemoryArchive = field(default_factory=AgentMemoryArchive)
    favorability: AgentMemoryFavorability = field(default_factory=AgentMemoryFavorability)


@dataclass
class Agent:
    """Agent 配置。"""

    creator: AgentCreator = field(default_factory=AgentCreator)
    system: AgentSystem = field(default_factory=AgentSystem)
    memory: AgentMemory = field(default_factory=AgentMemory)


@dataclass
class BotConfig:
    """机器人主配置。"""

    version: str = field(default="0.3.0", metadata={"description": "配置文件版本"})
    bot: Bot = field(default_factory=Bot)
    chat: Chat = field(default_factory=Chat)
    models: Models = field(default_factory=Models)
    willing: Willing = field(default_factory=Willing)
    tts: TTS = field(default_factory=TTS)
    plugins: Plugins = field(default_factory=Plugins)
    message: Message = field(default_factory=Message)
    file_server: FileServer = field(default_factory=FileServer)
    debug: Debug = field(default_factory=Debug)
    agent: Agent = field(default_factory=Agent)


@dataclass
class EnhancedChat(Chat):
    """Chat config with queue timestamp support."""

    message_timestamp_interval_seconds: int = field(
        default=300,
        metadata={"description": "消息队列时间戳插入间隔，单位秒"},
    )
    enable_periodic_user_info_update: bool = field(
        default=False,
        metadata={"description": "是否定时更新用户信息"},
    )
    user_info_update_interval_days: int = field(
        default=7,
        metadata={"description": "用户信息更新时间，单位天"},
    )
    reply_mode: str = field(
        default="common",
        metadata={"description": "回复模式：common 或 agent"},
    )
    at_mention_guaranteed_reply: bool = field(
        default=True,
        metadata={"description": "@ 时是否必回"},
    )
    willing_global_coefficient: float = field(
        default=1.0,
        metadata={"description": "common 模式全局回复概率系数"},
    )
    willing_agent_global_coefficient: float = field(
        default=1.0,
        metadata={"description": "agent 模式全局回复概率系数"},
    )
    friend_response_coefficient: dict[str, float] = field(
        default_factory=dict,
        metadata={"description": "私聊回复系数", "aliases": ("friend_Response_coefficient",)},
    )
    enable_group_startup_history_warmup: bool = field(
        default=False,
        metadata={"description": "是否在启动时读取群聊历史消息预热队列"},
    )
    enable_friend_startup_history_warmup: bool = field(
        default=False,
        metadata={"description": "是否在启动时读取私聊历史消息预热队列"},
    )
    startup_history_group_whitelist: List[str] = field(
        default_factory=list,
        metadata={"description": "启动历史预热群聊白名单"},
    )
    startup_history_friend_whitelist: List[str] = field(
        default_factory=list,
        metadata={"description": "启动历史预热私聊白名单"},
    )
    reply_cooldown_seconds: int = field(
        default=2,
        metadata={"description": "回复冷却时间，单位秒；距上次回复结束不足此时间则不触发新回复"},
    )
    reply_sentence_cooldown_seconds: float = field(
        default=2.0,
        metadata={"description": "群聊每条回复短句之间的冷却时间，单位秒；用于模拟打字间隔"},
    )
    private_chat_sentence_cooldown_seconds: float = field(
        default=2.0,
        metadata={"description": "私聊每条回复短句之间的冷却时间，单位秒"},
    )
    agent_wait_max_seconds: int = field(
        default=60,
        metadata={"description": "Agent wait 工具单次最大等待秒数"},
    )
    random_sticker_probability: float = field(
        default=0.1,
        metadata={"description": "回复事件中随机触发聊天互动agent发送表情包的概率，范围0.0~1.0"},
    )
    ai_reply_check: bool = field(
        default=False,
        metadata={"description": "AI回复检查；开启后 send_reply 会先返回切分结果供主Agent确认"},
    )
    long_reply_fallback_template: str = field(
        default="{bot_name}懒得和你说道理，你不配听",
        metadata={"description": "回复过长或切分条数过多时使用的默认回复，支持 {bot_name} 占位符"},
    )
    long_reply_max_length: int = field(
        default=300,
        metadata={"description": "回复最大字符数，超过此长度将触发 fallback 回复"},
    )
    long_reply_max_sentence_count: int = field(
        default=12,
        metadata={"description": "回复自动切分后允许的最大消息条数，超过此数量将触发 fallback 回复"},
    )
    enable_ai_reply_regenerate_on_length_limit: bool = field(
        default=True,
        metadata={
            "description": "当回复超过长度/句数限制时，是否让 AI 重新生成更简短的版本，"
            "而非直接使用 fallback 模板"
        },
    )
    emoji_page_size: int = field(
        default=50,
        metadata={"description": "表情包列表每页显示数量；总数超过此值时分页展示，agent 可使用翻页参数查看"},
    )
    enable_last_reply_tracking: bool = field(
        default=True,
        metadata={"description": "是否启用'上次回复到'位置追踪；开启后每次回复会记录最后位置并在提示词中显示"},
    )
    poke_weight: float = field(
        default=0.2,
        metadata={"description": "戳一戳事件在消息队列中的权重，结算队列长度时按此权重计算（0.2表示5个戳一戳等同1条消息）"},
    )
    reaction_weight: float = field(
        default=0.2,
        metadata={"description": "表情回应事件在消息队列中的权重，结算队列长度时按此权重计算（0.2表示5个表情回应等同1条消息）"},
    )
    official_bot_reply_coefficient: float = field(
        default=0.05,
        metadata={"description": "官方Bot回复概率系数，识别到消息发送者为官方Bot时，基础概率乘以此系数"},
    )
    private_chat_suspend_wait_seconds: int = field(
        default=300,
        metadata={"description": "私聊回复后挂起等待秒数；超时无新消息则结束会话，默认300秒（5分钟）"},
    )
    private_chat_max_tokens: int = field(
        default=10000,
        metadata={"description": "私聊会话最大token数；超过后重启聊天管线"},
    )
    private_chat_dynamic_warmup: bool = field(
        default=True,
        metadata={"description": "首次收到私聊消息时是否动态预热历史消息"},
    )
    private_chat_warmup_history_count: int = field(
        default=100,
        metadata={"description": "私聊动态预热时拉取的历史消息条数"},
    )
    private_chat_new_message_collect_seconds: float = field(
        default=5.0,
        metadata={"description": "私聊挂起期间收到首条新消息后继续收集新消息的时间窗口（秒）"},
    )
    private_chat_reply_delay_seconds: float = field(
        default=5.0,
        metadata={"description": "私聊收到消息后延迟多少秒再触发回复（在此期间收集后续消息）"},
    )


@dataclass
class EnhancedBotConfig(BotConfig):
    """Bot config using the enhanced chat schema."""

    chat: EnhancedChat = field(default_factory=EnhancedChat)


Chat = EnhancedChat
BotConfig = EnhancedBotConfig
