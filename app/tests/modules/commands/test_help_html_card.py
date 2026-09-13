"""spec(5) §4.2：/help HTML 卡片 + 分页 + 预渲染（R5-R9 / A8-A13、A15-A17）。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from neobot_app.commands.model import (
    PERM_EVERYONE,
    PERM_SUB_ADMIN,
    PERM_SUPER_ADMIN,
    Command,
)
from neobot_app.commands.registry import CommandRegistry
from neobot_app.commands.service import CommandService
from neobot_app.screenshot import ScreenshotResult, UnavailableScreenshots

BOT = 88888
SUPER = 10000
SUB = 30000
NOBODY = 40000
NOBODY2 = 40001
#: 卡片图片字节（内容不重要，只用于断言"发了图"）
PNG = b"\x89PNG\r\n\x1a\n" + b"help-card"


class FakeScreenshots:
    """截图替身：记录每次渲染的 HTML；可注入失败。"""

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[str] = []
        self.fail = fail

    async def render(self, *, html: str, options: Any, base_url: str | None = None):
        self.calls.append(html)
        if self.fail:
            raise RuntimeError("chromium 不可用")
        return ScreenshotResult(PNG, "png", 720, 200, 720.0, 200.0, 1.0)


class FakeFileServer:
    _enabled = True

    def __init__(self) -> None:
        self.registered: list[Path] = []

    def register_file(self, file_path: Path) -> str:
        self.registered.append(Path(file_path))
        return f"http://127.0.0.1:1/files/{Path(file_path).name}"


class FakeAdapter:
    def __init__(self) -> None:
        self.sent: list[tuple[Any, list[dict[str, Any]]]] = []

    async def send(self, conv: Any, segments: list[dict[str, Any]]) -> None:
        self.sent.append((conv, segments))


class FakeConverter:
    """markdown→图片渲染替身（三级降级链的第二级）。"""

    def __init__(self, directory: Path, *, ok: bool = True) -> None:
        self.directory = Path(directory)
        self.ok = ok
        self.calls: list[str] = []
        #: 命令服务会优先用它的输出目录落盘卡片图
        self._output_dir = self.directory

    async def convert(self, markdown: str, **kwargs: Any) -> Path:
        self.calls.append(markdown)
        if not self.ok:
            raise RuntimeError("markdown 渲染失败")
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / "md_card.png"
        path.write_bytes(PNG)
        return path


def _config():
    chat = SimpleNamespace(admin_accounts=[SUPER], sub_admin_accounts=[SUB])
    return SimpleNamespace(chat=chat, bot=SimpleNamespace(account=BOT))


def _command(
    name: str,
    *,
    permission: int = PERM_EVERYONE,
    usage: str = "",
    description: str | None = None,
    aliases: tuple[str, ...] = (),
    params: tuple[tuple[str, str], ...] = (),
    source: str = "",
) -> Command:
    return Command(
        name=name,
        description=description if description is not None else f"{name} 的说明",
        handler=lambda ctx: "x",
        permission=permission,
        usage=usage,
        aliases=aliases,
        params=params,
        source=source,
    )


def _help_command() -> Command:
    """真正的 /help 命令（测试只替换命令表，不替换处理器）。"""
    from neobot_app.commands.builtin import _handle_help

    return Command(
        name="help",
        description="查看可用命令列表",
        handler=_handle_help,
        permission=PERM_EVERYONE,
        usage="[命令名] [页码] [--refresh]",
        params=(("命令名", "可选。查看指定命令的详细说明"),),
    )


def _make_service(
    tmp_path: Path,
    *,
    commands: list[Command] | None = None,
    screenshots: Any = None,
    converter: Any = None,
    registry: CommandRegistry | None = None,
    adapter: Any = None,
):
    reg = registry if registry is not None else CommandRegistry()
    for command in commands or []:
        reg.register(command)
    if reg.get("help") is None:
        reg.register(_help_command())
    adapter = adapter if adapter is not None else FakeAdapter()
    file_server = FakeFileServer()
    service = CommandService(
        config=_config(),
        adapter=adapter,
        registry=reg,
        register_builtins=False,
        screenshots=screenshots,
        file_server=file_server,
        markdown_image_converter=converter,
        image_output_dir=tmp_path / "cards",
        help_cache_dir=tmp_path / "help_cache",
    )
    return service, adapter, file_server, reg


def _message(text: str, *, user_id: int = NOBODY):
    return SimpleNamespace(
        user_id=user_id, message=[{"type": "text", "data": {"text": text}}]
    )


async def _run(service: CommandService, text: str, *, user_id: int = NOBODY):
    """私聊触发命令（私聊不需要 @bot）。

    返回 None 表示命令已自行发送图片；否则返回实际发出的文本
    （走管线的命令返回交给主管线的 background 文案）。
    """
    captured: list[str] = []

    async def _capture(kind, conv, body, at_user_id):
        captured.append(body)

    service._send_callback = _capture
    result = await service.handle_message(
        _message(text, user_id=user_id), kind="private", queue_key="1"
    )
    if captured:
        return captured[0]
    return result.background


def _rows(html: str) -> int:
    """卡片里的命令行数（每行都带 [权限: xxx]）。"""
    return html.count("[权限: ")


# ── A8：走新 HTML 卡片路径（不是 markdown→图片） ──


async def test_help_uses_html_card_path(tmp_path: Path) -> None:
    screenshots = FakeScreenshots()
    converter = FakeConverter(tmp_path / "md")
    service, adapter, file_server, _ = _make_service(
        tmp_path,
        commands=[_command("ping", usage="[目标]")],
        screenshots=screenshots,
        converter=converter,
    )

    result = await _run(service, "/help")

    assert result is None  # 已自行发送图片（没有文本回复）
    assert screenshots.calls, "必须走 HTML 卡片渲染"
    assert 'class="card"' in screenshots.calls[0]
    assert converter.calls == [], "首选路径不得回落到 markdown→图片"
    assert len(adapter.sent) == 1
    assert adapter.sent[0][1][-1]["type"] == "image"
    assert file_server.registered, "卡片图必须经文件服务器注册后发送"


async def test_help_permission_filter_matches_registry(tmp_path: Path) -> None:
    """A8：权限过滤不变——低权限用户看不到高权限命令。"""
    screenshots = FakeScreenshots()
    service, _, _, _ = _make_service(
        tmp_path,
        commands=[
            _command("public"),
            _command("sub_only", permission=PERM_SUB_ADMIN),
            _command("super_only", permission=PERM_SUPER_ADMIN),
        ],
        screenshots=screenshots,
    )

    assert await _run(service, "/help", user_id=NOBODY) is None
    html = screenshots.calls[-1]
    assert "public" in html
    assert "sub_only" not in html
    assert "super_only" not in html


def test_empty_command_list_shows_empty_state() -> None:
    """无可见命令时显示空态文案（不是空白图）。"""
    from neobot_app.runtime import help_card

    payload = help_card.build_list_payload([])
    html = help_card.render_payload_html(payload)

    assert help_card.EMPTY_TEXT in html
    assert "共 0 条" in html
    assert "第 1/1 页" not in html


# ── A9：30 条/页与页脚 ──


async def test_help_pagination_thirty_per_page(tmp_path: Path) -> None:
    # 44 条夹具 + /help 自身 = 45 条可见命令
    commands = [_command(f"cmd{i:02d}") for i in range(44)]
    screenshots = FakeScreenshots()
    service, adapter, _, _ = _make_service(
        tmp_path, commands=commands, screenshots=screenshots
    )

    assert await _run(service, "/help") is None
    html1 = screenshots.calls[-1]
    assert _rows(html1) == 30
    assert "第 1/2 页" in html1
    assert "共 45 条" in html1
    assert "翻页" in html1

    assert await _run(service, "/help 2") is None
    html2 = screenshots.calls[-1]
    assert _rows(html2) == 15
    assert "第 2/2 页" in html2
    assert len(adapter.sent) == 2


async def test_help_single_page_has_no_pager(tmp_path: Path) -> None:
    screenshots = FakeScreenshots()
    service, _, _, _ = _make_service(
        tmp_path,
        commands=[_command("a"), _command("b")],
        screenshots=screenshots,
    )

    assert await _run(service, "/help") is None
    html = screenshots.calls[-1]
    assert _rows(html) == 3
    assert "共 3 条" in html
    assert "第 1/1 页" not in html
    assert "翻页" not in html


# ── A10：越界页码 ──


async def test_help_out_of_range_page_is_annotated(tmp_path: Path) -> None:
    commands = [_command(f"cmd{i:02d}") for i in range(44)]
    screenshots = FakeScreenshots()
    service, _, _, _ = _make_service(
        tmp_path, commands=commands, screenshots=screenshots
    )

    assert await _run(service, "/help 999") is None
    html_high = screenshots.calls[-1]
    assert "超出范围" in html_high
    assert "已显示第 2 页" in html_high
    assert _rows(html_high) == 15  # 最接近的合法页，绝不是空白图

    assert await _run(service, "/help 0") is None
    html_low = screenshots.calls[-1]
    assert "超出范围" in html_low
    assert "已显示第 1 页" in html_low
    assert _rows(html_low) == 30


# ── A11：详情卡片 ──


async def test_help_detail_card_fields(tmp_path: Path) -> None:
    command = _command(
        "ping",
        usage="[目标]",
        description="响应测试",
        aliases=("p", "pp"),
        params=(("目标", "可选目标"),),
        source="demo",
    )
    screenshots = FakeScreenshots()
    service, adapter, _, _ = _make_service(
        tmp_path, commands=[command], screenshots=screenshots
    )

    assert await _run(service, "/help ping") is None
    html = screenshots.calls[-1]
    for expected in (
        "/ping",
        "响应测试",
        "所有人",
        "[目标]",
        "/p",
        "/pp",
        "参数",
        "目标",
        "可选目标",
        "demo",
    ):
        assert expected in html, expected
    assert len(adapter.sent) == 1


async def test_help_detail_unknown_command_falls_back(tmp_path: Path) -> None:
    screenshots = FakeScreenshots()
    service, _, _, _ = _make_service(
        tmp_path, commands=[_command("ping")], screenshots=screenshots
    )

    result = await _run(service, "/help nope")

    assert result is not None
    assert "未找到命令" in result


# ── A12：卡片不含 token / 配置值 / 用户标识 ──


async def test_help_card_has_no_secrets(tmp_path: Path) -> None:
    screenshots = FakeScreenshots()
    service, _, _, _ = _make_service(
        tmp_path, commands=[_command("ping", usage="[目标]")], screenshots=screenshots
    )
    # 反断言夹具：配置里塞入 token，并用独特的用户号
    service._config.bot.api_key = "SECRET-TOKEN-abc"
    service._config.chat.web_token = "SECRET-TOKEN-abc"
    stranger = 987654321

    assert await _run(service, "/help", user_id=stranger) is None
    assert await _run(service, "/help ping", user_id=stranger) is None

    assert len(screenshots.calls) >= 2
    for html in screenshots.calls:
        assert "SECRET-TOKEN-abc" not in html
        assert str(stranger) not in html
        assert "api_key" not in html.lower()
        assert "token" not in html.lower()


# ── A13：三级降级 ──


async def test_help_degrades_to_markdown_image(tmp_path: Path) -> None:
    """① HTML 不可用 → 既有 markdown→图片 仍然出图。"""
    converter = FakeConverter(tmp_path / "md")
    service, adapter, _, _ = _make_service(
        tmp_path,
        commands=[_command("ping", usage="[目标]")],
        screenshots=UnavailableScreenshots(),
        converter=converter,
    )

    result = await _run(service, "/help")

    assert result is None
    assert converter.calls and "# 可用命令" in converter.calls[0]
    assert len(adapter.sent) == 1


async def test_help_degrades_to_plain_text(tmp_path: Path) -> None:
    """② 两级图片都不行 → 纯文本交回命令服务（用户一定有反馈）。"""
    service, adapter, _, _ = _make_service(
        tmp_path,
        commands=[_command("ping", usage="[目标]")],
        screenshots=UnavailableScreenshots(),
        converter=FakeConverter(tmp_path / "md", ok=False),
    )

    result = await _run(service, "/help")

    assert result is not None
    assert "可用命令:" in result
    assert "/ping [目标]" in result
    assert adapter.sent == []


# ── A15：第二次 /help 命中缓存 ──


async def test_second_help_hits_cache(tmp_path: Path) -> None:
    screenshots = FakeScreenshots()
    service, adapter, _, _ = _make_service(
        tmp_path,
        commands=[_command("ping"), _command("pong")],
        screenshots=screenshots,
    )

    assert await _run(service, "/help") is None
    assert len(screenshots.calls) == 1
    first_html = screenshots.calls[0]

    assert await _run(service, "/help") is None
    assert len(screenshots.calls) == 1, "第二次必须命中缓存，不再截图"
    assert len(adapter.sent) == 2, "命中缓存也要正常发图"

    cached = list((tmp_path / "help_cache").glob("help-*.png"))
    assert cached, "未命中时渲染结果必须写回缓存"
    index = json.loads(
        (tmp_path / "help_cache" / "index.json").read_text(encoding="utf-8")
    )
    assert len(str(index["fingerprint"])) == 16
    assert index["pages"]["0"] == 1
    assert first_html.count("[权限: ") == _rows(first_html)


# ── A16：三维度内容不同；同维度不同用户复用同一张图 ──


async def test_permission_dimensions_are_separate_and_reused(tmp_path: Path) -> None:
    commands = [
        _command("public", permission=PERM_EVERYONE),
        _command("sub_only", permission=PERM_SUB_ADMIN),
        _command("super_only", permission=PERM_SUPER_ADMIN),
    ]
    screenshots = FakeScreenshots()
    service, _, _, _ = _make_service(
        tmp_path, commands=commands, screenshots=screenshots
    )

    assert await _run(service, "/help", user_id=NOBODY) is None
    html_nobody = screenshots.calls[-1]
    assert "public" in html_nobody
    assert "sub_only" not in html_nobody
    assert "super_only" not in html_nobody

    # 同维度不同用户：复用同一张图（截图计数不增）
    assert await _run(service, "/help", user_id=NOBODY2) is None
    assert len(screenshots.calls) == 1

    assert await _run(service, "/help", user_id=SUB) is None
    html_sub = screenshots.calls[-1]
    assert "public" in html_sub and "sub_only" in html_sub
    assert "super_only" not in html_sub

    assert await _run(service, "/help", user_id=SUPER) is None
    html_super = screenshots.calls[-1]
    assert "super_only" in html_super

    assert len({html_nobody, html_sub, html_super}) == 3, "三个权限维度内容必须不同"

    cached = sorted((tmp_path / "help_cache").glob("help-*.png"))
    assert len(cached) == 3, "每个权限维度各一份缓存"


async def test_prerendered_cache_is_used_after_startup(tmp_path: Path) -> None:
    """启动 / 软重启预渲染后，各权限维度的 /help 直接命中缓存（不再截图）。"""
    from neobot_app.runtime import help_cache

    commands = [
        _command("public"),
        _command("sub_only", permission=PERM_SUB_ADMIN),
        _command("super_only", permission=PERM_SUPER_ADMIN),
    ]
    screenshots = FakeScreenshots()
    service, _, _, registry = _make_service(
        tmp_path, commands=commands, screenshots=screenshots
    )

    stats = await help_cache.prerender_help_menu(
        commands=registry.commands(),
        screenshots=screenshots,
        directory=tmp_path / "help_cache",
    )
    assert stats["rendered"] == 3
    renders = len(screenshots.calls)

    for user_id in (NOBODY, SUB, SUPER):
        assert await _run(service, "/help", user_id=user_id) is None
    assert len(screenshots.calls) == renders, "命中预渲染缓存后不得再截图"


async def test_image_send_failure_falls_through_to_text(tmp_path: Path) -> None:
    """HTML 渲染成功但发图失败时继续降级（不报错、用户仍有反馈）。"""

    class BadAdapter(FakeAdapter):
        async def send(self, conv: Any, segments: list[dict[str, Any]]) -> None:
            raise RuntimeError("发送失败")

    screenshots = FakeScreenshots()
    service, _, _, _ = _make_service(
        tmp_path,
        commands=[_command("ping")],
        screenshots=screenshots,
        adapter=BadAdapter(),
    )

    result = await _run(service, "/help")

    assert result is not None
    assert "可用命令:" in result
    assert screenshots.calls, "渲染本身是成功的，失败发生在发送环节"


# ── A17：指纹失效 / --refresh ──


async def test_plugin_load_unload_changes_fingerprint(tmp_path: Path) -> None:
    screenshots = FakeScreenshots()
    service, _, _, registry = _make_service(
        tmp_path, commands=[_command("ping")], screenshots=screenshots
    )

    assert await _run(service, "/help") is None
    assert len(screenshots.calls) == 1

    registry.register(_command("pong"))  # 模拟插件加载
    assert await _run(service, "/help") is None
    assert len(screenshots.calls) == 2, "命令集变化后旧缓存不得命中"
    html_after_load = screenshots.calls[-1]
    assert "ping" in html_after_load and "pong" in html_after_load

    registry.unregister("pong")  # 模拟插件卸载
    assert await _run(service, "/help") is None
    assert len(screenshots.calls) == 3, "卸载后同样要重渲染"


async def test_help_refresh_requires_sub_admin(tmp_path: Path) -> None:
    screenshots = FakeScreenshots()
    service, _, _, _ = _make_service(
        tmp_path, commands=[_command("ping")], screenshots=screenshots
    )

    result = await _run(service, "/help --refresh", user_id=NOBODY)

    assert result is not None
    assert "没有权限" in result
    assert screenshots.calls == []


async def test_help_refresh_rebuilds_and_prunes(tmp_path: Path) -> None:
    screenshots = FakeScreenshots()
    service, _, _, _ = _make_service(
        tmp_path, commands=[_command("ping")], screenshots=screenshots
    )

    result = await _run(service, "/help --refresh", user_id=SUB)

    assert result is None
    cache_dir = tmp_path / "help_cache"
    index = json.loads((cache_dir / "index.json").read_text(encoding="utf-8"))
    assert set(index["pages"]) == {"0", "1", "2"}, "三个权限维度都要重建"
    assert len(list(cache_dir.glob("help-*.png"))) == 3
    assert len(screenshots.calls) == 3  # 预渲染 3 张（用户请求的那一页命中缓存）

    # 容量上限：塞满垃圾文件后 --refresh 必须淘汰到上限以内
    for i in range(70):
        (cache_dir / f"junk-{i}.png").write_bytes(PNG)
    assert await _run(service, "/help --refresh", user_id=SUB) is None
    assert len(list(cache_dir.glob("*.png"))) <= 60


async def test_out_of_range_page_is_not_cached(tmp_path: Path) -> None:
    """越界页码的卡片带顶部标注，不能被当作普通页写进缓存。"""
    commands = [_command(f"cmd{i:02d}") for i in range(44)]
    screenshots = FakeScreenshots()
    service, _, _, _ = _make_service(
        tmp_path, commands=commands, screenshots=screenshots
    )

    assert await _run(service, "/help 999") is None
    assert "超出范围" in screenshots.calls[-1]

    # 越界卡片带顶部标注，不能被当成普通页写进缓存
    assert list((tmp_path / "help_cache").glob("help-*.png")) == []

    # 再请求第 2 页：仍要重新渲染，且渲染的是不带标注的普通页
    before = len(screenshots.calls)
    assert await _run(service, "/help 2") is None
    assert len(screenshots.calls) == before + 1
    assert "超出范围" not in screenshots.calls[-1]
    assert list((tmp_path / "help_cache").glob("help-0-p2-s30-*.png"))


# ── 卡片美化：三列布局 / 翻页条 / 详情卡标签（本轮新增） ──


def _fake_card_commands(count: int = 35) -> list[Command]:
    base = [
        ("help", "查看命令列表或某个命令的详细用法", "[命令名] [页码]", PERM_EVERYONE, ""),
        ("ping", "连通性测试", "", PERM_EVERYONE, ""),
        ("status", "把控制台运行概况渲染成一张图片", "[概况 用量 插件 错误]", PERM_SUB_ADMIN, "dashboard"),
        ("mg", "小游戏：漂流瓶 / 成语接龙 / 签到 / 抽签", "<游戏> [参数]", PERM_EVERYONE, "minigame"),
    ]
    out: list[Command] = []
    for index in range(count):
        name, desc, usage, permission, source = base[index % len(base)]
        if index >= len(base):
            name = f"{name}_{index // len(base) + 1}"
        out.append(
            _command(name, description=desc, usage=usage, permission=permission, source=source)
        )
    return out


def test_list_card_uses_three_column_command_table() -> None:
    """命令 / 说明 / 权限与来源 三列固定布局：命令列与来源都不再被挤到折行。"""
    from neobot_app.runtime import help_card

    payload = help_card.build_list_payload(_fake_card_commands(), page=1)
    block = payload["blocks"][0]
    assert block["kind"] == "rows"
    assert block["columns"] == ["命令", "说明", "权限 / 来源"]
    assert block["widths"] == ["36%", "42%", "22%"]
    assert block["variant"] == "commands"
    # 权限与来源各成一行（元信息列内堆叠），命令列只有用法文本
    first = block["rows"][0]
    assert first[2][0].startswith("[权限: ")
    assert all(isinstance(line, str) for line in first[2])

    html = help_card.render_payload_html(payload)
    assert 'class="rows rows--commands"' in html
    assert '<col style="width: 36%">' in html and '<col style="width: 22%">' in html
    assert '<span class="cell-line">[权限: ' in html
    assert "[命令名] [页码]" in html  # 用法整体出现在同一列
    assert "来源: minigame" in html


def test_list_card_pager_and_footer_are_not_redundant() -> None:
    """翻页条给页码 + 圆点进度；页脚只留总量与翻页提示（单页不出翻页条）。"""
    from neobot_app.runtime import help_card

    multi = help_card.build_list_payload(_fake_card_commands(35), page=1)
    assert multi["footer"] == "共 35 条 · 用 /help <页码> 翻页"
    assert multi["blocks"][-1] == {"kind": "pager", "page": 1, "pages": 2}

    html = help_card.render_payload_html(multi)
    assert "第 1/2 页" in html
    assert html.count('class="pager-dot is-current"') == 1
    assert html.count("pager-dot") >= 3  # CSS + 2 个圆点

    single = help_card.build_list_payload(_fake_card_commands(4), page=1)
    assert single["footer"] == "共 4 条"
    assert all(block["kind"] != "pager" for block in single["blocks"])
    single_html = help_card.render_payload_html(single)
    assert "第 1/1 页" not in single_html
    assert "翻页" not in single_html


def test_detail_card_uses_mono_usage_and_chip_labels() -> None:
    """详情卡：用法用等宽字体，权限 / 来源用胶囊标签（只影响 HTML 呈现）。"""
    from neobot_app.runtime import help_card

    command = _command("ping", usage="[目标]", source="demo", description="响应测试")
    payload = help_card.build_detail_payload(command)

    # payload 保持纯文本友好的形态，markdown / 纯文本降级不受影响
    kv = payload["blocks"][0]
    assert all(not isinstance(item[1], dict) for item in kv["items"])

    html = help_card.render_payload_html(payload)
    assert "cell--mono" in html and "/ping [目标]" in html
    assert "cell--chip" in html
    assert "| 用法 |" in help_card.render_payload_markdown(payload)


def test_help_cards_are_self_contained_with_theme_art() -> None:
    """美化后仍自包含：主题装饰是内联 SVG，没有外链 / 脚本 / @import。"""
    from neobot_app.runtime import help_card

    list_html = help_card.render_payload_html(
        help_card.build_list_payload(_fake_card_commands(35), page=1)
    )
    detail_html = help_card.render_payload_html(
        help_card.build_detail_payload(_fake_card_commands(1)[0])
    )

    for html in (list_html, detail_html):
        assert html.startswith("<!DOCTYPE html>")
        assert "http://" not in html and "https://" not in html
        assert "<script" not in html.lower() and "<link" not in html.lower()
        assert "@import" not in html
        assert 'class="card-emblem"' in html
