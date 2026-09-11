import re
from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, Iterator, List, Optional, TypedDict

_MODEL_KEY_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def normalize_model_key(value: Any) -> str:
    """把模型 key 规范化为 [A-Za-z0-9_.-]{1,64}（非法字符替换为 -）。"""
    text = str(value or "").strip()
    text = _MODEL_KEY_RE.sub("-", text).strip("-.")
    return text[:64]


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
    native_vision_default_image_count: int = field(
        default=4,
        metadata={"description": "原生视觉每轮默认自动加载的图片数量，0 关闭自动加载；手动加图工具不受此数量限制"},
    )
    max_group_chat_observations: Optional[int] = field(
        default=100,
        metadata={"description": "群聊观察上限"},
    )
    group_chat_chance: Optional[float] = field(
        default=0.5,
        metadata={"description": "群聊基础回复概率"},
    )
    group_use_black_list: Optional[bool] = field(
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
    max_friend_chat_observations: Optional[int] = field(
        default=100,
        metadata={"description": "私聊观察上限"},
    )
    friend_use_black_list: Optional[bool] = field(
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
    image_api: str = field(
        default="auto",
        metadata={
            "description": "生图接口形态（仅生图模型使用）：auto 有参考图时走 /images/edits（失败回退 "
            "/images/generations），edits 始终走 /images/edits（multipart），generations 始终走 "
            "/images/generations（参考图作为 JSON 字段传递）",
            "options": ["auto", "edits", "generations"],
            "options_strict": True,
        },
    )
    image_reference_param: str = field(
        default="image",
        metadata={
            "description": "generations 模式下参考图的 JSON 字段名（不同中转站可能是 image / images / "
            "image_url / image_urls / input_image）"
        },
    )


@dataclass
class DeepSeekModelSettings(ModelSettings):
    """DeepSeek 模型运行设置（包含思考模式相关配置）。
    注意：思考模式配置统一采用 OpenAI 样式作为参考填写，程序会自动根据实际 API 提供方进行样式转换。
    """

    deepseek_thinking_mode: str = field(
        default="enabled",
        metadata={
            "description": "思考模式开关（OpenAI 样式）：enabled 开启（默认），disabled 关闭，random 按概率随机开启",
            "options": ["enabled", "disabled", "random"],
            "options_strict": True,
        },
    )
    deepseek_reasoning_effort: str = field(
        default="high",
        metadata={
            "description": "思考强度控制（OpenAI 样式）：low/medium 映射为 high，xhigh 映射为 max，可选 high（默认）或 max",
            "options": ["high", "max"],
            "options_strict": True,
        },
    )
    deepseek_random_thinking_probability: float = field(
        default=0.6,
        metadata={
            "description": "随机思考开启概率，范围 0.0 到 1.0，仅在思考模式为 random 时生效"
        },
    )


#: 模型类型：决定面板中的用途分组与默认描述（不限制调用方引用）
MODEL_TYPE_LABELS: Dict[str, str] = {
    "chat": "对话 / 推理模型",
    "image": "生图模型",
    "vision": "图像识别模型",
    "tts": "语音（TTS）模型",
    "other": "其它",
}


def normalize_model_type(value: Any) -> str:
    """归一模型类型；未知值原样保留（便于配置里使用自定义类型）。"""
    text = str(value or "").strip().lower()
    return text or "chat"


@dataclass
class ModelDefinition:
    """模型库中的一个模型；调用方通过 key 引用它。"""

    key: str = field(
        default="",
        metadata={
            "description": "模型唯一标识（调用方引用名），只能包含字母、数字、下划线、点和短横线；"
            "面板不展示，新建时按模型名自动生成",
            "hidden": True,
        },
    )
    model_type: str = field(
        default="chat",
        metadata={
            "description": "模型类型：用于面板分组与筛选（对话 / 生图 / 图像识别 / 语音）",
            "options": list(MODEL_TYPE_LABELS),
            "options_strict": True,
        },
    )
    description: str = field(
        default="",
        metadata={
            "description": "模型用途说明（留空时按类型自动生成；Agent 选择生图模型时也会参考）"
        },
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
    settings: DeepSeekModelSettings = field(default_factory=DeepSeekModelSettings)
    native_vision: bool = field(
        default=False,
        metadata={
            "description": "该模型可直接接收图片块；主推理模型开启后，不可用或无法处理图片时"
            "自动回退到 vision_model（无需手选回退模型）"
        },
    )
    use_system_proxy: bool = field(
        default=False,
        metadata={
            "description": "该模型是否跟随系统/环境变量代理访问；默认关闭（直连），"
            "仅在需要通过本地代理（如 Clash）访问供应商时开启"
        },
    )
    balance_query_hint: str = field(
        default="",
        metadata={
            "description": "该模型/供应商的余额查询方式（文本描述，可写请求地址、方法、鉴权与返回字段）。"
            "留空表示没有查询提示，余额查询 skill 不会列出该模型"
        },
    )

    def __post_init__(self) -> None:
        self.key = normalize_model_key(self.key)
        self.model_type = normalize_model_type(self.model_type)
        if not str(self.description or "").strip():
            self.description = MODEL_TYPE_LABELS.get(self.model_type, "模型")

    @property
    def type_label(self) -> str:
        return MODEL_TYPE_LABELS.get(self.model_type, self.model_type)

    @property
    def display_name(self) -> str:
        return self.description or self.model_name or self.key


#: 兼容旧名称（历史配置与外部脚本可能仍引用 ModelRegistration）
ModelRegistration = ModelDefinition


def _default_primary_chat_model() -> "ModelDefinition":
    return ModelDefinition(
        key="deepseek-v4-pro",
        model_type="chat",
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


def _default_agent_model_1() -> "ModelDefinition":
    return ModelDefinition(
        key="deepseek-v4-flash-max",
        model_type="chat",
        description="Agent模型编号1：deepseek-v4-flash max 推理模式",
        provider="DeepSeek",
        model_name="deepseek-v4-flash",
        settings=DeepSeekModelSettings(
            temperature=1.0,
            max_output_tokens=20480,
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


def _default_agent_model_2() -> "ModelDefinition":
    return ModelDefinition(
        key="deepseek-v4-flash-high",
        model_type="chat",
        description="Agent模型编号2：deepseek-v4-flash high 推理模式",
        provider="DeepSeek",
        model_name="deepseek-v4-flash",
        settings=DeepSeekModelSettings(
            temperature=1.0,
            max_output_tokens=20480,
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


def _default_agent_model_3() -> "ModelDefinition":
    return ModelDefinition(
        key="deepseek-v4-flash-off",
        model_type="chat",
        description="Agent模型编号3：deepseek-v4-flash 非推理模式",
        provider="DeepSeek",
        model_name="deepseek-v4-flash",
        settings=DeepSeekModelSettings(
            temperature=1.0,
            max_output_tokens=20480,
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


def _default_vision_model() -> "ModelDefinition":
    return ModelDefinition(
        key="qwen3-vl-8b",
        model_type="vision",
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


def _default_tts_model() -> "ModelDefinition":
    return ModelDefinition(
        key="cosyvoice2",
        model_type="tts",
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


def _default_creator_image_model() -> "ModelDefinition":
    return ModelDefinition(
        key="flux-schnell",
        model_type="image",
        description="创作者Agent生图模型（默认）",
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


def _default_model_library() -> "List[ModelDefinition]":
    """默认模型库：模型单独存储，调用方只引用 key。"""
    return [
        _default_primary_chat_model(),
        _default_agent_model_1(),
        _default_agent_model_2(),
        _default_agent_model_3(),
        _default_vision_model(),
        _default_tts_model(),
        _default_creator_image_model(),
    ]


@dataclass
class ModelAssignments:
    """各调用方引用的模型 key（在模型库 [models.registry] 中定义）。"""

    primary_chat_model: str = field(
        default="deepseek-v4-pro",
        metadata={"description": "Agent模型编号0（主对话模型）引用的模型 key"},
    )
    agent_model_1: str = field(
        default="deepseek-v4-flash-max",
        metadata={"description": "Agent模型编号1引用的模型 key"},
    )
    agent_model_2: str = field(
        default="deepseek-v4-flash-high",
        metadata={"description": "Agent模型编号2引用的模型 key"},
    )
    agent_model_3: str = field(
        default="deepseek-v4-flash-off",
        metadata={"description": "Agent模型编号3引用的模型 key"},
    )
    vision_model: str = field(
        default="qwen3-vl-8b",
        metadata={"description": "图像识别模型引用的模型 key"},
    )
    tts_model: str = field(
        default="cosyvoice2",
        metadata={"description": "语音模型引用的模型 key"},
    )
    creator_image_models: List[str] = field(
        default_factory=lambda: ["flux-schnell"],
        metadata={
            "description": "创作者Agent生图模型列表（引用 key）；配置多个时由 Agent 按描述自行选择"
        },
    )

    #: 单值角色（顺序即面板展示顺序；ClassVar 表示不是配置字段）
    SINGLE_ROLES: ClassVar[tuple[str, ...]] = (
        "primary_chat_model",
        "agent_model_1",
        "agent_model_2",
        "agent_model_3",
        "vision_model",
        "tts_model",
    )

    def role_key(self, role: str) -> str:
        return str(getattr(self, role, "") or "").strip()

    def items(self) -> Iterator[tuple[str, str]]:
        """产出 (角色名, 模型 key)；生图列表逐项产出，角色名统一为 creator_image_models。"""
        for role in self.SINGLE_ROLES:
            key = self.role_key(role)
            if key:
                yield role, key
        for item in self.creator_image_models:
            key = str(item or "").strip()
            if key:
                yield "creator_image_models", key

    def image_keys(self) -> List[str]:
        return [str(item or "").strip() for item in self.creator_image_models if str(item or "").strip()]


@dataclass
class Models:
    """模型库 + 调用方分配。

    模型单独存储在 registry 中，各调用方（主对话/Agent/视觉/TTS/生图）只引用 key，
    这样同一个模型可以被多个调用方复用，改一处即可全局生效。
    """

    registry: List[ModelDefinition] = field(
        default_factory=_default_model_library,
        metadata={
            "description": "模型库：每个模型单独存储（key/描述/供应商/模型名/参数/价格），"
            "调用方通过 key 引用"
        },
    )
    assignments: ModelAssignments = field(
        default_factory=ModelAssignments,
        metadata={"description": "各调用方引用的模型 key"},
    )

    def by_key(self) -> Dict[str, ModelDefinition]:
        return {item.key: item for item in self.registry if item.key}

    def get(self, key: str) -> Optional[ModelDefinition]:
        return self.by_key().get(str(key or "").strip())

    def iter_definitions(self) -> Iterator[tuple[str, ModelDefinition]]:
        """遍历模型库：(key, 模型定义)。"""
        for item in self.registry:
            if item.key:
                yield item.key, item

    def iter_role_models(self) -> Iterator[tuple[str, ModelDefinition]]:
        """遍历调用方实际引用的模型：(角色名, 模型定义)；key 缺失时跳过。"""
        library = self.by_key()
        for role, key in self.assignments.items():
            definition = library.get(key)
            if definition is not None:
                yield role, definition

    def iter_registrations(self) -> Iterator[tuple[str, ModelDefinition]]:
        """兼容旧接口：等价于 iter_role_models()。"""
        return self.iter_role_models()

    def missing_assignment_keys(self) -> List[str]:
        """返回引用了但模型库里不存在的 key。"""
        library = self.by_key()
        return sorted({key for _role, key in self.assignments.items() if key not in library})

    @property
    def creator_image_model_names(self) -> List[str]:
        return self.assignments.image_keys()


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
    self_heal: int = field(
        default=3,
        metadata={"description": "自修复 Agent 使用的模型编号，0-3；默认 3（低成本非推理模型）"},
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



@dataclass
class Debug:
    """调试配置。"""

    enabled: bool = field(
        default=False,
        metadata={"description": "是否启用 Debug 模式"},
    )
    retention_days: int = field(
        default=10,
        metadata={
            "description": "调试数据保留天数（默认 10）：data/debug/log 下更早的分片"
            "与回复事件明细会被自动清理"
        },
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
            "description": "启动时直接进入待机（只启动面板等核心服务，不启动 bot 运行时）；"
            "适合先开面板补配置再启动运行"
        },
    )
    connect_onebot: Optional[bool] = field(
        default=True,
        metadata={
            "description": "待机时是否保持与 OneBot 的连接（默认保持：QQ 命令仍可用，"
            "便于随时恢复运行；关闭后待机期只有面板可用）"
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


@dataclass
class GalleryConfig:
    """图库配置。"""

    capacity: Optional[int] = field(
        default=10,
        metadata={"description": "图库容量上限；为0时禁用图库管理工具"},
    )
    page_size: Optional[int] = field(
        default=50,
        metadata={"description": "图库列表每页显示数量；图片总数超过此值时分页展示"},
    )


@dataclass
class CreatorEmojiConfig:
    """表情包管理配置。"""

    allow_add: Optional[bool] = field(
        default=False,
        metadata={"description": "是否允许 Creator Agent 增加表情包"},
    )
    allow_delete: Optional[bool] = field(
        default=False,
        metadata={"description": "是否允许 Creator Agent 删除表情包"},
    )
    page_size: int = field(
        default=50,
        metadata={"description": "表情包列表每页显示数量；总数超过此值时分页展示"},
    )


@dataclass
class BackgroundDrawConfig:
    """后台绘图配置。"""

    background_enabled: Optional[bool] = field(
        default=True,
        metadata={"description": "是否启用后台绘图；关闭则回退到同步阻塞模式"},
    )
    cooldown_seconds: Optional[int] = field(
        default=60,
        metadata={"description": "绘图冷却秒数；同一管线上次绘图开始后此时间内不可再次提交"},
    )
    notification_retry_seconds: Optional[int] = field(
        default=30,
        metadata={"description": "绘图完成后通知主Agent，若无回应此秒数后重试"},
    )
    max_retries: Optional[int] = field(
        default=1,
        metadata={"description": "通知最大重试次数（不含首次）；默认1表示首次通知后重试1次"},
    )
    startup_grace_seconds: Optional[float] = field(
        default=3.0,
        metadata={"description": "后台绘图启动宽限期（秒）；此时间内若API报错则立即返回失败并取消冷却"},
    )
    max_tasks_per_pipeline: Optional[int] = field(
        default=20,
        metadata={"description": "每个聊天流最多保留的后台绘图任务数；超出后自动销毁最旧的非活跃任务"},
    )


@dataclass
class ImageCreationConfig:
    """图像创作配置（生图、图库、表情包）。"""

    enabled: bool = field(
        default=False,
        metadata={"description": "是否启用图像创作功能"},
    )
    gallery: GalleryConfig = field(default_factory=GalleryConfig)
    emoji: CreatorEmojiConfig = field(default_factory=CreatorEmojiConfig)
    drawing: BackgroundDrawConfig = field(default_factory=BackgroundDrawConfig)
    image_inspect_enabled: bool = field(
        default=False,
        metadata={
            "description": "是否启用生图检查工具 inspect_image（需视觉模型支持）；"
            "关闭时工具不注册不注入提示词，开启后动态注入"
        },
    )


@dataclass
class AgentSystem:
    """System Agent 配置。"""

    allowed_work_dirs: List[str] = field(
        default_factory=lambda: ["./Data/"],
        metadata={"description": "System Agent 允许操作的工作目录"},
    )


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
        default=180.0,
        metadata={
            "description": "单次记忆总结的总时长预算(秒)；超过即中止本轮并进入失败冷却，"
            "避免多轮工具调用把一次总结拖成数十分钟"
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
        metadata={"description": "允许文件操作 agent 只读访问的目录列表"},
    )
    maintenance: SandboxMaintenance = field(
        default_factory=SandboxMaintenance,
        metadata={"description": "沙箱持久化文件定时维护配置"},
    )


@dataclass
class VisionDetect:
    """本地视觉检测(ONNX/YOLO)配置。

    模型文件放入 models_dir 目录(每个 .onnx 一个模型),程序自动维护
    index_file 索引骨架(models.toml),用户只需在索引中填写每个模型的
    id/name/description,AI 即可依据 description 主动选择模型。
    运行 `neobot init` 可随时重新扫描模型目录。
    """

    enabled: bool = field(
        default=True,
        metadata={"description": "是否启用本地视觉检测服务；关闭后 skill 不注册"},
    )
    models_dir: str = field(
        default="./data/vision_detect/models",
        metadata={"description": "ONNX 模型文件目录（相对 data 目录）"},
    )
    index_file: str = field(
        default="./data/vision_detect/models.toml",
        metadata={"description": "模型索引文件（相对 data 目录，程序自动生成骨架）"},
    )
    default_conf: float = field(
        default=0.35,
        metadata={"description": "默认置信度阈值（0.0-1.0），仅作为 models.toml [library] 段首次生成的初始值；运行期以 models.toml 中的配置为准"},
    )
    default_iou: float = field(
        default=0.45,
        metadata={"description": "默认 NMS IoU 阈值，仅作为 models.toml [library] 段首次生成的初始值"},
    )
    imgsz: int = field(
        default=0,
        metadata={"description": "默认输入尺寸（0 = 从模型自动推断），仅作为 models.toml [library] 段首次生成的初始值"},
    )
    auto_refresh: bool = field(
        default=True,
        metadata={"description": "每次调用前检查模型目录/索引变化并热重载"},
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
    file_operation: AgentFileOperation = field(default_factory=AgentFileOperation)
    self_healing: AgentSelfHeal = field(default_factory=AgentSelfHeal)
    vision_detect: VisionDetect = field(default_factory=VisionDetect)
    tools: AgentToolsConfig = field(default_factory=AgentToolsConfig)


@dataclass
class WebSearchConfig:
    """联网搜索工具包配置。"""

    enabled: bool = field(
        default=True,
        metadata={"description": "是否启用联网搜索工具包；关闭后搜索工具不会注册"},
    )
    preview_pages_limit: Optional[int] = field(
        default=30,
        metadata={"description": "单次搜索返回结果总数上限（含主查询+所有变体），默认 30"},
    )
    max_search_rounds: Optional[int] = field(
        default=5,
        metadata={"description": "单次会话最多搜索轮次，默认 5"},
    )
    variant_result_limit: Optional[int] = field(
        default=6,
        metadata={"description": "研究模式中每个变体查询返回的最大结果数，默认 6"},
    )


@dataclass
class BotConfig:
    """机器人主配置。"""

    version: str = field(
        default="0.6.0",
        metadata={"description": "配置文件版本（由程序维护，请勿手动修改）", "readonly": True},
    )
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
    standby: Standby = field(default_factory=Standby)
    scheduled_task: ScheduledTask = field(default_factory=ScheduledTask)
    agent: Agent = field(default_factory=Agent)
    web_search: WebSearchConfig = field(default_factory=WebSearchConfig)


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
        default=5.0,
        metadata={"description": "@ 提及时的回复延迟秒数；在此期间收集后续群消息后再生成回复"},
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
        default=60.0,
        metadata={
            "description": "群聊 agent 回复管线最长静默时间；超过后强制关闭管线。wait 工具等待时间不计入静默时间，0 表示禁用"
        },
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
    inject_member_archives: Optional[bool] = field(
        default=False,
        metadata={
            "description": "群聊提示词是否注入群成员的个人档案；默认 false（只注入群档案），"
            "群员档案由 agent 用 archive_crud__read_archive 按需读取"
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
    official_bot_reply_coefficient: Optional[float] = field(
        default=0.05,
        metadata={"description": "官方Bot回复概率系数，识别到消息发送者为官方Bot时，基础概率乘以此系数"},
    )
    private_chat_suspend_wait_seconds: Optional[int] = field(
        default=300,
        metadata={"description": "私聊回复后挂起等待秒数；超时无新消息则结束会话，默认300秒（5分钟）"},
    )
    private_chat_max_tokens: Optional[int] = field(
        default=50000,
        metadata={"description": "私聊会话最大token数；超过后重启聊天管线"},
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
    admin_accounts: List[str] = field(
        default_factory=list,
        metadata={"description": "超级管理员QQ号列表，用于接收余额不足等系统通知；仅可通过配置增减"},
    )
    sub_admin_accounts: List[str] = field(
        default_factory=list,
        metadata={"description": "次级管理员QQ号列表；超级管理员可通过 /add_admin、/del_admin 命令增删"},
    )
    balance_check_cooldown_seconds: Optional[int] = field(
        default=300,
        metadata={"description": "余额检查冷却秒数；每次检查后至少间隔此秒数才会再次查询；默认300秒"},
    )


@dataclass
class EnhancedBotConfig(BotConfig):
    """采用增强聊天配置结构的机器人配置。"""

    chat: EnhancedChat = field(default_factory=EnhancedChat)


Chat = EnhancedChat
BotConfig = EnhancedBotConfig
