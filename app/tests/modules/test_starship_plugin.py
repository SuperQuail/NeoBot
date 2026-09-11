"""官方插件 starship（星舰游戏）的后端契约测试。

覆盖：配置校验、小游戏注册表与分数校验、HTTP 扩展的路由分发。
前端玩法不在单测范围内（用浏览器实测）。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from aiohttp import web

from neobot_app.builtin_plugins.starship import minigames as minigames_module
from neobot_app.builtin_plugins.starship.config import StarshipConfig
from neobot_app.builtin_plugins.starship.web_extension import StarshipWebExtension


class FakeRequest:
    def __init__(self, path: str, method: str = "GET") -> None:
        self.path = path
        self.method = method


class FakeLogger:
    def info(self, *args: Any, **kwargs: Any) -> None: ...
    def warning(self, *args: Any, **kwargs: Any) -> None: ...
    def error(self, *args: Any, **kwargs: Any) -> None: ...
    def exception(self, *args: Any, **kwargs: Any) -> None: ...


def make_extension(**overrides: Any) -> StarshipWebExtension:
    config = StarshipConfig(**overrides)
    return StarshipWebExtension(config=config, api=object(), logger=FakeLogger())


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


def test_route_is_normalized_and_validated() -> None:
    assert StarshipConfig(route="/ship/").prefix == "/ship"
    with pytest.raises(ValueError):
        StarshipConfig(route="")
    with pytest.raises(ValueError):
        StarshipConfig(route="a/b")


def test_quality_must_be_known_level() -> None:
    assert StarshipConfig(default_quality="HIGH").default_quality == "high"
    with pytest.raises(ValueError):
        StarshipConfig(default_quality="ultra")


# ---------------------------------------------------------------------------
# 小游戏目录
# ---------------------------------------------------------------------------


def test_builtin_minigames_are_registered() -> None:
    minigames_module.register_builtin_minigames()
    ids = minigames_module.registry.ids()
    assert "turret" in ids
    assert "repair" in ids
    payload = minigames_module.registry.catalog()[0]
    assert {"id", "name", "description", "score_label", "max_score"} <= set(payload)


def test_score_validation_rejects_unknown_and_oversized() -> None:
    minigames_module.register_builtin_minigames()
    assert minigames_module.registry.validate_score("turret", 120) == 120
    with pytest.raises(ValueError):
        minigames_module.registry.validate_score("nope", 1)
    with pytest.raises(ValueError):
        minigames_module.registry.validate_score("turret", -1)
    with pytest.raises(ValueError):
        minigames_module.registry.validate_score("turret", 10**9)
    with pytest.raises(ValueError):
        minigames_module.registry.validate_score("turret", "abc")


def test_register_minigame_from_other_plugin() -> None:
    spec = minigames_module.registry.register(
        id="docking",
        name="对接演练",
        description="测试用",
        max_score=1000,
    )
    assert spec.id == "docking"
    assert any(item["id"] == "docking" for item in minigames_module.registry.catalog())
    minigames_module.registry.unregister("docking")


# ---------------------------------------------------------------------------
# HTTP 扩展路由
# ---------------------------------------------------------------------------


def test_extension_declares_prefix_and_auth_scope() -> None:
    extension = make_extension()
    assert extension.prefixes == ("/game",)
    # 静态资源与页面不要求登录，数据接口要求
    assert extension.auth_prefixes == ("/game/api",)
    entry = extension.panel_entry()
    assert entry is not None
    assert entry["path"] == "/game/"
    assert entry["title"] == "NeoBot 星舰"


def test_panel_entry_hidden_when_disabled() -> None:
    extension = make_extension(show_in_sidebar=False)
    assert extension.panel_entry() is None


def test_custom_route_moves_prefix() -> None:
    extension = make_extension(route="starship")
    assert extension.prefixes == ("/starship",)
    assert extension.auth_prefixes == ("/starship/api",)


def test_foreign_paths_fall_through() -> None:
    extension = make_extension()
    result = asyncio.run(extension.handle_request(FakeRequest("/other"), "/other"))
    assert result is None


def test_bare_prefix_redirects_to_directory() -> None:
    extension = make_extension()
    response = asyncio.run(
        extension.handle_request(FakeRequest("/game"), "/game")
    )
    assert response.status == 302
    assert response.headers["Location"] == "/game/"


def test_index_reports_build_hint_when_bundle_missing(tmp_path: Path) -> None:
    extension = make_extension()
    extension.web_root = tmp_path
    extension.index_file = tmp_path / "index.html"
    response = asyncio.run(
        extension.handle_request(FakeRequest("/game/"), "/game/")
    )
    assert response.status == 503


def test_static_asset_path_traversal_is_rejected(tmp_path: Path) -> None:
    extension = make_extension()
    extension.web_root = tmp_path
    extension._assets = type(extension._assets)(tmp_path / "assets")  # noqa: SLF001
    response = asyncio.run(
        extension.handle_request(
            FakeRequest("/game/assets/../../secret.txt"),
            "/game/assets/../../secret.txt",
        )
    )
    assert response.status == 404


def test_unknown_api_returns_json_404() -> None:
    class FakeApi:
        async def bootstrap(self, request: Any, *, base: str = "") -> web.Response:
            return web.json_response({"ok": True, "base": base})

    extension = make_extension()
    extension.api = FakeApi()
    response = asyncio.run(
        extension.handle_request(FakeRequest("/game/api/health"), "/game/api/health")
    )
    assert response.status == 200
    missing = asyncio.run(
        extension.handle_request(FakeRequest("/game/api/nope"), "/game/api/nope")
    )
    assert missing.status == 404


def test_bootstrap_receives_panel_base_path() -> None:
    captured: dict[str, str] = {}

    class FakeApi:
        async def bootstrap(self, request: Any, *, base: str = "") -> web.Response:
            captured["base"] = base
            return web.json_response({"ok": True})

    extension = make_extension()
    extension.api = FakeApi()
    asyncio.run(
        extension.handle_request(
            FakeRequest("/nb/game/api/bootstrap"), "/game/api/bootstrap"
        )
    )
    # 面板挂在 /nb 子路径下时，游戏接口要能算出面板根路径
    assert captured["base"] == "/nb"
