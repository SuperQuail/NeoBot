from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from neobot_chat.providers import (
    AnthropicProvider,
    DeepSeekOfficialProvider,
    OpenAIProvider,
    Provider,
)
from neobot_chat.schema.exceptions import ValidationError


@dataclass(frozen=True)
class ModelPricing:
    """模型价格信息。"""

    input_price_per_mtokens: float = 0.0
    output_price_per_mtokens: float = 0.0
    cache_hit_price_per_mtokens: float = 0.0
    billing_metric: str = ""


@dataclass(frozen=True)
class ModelSettings:
    """模型运行设置。"""

    temperature: float | None = None
    max_output_tokens: int | None = None
    timeout_seconds: float = 120.0
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    extra_body: dict[str, Any] = field(default_factory=dict)


def _normalize_provider_kind(provider_name: str) -> str:
    normalized = provider_name.strip().casefold().replace("-", "_")
    if normalized in {"anthropic"}:
        return "anthropic"
    if normalized in {"deepseek", "deepseek_offical", "deepseek_official"}:
        return "deepseek"
    if normalized in {"openai"}:
        return "openai"
    # 默认按 OpenAI 兼容接口处理，便于接入自定义平台代理。
    return "openai"


@dataclass(frozen=True)
class RegisteredModel:
    """已注册模型。"""

    name: str
    description: str
    provider_name: str
    model_name: str
    base_url: str
    api_key: str
    pricing: ModelPricing = field(default_factory=ModelPricing)
    settings: ModelSettings = field(default_factory=ModelSettings)

    @property
    def provider_kind(self) -> str:
        return _normalize_provider_kind(self.provider_name)

    def create_provider(self) -> Provider:
        """根据注册信息创建 Provider 实例。"""
        if not self.base_url:
            raise ValidationError(f"Model '{self.name}' is missing base_url")
        if not self.api_key:
            raise ValidationError(f"Model '{self.name}' is missing api_key")

        if self.provider_kind == "anthropic":
            return AnthropicProvider(
                api_key=self.api_key,
                model=self.model_name,
                base_url=self.base_url,
                max_tokens=self.settings.max_output_tokens or 4096,
                timeout=self.settings.timeout_seconds,
                temperature=self.settings.temperature,
                top_p=self.settings.top_p,
                extra_body=self.settings.extra_body,
            )

        if self.provider_kind == "deepseek":
            return DeepSeekOfficialProvider(
                api_key=self.api_key,
                model=self.model_name,
                base_url=self.base_url,
                timeout=self.settings.timeout_seconds,
                temperature=self.settings.temperature,
                max_tokens=self.settings.max_output_tokens,
                top_p=self.settings.top_p,
                frequency_penalty=self.settings.frequency_penalty,
                presence_penalty=self.settings.presence_penalty,
                extra_body=self.settings.extra_body,
            )

        return OpenAIProvider(
            api_key=self.api_key,
            model=self.model_name,
            base_url=self.base_url,
            timeout=self.settings.timeout_seconds,
            temperature=self.settings.temperature,
            max_tokens=self.settings.max_output_tokens,
            top_p=self.settings.top_p,
            frequency_penalty=self.settings.frequency_penalty,
            presence_penalty=self.settings.presence_penalty,
            extra_body=self.settings.extra_body,
        )


class ModelRegistry:
    """模型注册中心。"""

    def __init__(self) -> None:
        self._models: dict[str, RegisteredModel] = {}

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._models.keys())

    def clear(self) -> None:
        self._models.clear()

    def register(self, model: RegisteredModel, *, replace: bool = True) -> None:
        if not replace and model.name in self._models:
            raise ValidationError(f"Model '{model.name}' is already registered")
        self._models[model.name] = model

    def get(self, name: str) -> RegisteredModel:
        try:
            return self._models[name]
        except KeyError as exc:
            raise ValidationError(f"Model '{name}' is not registered") from exc

    def create_provider(self, name: str) -> Provider:
        return self.get(name).create_provider()

    def items(self) -> tuple[tuple[str, RegisteredModel], ...]:
        return tuple(self._models.items())


model_registry = ModelRegistry()


def get_model_registry() -> ModelRegistry:
    return model_registry


def register_model(model: RegisteredModel, *, replace: bool = True) -> None:
    model_registry.register(model, replace=replace)


def get_registered_model(name: str) -> RegisteredModel:
    return model_registry.get(name)


def create_provider(name: str) -> Provider:
    return model_registry.create_provider(name)
