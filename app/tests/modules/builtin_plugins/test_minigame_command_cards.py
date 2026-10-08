"""小游戏命令的卡片化与榜单隐私（issue #85）。

- /mg 菜单 / 积分 / 玩法规则 / 排行榜都出图；渲染不可用时回等价纯文本；
- 排行榜**不下发完整 QQ 号**（掩码前 2 后 2）；
- 无参数的 /mg help 直接复用菜单卡，不再堆一张三千像素高的规则卡。
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from neobot_app.builtin_plugins.minigame import MinigamePlugin
from neobot_app.builtin_plugins.minigame.games import build_games
from neobot_app.commands import card as card_module

QQ_PATTERN = re.compile(r"\d{5,15}")


class _MgService:
    async def get_profile(self, user_id):
        return {"score": 128}

    async def streak(self, user_id):
        return 5

    async def leaderboard(self, *, page=1, page_size=10):
        return {
            "page": 1,
            "page_size": 10,
            "total": 2,
            "rows": [
                {"user_id": "10001", "score": 320, "plays": 21, "best_score": 88},
                {"user_id": "20002", "score": 128, "plays": 9, "best_score": 42},
            ],
        }

    async def group_leaderboard(self, conversation_id, *, limit=5):
        return [{"user_id": "20002", "score": 128}]


@pytest.fixture()
def captured(monkeypatch) -> list[str]:
    cards: list[str] = []

    async def _capture(html, **_kwargs):
        cards.append(str(html))
        return None

    monkeypatch.setattr(card_module, "render_card_image", _capture)
    return cards


def _plugin() -> MinigamePlugin:
    plugin = MinigamePlugin.__new__(MinigamePlugin)
    plugin.games = build_games()
    plugin.service = _MgService()
    return plugin


def _ctx() -> SimpleNamespace:
    return SimpleNamespace(
        service=SimpleNamespace(screenshots=None),
        kind="group",
        conv_id="999000111",
        user_id=10001,
        message=SimpleNamespace(user_id=10001, message=[]),
        raw_args="",
        args=[],
        at_qqs=[],
    )


def _visible(html: str) -> str:
    without_style = re.sub(r"<style.*?</style>", "", html, flags=re.DOTALL)
    return re.sub(r"<[^>]+>", " ", without_style)


def test_mask_user_id_keeps_only_head_and_tail() -> None:
    assert MinigamePlugin._mask_user_id("10001") == "10****01"
    assert MinigamePlugin._mask_user_id("123") == "玩家"
    assert MinigamePlugin._mask_user_id("") == "玩家"


async def test_menu_card_lists_games(captured: list[str]) -> None:
    result = await _plugin().menu_card(_ctx())

    # 本用例把渲染换成「只捕获 HTML」，因此拿到的是纯文本降级；真实端口可用时返回 None
    assert isinstance(result, str) and "NeoBot 小游戏" in result
    html = captured[-1]
    visible = _visible(html)
    assert "NeoBot 小游戏" in visible
    for game in build_games():
        assert game.name in visible


async def test_rank_card_masks_qq(captured: list[str]) -> None:
    plugin = _plugin()

    await plugin.rank_command(_ctx(), rest="", conversation_id="999000111")

    visible = _visible(captured[-1])
    assert "积分排行榜" in visible
    assert "10****01" in visible and "20****02" in visible
    # 榜单对全群可见：完整 QQ 号一个都不许出现
    for raw in ("10001", "20002"):
        assert raw not in visible
    assert QQ_PATTERN.search(visible) is None


async def test_rank_text_fallback_also_masks(captured: list[str], monkeypatch) -> None:
    plugin = _plugin()

    async def _no_render(_html, **_kwargs):
        return None

    monkeypatch.setattr(card_module, "render_card_image", _no_render)
    text = await plugin.rank_command(_ctx(), rest="", conversation_id="999000111")

    assert isinstance(text, str) and "积分排行榜" in text
    assert "10001" not in text and "20002" not in text
    assert QQ_PATTERN.search(text) is None


async def test_help_without_argument_reuses_menu_card(captured: list[str]) -> None:
    plugin = _plugin()

    await plugin.help_card(_ctx(), "")

    assert len(captured) == 1, "无参数 /mg help 应当只出一张卡（菜单）"
    assert "NeoBot 小游戏" in _visible(captured[-1])


async def test_help_with_game_renders_rules_card(captured: list[str]) -> None:
    plugin = _plugin()

    await plugin.help_card(_ctx(), "瓶")

    visible = _visible(captured[-1])
    assert "玩法规则" in visible
    assert "漂流瓶" in visible
