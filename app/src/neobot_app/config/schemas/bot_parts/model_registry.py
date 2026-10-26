"""模型库段：出厂模型、调用方分配与 Agent 模型编号路由。"""

from dataclasses import dataclass, field
from typing import ClassVar, Dict, Iterator, List, Optional

from .models import DeepSeekModelSettings, ModelDefinition, ModelPricing, ModelSettings


def _default_primary_chat_model() -> "ModelDefinition":
    return ModelDefinition(
        # key 与真实模型名对齐：DeepSeek 侧只有 deepseek-flash，旧 key 里的 "v4-pro"
        # 是历史遗留（早期 model_name 确实叫 deepseek-v4-*），它既不存在的模型、
        # 又让「引用的 key」看起来像另一个模型。只有 flash，不再保留 pro 条目。
        model_ref="deepseek-flash",
        model_type="chat",
        display_name="主对话模型（Agent模型编号0，deepseek-flash max 推理）",
        provider="DeepSeek",
        model_name="deepseek-flash",
        native_vision=True,
        settings=DeepSeekModelSettings(
            temperature=1.0,
            max_output_tokens=200000,
            timeout_seconds=120.0,
            top_p=1.0,
            frequency_penalty=0.0,
            presence_penalty=0.0,
            deepseek_thinking_mode="enabled",
            deepseek_reasoning_effort="max",
            deepseek_random_thinking_probability=0.6,
        ),
        # DeepSeek 官方定价（元/百万 tokens，填**高峰价**）：
        # https://api-docs.deepseek.com/zh-cn/quick_start/pricing/
        # 空闲时段 = 高峰价 ×0.5，由 billing_script 折算 —— 所以这里填高峰价，
        # 填均价会让统计金额系统性偏小（模板顶部有同样的提醒）。
        pricing=ModelPricing(
            input_price_per_mtokens=2.0,
            output_price_per_mtokens=8.0,
            cache_hit_price_per_mtokens=0.04,
        ),
        billing_script="deepseek_peak_valley",
    )


def _default_agent_model_1() -> "ModelDefinition":
    return ModelDefinition(
        model_ref="deepseek-flash-max",
        model_type="chat",
        display_name="Agent模型编号1：deepseek-flash max 推理模式",
        provider="DeepSeek",
        model_name="deepseek-flash",
        native_vision=True,
        settings=DeepSeekModelSettings(
            temperature=1.0,
            max_output_tokens=200000,
            timeout_seconds=120.0,
            top_p=1.0,
            frequency_penalty=0.0,
            presence_penalty=0.0,
            deepseek_thinking_mode="enabled",
            deepseek_reasoning_effort="max",
            deepseek_random_thinking_probability=0.6,
        ),
        # DeepSeek 官方定价（元/百万 tokens，填**高峰价**）：
        # https://api-docs.deepseek.com/zh-cn/quick_start/pricing/
        # 空闲时段 = 高峰价 ×0.5，由 billing_script 折算 —— 所以这里填高峰价，
        # 填均价会让统计金额系统性偏小（模板顶部有同样的提醒）。
        pricing=ModelPricing(
            input_price_per_mtokens=2.0,
            output_price_per_mtokens=8.0,
            cache_hit_price_per_mtokens=0.04,
        ),
        billing_script="deepseek_peak_valley",
    )


def _default_agent_model_2() -> "ModelDefinition":
    return ModelDefinition(
        model_ref="deepseek-flash-high",
        model_type="chat",
        display_name="Agent模型编号2：deepseek-flash high 推理模式",
        provider="DeepSeek",
        model_name="deepseek-flash",
        native_vision=True,
        settings=DeepSeekModelSettings(
            temperature=1.0,
            max_output_tokens=200000,
            timeout_seconds=120.0,
            top_p=1.0,
            frequency_penalty=0.0,
            presence_penalty=0.0,
            deepseek_thinking_mode="enabled",
            deepseek_reasoning_effort="high",
            deepseek_random_thinking_probability=0.6,
        ),
        # DeepSeek 官方定价（元/百万 tokens，填**高峰价**）：
        # https://api-docs.deepseek.com/zh-cn/quick_start/pricing/
        # 空闲时段 = 高峰价 ×0.5，由 billing_script 折算 —— 所以这里填高峰价，
        # 填均价会让统计金额系统性偏小（模板顶部有同样的提醒）。
        pricing=ModelPricing(
            input_price_per_mtokens=2.0,
            output_price_per_mtokens=8.0,
            cache_hit_price_per_mtokens=0.04,
        ),
        billing_script="deepseek_peak_valley",
    )


