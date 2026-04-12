"""配置模型 — 统一导出"""

from neobot_app.config.schemas.bot import (
    Bot,
    BotConfig,
    Chat,
    KeyWordRule,
    ModelPricing,
    ModelRegistration,
    ModelSettings,
    Models,
    Message,
    Plugins,
    TTS,
    TTSReferenceVoice,
)
from neobot_app.config.schemas.env import ApiPlatformConfig, EnvConfig

__all__ = [
    "Bot",
    "BotConfig",
    "Chat",
    "ApiPlatformConfig",
    "EnvConfig",
    "KeyWordRule",
    "Message",
    "ModelPricing",
    "ModelRegistration",
    "ModelSettings",
    "Models",
    "Plugins",
    "TTS",
    "TTSReferenceVoice",
]
