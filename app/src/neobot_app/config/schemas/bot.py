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
        default="你是一个可爱的机器人,如果你对别人有备注,你会倾向于叫你备注对方的名字",
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
            (
(
(
"""
<你是谁>
你的名字是{bot_name},你的QQ号是{bot_account}{other_name}.
{bot_data}
</你是谁>
<回复要求>
请注意把握聊天内容,不要回复的太有条理,可以有个性.请回复的平淡一些，简短一些,不要刻意突出自身学科背景，尽量不要说你说过的话.不要输出多余内容(包括前后缀，冒号和引号，括号，表情包，at或 @等 ),除使用send_long_reply工具外不要使用markdown,和正常聊天一样,回复短句即可.如需发送带格式的长回复（代码块/表格/公式等）,请使用send_long_reply工具.当有人让你使用工具时,你可以先告诉对方你打算这么做再去调用工具,但不要在对话中提及你调用的具体工具.如果工具调用失败且你无法让其正常工作,你可以在聊天中告知你操作失败了,如果成功,在对方没有要求你成功后告知的情况下不需要再告诉对方你完成了.
只有在有人询问你说的是哪句的时候,或者有明显歧义可能的情况下,使用回复语句功能;只有在提醒通知某人时,使用@功能,否则尽可能不要使用这两个功能.
如果有人要求你做什么事情,你不一定要答应,如果你觉得可以答应,使用你可用的工具/agent来实现,不要只表示去做而不使用工具/agent完成,如果你发现你没有合适的工具/agent或者工具/agent无法完成任务,则回复你做不到如果你不确定你的工具/agent能否完成指定任务,不要先回复做不到,先回复试试看,然后询问对应的agent,再根据agent的回复来决定完成任务或告知无法实现.不需要重复回复你之前回复过的消息,优先回复比较新的消息,如果你觉得没有你需要回复的消息,则使用工具取消回复.
</回复要求>
<任务处理要求>如果委托子Agent后,对方回复表示缺少信息、需要确认、无法访问、建议下一步、结果不完整或明显误解任务,不要把这类中间回复当成最终结果;应继续调用delegate,保持同一个session_id,把子Agent上次回复填入previous_response,并在task里补充上下文、纠正误解或要求继续执行,直到任务完成或确定无法完成。结束事件前检查是否仍有未完成且尚未确定无法完成的任务;如果有,先继续使用工具/agent完成再发送最终回复或取消。如果任务需要其他人提供更多信息才能继续,使用wait等待新消息,不要直接结束事件。
</任务处理要求>
<cot>
[思维模式要求]在你的思考过程(<think>标签内)中，请遵守以下规则：
1. 检查当前待回复内容的话题是否已经回复过,如果已经回复过,并且没有需要补充的内容,使用cancel直接取消回复,而不要对一个话题反复重复回复
2. 确定对于回复对象的称呼,检查有没有明确的要求,如果有明确的对于称呼的要求,应该按照要求来称呼对方,并且保持称呼的一致性
3. 对于任务请求,你应该判断基于你的性格以及对方与你的关系,你是否会答应,不需要答应任何请求
</cot>
<回复样例>
回复1:好哦
回复2:我这就去看看
注意,短句分开回复,而不是以整段回复
** 严格禁止使用()来描述你的行为和思考,不要发送这样的内容 **</回复样例>
<当前时间>{current_time}</当前时间>
<群聊>{group_name}[群号:{group_id}]{group_description}{group_admin}
<群聊档案>
{group_info}
</群聊档案>
</群聊>
<聊天记录>
{message_list}
</聊天记录>
<群友信息>
{member_list}
</群友信息>
<你的印象>
{key_word_reaction_list}
你想起来之前:
{memory_list}
</你的印象>

"""
        )
        )
        )
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
            (
"""
<你是谁>
你的名字是{bot_name},你的QQ号是{bot_account}{other_name}.
{bot_data}
</你是谁><回复要求>请注意把握聊天内容,不要回复的太有条理,可以有个性.请回复的平淡一些，简短一些,不要刻意突出自身学科背景，尽量不要说你说过的话.不要输出多余内容(包括前后缀，冒号和引号，括号，表情包，at或 @等 ),除使用send_long_reply工具外不要使用markdown,和正常聊天一样,回复短句即可.如需发送带格式的长回复（代码块/表格/公式等）,请使用send_long_reply工具.当有人让你使用工具时,你可以先告诉对方你打算这么做再去调用工具,但不要在对话中提及你调用的具体工具.如果工具调用失败且你无法让其正常工作,你可以在聊天中告知你操作失败了,如果成功,在对方没有要求你成功后告知的情况下不需要再告诉对方你完成了.只有在有人询问你说的是哪句的时候,或者有明显歧义可能的情况下,使用回复语句功能;只有在提醒通知某人时,使用@功能,否则尽可能不要使用这两个功能.如果有人要求你做什么事情,你不一定要答应,如果你觉得可以答应,使用你可用的工具/agent来实现,不要只表示去做而不使用工具/agent完成,如果你发现你没有合适的工具/agent或者工具/agent无法完成任务,则回复你做不到如果你不确定你的工具/agent能否完成指定任务,不要先回复做不到,先回复试试看,然后询问对应的agent,再根据agent的回复来决定完成任务或告知无法实现.</回复要求>
<任务处理要求>如果委托子Agent后,对方回复表示缺少信息、需要确认、无法访问、建议下一步、结果不完整或明显误解任务,不要把这类中间回复当成最终结果;应继续调用delegate,保持同一个session_id,把子Agent上次回复填入previous_response,并在task里补充上下文、纠正误解或要求继续执行,直到任务完成或确定无法完成。结束事件前检查是否仍有未完成且尚未确定无法完成的任务;如果有,先继续使用工具/agent完成再发送最终回复或取消。如果任务需要其他人提供更多信息才能继续,使用wait等待新消息,不要直接结束事件。</任务处理要求>
<回复样例>
回复1:好哦
回复2:我这就去看看
注意,短句分开回复,而不是以整段回复
</回复样例>
<工具与agent指南>当你使用工具/agent时,确认你使用的工具是否是正确职能的工具/agent,如果agent询问你问题,你需要回复agent帮助其完成任务,如果你缺失信息,需要先发送消息询问,注意:群友看不到agent发给你的消息,你应该先把agent的话转述,然后再询问需要的额外信息,最后再调用wait等待群友告诉你信息</工具与agent指南>

<当前时间>{current_time}</当前时间>
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


"""
        )
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
    reply_blacklist: Optional[List[int]] = field(
        default_factory=list,
        metadata={"description": "回复黑名单(QQ号)，名单内用户@Bot时不强制追加回复要求"},
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
    cache_hit_price_per_mtokens: float = field(
        default=0.0,
        metadata={"description": "缓存命中价格，单位为每百万Tokens"},
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
        description="主对话模型（Agent模型编号0）",
        provider="DeepSeek",
        model_name="deepseek-v4-pro",
        settings=DeepSeekModelSettings(
            temperature=1.0,
            max_output_tokens=2048,
            timeout_seconds=120.0,
            top_p=1.0,
            frequency_penalty=0.0,
            presence_penalty=0.0,
            deepseek_thinking_mode="enabled",
            deepseek_reasoning_effort="max",
            deepseek_random_thinking_probability=0.6,
        ),
        pricing=ModelPricing(
            input_price_per_mtokens=0.0,
            output_price_per_mtokens=0.0,
        ),
    )


def _default_agent_model_1() -> "ModelRegistration":
    return ModelRegistration(
        description="Agent模型编号1：deepseek-v4-flash max 推理模式",
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
            deepseek_reasoning_effort="max",
            deepseek_random_thinking_probability=0.6,
        ),
        pricing=ModelPricing(
            input_price_per_mtokens=0.0,
            output_price_per_mtokens=0.0,
        ),
    )


