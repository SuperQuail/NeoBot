"""小游戏卡片主题（Minecraft / 各玩法艺术主题）与专属美术的用例。

覆盖：
- 插件 load 注册、unload 注销，卸载后不残留；
- Minecraft 主题契约（像素字体、整数倍字号、平铺尺寸写在 css 而不是变量里）；
- 全部插件主题自包含（无外链 / 无脚本 / 无 @import）；
- 主题随机只在玩法候选池内，fixed 模式只出指定主题；
- 四个游戏卡片各自带专属美术标记；
- 用户正文仍然被转义，美术片段里没有用户输入。
"""

from __future__ import annotations

import random
import re
from pathlib import Path
from typing import Any

import pytest

from neobot_app.builtin_plugins.minigame import art, themes
from neobot_app.builtin_plugins.minigame.config import MinigameConfig
from neobot_app.builtin_plugins.minigame.games.fortune import FORTUNE_LEVELS
from neobot_app.runtime import html_card

from test_minigame_plugin import (  # noqa: E402 - 同目录用例的替身与装配
    FakeScreenshots,
    build,
    scan_unsafe_tags,
)

#: 每个游戏卡片必须出现的专属美术标记（卷轴 / 印章 / 竹签 / 海浪 …）
CARD_ART_MARKERS: dict[str, tuple[str, ...]] = {
    "bottle": ("mgart-sea", "mgart-wave", "mgart-beach", "mgart-glass", "mgart-note"),
    "chengyu": ("mgart-scroll", "mgart-brush", "mgart-seal", "mgart-progress"),
    "checkin": ("mgart-cal-page", "mgart-stamp", "mgart-streak-dot"),
    "fortune": (
        "mgart-fortune",
        "mgart-bamboo",
        "mgart-bamboo-node",
        "mgart-tube",
        "mgart-rack",
    ),
}

#: 自包含约束：卡片 HTML 里不允许出现的串
FORBIDDEN = ("http://", "https://", "@import", "<script", "javascript:")


class CaptureLogger:
    """记录日志的替身（断言「这次抽到哪个主题」确实落了日志）。"""

    def __init__(self) -> None:
        self.infos: list[str] = []

    def debug(self, *args: Any, **kwargs: Any) -> None: ...
    def warning(self, *args: Any, **kwargs: Any) -> None: ...
    def error(self, *args: Any, **kwargs: Any) -> None: ...
    def exception(self, *args: Any, **kwargs: Any) -> None: ...

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        self.infos.append(str(message))


# ── 注册 / 注销 ───────────────────────────────────────────────────


async def test_plugin_load_registers_themes_and_unload_removes_them(
    tmp_path: Path,
) -> None:
    """插件 load 注册三套主题；unload 之后不留痕，内置主题也不受影响。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        registered = html_card.registered_themes()
        for name in themes.PLUGIN_THEMES:
            assert name in registered
            assert name in html_card.THEME_SPECS
            assert name in html_card.THEMES

        assert await harness.plugin.unload() is None

        for name in themes.PLUGIN_THEMES:
            assert name not in html_card.THEME_SPECS, f"{name} 卸载后仍残留"
            assert name not in html_card.THEMES
            assert name not in html_card.registered_themes()
        for name in themes.BUILTIN_THEME_IDS:
            assert name in html_card.THEME_SPECS, "内置主题不得被注销"
    finally:
        await harness.close()


def test_theme_registration_is_idempotent() -> None:
    """重复注册等价于覆盖，不会抛「主题已注册」。"""
    try:
        assert themes.register_minigame_themes() == themes.PLUGIN_THEMES
        themes.register_minigame_themes()
        assert themes.unregister_minigame_themes() == themes.PLUGIN_THEMES
        assert themes.unregister_minigame_themes() == (), "重复注销应当是 no-op"
    finally:
        themes.unregister_minigame_themes()


async def test_unknown_theme_falls_back_to_default(tmp_path: Path) -> None:
    """主题缺失时选择函数回落 default，绝不出未注册的主题名。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        assert await harness.plugin.unload() is None
        # 插件主题已注销：random 池里只剩内置主题，fixed 指定 minecraft 也要回落
        harness.plugin._theme_memo.clear()
        for game_id in themes.GAME_THEME_POOLS:
            picked = harness.plugin.pick_card_theme(game_id)
            assert html_card.resolve_theme(picked) == picked
        assert themes.resolve_theme("bottle", mode="fixed", theme="minecraft", rng=random.Random(1)) == "default"
    finally:
        await harness.close()


