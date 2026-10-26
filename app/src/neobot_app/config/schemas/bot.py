"""配置 schema 总入口：定义按域拆到 bot_parts/，这里原样 re-export。

neobot_app.config.schemas.bot 是配置 schema 的公开导入点；拆分只移动定义，
字段、默认值与元数据保持不变。
"""

from .bot_parts.adapter import Adapter
from .bot_parts.agent import (
    AgentSystem,
    AgentProblemSolver,
    AgentBrowser,
    SandboxMaintenance,
    AgentSandbox,
    AgentOneBot,
    AgentSkill,
    AgentFileOperation,
    AgentSelfHeal,
    AgentToolsConfig,
    Agent,
)
from .bot_parts.billing import Billing
from .bot_parts.chat import EnhancedChat
from .bot_parts.config import EnhancedBotConfig
from .bot_parts.core import normalize_model_key, KeyWordRule, Bot
from .bot_parts.integrations import WebSearchConfig, Bilibili, ASR
from .bot_parts.media import (
    GalleryConfig,
    CreatorEmojiConfig,
    BackgroundDrawConfig,
    ImageCreationConfig,
    VisionDetect,
    AvatarsConfig,
)
from .bot_parts.memory import (
    AgentMemoryTrigger,
    AgentMemoryArchive,
    AgentMemoryFavorability,
    AgentMemoryItemArchive,
    AgentMemory,
)
from .bot_parts.model_registry import ModelAssignments, Models, AgentModelRouting
from .bot_parts.models import (
    ModelPricing,
    ModelSettings,
    DeepSeekModelSettings,
    MODEL_TYPE_LABELS,
    normalize_model_type,
    ModelDefinition,
    ModelRegistration,
)
from .bot_parts.runtime import Willing, Plugins, Message, FileServer, Debug, Standby, ScheduledTask
from .bot_parts.tts import TTSReferenceVoice, HuoShanTTS, TTS
# 兼容 config/migrations.py 的私有导入（拆分前就在本模块）
from .bot_parts.model_registry import _default_model_library as _default_model_library

#: 历史公开名：Chat 指增强聊天配置，BotConfig 指增强主配置（与拆分前一致）
Chat = EnhancedChat
BotConfig = EnhancedBotConfig

__all__ = [
    "ASR",
    "Adapter",
    "Agent",
    "AgentBrowser",
    "AgentFileOperation",
    "AgentMemory",
    "AgentMemoryArchive",
    "AgentMemoryFavorability",
    "AgentMemoryItemArchive",
    "AgentMemoryTrigger",
    "AgentModelRouting",
    "AgentOneBot",
    "AgentProblemSolver",
    "AgentSandbox",
    "AgentSelfHeal",
    "AgentSkill",
    "AgentSystem",
    "AgentToolsConfig",
    "AvatarsConfig",
    "BackgroundDrawConfig",
    "Bilibili",
    "Billing",
    "Bot",
    "BotConfig",
    "Chat",
    "CreatorEmojiConfig",
    "Debug",
    "DeepSeekModelSettings",
    "EnhancedBotConfig",
    "EnhancedChat",
    "FileServer",
    "GalleryConfig",
    "HuoShanTTS",
    "ImageCreationConfig",
    "KeyWordRule",
    "MODEL_TYPE_LABELS",
    "Message",
    "ModelAssignments",
    "ModelDefinition",
    "ModelPricing",
    "ModelRegistration",
    "ModelSettings",
    "Models",
    "Plugins",
    "SandboxMaintenance",
    "ScheduledTask",
    "Standby",
    "TTS",
    "TTSReferenceVoice",
    "VisionDetect",
    "WebSearchConfig",
    "Willing",
    "normalize_model_key",
    "normalize_model_type",
]
