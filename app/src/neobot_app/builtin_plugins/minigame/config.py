"""小游戏插件配置模型（spec(5) §4.4）。

配置保存在插件数据目录 plugins_data/minigame/config.toml（由 PluginRuntime 注入），
这里的默认值与 plugin.toml 的 [config] 打包默认值必须一致（有测试守住）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from .themes import KNOWN_THEME_IDS, THEME_MODES, default_theme

#: 全部内置玩法 id（也是 enabled_games 的默认值）
ALL_GAME_IDS: tuple[str, ...] = ("bottle", "chengyu", "checkin", "fortune")


class MinigameConfig(BaseModel):
    """小游戏运行配置（plugins_data/minigame/config.toml）。"""

    enabled_games: list[str] = Field(
        default_factory=lambda: list(ALL_GAME_IDS),
        description="启用的玩法 id 列表（bottle / chengyu / checkin / fortune）；去掉某项即整体下线该玩法。",
    )
    bottle_pool_max: int = Field(
        default=1000,
        ge=1,
        le=1_000_000,
        description="漂流瓶池上限：池满时随机挑一条既有待捞瓶转 expired 归档（不按时间、不删除）。",
    )
    bottle_content_max_chars: int = Field(
        default=500,
        ge=1,
        le=10_000,
        description="漂流瓶正文长度上限（去空白后 1 到该值）。",
    )
    bottle_show_sender_id: bool = Field(
        default=True,
        # [WIP · 尚未接线] 目前普通瓶一律显示 QQ 号，本项读得到但不生效；
        # 后续开发计划见 TODO/待办事项.md「WIP 与后续计划」。
        description="[WIP · 尚未接线] 普通（非匿名）发瓶卡片是否显示发送者 QQ 号；当前不生效。",
    )
    bottle_avatar_cache_days: int = Field(
        default=7,
        ge=0,
        le=365,
        description="漂流瓶头像的本体缓存天数（仅作展示提示；头像统一取自本体 AvatarStore）。",
    )
    checkin_score_min: int = Field(
        default=1,
        ge=0,
        le=100_000,
        description="每日签到随机积分的下限。",
    )
    checkin_score_max: int = Field(
        default=10,
        ge=0,
        le=100_000,
        description="每日签到随机积分的上限。",
    )
    checkin_streak_bonus: int = Field(
        default=1,
        ge=0,
        le=1000,
        description="连续签到每天的附加积分。",
    )
    checkin_streak_bonus_cap: int = Field(
        default=5,
        ge=0,
        le=1000,
        description="连续签到附加积分的上限。",
    )
    chengyu_target_min: int = Field(
        default=3,
        ge=1,
        le=100,
        description="成语接龙目标条数下限（胜利条件 N）。",
    )
    chengyu_target_max: int = Field(
        default=10,
        ge=1,
        le=100,
        description="成语接龙目标条数上限。",
    )
    chengyu_max_steps: int = Field(
        default=10,
        ge=1,
        le=1000,
        description="单局成语接龙最多步数（用满即结束本局）。",
    )
    chengyu_step_timeout_seconds: int = Field(
        default=60,
        ge=1,
        le=86_400,
        description="成语接龙每条提交的时限（秒）。",
    )
    fortune_include_bad_luck: bool = Field(
        default=False,
        description="抽签是否包含凶兆档位（小凶 / 凶）。",
    )
    record_keep_days: int = Field(
        default=30,
        ge=1,
        le=3650,
        description="战绩流水（mg_record）保留天数。",
    )
    theme_mode: str = Field(
        default="random",
        description=(
            "卡片主题模式：random = 每张卡片按该玩法的候选主题池随机；"
            "fixed = 固定使用 theme（留空则用该玩法的默认主题）。"
        ),
    )
    theme: str = Field(
        default="",
        description=(
            "theme_mode = fixed 时使用的主题名（minecraft / bottle / fortune / "
            "chengyu / checkin / game / default）；留空表示各玩法用自己的默认主题。"
        ),
    )

    @field_validator("enabled_games")
    @classmethod
    def _normalize_enabled_games(cls, value: list[str]) -> list[str]:
        """去重保序；非法 id 直接剔除（配置写错不该让插件起不来）。"""
        seen: list[str] = []
        for item in value or []:
            name = str(item).strip()
            if name and name in ALL_GAME_IDS and name not in seen:
                seen.append(name)
        return seen

    @field_validator("theme_mode")
    @classmethod
    def _normalize_theme_mode(cls, value: str) -> str:
        """未知模式直接报错（避免「写错了但看起来生效了」）。"""
        mode = str(value or "random").strip().lower()
        if mode not in THEME_MODES:
            raise ValueError(
                "theme_mode 只能是 random 或 fixed，收到：" + str(value)
            )
        return mode

    @field_validator("theme")
    @classmethod
    def _normalize_theme(cls, value: str) -> str:
        """未知主题名直接报错，并列出可用主题。"""
        name = str(value or "").strip().lower()
        if name and name not in KNOWN_THEME_IDS:
            raise ValueError(
                "未知的卡片主题："
                + str(value)
                + "（可用："
                + " / ".join(KNOWN_THEME_IDS)
                + "）"
            )
        return name

    @field_validator("chengyu_target_max")
    @classmethod
    def _target_range(cls, value: int, info) -> int:
        lower = info.data.get("chengyu_target_min")
        if lower is not None and int(value) < int(lower):
            raise ValueError("chengyu_target_max 不能小于 chengyu_target_min")
        return int(value)

    @field_validator("checkin_score_max")
    @classmethod
    def _score_range(cls, value: int, info) -> int:
        lower = info.data.get("checkin_score_min")
        if lower is not None and int(value) < int(lower):
            raise ValueError("checkin_score_max 不能小于 checkin_score_min")
        return int(value)

    @property
    def enabled_game_ids(self) -> tuple[str, ...]:
        """按启用顺序返回玩法 id。"""
        return tuple(self.enabled_games)

    def default_theme_for(self, game_id: str) -> str:
        """fixed 模式且 theme 留空时，该玩法使用的默认主题。"""
        return str(self.theme or default_theme(game_id))


__all__ = ["ALL_GAME_IDS", "KNOWN_THEME_IDS", "MinigameConfig", "THEME_MODES"]