# ── Minecraft 主题契约 ────────────────────────────────────────────


async def test_minecraft_theme_is_pixel_and_embeds_fonts(tmp_path: Path) -> None:
    """MC 主题：像素字体内嵌 + 整数倍字号 + 泥土平铺 + 3D 凸起边框。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        spec = html_card.THEME_SPECS["minecraft"]
        variables = html_card.THEMES["minecraft"]

        assert variables["--font-smoothing"] == "none"
        assert variables["--card-font-size"] == "16px"
        assert variables["--title-size"] == "24px"
        assert variables["--accent"] == "#7cc576"
        assert variables["--radius"] == "0px"
        assert "inset 4px 4px 0" in variables["--card-shadow"], "3D 凸起边框（左上亮）"
        assert "inset -4px -4px 0" in variables["--card-shadow"], "3D 凸起边框（右下暗）"

        # 平铺尺寸必须写在 css 里：写成变量会当缺省值泄漏给别的主题
        assert "--card-bg-size" not in variables
        assert "--card-bg-repeat" not in variables
        assert "background-size: 48px 48px" in spec.css
        assert "background-repeat: repeat" in spec.css
        assert "--card-bg-repeat" not in spec.css

        # 泥土平铺是自包含 data URI，且暴露成 --svg-dirt
        assert variables["--svg-dirt"].startswith('url("data:image/svg+xml,')
        assert "http://" not in variables["--card-bg-image"]

        # 内嵌字体：Monocraft（常规 + 粗体）在前，FusionPixel 兜底中文
        assert spec.fonts[0] == '"Monocraft"'
        assert spec.fonts[1] == '"FusionPixel"'
        weights = [font.weight for font in spec.embed_fonts if font.family == "Monocraft"]
        assert weights == ["400", "700"]
        assert [font.family for font in spec.embed_fonts].count("FusionPixel") == 1
        for font in spec.embed_fonts:
            assert Path(str(font.source)).is_file(), str(font.source)

        assert "Monocraft" in html_card.render_card_html(
            title="像素", blocks=[], theme="minecraft"
        )
    finally:
        await harness.close()


def test_no_theme_leaks_tiling_variables() -> None:
    """任何主题都不许把平铺尺寸写进 variables（否则会漏给其它主题）。"""
    try:
        themes.register_minigame_themes()
        assert "data:image/svg+xml" in html_card.THEMES["minecraft"]["--card-bg-image"]
        for name in html_card.registered_themes():
            variables = html_card.THEMES[name]
            assert "--card-bg-size" not in variables, name
            assert "--card-bg-repeat" not in variables, name
        # 泥土图案只出现在 minecraft 里
        assert "data:image/svg+xml" not in html_card.THEMES["default"]["--card-bg-image"]
        assert "data:image/svg+xml" not in html_card.THEMES["game"]["--card-bg-image"]
    finally:
        themes.unregister_minigame_themes()


def test_plugin_themes_are_self_contained() -> None:
    """插件主题出的卡片自包含：无外链 / 无脚本 / 无 @import。"""
    try:
        themes.register_minigame_themes()
        for name in themes.PLUGIN_THEMES:
            html = html_card.render_card_html(
                title="自包含检查",
                subtitle=name,
                blocks=[
                    {"kind": "kv", "items": [["键", "值"]]},
                    {"kind": "note", "text": "无外链"},
                ],
                theme=name,
            )
            lowered = html.lower()
            for token in FORBIDDEN:
                assert token not in lowered, (name, token)
            assert scan_unsafe_tags(html) == []
    finally:
        themes.unregister_minigame_themes()


# ── 主题随机 / 固定 ───────────────────────────────────────────────


async def test_random_theme_stays_inside_each_game_pool(tmp_path: Path) -> None:
    """random 模式：每个玩法只从自己的候选池里挑，且池内两个主题都会出现。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        assert harness.plugin.config is not None
        assert harness.plugin.config.theme_mode == "random", "默认必须是随机主题"
        harness.plugin._theme_rng = random.Random(20260913)
        for game_id, pool in themes.GAME_THEME_POOLS.items():
            seen = {harness.plugin.pick_card_theme(game_id) for _ in range(80)}
            assert seen <= set(pool), f"{game_id} 挑到了候选池之外的主题: {seen}"
            assert len(seen) > 1, f"{game_id} 从未挑到第二个主题: {seen}"

        assert harness.plugin.pick_card_theme("bottle", cache_key="k") in themes.theme_pool("bottle")
    finally:
        await harness.close()


