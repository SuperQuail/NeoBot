"""模型定义段：计费、运行参数、DeepSeek 思考参数与模型条目。"""

from dataclasses import dataclass, field
from typing import Any, Dict, List

from .core import normalize_model_key


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
    # ── 可选参数（spec(4) Part B）：只有列入 enabled_params 才会下发到请求体 ──
    # 值一律原地保留：未列入 enabled_params 只是不下发，重新加入即恢复。
    # hidden=True：不出现在通用表单里，改由模型参数区（kind=model_params）按需增删。
    frequency_penalty: float = field(
        default=0.0,
        metadata={"description": "频率惩罚", "hidden": True},
    )
    presence_penalty: float = field(
        default=0.0,
        metadata={"description": "存在惩罚", "hidden": True},
    )
    image_api: str = field(
        default="auto",
        metadata={
            "description": "生图接口形态（仅生图模型使用）：auto 有参考图时走 /images/edits（失败回退 "
            "/images/generations），edits 始终走 /images/edits（multipart），generations 始终走 "
            "/images/generations（参考图作为 JSON 字段传递）",
            "options": ["auto", "edits", "generations"],
            "options_strict": True,
            "hidden": True,
        },
    )
    image_reference_param: str = field(
        default="image",
        metadata={
            "description": "generations 模式下参考图的 JSON 字段名（不同中转站可能是 image / images / "
            "image_url / image_urls / input_image）",
            "hidden": True,
        },
    )
    enabled_params: List[str] = field(
        default_factory=list,
        metadata={
            "description": "本模型启用的可选参数名清单（spec(4) Part B）：只有列在这里的可选参数才会"
            "进入请求体；未列入的参数值原样保留在配置里，重新加入即恢复。可用名字见参数目录"
            "（频率惩罚 / 存在惩罚 / 生图接口形态 / 参考图字段名 / DeepSeek 思考参数）",
            "hidden": True,
        },
    )
    extra_body: Dict[str, Any] = field(
        default_factory=dict,
        metadata={
            "description": "自定义请求体参数（key = 参数名，value 原样并入请求体）：聊天模型并入聊天"
            "请求体，生图模型并入生图 payload。键名不得以双下划线（__）开头（内部命名空间）",
            "hidden": True,
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
            "hidden": True,
        },
    )
    deepseek_reasoning_effort: str = field(
        default="high",
        metadata={
            "description": "思考强度控制（OpenAI 样式）：low/medium 映射为 high，xhigh 映射为 max，可选 high（默认）或 max",
            "options": ["high", "max"],
            "options_strict": True,
            "hidden": True,
        },
    )
    deepseek_random_thinking_probability: float = field(
        default=0.6,
        metadata={
            "description": "随机思考开启概率，范围 0.0 到 1.0，仅在思考模式为 random 时生效",
            "hidden": True,
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
    """模型库中的一个模型。

    三个名字必须分清（这是最容易出错的地方）：

    - ``model_ref``：**本机引用名**，只是调用方（``[models.assignments]``）用来指向本条目
      的唯一标识，**永远不会发给供应商**；
    - ``display_name``：面板/日志里**给人看的名字**（也作为 Agent 选择生图模型的参考）；
    - ``model_name``：**真正发给供应商的模型标识**，写进请求体 ``{"model": ...}``。

    换句话说：``model_ref`` 是「我们怎么称呼它」，``model_name`` 是「供应商怎么称呼它」。
    改 ``model_ref`` 不影响调用，改 ``model_name`` 才会改变实际调用的模型。
    """

    model_ref: str = field(
        default="",
        metadata={
            "description": "本机引用名（调用方在 [models.assignments] 里引用它）："
            "只能包含字母、数字、下划线、点和短横线；**不会发给供应商**。"
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
    display_name: str = field(
        default="",
        metadata={
            "description": "模型显示名：面板列表、启动日志与 Agent 选择生图模型时使用的名字；"
            "留空时按模型类型自动生成。它只是给人看的标签，**不影响实际调用**"
        },
    )
    provider: str = field(
        default="DeepSeek",
        metadata={"description": "模型供应商"},
    )
    model_name: str = field(
        default="deepseek-chat",
        metadata={
            "description": "模型名：**真正发给供应商的模型标识**（请求体 model 字段）。"
            "必须是供应商侧存在的名字，写错会在调用时报错"
        },
    )
    pricing: ModelPricing = field(default_factory=ModelPricing)
    settings: DeepSeekModelSettings = field(default_factory=DeepSeekModelSettings)
    native_vision: bool = field(
        default=False,
        metadata={
            "description": "该模型可直接接收图片块；model_type=vision 的图像识别模型无需配置"
            "（一律视为原生视觉）。主推理模型开启后，不可用或无法处理图片时"
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
    billing_script: str = field(
        default="",
        metadata={
            "description": "该模型使用的计价脚本名（对应 <数据目录>/Billing/<名字>.py）。"
            "留空 = 该模型走固定计费；多个模型可引用同一名字（脚本只加载一份）。"
            "需配合 [billing].enabled=true 生效"
        },
    )
    billing_config: Dict[str, Any] = field(
        default_factory=dict,
        metadata={
            "description": "传给计价脚本的参数表（脚本内通过 ctx[\"billing_config\"] 读取），"
            "例如按次计费脚本的 price_per_call = 0.01；同一脚本可被多个模型复用、各自定价"
        },
    )

    def __post_init__(self) -> None:
        self.model_ref = normalize_model_key(self.model_ref)
        self.model_type = normalize_model_type(self.model_type)
        # 图像识别模型天然具备视觉能力（原生视觉回退路由本就按"图片原样发送"处理），
        # 因此 model_type=vision 的模型无需用户手工配置 native_vision。
        if self.model_type == "vision":
            self.native_vision = True
        if not str(self.display_name or "").strip():
            self.display_name = MODEL_TYPE_LABELS.get(self.model_type, "模型")

    @property
    def type_label(self) -> str:
        return MODEL_TYPE_LABELS.get(self.model_type, self.model_type)

    @property
    def label(self) -> str:
        """展示用兜底标签：显示名 → 模型名 → 引用名。"""
        return self.display_name or self.model_name or self.model_ref


#: 兼容旧名称（历史配置与外部脚本可能仍引用 ModelRegistration）
ModelRegistration = ModelDefinition
