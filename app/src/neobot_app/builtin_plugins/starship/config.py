"""星舰插件配置（plugins_data/starship/config.toml）。

配置与本体 config.toml 解耦：面板「插件 → starship → 配置」编辑的是插件数据目录
下的这个文件；插件自带 plugin.toml 的 [config] 提供打包默认值与字段说明注释。
是否启用星舰插件不是配置项（记录在 plugin_state.json）。
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

_ROUTE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")

#: 画质档位
QUALITY_LEVELS = ("low", "medium", "high")


class StarshipConfig(BaseModel):
    """星舰游戏配置。"""

    route: str = Field(
        default="game",
        description="游戏挂载路径（面板根路径下的单段路径），默认 /game/。",
    )
    title: str = Field(
        default="NeoBot 星舰",
        description="面板侧栏入口与游戏引导页显示的名字。",
    )
    show_in_sidebar: bool = Field(
        default=True,
        description="是否在网页面板侧栏显示星舰入口。",
    )
    default_quality: str = Field(
        default="medium",
        description="默认画质档位：low（节能）/ medium（标准）/ high（高画质）。玩家可在游戏内覆盖。",
    )
    allow_minigames: bool = Field(
        default=True,
        description="是否允许进入小游戏（舱外炮塔、损管抢修）。",
    )
    leaderboard_size: int = Field(
        default=20,
        ge=3,
        le=100,
        description="排行榜接口默认返回的条数。",
    )
    jump_interval_minutes: int = Field(
        default=6,
        ge=0,
        le=120,
        description="随机跃迁间隔（分钟），0 表示关闭自动跃迁（仍可在星图导航台手动跃迁）。",
    )
    enable_audio: bool = Field(
        default=True,
        description="是否启用 WebAudio 实时合成音效（脚步声、跃迁、告警、点唱机等）。",
    )

    @field_validator("route")
    @classmethod
    def _validate_route(cls, value: str) -> str:
        normalized = str(value or "").strip().strip("/")
        if not normalized:
            raise ValueError("starship.route 不能为空")
        if not _ROUTE_RE.match(normalized):
            raise ValueError(
                "starship.route 只能包含字母、数字、点、下划线与连字符（单段路径）"
            )
        return normalized

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        normalized = str(value or "").strip()
        return normalized or "NeoBot 星舰"

    @field_validator("default_quality")
    @classmethod
    def _validate_quality(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in QUALITY_LEVELS:
            raise ValueError(f"starship.default_quality 必须是 {', '.join(QUALITY_LEVELS)} 之一")
        return normalized

    @property
    def prefix(self) -> str:
        """带前导斜杠的挂载路径（不含面板 base_path）。"""
        return f"/{self.route}"
