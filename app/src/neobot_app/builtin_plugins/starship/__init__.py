"""NeoBot 星舰：官方娱乐插件。

把网页面板（前置插件 dashboard）的控制台功能做成一艘可自由探索的 3D 科幻战舰：

- 每个控制台菜单都是舰上的一个舱室终端（3D 全息曲面屏，非平面贴图）；
- 太空场景（星云、行星、小行星流、过往飞船、随机跃迁）在舷窗外实时渲染；
- 待机等状态下终端会熄屏，游戏内明确提示原因；
- 页面与接口都挂在面板同一个端口上（由 dashboard 提供 HTTP 扩展点）。

依赖关系：

    dependencies = ["dashboard>=1.0.0"]

前置面板缺失 / 被停用时本插件会被自动禁用（不影响 NeoBot 启动），
面板恢复后运行时会把本插件自动拉起来。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Mapping

from neobot_modloader import Migration, Plugin

from .api import StarshipApi
from .config import StarshipConfig
from .minigames import MinigameSpec, register_builtin_minigames, registry as minigame_registry
from .models import Base
from .migrations import add_score_detail_index, create_initial_schema
from .web_extension import StarshipWebExtension

plugin = Plugin(
    "starship",
    version="1.0.0",
    description="NeoBot 星舰：把控制台搬进一艘可自由探索的 3D 科幻战舰",
    author="NeoBot",
    config=StarshipConfig,
    dependencies=("dashboard>=1.0.0",),
    priority=-1,
    hot_reload=True,
    config_hot_reload=False,
)

database = plugin.sqlite_database(
    "main",
    filename="starship.db",
    metadata=Base.metadata,
    migrations=[
        Migration(version=1, name="initial-schema", upgrade=create_initial_schema),
        Migration(version=2, name="score-rank-index", upgrade=add_score_detail_index),
    ],
)

#: 面板 HTTP 扩展名（注销时用同一个名字）
EXTENSION_NAME = "starship"


class StarshipPlugin:
    """星舰插件运行时状态。"""

    def __init__(self) -> None:
        self.ctx: Any = None
        self.config: StarshipConfig | None = None
        self.extension: StarshipWebExtension | None = None
        self.api: StarshipApi | None = None
        self.registered = False
        self.started_at = time.time()
        self.last_error: str | None = None

    # ------------------------------------------------------------------

    async def load(self, ctx: Any) -> None:
        self.ctx = ctx
        self.config = (
            ctx.config
            if isinstance(ctx.config, StarshipConfig)
            else StarshipConfig.model_validate(dict(ctx.config or {}))
        )
        self.last_error = None
        register_builtin_minigames()

        config = self.config
        services = getattr(getattr(ctx, "plugin_host", None), "services", None)
        api = StarshipApi(
            config=config,
            database=database,
            logger=ctx.logger,
            services=services,
            plugin_control=getattr(ctx, "plugin_control", None),
            adapter=getattr(ctx, "adapter", None),
            started_at=self.started_at,
        )
        self.api = api
        extension = StarshipWebExtension(config=config, api=api, logger=ctx.logger)
        self.extension = extension
        await self._register_extension(ctx, extension, config.prefix)

    async def _register_extension(
        self, ctx: Any, extension: StarshipWebExtension, prefix: str
    ) -> None:
        """通过前置插件的能力把自己的页面挂到面板端口上。

        这里演示依赖体系里「调用前置插件功能」的标准写法：
        ctx.require_plugin 校验前置插件就绪与版本，handle.call 调用它的能力。
        面板没起来（端口被占用等）只记错误、不抛异常：游戏不可用，
        但插件仍处于已加载状态，面板里能看到原因。
        """
        try:
            handle = ctx.require_plugin("dashboard", ">=1.0.0")
            await handle.call(
                "web.register_extension",
                {"name": EXTENSION_NAME, "extension": extension},
            )
        except Exception as exc:
            self.registered = False
            self.last_error = f"挂载到网页面板失败: {exc}"
            ctx.logger.error(
                f"星舰游戏挂载失败（面板不可用？）: {exc}；"
                f"面板恢复后可在面板插件页重载本插件"
            )
            return
        self.registered = True
        ctx.logger.info(
            f"星舰游戏已挂载到网页面板: {prefix}/（依赖 dashboard 提供 HTTP 扩展点）"
        )

    async def unload(self) -> None:
        ctx = self.ctx
        if ctx is None:
            return
        if not self.registered:
            return
        try:
            handle = ctx.require_plugin("dashboard", ">=1.0.0")
            await handle.call("web.unregister_extension", {"name": EXTENSION_NAME})
        except Exception as exc:
            ctx.logger.warning(f"注销星舰 HTTP 扩展失败: {exc}")
        self.registered = False

    # ------------------------------------------------------------------
    # 对外能力（其它插件可调用）
    # ------------------------------------------------------------------

    async def register_minigame(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """注册一款小游戏的元数据（玩法实现仍需客户端模块）。

        调用示例::

            handle = ctx.require_plugin("starship", ">=1.0.0")
            await handle.call("minigame.register", {
                "id": "docking",
                "name": "对接演练",
                "description": "在限定时间内完成对接",
                "score_label": "对接得分",
                "max_score": 50000,
            })
        """
        data = dict(payload or {})
        game_id = str(data.pop("id", "") or "").strip()
        if not game_id:
            raise ValueError("缺少小游戏 id")
        spec = minigame_registry.register(
            MinigameSpec(
                id=game_id,
                name=str(data.get("name") or game_id),
                description=str(data.get("description") or ""),
                icon=str(data.get("icon") or "game"),
                score_label=str(data.get("score_label") or "得分"),
                max_score=int(data.get("max_score") or 1_000_000),
                higher_is_better=bool(data.get("higher_is_better", True)),
                tags=tuple(str(item) for item in (data.get("tags") or ())),
                order=int(data.get("order") or 100),
            )
        )
        return spec.payload()

    def describe(self) -> dict[str, Any]:
        return {
            "mounted": self.registered,
            "prefix": self.config.prefix if self.config else "",
            "error": self.last_error,
            "minigames": minigame_registry.ids(),
        }


_instance = StarshipPlugin()


# ── 能力：其它插件通过 ctx.require_plugin("starship").call(...) 调用 ──


@plugin.capability("minigame.register")
async def _capability_register_minigame(payload: Any) -> dict[str, Any]:
    return await _instance.register_minigame(payload if isinstance(payload, dict) else {})


@plugin.capability("minigame.list")
async def _capability_list_minigames(payload: Any) -> list[dict[str, Any]]:
    return minigame_registry.catalog()


@plugin.capability("starship.describe")
async def _capability_describe(payload: Any) -> dict[str, Any]:
    return _instance.describe()


# ── 生命周期 ──────────────────────────────────────────────────────


@plugin.on_load
async def _starship_load(ctx: Any) -> None:
    await _instance.load(ctx)


@plugin.on_shutdown
async def _starship_shutdown() -> None:
    await _instance.unload()


__all__ = ["database", "plugin"]
