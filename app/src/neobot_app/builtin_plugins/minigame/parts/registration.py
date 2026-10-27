"""插件对象、独立数据库、工具包与技能名辅助。"""

from __future__ import annotations

from neobot_modloader import Plugin
from neobot_modloader import PluginDatabase
from ..config import ALL_GAME_IDS
from ..config import MinigameConfig
from ..games import build_games
from ..migrations import DATABASE_FILENAME
from ..migrations import build_migrations
from ..models import Base

from .constants import PACKAGE_BASE


plugin = Plugin(
    "minigame",
    version="1.0.0",
    description="NeoBot 官方小游戏：漂流瓶 / 成语接龙 / 签到与积分 / 抽签（AI 交互型）",
    author="NeoBot",
    config=MinigameConfig,
    dependencies=(),
    hot_reload=True,
    config_hot_reload=True,
)

def create_database(filename: str = DATABASE_FILENAME) -> PluginDatabase:
    """构造本插件的独立数据库对象（测试可用它建临时库，与下面的注册实例互不影响）。"""
    return PluginDatabase(
        "minigame",
        "main",
        filename=filename,
        metadata=Base.metadata,
        migrations=build_migrations(),
    )

#: 插件独立库（plugins_data/minigame/databases/minigame.db），随插件加载自动 bind + 迁移
database = plugin.sqlite_database(
    "main",
    filename=DATABASE_FILENAME,
    metadata=Base.metadata,
    migrations=build_migrations(),
)

def skill_name_for(package: str) -> str:
    """工具包对应的技能名（SkillManager 里的名字，可与 skills__load_tools 一起用）。"""
    return f"{plugin.name}_{package}"

def preactivate_for(game_id: str) -> tuple[str, ...]:
    """某个玩法要预激活的技能包：玩法包 + 通用包。"""
    packages: list[str] = []
    if str(game_id) in ALL_GAME_IDS:
        packages.append(str(game_id))
    packages.append(PACKAGE_BASE)
    return tuple(skill_name_for(item) for item in packages)

def _declare_tool_packages() -> None:
    """声明工具包：description 进技能索引，instructions 是给模型看的玩法说明（R15）。

    一个插件拆成多个**可独立加载**的技能包（minigame_bottle 等），工具最终名仍是
    minigame__<tool>；命中某个玩法时可以只预激活那个包，而不是整套工具。
    """
    for game in build_games():
        plugin.tool_package(
            game.id,
            description=f"{game.name}：{game.summary}",
            instructions=game.describe(),
        )
    plugin.tool_package(
        PACKAGE_BASE,
        description="小游戏通用：查规则 / 查积分",
        instructions=(
            "小游戏通用工具：\n"
            "- minigame__help(game)：查看某个玩法的规则与边界"
            "（bottle / chengyu / checkin / fortune，也接受中文名）\n"
            "- minigame__points(user_id?)：查看积分与连续签到天数"
            "（只读，你不能加减积分；积分由玩法和其它插件产生）\n"
            "各玩法的完整说明在对应技能包里：minigame_bottle / minigame_chengyu / "
            "minigame_checkin / minigame_fortune。"
        ),
    )


_declare_tool_packages()
