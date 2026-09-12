"""小游戏注册表（服务端）。

职责分工：

- **服务端**（本模块）维护小游戏的「身份与规则」：id、名字、说明、计分单位、
  分数上限、标签。成绩入库前按这里的规则校验，避免前端伪造离谱分数。
- **客户端**（frontend/src/minigames）维护具体玩法实现，按 id 与这里对应。

因此后续增加小游戏有两条路：

1. 只加玩法：在 frontend/src/minigames/index.ts 里调用 registerMinigame(...)，
   id 用已有的或新增的服务端条目；
2. 由其它插件提供玩法元数据：调用星舰插件的能力 minigame.register
   （见 __init__.py），游戏页面会自动把它列进终端目录。

客户端没有实现的 id 会在游戏内标注「需要升级客户端模块」，不会崩溃。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class MinigameSpec:
    """一款小游戏的元数据与计分规则。"""

    id: str
    name: str
    description: str = ""
    icon: str = "game"
    #: 计分单位（例如「分」「秒」）
    score_label: str = "得分"
    #: 允许提交的最大分数（超出直接拒绝，防止脏数据）
    max_score: int = 1_000_000
    #: 分数越高越好（False 表示用时越短越好）
    higher_is_better: bool = True
    tags: tuple[str, ...] = ()
    order: int = 100
    detail: dict[str, Any] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "score_label": self.score_label,
            "max_score": self.max_score,
            "higher_is_better": self.higher_is_better,
            "tags": list(self.tags),
            "order": self.order,
            "detail": dict(self.detail),
        }


class MinigameRegistry:
    """小游戏目录。重复注册同 id 会覆盖（便于插件升级玩法）。"""

    def __init__(self) -> None:
        self._specs: dict[str, MinigameSpec] = {}

    def register(self, spec: MinigameSpec | None = None, **kwargs: Any) -> MinigameSpec:
        if spec is None:
            spec = MinigameSpec(**kwargs)
        if not spec.id or not spec.id.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"非法的小游戏 id: {spec.id!r}")
        self._specs[spec.id] = spec
        return spec

    def unregister(self, game_id: str) -> bool:
        return self._specs.pop(str(game_id), None) is not None

    def get(self, game_id: str) -> MinigameSpec | None:
        return self._specs.get(str(game_id))

    def catalog(self) -> list[dict[str, Any]]:
        return [
            spec.payload()
            for spec in sorted(self._specs.values(), key=lambda item: (item.order, item.id))
        ]

    def ids(self) -> list[str]:
        return sorted(self._specs)

    def validate_score(self, game_id: str, score: Any) -> int:
        """校验并归一化分数；非法输入抛 ValueError。"""
        spec = self.get(game_id)
        if spec is None:
            raise ValueError(f"未知的小游戏: {game_id}")
        try:
            value = int(score)
        except (TypeError, ValueError) as exc:
            raise ValueError("分数必须是整数") from exc
        if value < 0:
            raise ValueError("分数不能为负")
        if value > spec.max_score:
            raise ValueError(f"分数超出上限 {spec.max_score}")
        return value

    def register_many(self, specs: Iterable[MinigameSpec]) -> None:
        for spec in specs:
            self.register(spec)


#: 全局小游戏目录（进程内单例：其它插件也能往里注册玩法元数据）
registry = MinigameRegistry()


def register_builtin_minigames() -> None:
    """内置小游戏（与前端 frontend/src/minigames 一一对应）。"""
    registry.register_many(
        [
            MinigameSpec(
                id="turret",
                name="舱外炮塔",
                description="小行星群正在接近，用舷侧炮塔把它们打成碎片，别让舰体受伤。",
                icon="target",
                score_label="击毁得分",
                max_score=200_000,
                tags=("射击", "单人"),
                order=10,
            ),
            MinigameSpec(
                id="repair",
                name="损管抢修",
                description="反应堆回路被震断，限时把电力从堆芯接到各个系统，越早完成分数越高。",
                icon="wrench",
                score_label="抢修得分",
                max_score=100_000,
                tags=("解谜", "限时"),
                order=20,
            ),
        ]
    )


__all__ = [
    "MinigameRegistry",
    "MinigameSpec",
    "register_builtin_minigames",
    "registry",
]