async def test_fixed_mode_only_uses_configured_theme(tmp_path: Path) -> None:
    """fixed 模式：指定主题时四个玩法都出同一个主题；留空时各用默认主题。"""
    config = MinigameConfig(theme_mode="fixed", theme="minecraft")
    harness = await build(tmp_path, config=config, screenshots=FakeScreenshots())
    try:
        for game_id in themes.GAME_THEME_POOLS:
            for _ in range(5):
                assert harness.plugin.pick_card_theme(game_id) == "minecraft"
    finally:
        await harness.close()

    harness2 = await build(
        tmp_path,
        config=MinigameConfig(theme_mode="fixed"),
        screenshots=FakeScreenshots(),
    )
    try:
        for game_id in themes.GAME_THEME_POOLS:
            assert harness2.plugin.pick_card_theme(game_id) == themes.default_theme(game_id)
    finally:
        await harness2.close()


async def test_fixed_theme_is_used_by_rendered_cards(tmp_path: Path) -> None:
    """fixed=minecraft 时，命令通道出的卡片确实是 MC 主题的 HTML。"""
    screenshots = FakeScreenshots()
    harness = await build(
        tmp_path,
        config=MinigameConfig(theme_mode="fixed", theme="minecraft"),
        screenshots=screenshots,
    )
    try:
        await harness.send("/mg 签到")
        html = screenshots.calls[-1]
        assert "Monocraft" in html
        assert html_card.THEMES["minecraft"]["--accent"] in html
    finally:
        await harness.close()


async def test_picked_theme_is_logged(tmp_path: Path) -> None:
    """「这次抽到哪个主题」必须落日志，便于排查。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    logger = CaptureLogger()
    harness.plugin._logger = logger
    try:
        picked = harness.plugin.pick_card_theme("fortune")
        assert logger.infos, "主题选择必须记日志"
        assert any(picked in line and "fortune" in line for line in logger.infos)
    finally:
        await harness.close()


async def test_same_result_reuses_same_theme(tmp_path: Path) -> None:
    """同一结果的卡片（例如当天重复抽签）沿用同一主题。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        harness.plugin._theme_rng = random.Random(3)
        picks = {harness.plugin.pick_card_theme("fortune", cache_key="2002:2026-09-13") for _ in range(20)}
        assert len(picks) == 1
        assert "fortune|2002:2026-09-13" in harness.plugin._theme_memo
    finally:
        await harness.close()


async def test_fortune_resend_renders_identical_html(tmp_path: Path) -> None:
    """/mg 抽签 当天重复请求必须重发同一张图（主题也得一样）。"""
    screenshots = FakeScreenshots()
    harness = await build(tmp_path, screenshots=screenshots)
    try:
        await harness.send("/mg 抽签")
        first = screenshots.calls[-1]
        await harness.send("/mg 抽签")
        assert screenshots.calls[-1] == first
    finally:
        await harness.close()


# ── 配置校验 ─────────────────────────────────────────────────────


def test_config_rejects_unknown_theme_and_mode() -> None:
    """未知 mode / 未知主题名都要有明确报错。"""
    with pytest.raises(Exception) as bad_mode:
        MinigameConfig(theme_mode="ramdom")
    assert "theme_mode" in str(bad_mode.value)

    with pytest.raises(Exception) as bad_theme:
        MinigameConfig(theme="minecraf")
    assert "未知的卡片主题" in str(bad_theme.value)

    assert MinigameConfig(theme_mode="FIXED").theme_mode == "fixed"
    assert MinigameConfig(theme=" Minecraft ").theme == "minecraft"
    assert MinigameConfig().theme_mode == "random"
    assert MinigameConfig().theme == ""
    assert MinigameConfig(theme_mode="fixed").default_theme_for("fortune") == "fortune"
    assert MinigameConfig(theme_mode="fixed", theme="game").default_theme_for("fortune") == "game"


