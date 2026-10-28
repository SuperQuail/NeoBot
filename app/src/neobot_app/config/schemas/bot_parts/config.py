"""主配置段：BotConfig / EnhancedBotConfig 汇总各域配置。"""

from dataclasses import dataclass, field

from .adapter import Adapter
from .agent import Agent
from .billing import Billing
from .chat import EnhancedChat
from .core import Bot, Chat
from .integrations import ASR, Bilibili, WebSearchConfig
from .media import AvatarsConfig
from .model_registry import AgentModelRouting, Models
from .runtime import Debug, FileServer, Message, Plugins, ScheduledTask, Standby, Willing
from .tts import TTS


@dataclass
class BotConfig:
    """机器人主配置。"""

    version: str = field(
        default="0.9.0",
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
    billing: Billing = field(default_factory=Billing)
    avatars: AvatarsConfig = field(default_factory=AvatarsConfig)
    bilibili: Bilibili = field(default_factory=Bilibili)
    asr: ASR = field(default_factory=ASR)


@dataclass
class EnhancedBotConfig(BotConfig):
    """采用增强聊天配置结构的机器人配置。"""

    chat: EnhancedChat = field(default_factory=EnhancedChat)
