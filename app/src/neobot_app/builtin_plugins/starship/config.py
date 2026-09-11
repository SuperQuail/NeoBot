"""星舰插件配置（plugins_data/starship/config.toml）。"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

_ROUTE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")

#: 画质档位
QUALITY_LEVELS = ("low", "medium", "high")


class StarshipConfig(BaseModel):
    """星舰游戏配置。"""

    #: 游戏挂载路径（相对面板根，例如 game -> /game/）
    route: str = "game"
    #: 面板侧栏与游戏内 HUD 显示的名字
    title: str = "NeoBot 星舰"
    #: 是否在面板侧栏显示入口
    show_in_sidebar: bool = True
    #: 默认画质（玩家在游戏内还可以自己调，存在浏览器本地）
    default_quality: str = "medium"
    #: 是否允许进入小游戏
    allow_minigames: bool = True
    #: 排行榜返回条数
    leaderboard_size: int = Field(default=20, ge=3, le=100)
    #: 随机跃迁间隔（分钟）；0 表示关闭自动跃迁
    jump_interval_minutes: int = Field(default=6, ge=0, le=120)
    #: 是否启用 WebAudio 合成音效
    enable_audio: bool = True

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
