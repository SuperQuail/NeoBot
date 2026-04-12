from dataclasses import dataclass, field, fields as dataclass_fields
from typing import Any, Dict, Iterator, List, Optional, TypedDict


class KeyWordRule(TypedDict, total=False):
    """关键词规则类型"""

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
    """机器人基础配置"""

    account: int = field(
        default=0, metadata={"description": "机器人QQ号", "placeholder": True}
    )
    nick_name: str = field(default="Neo Bot", metadata={"description": "Bot昵称"})
    alias_name: Optional[List[str]] = field(
        default_factory=lambda: ["Neo", "铸币bot"], metadata={"description": "Bot别称"}
    )
    bot_data: str = field(
        default="你是一个可爱的机器人", metadata={"description": "描述机器人的人设"}
    )
    enable_bot_get_married: bool = field(
        default=False, metadata={"description": "是否允许bot与好友结婚"}
    )


@dataclass
class Chat:
    group_prompt_template: str = field(
        default="""<当前时间>{current_time}</当前时间>
<群聊>{group_name}[群号:{group_id}]{group_description}</群聊>
<聊天记录>
{message_list}
</聊天记录>
<群友信息>
{member_list}
</群友信息>
<你是谁>
你的名字是{bot_name},你的QQ号是{bot_account}{other_name}.
{bot_data},现在你在这个群里聊天,你打算用日常,口语化的方式回复最后几句聊天记录里你比较感兴趣的内容,个性化一些,不用特意突出科学背景,聊天时你一般不会使用冒号,括号,句号也一般不使用,而是直接换行分成多条(多次调用回复工具).一次回复一句即可,不要太长.
</你是谁>
<你的印象>
{key_word_reaction_list}
你想起来之前:
{memory_list}
这些内容都是之前的内容,可能很久之前,也可能只是不久之前.
</你的印象>""",
        metadata={"description": "Bot提示词模板,非开发者不建议修改"},
    )
    max_group_chat_observations: int = field(
        default=100,
        metadata={"description": "群聊观察上限,决定bot最多可以看到多少条聊天记录"},
    )
    group_chat_chance: float = field(
        default=0.5, metadata={"description": "群聊基础回复概率"}
    )
    group_use_black_list: bool = field(
        default=True,
        metadata={"description": "true为群聊列表使用黑名单,false表示使用白名单"},
    )
    group_list: Optional[List[str]] = field(
        default_factory=lambda: ["111111", "222222"],
        metadata={
            "description": "群名单，根据 group_use_black_list 字段确定是白名单/黑名单，决定 bot 是否会在对应群聊对话"
        },
    )
    group_Response_coefficient: Optional[Dict[str, float]] = field(
        default_factory=lambda: {"111111": 0.5, "222222": 0.5},
        metadata={
            "description": "群聊回复系数，根据群聊 ID 配置回复概率，会在结算时与基础回复概率相乘"
        },
    )
    group_description: Optional[Dict[str, str]] = field(
        default_factory=lambda: {"111111": "这是不知道谁不知道干什么的群"},
        metadata={"description": "群描述，可以为特定群配置专属简介"},
    )
    friend_prompt_template: str = field(
        default="""<当前时间>{current_time}</当前时间>
<聊天对象>{friend_name}(你的备注:{remark})</聊天对象>
<你对ta的印象>{profile}</你对ta的印象>
<对方信息>
{friend_info}
</对方信息>
<你的记忆>
你想起来{memory_list}
</你的记忆>
<聊天记录>
{message_list}
</聊天记录>
<你是谁>
你的名字是{bot_name},你的QQ号是{bot_account}{other_name}.
{bot_data},现在你在这个群里聊天,你打算用日常,口语化的方式回复最后几句聊天记录里你比较感兴趣的内容,个性化一些,不用特意突出科学背景,聊天时你一般不会使用冒号,括号,句号也一般不使用,而是直接换行分成多条.一次回复一句即可,不要超过三小句.
</你是谁>"""
    )
    max_friend_chat_observations: int = field(
        default=100,
        metadata={"description": "群聊观察上限,决定bot最多可以看到多少条聊天记录"},
    )
    friend_chat_chance: float = field(
        default=0.5, metadata={"description": "私聊基础回复概率"}
    )
    friend_use_black_list: bool = field(
        default=True, metadata={"description": "true时私聊使用黑名单,false使用黑名单"}
    )
    friend_list: Optional[List[str]] = field(
        default_factory=lambda: ["111111", "222222"],
        metadata={
            "description": "好友名单，根据 friend_use_black_list 字段确定是白名单/黑名单，决定 bot 是否会在对应私聊对话"
        },
    )
    friend_description: Optional[Dict[str, str]] = field(
        default_factory=lambda: {"111111": "这是不知道谁不知道干什么的人"},
        metadata={"description": "好友描述，可以为特定好友配置专属简介"},
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
            }
        ],
        metadata={
            "description": "关键词规则列表；每条规则可配置是否启用、关键词、提示词列表、忽略大小写、匹配模式、最小深度和最大深度"
        },
    )