# ── 四个游戏的专属美术 ───────────────────────────────────────────


async def test_all_four_cards_carry_their_own_art(tmp_path: Path) -> None:
    """四个玩法各自的卡片都带专属美术标记（海浪 / 卷轴 / 日历印章 / 竹签）。"""
    screenshots = FakeScreenshots()
    harness = await build(tmp_path, screenshots=screenshots)
    try:
        await harness.send("/mg 瓶 丢 今天也要开心")
        bottle_html = screenshots.calls[-1]
        await harness.send("/mg 成语接龙")
        chengyu_html = screenshots.calls[-1]
        await harness.send("/mg 签到")
        checkin_html = screenshots.calls[-1]
        await harness.send("/mg 抽签")
        fortune_html = screenshots.calls[-1]

        for game_id, html in (
            ("bottle", bottle_html),
            ("chengyu", chengyu_html),
            ("checkin", checkin_html),
            ("fortune", fortune_html),
        ):
            for marker in CARD_ART_MARKERS[game_id]:
                assert marker in html, f"{game_id} 缺少美术标记 {marker}"
            assert scan_unsafe_tags(html) == []

        # 美术确实注入在插槽 / 标记位上（不是被兜底塞到内容区开头）
        assert 'data-slot="bottle-art"><div class="mgart-sea">' in bottle_html
        assert 'data-marker="@@MG_AVATAR@@"><div class="mgart-who">' in bottle_html
        assert 'data-marker="@@MG_CONTENT@@"><div class="mgart-note">' in bottle_html
        assert 'data-slot="chengyu-art"><div class="mgart-scroll">' in chengyu_html
        assert 'data-slot="chengyu-progress"><div class="mgart-progress">' in chengyu_html
        assert 'data-slot="checkin-art"><div class="mgart-cal">' in checkin_html
        assert 'data-slot="fortune-art"><div class="mgart-fortune">' in fortune_html

        # 抽签：竹签上有竹节与档位文字（档位来自程序常量）
        assert "mgart-bamboo-node" in fortune_html
        assert any(level.label in fortune_html for level in FORTUNE_LEVELS)
        # 签到：日历页 + 点阵里至少有一个已点亮的点
        assert "mgart-streak-dot is-on" in checkin_html
        # 成语接龙：进度链路上有节点与「第 k/N 条」
        session = harness.plugin.chengyu_sessions["888"]
        assert f"第 0/{session.target} 条" in chengyu_html
        # 漂流瓶：纸条正文容器
        assert "mgart-note" in bottle_html and "今天也要开心" in bottle_html
    finally:
        await harness.close()


def test_art_fragments_have_no_user_input_and_no_outlinks() -> None:
    """美术片段是纯常量：无外链、无事件处理器、无脚本。"""
    fragments = [
        art.bottle_scene(anonymous=False),
        art.bottle_scene(anonymous=True),
        art.bottle_note("<p>已净化的正文</p>"),
        art.bottle_avatar('<img class="mg-avatar" src="data:image/png;base64,AA">', anonymous=True, label="神秘的人"),
        art.chengyu_scroll(status="接龙中"),
        art.chengyu_progress(steps=2, target=5, max_steps=10),
        art.checkin_art(day="2026-09-13", streak=3, already=False),
        art.checkin_art(day="2026-09-13", streak=3, already=True),
        art.fortune_art(label="大吉", key="great", caption="今日一签"),
    ]
    for fragment in fragments:
        lowered = fragment.lower()
        for token in ("http://", "https://", "@import", "<script", "javascript:"):
            assert token not in lowered, token
        assert not re.search(r"""[\s"']on[a-z]{3,}\s*=""", fragment), "不许出现事件处理器"