def _default_agent_model_3() -> "ModelDefinition":
    return ModelDefinition(
        model_ref="deepseek-flash-off",
        model_type="chat",
        display_name="Agent模型编号3：deepseek-flash 非推理模式",
        provider="DeepSeek",
        model_name="deepseek-flash",
        native_vision=True,
        settings=DeepSeekModelSettings(
            temperature=1.0,
            max_output_tokens=200000,
            timeout_seconds=120.0,
            top_p=1.0,
            frequency_penalty=0.0,
            presence_penalty=0.0,
            deepseek_thinking_mode="disabled",
            deepseek_reasoning_effort="high",
            deepseek_random_thinking_probability=0.6,
        ),
        # DeepSeek 官方定价（元/百万 tokens，填**高峰价**）：
        # https://api-docs.deepseek.com/zh-cn/quick_start/pricing/
        # 空闲时段 = 高峰价 ×0.5，由 billing_script 折算 —— 所以这里填高峰价，
        # 填均价会让统计金额系统性偏小（模板顶部有同样的提醒）。
        pricing=ModelPricing(
            input_price_per_mtokens=2.0,
            output_price_per_mtokens=8.0,
            cache_hit_price_per_mtokens=0.04,
        ),
        billing_script="deepseek_peak_valley",
    )


def _default_tts_model() -> "ModelDefinition":
    return ModelDefinition(
        model_ref="cosyvoice2",
        model_type="tts",
        display_name="语音模型",
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


def _default_model_library() -> "List[ModelDefinition]":
    """默认模型库：模型单独存储，调用方只引用 key。

    默认只带 DeepSeek 对话模型与语音模型，理由：
    - **不预置生图模型**：原先的 `flux-schnell` 指向平台侧并不存在的模型名，
      留着只会让新用户以为「绘图能用」，实际一调就报模型不存在；
    - **不预置独立视觉模型**：默认视觉模型就是 deepseek-flash（high 推理，见
      `ModelAssignments.vision_model`），它是真实可用的模型，用户少申请一个平台 Key。
    """
    return [
        _default_primary_chat_model(),
        _default_agent_model_1(),
        _default_agent_model_2(),
        _default_agent_model_3(),
        _default_tts_model(),
    ]


@dataclass
class ModelAssignments:
    """各调用方引用的模型 key（在模型库 [models.registry] 中定义）。"""

    primary_chat_model: str = field(
        default="deepseek-flash",
        metadata={"description": "Agent模型编号0（主对话模型）引用的模型 key"},
    )
    agent_model_1: str = field(
        default="deepseek-flash-max",
        metadata={"description": "Agent模型编号1引用的模型 key"},
    )
    agent_model_2: str = field(
        default="deepseek-flash-high",
        metadata={"description": "Agent模型编号2引用的模型 key"},
    )
    agent_model_3: str = field(
        default="deepseek-flash-off",
        metadata={"description": "Agent模型编号3引用的模型 key"},
    )
    vision_model: str = field(
        default="deepseek-flash-high",
        metadata={
            "description": "图像识别模型引用的模型 key；默认复用 deepseek-flash（high 推理）"
            "——它是真实可用的模型，避免新用户为了看图再申请一个平台 Key"
        },
    )
    tts_model: str = field(
        default="cosyvoice2",
        metadata={"description": "语音模型引用的模型 key"},
    )
    creator_image_models: List[str] = field(
        default_factory=list,
        metadata={
            "description": "创作者Agent生图模型列表（引用 key）；配置多个时由 Agent 按描述自行选择。"
            "**默认为空**：出厂不预置生图模型，需要 AI 绘图时再在模型库里加一个真实可用的生图模型"
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
        metadata={"description": "各调用方引用的模型（值为模型条目里的 model_ref 引用名）"},
    )

    def by_ref(self) -> Dict[str, ModelDefinition]:
        """引用名 -> 模型条目。引用名只是本机标识，不会发给供应商。"""
        return {item.model_ref: item for item in self.registry if item.model_ref}

    def get(self, model_ref: str) -> Optional[ModelDefinition]:
        return self.by_ref().get(str(model_ref or "").strip())

    def iter_definitions(self) -> Iterator[tuple[str, ModelDefinition]]:
        """遍历模型库：(引用名, 模型定义)。"""
        for item in self.registry:
            if item.model_ref:
                yield item.model_ref, item

    def iter_role_models(self) -> Iterator[tuple[str, ModelDefinition]]:
        """遍历调用方实际引用的模型：(角色名, 模型定义)；引用名缺失时跳过。"""
        library = self.by_ref()
        for role, model_ref in self.assignments.items():
            definition = library.get(model_ref)
            if definition is not None:
                yield role, definition

    def iter_registrations(self) -> Iterator[tuple[str, ModelDefinition]]:
        """兼容旧接口：等价于 iter_role_models()。"""
        return self.iter_role_models()

    def missing_assignment_refs(self) -> List[str]:
        """返回引用了但模型库里不存在的引用名（model_ref）。"""
        library = self.by_ref()
        return sorted(
            {
                model_ref
                for _role, model_ref in self.assignments.items()
                if model_ref not in library
            }
        )

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
        default=1,
        metadata={
            "description": "自修复 Agent 使用的模型编号，0-3；默认 1（强推理模型）——"
            "自修复要读日志、定位缺陷并改代码，弱模型会反复试错"
        },
    )