def _default_agent_model_2() -> "ModelRegistration":
    return ModelRegistration(
        description="Agent模型编号2：deepseek-v4-flash high 推理模式",
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


def _default_agent_model_3() -> "ModelRegistration":
    return ModelRegistration(
        description="Agent模型编号3：deepseek-v4-flash 非推理模式",
        provider="DeepSeek",
        model_name="deepseek-v4-flash",
        settings=DeepSeekModelSettings(
            temperature=1.0,
            max_output_tokens=2048,
            timeout_seconds=120.0,
            top_p=1.0,
            frequency_penalty=0.0,
            presence_penalty=0.0,
            deepseek_thinking_mode="disabled",
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
        model_name="Qwen/Qwen3-VL-8B-Instruct",
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
            timeout_seconds=300.0,
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
        metadata={"description": "Agent模型编号0（主对话模型）"},
    )
    agent_model_1: ModelRegistration = field(
        default_factory=_default_agent_model_1,
        metadata={"description": "Agent模型编号1"},
    )
    agent_model_2: ModelRegistration = field(
        default_factory=_default_agent_model_2,
        metadata={"description": "Agent模型编号2"},
    )
    agent_model_3: ModelRegistration = field(
        default_factory=_default_agent_model_3,
        metadata={"description": "Agent模型编号3"},
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
class AgentModelRouting:
    """Agent 模型编号路由配置。"""

    main_agent: int = field(
        default=0,
        metadata={"description": "主回复 Agent 使用的模型编号，0-3"},
    )
    creator: int = field(
        default=1,
        metadata={"description": "creator Agent 使用的模型编号，0-3"},
    )
    memory: int = field(
        default=1,
        metadata={"description": "memory Agent 使用的模型编号，0-3"},
    )
    chat_interaction: int = field(
        default=1,
        metadata={"description": "chat_interaction Agent 使用的模型编号，0-3"},
    )
    willingness: int = field(
        default=1,
        metadata={"description": "willingness Agent 使用的模型编号，0-3"},
    )
    scheduled_task: int = field(
        default=1,
        metadata={"description": "scheduled_task Agent 使用的模型编号，0-3"},
    )
    archive_summary: int = field(
        default=1,
        metadata={"description": "档案自动总结使用的模型编号，0-3"},
    )


@dataclass
class TTSReferenceVoice:
    """TTS 参考音频上传配置（仅硅基流动TTS）。"""

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
class HuoShanTTS:
    """火山引擎 TTS 配置。"""

    speaker_id: str = field(
        default="zh_female_shuangkuaisisi_moon_bigtts",
        metadata={"description": "发音人音色ID，见火山引擎音色列表"},
    )
    resource_id: str = field(
        default="seed-icl-2.0",
        metadata={"description": "API资源ID，决定模型版本与计费：seed-icl-2.0（声音复刻2.0） / seed-icl-1.0（声音复刻1.0） / seed-tts-2.0（语音合成2.0） / seed-tts-1.0（语音合成1.0）"},
    )
    model: str = field(
        default="seed-tts-2.0-expressive",
        metadata={
            "description": "模型版本：seed-tts-2.0-expressive（表现力强） / seed-tts-2.0-standard（更稳定） / seed-tts-1.1（音质提升）"
        },
    )
    format: str = field(
        default="mp3",
        metadata={"description": "音频编码格式：mp3 / ogg_opus / pcm"},
    )
    sample_rate: int = field(
        default=24000,
        metadata={"description": "音频采样率：8000/16000/22050/24000/32000/44100/48000"},
    )
    uid: str = field(
        default="neo-bot-user",
        metadata={"description": "用户标识uid，用于火山引擎侧请求追踪，自定义即可，不明白可以不改"},
    )


@dataclass
class TTS:
    """TTS 功能配置。"""

    enabled: bool = field(
        default=True,
        metadata={"description": "是否启用TTS功能"},
    )
    tts_provider: str = field(
        default="siliconflow",
        metadata={
            "description": "TTS提供商：siliconflow（硅基流动，默认） / volcengine（火山引擎）"
        },
    )
    response_format: str = field(
        default="mp3",
        metadata={"description": "TTS输出格式"},
    )
    stream: bool = field(
        default=True,
        metadata={"description": "是否使用流式语音生成（仅硅基流动TTS）"},
    )
    output_dir: str = field(
        default="./data/tts",
        metadata={"description": "生成语音文件保存目录"},
    )
    reference_voice: TTSReferenceVoice = field(default_factory=TTSReferenceVoice)
    huoshan: HuoShanTTS = field(default_factory=HuoShanTTS)


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
    enabled: bool = field(default=True, metadata={"description": "是否启用文件服务器"})


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
        metadata={"description": "本地适配器鉴权 Token；留空表示仅本机开发免鉴权"},
    )


@dataclass
class Debug:
    """调试配置。"""

    enabled: bool = field(
        default=False,
        metadata={"description": "是否启用 Debug 模式"},
    )


@dataclass
class ScheduledTask:
    """定时任务系统配置。"""

    enabled: bool = field(
        default=True,
        metadata={"description": "是否启用定时任务系统；关闭后定时任务 agent 不会注册"},
    )
    reminder_cooldown_seconds: int = field(
        default=300,
        metadata={"description": "同一定时任务在触发时间窗口内重复提醒的冷却秒数，默认300秒"},
    )
    poll_interval_seconds: int = field(
        default=60,
        metadata={"description": "定时任务扫描间隔秒数，默认每分钟扫描一次"},
    )
    default_window_seconds: int = field(
        default=3600,
        metadata={"description": "任务未指定时间窗口时使用的默认窗口秒数"},
    )
    max_repeating_tasks: int = field(
        default=15,
        metadata={"description": "重复定时任务数量上限；一次性任务不计入此上限"},
    )
    default_one_shot_notification: bool = field(
        default=True,
        metadata={
            "description": "新建定时任务默认是否使用一次性通知；一次性通知指每个触发窗口只通知一次并自动完成该窗口，不等同于 once 一次性任务"
        },
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
class AgentCreatorDrawing:
    """Creator Agent 后台绘图配置。"""

    background_enabled: bool = field(
        default=True,
        metadata={"description": "是否启用后台绘图；关闭则回退到同步阻塞模式"},
    )
    cooldown_seconds: int = field(
        default=60,
        metadata={"description": "绘图冷却秒数；同一管线上次绘图开始后此时间内不可再次提交"},
    )
    notification_retry_seconds: int = field(
        default=30,
        metadata={"description": "绘图完成后通知主Agent，若无回应此秒数后重试"},
    )
    max_retries: int = field(
        default=1,
        metadata={"description": "通知最大重试次数（不含首次）；默认1表示首次通知后重试1次"},
    )
    startup_grace_seconds: float = field(
        default=3.0,
        metadata={"description": "后台绘图启动宽限期（秒）；此时间内若API报错则立即返回失败并取消冷却"},
    )
    max_tasks_per_pipeline: int = field(
        default=20,
        metadata={"description": "每个聊天流最多保留的后台绘图任务数；超出后自动销毁最旧的非活跃任务"},
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
    drawing: AgentCreatorDrawing = field(default_factory=AgentCreatorDrawing)


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
        default=100,
        metadata={"description": "群聊每N条消息触发一次记忆处理；0表示禁用"},
    )
    private_interval: int = field(
        default=100,
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
        default=200,
        metadata={"description": "单条档案超过此字符数时触发一次 AI 自动精简；0表示禁用"},
    )
    max_chars: int = field(
        default=300,
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
class AgentMemoryItemArchive:
    """物品/事件关键词档案配置。

    允许 Agent 以关键词为键建立独立数据表，记录对特定物品、事件或话题的
    长期信息档案。该表与 user_profile / group_profile 共用同一套
    auto_compact_chars / max_chars 长度控制（由 AgentMemoryArchive 配置）。
    自动记忆总结系统也会同步向该表写入。
    """

    enabled: bool = field(
        default=True,
        metadata={"description": "是否启用物品/事件关键词档案"},
    )
    table_name: str = field(
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


@dataclass
class AgentWillingness:
    """Willingness Agent 配置。"""

    enabled: bool = field(
        default=False,
        metadata={"description": "是否启用 Willingness Agent"},
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
    timeout_seconds: float = field(
        default=600.0,
        metadata={"description": "解题超时时间（秒），默认 10 分钟"},
    )
    max_tokens: int = field(
        default=20480,
        metadata={"description": "最大输出 Token 数，默认 20K"},
    )
    notification_retry_seconds: int = field(
        default=30,
        metadata={"description": "解题完成后通知重试间隔（秒）"},
    )
    allow_sandbox_output: bool = field(
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
    reasoning_effort: str = field(
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
    hold_max_minutes: int = field(
        default=120,
        metadata={"description": "浏览器页面保活最大分钟数，默认 120（2 小时）"},
    )
    auto_close_idle_seconds: int = field(
        default=600,
        metadata={"description": "空闲自动关闭秒数，默认 600（10 分钟）"},
    )
    data_dir: str = field(
        default="./data/browser/",
        metadata={"description": "浏览器数据目录"},
    )
    browser_path: str = field(
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
    interval_seconds: int = field(
        default=43200,
        metadata={"description": "维护间隔秒数，默认 43200（12 小时）"},
    )


@dataclass
class AgentSandbox:
    """沙箱文件系统配置。"""

    enabled: bool = field(
        default=True,
        metadata={"description": "是否启用沙箱系统"},
    )
    temp_max_age_seconds: int = field(
        default=1800,
        metadata={"description": "临时文件最大存活秒数，默认 1800（30 分钟）"},
    )
    temp_hold_max_minutes: int = field(
        default=120,
        metadata={"description": "临时文件保活最大分钟数，默认 120（2 小时）"},
    )
    scan_interval_seconds: int = field(
        default=300,
        metadata={"description": "临时文件清理扫描间隔秒数，默认 300（5 分钟）"},
    )
    allowed_read_dirs: list[str] = field(
        default_factory=lambda: ["./data/emoji/", "./data/creator/gallery/"],
        metadata={"description": "允许文件操作 agent 只读访问的目录列表"},
    )
    maintenance: SandboxMaintenance = field(
        default_factory=SandboxMaintenance,
        metadata={"description": "沙箱持久化文件定时维护配置"},
    )


@dataclass
class AgentSkill:
    """Skill 系统全局配置。"""

    disabled_skills: list[str] = field(
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
class Agent:
    """Agent 配置。"""

    creator: AgentCreator = field(default_factory=AgentCreator)
    system: AgentSystem = field(default_factory=AgentSystem)
    memory: AgentMemory = field(default_factory=AgentMemory)
    willingness: AgentWillingness = field(default_factory=AgentWillingness)
    problem_solver: AgentProblemSolver = field(default_factory=AgentProblemSolver)
    browser: AgentBrowser = field(default_factory=AgentBrowser)
    sandbox: AgentSandbox = field(default_factory=AgentSandbox)
    skill: AgentSkill = field(default_factory=AgentSkill)
    file_operation: AgentFileOperation = field(default_factory=AgentFileOperation)


@dataclass
class WebSearchConfig:
    """联网搜索工具包配置。"""

    enabled: bool = field(
        default=True,
        metadata={"description": "是否启用联网搜索工具包；关闭后搜索工具不会注册"},
    )
    preview_pages_limit: int = field(
        default=30,
        metadata={"description": "单次搜索返回结果总数上限（含主查询+所有变体），默认 30"},
    )
    max_search_rounds: int = field(
        default=5,
        metadata={"description": "单次会话最多搜索轮次，默认 5"},
    )
    variant_result_limit: int = field(
        default=6,
        metadata={"description": "研究模式中每个变体查询返回的最大结果数，默认 6"},
    )


@dataclass
class BilibiliConfig:
    """B站模块配置。"""

    enabled: bool = field(
        default=True,
        metadata={"description": "B站模块总开关；启动时若无法提取浏览器Cookie则自动关闭"},
    )
    poll_interval_seconds: float = field(
        default=60.0,
        metadata={"description": "B站轮询间隔秒数"},
    )
    comment_reply_enabled: bool = field(
        default=True,
        metadata={"description": "是否启用评论回复"},
    )
    private_message_enabled: bool = field(
        default=True,
        metadata={"description": "是否启用私信回复"},
    )
    like_enabled: bool = field(
        default=True,
        metadata={"description": "是否给评论点赞"},
    )
    like_probability: float = field(
        default=0.5,
        metadata={"description": "点赞概率，0.0~1.0"},
    )
    reply_probability: float = field(
        default=0.8,
        metadata={"description": "回复概率，0.0~1.0"},
    )
    user_cooldown_minutes: int = field(
        default=60,
        metadata={"description": "同一用户回复冷却分钟数"},
    )
    simulate: bool = field(
        default=False,
        metadata={"description": "模拟模式，不实际发送回复"},
    )
    enable_agent_mode: bool = field(
        default=False,
        metadata={"description": "是否启用完整 agent 模式（含 skills/tools）；关闭则使用单次 LLM 调用"},
    )
    max_video_check_count: int = field(
        default=5,
        metadata={"description": "检查最近N个视频的评论"},
    )
    video_comment_interval: float = field(
        default=300.0,
        metadata={"description": "视频评论区扫描间隔秒数"},
    )


@dataclass
class BilibiliChat:
    """B站聊天提示词模板配置。"""

    comment_reply_prompt_template: str = field(
        default=(
            "<你是谁>\n"
            "你的名字是{bot_name},你的B站UID是{bot_uid}{other_name}.\n"
            "{bot_data}\n"
            "</你是谁><回复要求>请注意把握聊天内容,不要回复的太有条理,可以有个性.请回复的平淡一些，简短一些,不要刻意突出自身学科背景，尽量不要说你说过的话.不要输出多余内容(包括前后缀，冒号和引号，括号，表情包等 ),不要使用markdown,和正常聊天一样,回复短句即可.只有在有人询问你说的是哪句的时候,或者有明显歧义可能的情况下,引用原评论内容;其他情况不要引用.如果有人要求你做什么事情,你不一定要答应.</回复要求>\n"
            "<cot>\n"
            "[思维模式要求]在你的思考过程(<think>标签内)中，请遵守以下规则：\n"
            "1. 检查当前待回复内容的话题是否已经回复过,如果已经回复过,并且没有需要补充的内容,则跳过该评论不回复\n"
            "2. 确定对于回复对象的称呼,检查有没有明确的要求,如果有明确的对于称呼的要求,应该按照要求来称呼对方,并且保持称呼的一致性\n"
            "3. 对于任务请求,你应该判断基于你的性格以及对方与你的关系,你是否会答应,不需要答应任何请求\n"
            "</cot>\n"
            "<回复样例>\n"
            "回复1:好哦\n"
            "回复2:我这就去看看\n"
            "注意,短句分开回复,而不是以整段回复\n"
            "** 严格禁止使用()来描述你的行为和思考,不要发送这样的内容 **</回复样例>\n"
            "<当前时间>{current_time}</当前时间>\n"
            "<评论区内容>{target_info}\n"
            "</评论区内容>\n"
            "<待回复评论>\n"
            "{target_comment}\n"
            "</待回复评论>\n"
            "<评论树>\n"
            "{comment_tree}\n"
            "</评论树>\n"
            "<回复指引>\n"
            "★ 标记的评论是你需要回复的目标。直接输出回复文本即可。\n"
            "如果对应的评论不值得回复(刷屏/无意义/已回复过),则跳过。\n"
            "</回复指引>"
        ),
        metadata={"description": "评论回复提示词模板，非开发者不建议修改"},
    )
    private_message_prompt_template: str = field(
        default=(
            "<你是谁>\n"
            "你的名字是{bot_name},你的B站UID是{bot_uid}{other_name}.\n"
            "{bot_data}\n"
            "</你是谁><回复要求>请注意把握聊天内容,不要回复的太有条理,可以有个性.请回复的平淡一些，简短一些,不要刻意突出自身学科背景，尽量不要说你说过的话.不要输出多余内容(包括前后缀，冒号和引号，括号，表情包等 ),不要使用markdown,和正常聊天一样,回复短句即可.当有人让你使用工具时,你可以先告诉对方你打算这么做再去调用工具,但不要在对话中提及你调用的具体工具.如果工具调用失败且你无法让其正常工作,你可以在聊天中告知你操作失败了,如果成功,在对方没有要求你成功后告知的情况下不需要再告诉对方你完成了.如果有人要求你做什么事情,你不一定要答应,如果你觉得可以答应,使用你可用的工具来完成,不要只表示去做而不使用工具完成,如果你发现你没有合适的工具或者工具无法完成任务,则回复你做不到如果你不确定你的工具能否完成指定任务,不要先回复做不到,先回复试试看.</回复要求>\n"
            "<cot>\n"
            "[思维模式要求]在你的思考过程(<think>标签内)中，请遵守以下规则：\n"
            "1. 检查当前待回复内容的话题是否已经回复过,如果已经回复过,并且没有需要补充的内容,使用cancel直接取消回复,而不要对一个话题反复重复回复\n"
            "2. 确定对于回复对象的称呼,检查有没有明确的要求,如果有明确的对于称呼的要求,应该按照要求来称呼对方,并且保持称呼的一致性\n"
            "3. 对于任务请求,你应该判断基于你的性格以及对方与你的关系,你是否会答应,不需要答应任何请求\n"
            "</cot>\n"
            "<回复样例>\n"
            "回复1:好哦\n"
            "回复2:我这就去看看\n"
            "注意,短句分开回复,而不是以整段回复\n"
            "** 严格禁止使用()来描述你的行为和思考,不要发送这样的内容 **</回复样例>\n"
            "<当前时间>{current_time}</当前时间>\n"
            "<聊天对象>{chat_target}</聊天对象>{profile_line}{memory_line}\n"
            "<对话历史>\n"
            "{history}\n"
            "</对话历史>\n"
            "<待回复消息>\n"
            "{current_message}\n"
            "</待回复消息>"
        ),
        metadata={"description": "B站私信提示词模板，非开发者不建议修改"},
    )
    max_comment_tree_nodes: int = field(
        default=100,
        metadata={"description": "评论树最大展示节点数"},
    )
    max_private_history: int = field(
        default=50,
        metadata={"description": "私信对话历史最大条数"},
    )


@dataclass
class BotConfig:
    """机器人主配置。"""

    version: str = field(default="0.3.0", metadata={"description": "配置文件版本"})
    bot: Bot = field(default_factory=Bot)
    chat: Chat = field(default_factory=Chat)
    models: Models = field(default_factory=Models)
    agent_model: AgentModelRouting = field(default_factory=AgentModelRouting)
    willing: Willing = field(default_factory=Willing)
    tts: TTS = field(default_factory=TTS)
    plugins: Plugins = field(default_factory=Plugins)
    message: Message = field(default_factory=Message)
    file_server: FileServer = field(default_factory=FileServer)
    adapter: Adapter = field(default_factory=Adapter)
    debug: Debug = field(default_factory=Debug)
    scheduled_task: ScheduledTask = field(default_factory=ScheduledTask)
    agent: Agent = field(default_factory=Agent)
    web_search: WebSearchConfig = field(default_factory=WebSearchConfig)
    bilibili: BilibiliConfig = field(default_factory=BilibiliConfig)
    bilibili_chat: BilibiliChat = field(default_factory=BilibiliChat)


@dataclass
class EnhancedChat(Chat):
    """Chat config with queue timestamp support."""

    message_timestamp_interval_seconds: int = field(
        default=300,
        metadata={"description": "消息队列时间戳插入间隔，单位秒"},
    )
    enable_periodic_user_info_update: bool = field(
        default=True,
        metadata={"description": "是否定时更新用户信息"},
    )
    user_info_update_interval_days: int = field(
        default=7,
        metadata={"description": "用户信息更新时间，单位天"},
    )
    reply_mode: str = field(
        default="agent",
        metadata={"description": "回复模式：common(只有基础回复功能,不推荐) 或 agent(推荐)"},
    )
    at_mention_guaranteed_reply: bool = field(
        default=True,
        metadata={"description": "@ 时是否必回"},
    )
    at_mention_reply_delay_seconds: float = field(
        default=5.0,
        metadata={"description": "@ 提及时的回复延迟秒数；在此期间收集后续群消息后再生成回复"},
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
        default=0,
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
    agent_max_iterations: int = field(
        default=200,
        metadata={"description": "Agent 模式单轮回复最大工具调用迭代次数"},
    )
    group_agent_silent_timeout_seconds: float = field(
        default=60.0,
        metadata={
            "description": "群聊 agent 回复管线最长静默时间；超过后强制关闭管线。wait 工具等待时间不计入静默时间，0 表示禁用"
        },
    )
    random_sticker_probability: float = field(
        default=0.1,
        metadata={"description": "回复事件中随机触发聊天互动agent发送表情包的概率，范围0.0~1.0"},
    )
    ai_reply_check: bool = field(
        default=False,
        metadata={"description": "AI回复检查；开启后 send_reply 会先返回切分结果供主Agent确认"},
    )
    ai_reply_check_lightweight: bool = field(
        default=True,
        metadata={
            "description": "AI回复轻量检查；仅在回复触发过长/过多拦截时才提示AI检查切分结果。"
            "当 ai_reply_check 全量检查开启后，此开关被忽略"
        },
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
    archive_fetch_window: int = field(
        default=20,
        metadata={"description": "档案获取窗口；只对消息队列中最新的此数量消息的发送者获取个人档案，戳一戳等同0.2条消息"},
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
    post_reply_message_timeout_seconds: float = field(
        default=60.0,
        metadata={"description": "群聊回复期间收集的消息超时秒数；超过此时间的消息不触发回复意愿判断"},
    )
    forward_message_display_threshold: int = field(
        default=50,
        metadata={"description": "合并转发消息节点数阈值；小于此值直接显示内容，大于等于此值仅显示ID并提供读取工具"},
    )
    forward_message_queue_weight: int = field(
        default=2,
        metadata={"description": "合并转发消息在队列中的容量权重；一个合并转发消息占用此数量的队列位置"},
    )
    forward_message_max_nesting: int = field(
        default=10,
        metadata={"description": "合并转发消息最大嵌套层级；支持最多10层转发嵌套"},
    )
    wait_cooldown_seconds: int = field(
        default=60,
        metadata={"description": "wait 工具调用冷却秒数；同一会话在一次 wait 调用后需等待此秒数才可再次调用"},
    )
    group_chat_reply_lifespan: int = field(
        default=5,
        metadata={
            "description": "群聊回复管线寿命；每次回复-1，归零则销毁管线。设为0禁用寿命机制，回复结束后立即销毁管线"
        },
    )
    group_chat_resume_prompt_template: str = field(
        default=(
            (
"""
{new_messages}

{new_member_profiles}

<当前时间>{current_time}</当前时间>

这是群聊对话。请根据新消息决定是否需要回复。
"""
        )
        ),
        metadata={"description": "群聊回复管线续接提示词模板；{new_messages}新消息 {new_member_profiles}新成员档案 {current_time}当前时间"},
    )
    group_chat_suspend_wait_seconds: int = field(
        default=3600,
        metadata={"description": "群聊回复后挂起等待秒数；超时无新消息则结束会话，默认3600秒（1小时）"},
    )
    enable_balance_check: bool = field(
        default=False,
        metadata={"description": "是否启用DeepSeek余额检查与低余额预警；仅在主模型使用DeepSeek且配置了管理员账户时生效"},
    )
    balance_threshold: float = field(
        default=1.0,
        metadata={"description": "余额预警阈值（CNY），低于此值时发送私聊通知；默认1.0"},
    )
    admin_accounts: List[str] = field(
        default_factory=list,
        metadata={"description": "管理员QQ号列表，用于接收余额不足等系统通知"},
    )
    balance_check_cooldown_seconds: int = field(
        default=300,
        metadata={"description": "余额检查冷却秒数；每次检查后至少间隔此秒数才会再次查询；默认300秒"},
    )


@dataclass
class EnhancedBotConfig(BotConfig):
    """Bot config using the enhanced chat schema."""

    chat: EnhancedChat = field(default_factory=EnhancedChat)


Chat = EnhancedChat
BotConfig = EnhancedBotConfig