@dataclass
class ModelPricing:
    """模型价格配置。"""

    input_price_per_mtokens: float = field(
        default=0.0,
        metadata={"description": "输入价格，单位为每百万 Tokens"},
    )
    output_price_per_mtokens: float = field(
        default=0.0,
        metadata={"description": "输出价格，单位为每百万 Tokens"},
    )
    billing_metric: str = field(
        default="",
        metadata={"description": "闈非 Token 计费模型的平台计费标识"},
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
        metadata={"description": "单次最大回复 Tokens"},
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
class ModelRegistration:
    """单个模型注册配置。"""

    description: str = field(
        default="主对话模型",
        metadata={"description": "模型用途说明"},
    )
    provider: str = field(
        default="DeepSeek",
        metadata={"description": "模型供应商，对应 env 中的平台名字"},
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
        model_name="deepseek-reasoner",
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

    def iter_registrations(self) -> Iterator[tuple[str, ModelRegistration]]:
        """遍历所有可注册模型。"""
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
        metadata={"description": "参考音频上传失败时是否自动禁用 TTS"},
    )


@dataclass
class TTS:
    """TTS 功能配置。"""

    enabled: bool = field(
        default=True,
        metadata={"description": "是否启用 TTS 功能"},
    )
    response_format: str = field(
        default="mp3",
        metadata={"description": "TTS 输出格式"},
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
    """回复意愿管理器配置"""

    manager_name: str = field(
        default="Quail",
        metadata={"description": "回复意愿管理器名称，默认内置鹌鹑意愿生成器 Quail"},
    )
    observe_window: int = field(
        default=5,
        metadata={"description": "仔细观察窗口，取消息队列最后几条消息作为意愿计算重点观察内容"},
    )
    reply_threshold: float = field(
        default=0.5,
        metadata={"description": "回复概率达到该阈值时视为建议回复"},
    )


@dataclass
class Plugins:
    """插件配置"""

    enabled: bool = field(default=True, metadata={"description": "是否启用插件"})
    dir: str = field(default="./plugins", metadata={"description": "插件目录"})


@dataclass
class Message:
    """消息处理配置"""

    max_length: Optional[int] = field(
        default=1000, metadata={"description": "消息最大长度"}
    )
    enable_group: Optional[bool] = field(
        default=True, metadata={"description": "是否处理群消息"}
    )
    enable_private: Optional[bool] = field(
        default=True, metadata={"description": "是否处理私聊消息"}
    )


@dataclass
class FileServer:
    """文件服务器配置"""

    port: int = field(default=8765, metadata={"description": "文件服务器端口"})
    host: str = field(
        default="127.0.0.1",
        metadata={"description": "文件服务器主机地址，设置为 0.0.0.0 可外部访问"},
    )
    public_url: Optional[str] = field(
        default=None,
        metadata={"description": "访问地址，如 http://your-domain.com:8765"},
    )


@dataclass
class BotConfig:
    """机器人主配置"""

    version: str = field(default="0.2.0", metadata={"description": "配置文件版本"})
    bot: Bot = field(default_factory=Bot)
    chat: Chat = field(default_factory=Chat)
    models: Models = field(default_factory=Models)
    willing: Willing = field(default_factory=Willing)
    tts: TTS = field(default_factory=TTS)
    plugins: Plugins = field(default_factory=Plugins)
    message: Message = field(default_factory=Message)
    file_server: FileServer = field(default_factory=FileServer)


@dataclass
class EnhancedChat(Chat):
    """Chat config with queue timestamp support."""

    message_timestamp_interval_seconds: int = field(
        default=300,
        metadata={"description": "消息队列时间戳插入间隔，单位秒，默认五分钟"},
    )
    enable_periodic_user_info_update: bool = field(
        default=False,
        metadata={"description": "是否定时更新用户信息；开启后当数据库中的用户信息超过更新时间时会重新拉取"},
    )
    user_info_update_interval_days: int = field(
        default=7,
        metadata={"description": "用户信息更新时间，单位天；仅在开启定时更新用户信息时生效"},
    )
    enable_group_startup_history_warmup: bool = field(
        default=False,
        metadata={
            "description": "是否在程序启动时读取群聊历史聊天记录以预热消息队列，可能存在风控风险，默认关闭"
        },
    )
    enable_friend_startup_history_warmup: bool = field(
        default=False,
        metadata={
            "description": "是否在程序启动时读取私聊历史聊天记录以预热消息队列，可能存在风控风险，默认关闭"
        },
    )
    startup_history_group_whitelist: List[str] = field(
        default_factory=list,
        metadata={
            "description": "启动时读取历史聊天记录的群聊白名单，填写群号；留空表示获取全部群聊历史，仅在开启启动历史预热时生效"
        },
    )
    startup_history_friend_whitelist: List[str] = field(
        default_factory=list,
        metadata={
            "description": "启动时读取历史聊天记录的私聊白名单，填写QQ号；留空表示获取全部私聊历史，仅在开启启动历史预热时生效"
        },
    )


@dataclass
class EnhancedBotConfig(BotConfig):
    """Bot config using the enhanced chat schema."""

    chat: EnhancedChat = field(default_factory=EnhancedChat)


Chat = EnhancedChat
BotConfig = EnhancedBotConfig
