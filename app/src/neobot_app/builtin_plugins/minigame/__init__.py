"""NeoBot 官方小游戏插件（spec(5) §1.4-§1.8、§4.4-§4.8 / R12-R32）。

核心思路（R12）：**不对游戏的逻辑路径做约束**。程序只提供必须持久化 / 必须
限流的能力 —— 数据表、随机结果、每日上限、计分记账、头像、渲染；玩法与判定
按需调用模型，突出 AI 交互互动，而不是把规则写死在程序里。

两条入口（R15）：

1. **命令入口**：/mg（别名 /游戏）—— 格式完全正确时直接执行并回图；格式错误、
   缺参数、或用户只以自然语言表达意图时置 ctx.sync_reply = True，把「事实 +
   提示词」交给主管线，由模型组织回复（与 /sleep 同一机制，不新造管线）。
2. **agent 入口**：插件工具 `minigame__bottle_write` 等（框架自动加
   {plugin}__ 前缀）与本模块给模型看的说明文本。

另有**关键词 / 意图入口**（R14 / D11）：插件消息处理器承接「漂流瓶」「签到」
「抽签」等关键词，进入 agent 交互路径（agent 主动开场），**不直接执行游戏动作**；
未命中关键词时完全不触发。

另有**对外能力**（R33）：其它插件通过
ctx.require_plugin("minigame").call("points.add", ...) 读写本插件的统一积分账户
（points.get / points.add / points.rank / points.describe，见文件末尾）。

停用 / 卸载时命令随 ctx.app_commands.unregister_all() 摘除、工具由宿主随
插件技能注销；与本体或其它插件重名时按 spec(4) D21 自动变 minigame__<name>。
"""

from __future__ import annotations

import random as random
import re as re
import time as time
from typing import Any as Any
from typing import Mapping as Mapping
from neobot_app.message.fast_reply_keywords import register_reply_trigger_keywords as register_reply_trigger_keywords
from neobot_app.message.fast_reply_keywords import unregister_reply_trigger_keywords as unregister_reply_trigger_keywords
from neobot_modloader import Plugin as Plugin
from neobot_modloader import PluginDatabase as PluginDatabase
from neobot_modloader.message import Message as Message
from .avatars import AvatarProvider as AvatarProvider
from .config import ALL_GAME_IDS as ALL_GAME_IDS
from .config import MinigameConfig as MinigameConfig
from .games import Game as Game
from .games import GameRequest as GameRequest
from .games import build_games as build_games
from .games import find_game as find_game
from .games.checkin import READONLY_NOTICE as READONLY_NOTICE
from .games.checkin import format_points_text as format_points_text
from .migrations import DATABASE_FILENAME as DATABASE_FILENAME
from .migrations import build_migrations as build_migrations
from .models import Base as Base
from .service import MinigameService as MinigameService
from .themes import register_minigame_themes as register_minigame_themes
from .themes import resolve_theme as resolve_theme
from .themes import unregister_minigame_themes as unregister_minigame_themes

from .parts.constants import (
    TOOL_PREFIX,
    KEYWORDS,
    INTERACTION_TTL_SECONDS,
    RANK_PAGE_SIZE,
    POINTS_API_NAME,
    POINTS_API_VERSION,
    POINTS_RANK_MAX_PAGE_SIZE,
    MENU_FOOTER,
    PACKAGE_BASE as PACKAGE_BASE,
    _MG_COMMAND_RE as _MG_COMMAND_RE,
)
from .parts.registration import (
    plugin,
    create_database,
    database,
    skill_name_for as skill_name_for,
    preactivate_for as preactivate_for,
    _declare_tool_packages as _declare_tool_packages,
)
from .parts.utils import _sender_name as _sender_name, _event_text as _event_text
from .parts.plugin_state import _PluginStateMixin
from .parts.plugin_cards import _PluginCardsMixin
from .parts.plugin_commands import _PluginCommandsMixin
from .parts.plugin_points import _PluginPointsMixin
from .parts.plugin_help import _PluginHelpMixin
from .parts.plugin_keywords import _PluginKeywordsMixin
from .parts.hooks import bind_runtime as bind_runtime


class MinigamePlugin(
    _PluginStateMixin,
    _PluginCardsMixin,
    _PluginCommandsMixin,
    _PluginPointsMixin,
    _PluginHelpMixin,
    _PluginKeywordsMixin,
):
    """小游戏插件的运行时状态。"""

    NEED_IDENTITY_HINT = (
        "无法确定是哪个用户（工具调用没有携带会话信息）。"
        "请让用户先发一条消息（例如 /mg 积分 或直接说「签到」）再调用本工具，"
        "或者把用户的 QQ 号作为 user_id 参数传进来。"
    )

    def __init__(self) -> None:
        self.ctx: Any = None
        self.config: MinigameConfig | None = None
        self.service: MinigameService | None = None
        self.avatars: AvatarProvider | None = None
        self.games: list[Game] = []
        self.chengyu_sessions: dict[str, Any] = {}
        self._games_by_id: dict[str, Game] = {}
        self._latest: dict[str, Any] | None = None
        self._closed_sessions: list[dict[str, Any]] = []
        self._keyword_hits: list[str] = []
        self._rng = random.Random()
        # 卡片主题用独立的随机源：不消耗玩法本身的随机数（签到分数 / 抽签档位 / 接龙目标）
        self._theme_rng = random.Random()
        self._theme_memo: dict[str, str] = {}
        self._monotonic = time.monotonic
        self._logger: Any = None


_instance = MinigamePlugin()


def _runtime() -> MinigamePlugin:
    return _instance


bind_runtime(_runtime)


__all__ = [
    "ALL_GAME_IDS",
    "INTERACTION_TTL_SECONDS",
    "KEYWORDS",
    "MENU_FOOTER",
    "MinigamePlugin",
    "POINTS_API_NAME",
    "POINTS_API_VERSION",
    "POINTS_RANK_MAX_PAGE_SIZE",
    "RANK_PAGE_SIZE",
    "TOOL_PREFIX",
    "create_database",
    "database",
    "plugin",
]