def test_fortune_art_only_draws_known_levels() -> None:
    """竹签上的文字只可能是内置档位：任何其它输入都不画字（防注入）。"""
    assert art.safe_level_label("大吉") == "大吉"
    assert art.safe_level_label("<script>alert(1)</script>") == ""
    assert art.safe_level_label("onerror=alert(1)") == ""
    evil = art.fortune_art(label="<script>alert(1)</script>", key="great", caption="")
    assert "<script" not in evil.lower()
    assert "alert(1)" not in evil


async def test_user_text_is_still_escaped_in_new_cards(tmp_path: Path) -> None:
    """改版后的卡片同样先转义：<script> / onerror / javascript: 都不产生真实标签。"""
    screenshots = FakeScreenshots()
    harness = await build(tmp_path, screenshots=screenshots)
    try:
        payload = "<script>alert(1)</script> <img src=x onerror=alert(1)> [x](javascript:alert(1))"
        await harness.send("/mg 瓶 丢 " + payload)
        html = screenshots.calls[-1]

        assert "<script" not in html.lower()
        assert scan_unsafe_tags(html) == []
        assert "javascript:" not in html
        assert "&lt;script&gt;" in html, "原始 HTML 必须变成字面文本"
        tag_text = "\n".join(re.findall(r"<[^>]*>", html))
        assert "onerror=alert(1)" not in tag_text
        # 美术片段本身不含用户输入
        assert "alert(1)" not in art.bottle_scene(anonymous=False)
    finally:
        await harness.close()


async def test_chengyu_word_pending_is_escaped(tmp_path: Path) -> None:
    """成语接龙卡片上的「待判定」词同样被转义。"""
    screenshots = FakeScreenshots()
    harness = await build(tmp_path, screenshots=screenshots)
    try:
        await harness.send("/mg 成语接龙")
        await harness.send("/mg 成语接龙 <img src=x onerror=alert(1)>")
        html = screenshots.calls[-1]

        assert scan_unsafe_tags(html) == []
        assert "<img src=x" not in html
        assert "&lt;img" in html
    finally:
        await harness.close()


async def test_four_cards_render_under_both_pool_themes(tmp_path: Path) -> None:
    """候选池里的两个主题都能出图（艺术主题 + minecraft）。"""
    screenshots = FakeScreenshots()
    harness = await build(tmp_path, screenshots=screenshots)
    try:
        from neobot_app.builtin_plugins.minigame.games import bottle, checkin, chengyu, fortune

        avatar = harness.plugin.avatars
        assert avatar is not None
        for theme in ("bottle", "minecraft"):
            card = bottle.BottleCard(
                title="漂流瓶已投出",
                subtitle="主题 " + theme,
                sender_label="小青",
                sender_id_label="1234567",
                content="正文",
                avatar_user_id="1234567",
                avatar_name="小青",
                anonymous=False,
                visibility=bottle.visibility_notice(anonymous=False),
            )
            html = bottle.build_card_html(card, avatars=avatar, theme=theme)
            assert "mgart-sea" in html and scan_unsafe_tags(html) == []

        for theme in ("chengyu", "minecraft"):
            card = chengyu.ChengyuCard(title="成语接龙", subtitle="主题 " + theme, target=5, steps=1, max_steps=10)
            html = chengyu.build_card_html(card, theme=theme)
            assert "mgart-scroll" in html and scan_unsafe_tags(html) == []

        for theme in ("checkin", "minecraft"):
            card = checkin.CheckinCard(
                title="每日签到",
                subtitle="主题 " + theme,
                stats=[("本次得分", "+7 分", "accent")],
                details=[("连续签到", "6 天")],
                day="2026-09-13",
                streak=6,
            )
            html = checkin.build_card_html(card, theme=theme)
            assert "mgart-cal-page" in html and scan_unsafe_tags(html) == []

        for theme in ("fortune", "minecraft"):
            card = fortune.FortuneCard(
                title="今日运势",
                subtitle="主题 " + theme,
                rows=[("运势", "大吉"), ("签文", "诸事顺遂")],
                level_key="great",
                caption="今日一签",
            )
            html = fortune.build_card_html(card, theme=theme)
            assert "mgart-bamboo" in html and scan_unsafe_tags(html) == []
    finally:
        await harness.close()
