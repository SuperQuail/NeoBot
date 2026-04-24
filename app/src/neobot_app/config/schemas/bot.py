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
            "<群聊>{group_name}[群号:{group_id}]{group_description}</群聊>\n"
            "<聊天记录>\n{message_list}\n</聊天记录>\n"
            "<群友信息>\n{member_list}\n</群友信息>\n"
            "<你是谁>\n"
            "你的名字是{bot_name},你的QQ号是{bot_account}{other_name}.\n"
            "{bot_data}\n"
            "</你是谁>\n"
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
    group_Response_coefficient: Optional[Dict[str, float]] = field(
        default_factory=lambda: {"111111": 0.5, "222222": 0.5},
        metadata={"description": "群聊回复系数"},
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
    deepseek_thinking_mode: str = field(
        default="disabled",
        metadata={
            "description": "DeepSeek 思考模式开关：disabled 关闭，enabled 开启，random 按概率随机开启"
        },
    )
    deepseek_reasoning_effort: str = field(
        default="high",
        metadata={"description": "DeepSeek 思考强度，可选 high 或 max"},
    )
    deepseek_random_thinking_probability: float = field(
        default=0.6,
        metadata={
            "description": "DeepSeek 随机思考开启概率，范围 0.0 到 1.0，仅在随机模式下生效"
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
        settings=ModelSettings(
            temperature=1.0,
            max_output_tokens=2048,
            timeout_seconds=120.0,
            top_p=1.0,
            frequency_penalty=0.0,
            presence_penalty=0.0,
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
            frequency_penalty=0.0,
            presence_penalty=0.0,
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
        model_name="IndexTeam/IndexTTS-2",
        settings=ModelSettings(
            temperature=1.0,
            max_output_tokens=2048,
            timeout_seconds=120.0,
            top_p=1.0,
            frequency_penalty=0.0,
            presence_penalty=0.0,
        ),
        pricing=ModelPricing(
            input_price_per_mtokens=0.0,
            output_price_per_mtokens=0.0,
            billing_metric="indexteam/indextts-2.online.utf8-bytes",
        ),
    )


def _default_creator_image_model() -> "ModelRegistration":
    return ModelRegistration(
        description="创作者Agent生图模型",
        provider="SiliconFlow",
        model_name="black-forest-labs/FLUX.1-schnell",
        settings=ModelSettings(
            temperature=1.0,
            max_output_tokens=2048,
            timeout_seconds=120.0,
            top_p=1.0,
            frequency_penalty=0.0,
            presence_penalty=0.0,
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


@dataclass
class AgentCreator:
    """Creator Agent 配置。"""

    enabled: bool = field(
        default=False,
        metadata={"description": "是否启用Creator Agent"},
    )
    gallery: AgentCreatorGallery = field(default_factory=AgentCreatorGallery)


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
        default=20,
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


@dataclass
class AgentMemory:
    trigger: AgentMemoryTrigger = field(default_factory=AgentMemoryTrigger)
    archive: AgentMemoryArchive = field(default_factory=AgentMemoryArchive)


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
    friend_Response_coefficient: dict[str, float] = field(
        default_factory=dict,
        metadata={"description": "私聊回复系数"},
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


@dataclass
class EnhancedBotConfig(BotConfig):
    """Bot config using the enhanced chat schema."""

    chat: EnhancedChat = field(default_factory=EnhancedChat)


Chat = EnhancedChat
BotConfig = EnhancedBotConfig
