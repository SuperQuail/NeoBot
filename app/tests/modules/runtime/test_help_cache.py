"""spec(5) §4.2：/help 预渲染缓存 runtime/help_cache.py（R9 / A14-A17 的缓存侧）。"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from neobot_app.commands.model import (
    PERM_EVERYONE,
    PERM_SUB_ADMIN,
    PERM_SUPER_ADMIN,
    Command,
)
from neobot_app.runtime import help_cache
from neobot_app.screenshot import ScreenshotResult, UnavailableScreenshots

PNG = b"\x89PNG\r\n\x1a\n" + b"cache-image"


class FakeScreenshots:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def render(self, *, html: str, options: object, base_url: str | None = None):
        self.calls.append(html)
        return ScreenshotResult(PNG, "png", 720, 200, 720.0, 200.0, 1.0)


def _command(
    name: str,
    *,
    permission: int = PERM_EVERYONE,
    usage: str = "",
    description: str | None = None,
) -> Command:
    return Command(
        name=name,
        description=description if description is not None else f"{name} 说明",
        handler=lambda ctx: "x",
        permission=permission,
        usage=usage,
    )


# ── 指纹 ──


def test_fingerprint_matches_spec_formula() -> None:
    commands = [
        _command("b", usage="[x]", description="B 的说明"),
        _command("a", permission=PERM_SUB_ADMIN),
    ]
    rows = sorted([("b", "[x]", "B 的说明", 0), ("a", "", "a 说明", 1)])
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    assert help_cache.command_fingerprint(commands) == expected
    assert len(help_cache.command_fingerprint(commands)) == 16


def test_fingerprint_changes_with_command_set() -> None:
    base = help_cache.command_fingerprint([_command("a")])
    assert help_cache.command_fingerprint([_command("a"), _command("b")]) != base
    assert help_cache.command_fingerprint([_command("a", usage="[x]")]) != base
    assert help_cache.command_fingerprint([_command("a", description="改了")]) != base
    assert (
        help_cache.command_fingerprint([_command("a", permission=PERM_SUB_ADMIN)])
        != base
    )
    assert help_cache.command_fingerprint([_command("a")]) == base


def test_cache_paths_follow_spec_names(tmp_path: Path) -> None:
    listed = help_cache.list_cache_path(
        fingerprint="abc123", perm=1, page=2, size=30, directory=tmp_path
    )
    assert listed.name == "help-1-p2-s30-abc123.png"
    detail = help_cache.detail_cache_path(
        command=_command("ping"), fingerprint="abc123", perm=0, directory=tmp_path
    )
    assert detail.name == "detail-ping-0-abc123.png"


# ── 索引 ──


def test_index_freshness_and_renderer_version(tmp_path: Path, monkeypatch) -> None:
    cache = help_cache.HelpCache(directory=tmp_path)
    cache.write_index(
        {
            "fingerprint": "fp",
            "renderer_version": help_cache.RENDERER_VERSION,
            "size": 30,
            "pages": {},
        }
    )

    assert cache.is_fresh("fp") is True
    assert cache.is_fresh("other") is False

    monkeypatch.setattr(help_cache, "RENDERER_VERSION", "999")
    assert cache.is_fresh("fp") is False, "渲染器版本变化必须让缓存失效"


def test_index_invalid_when_page_size_changes(tmp_path: Path) -> None:
    cache = help_cache.HelpCache(directory=tmp_path)
    cache.write_index(
        {
            "fingerprint": "fp",
            "renderer_version": help_cache.RENDERER_VERSION,
            "size": 10,
            "pages": {},
        }
    )
    assert cache.is_fresh("fp") is False


# ── 读写与容量 ──


def test_list_and_detail_roundtrip(tmp_path: Path) -> None:
    commands = [_command("ping")]
    command = commands[0]
    cache = help_cache.HelpCache(directory=tmp_path)
    fingerprint = help_cache.command_fingerprint(commands)

    assert cache.load_list_image(commands, perm=0, page=1) is None
    cache.store_list_image(PNG, fingerprint=fingerprint, perm=0, page=1, pages=2)
    assert cache.load_list_image(commands, perm=0, page=1) == PNG
    assert cache.load_list_image(commands, perm=1, page=1) is None

    assert cache.load_detail_image(command, perm=0, fingerprint=fingerprint) is None
    cache.store_detail_image(PNG, command=command, perm=0, fingerprint=fingerprint)
    assert (
        cache.load_detail_image(command, perm=0, fingerprint=fingerprint) == PNG
    )


def test_detail_cache_alone_can_be_hit(tmp_path: Path) -> None:
    """只渲染过详情卡片（没预渲染列表）时，第二次也必须命中缓存。"""
    command = _command("ping")
    commands = [command]
    fingerprint = help_cache.command_fingerprint(commands)

    first = help_cache.HelpCache(directory=tmp_path)
    assert first.load_detail_image(command, perm=0, fingerprint=fingerprint) is None
    assert first.store_detail_image(
        PNG, command=command, perm=0, fingerprint=fingerprint
    )
    second = help_cache.HelpCache(directory=tmp_path)
    assert second.load_detail_image(command, perm=0, fingerprint=fingerprint) == PNG


def test_prune_enforces_max_files(tmp_path: Path) -> None:
    cache = help_cache.HelpCache(directory=tmp_path, max_files=5)
    for i in range(9):
        path = tmp_path / f"help-0-p1-s30-fp{i}.png"
        path.write_bytes(PNG)
        os.utime(path, (1000 + i, 1000 + i))

    assert cache.prune() == 4
    assert len(list(tmp_path.glob("*.png"))) == 5
    assert not (tmp_path / "help-0-p1-s30-fp0.png").exists(), "按生成时间淘汰最旧的"
    assert (tmp_path / "help-0-p1-s30-fp8.png").exists()


def test_cleanup_stale_removes_old_fingerprint(tmp_path: Path) -> None:
    cache = help_cache.HelpCache(directory=tmp_path)
    (tmp_path / "help-0-p1-s30-oldfp.png").write_bytes(PNG)
    (tmp_path / "help-0-p1-s30-newfp.png").write_bytes(PNG)
    (tmp_path / "index.json").write_text("{}", encoding="utf-8")

    assert cache.cleanup_stale("newfp") == 1
    assert (tmp_path / "help-0-p1-s30-newfp.png").exists()
    assert not (tmp_path / "help-0-p1-s30-oldfp.png").exists()
    assert (tmp_path / "index.json").exists(), "索引文件不是缓存图片，不参与清理"


# ── A14：预渲染 3 个权限维度 / 失败不影响启动 ──


async def test_prerender_covers_three_permission_dimensions(tmp_path: Path) -> None:
    """A14：启动与软重启后，3 个权限维度的列表图都在缓存目录里。"""
    commands = [
        _command("public"),
        _command("sub_only", permission=PERM_SUB_ADMIN),
        _command("super_only", permission=PERM_SUPER_ADMIN),
    ]
    screenshots = FakeScreenshots()

    stats = await help_cache.prerender_help_menu(
        commands=commands, screenshots=screenshots, directory=tmp_path
    )
    assert stats["failed"] == 0
    assert stats["rendered"] == 3
    assert len(screenshots.calls) == 3
    for perm in (0, 1, 2):
        assert list(tmp_path.glob(f"help-{perm}-p1-s30-*.png")), perm

    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert set(index["pages"]) == {"0", "1", "2"}
    assert index["renderer_version"] == help_cache.RENDERER_VERSION
    assert index["generated_at"]

    # 软重启 = 运行时工厂重建应用后再跑一次同一个协程
    stats2 = await help_cache.prerender_help_menu(
        commands=commands, screenshots=screenshots, directory=tmp_path
    )
    assert stats2["rendered"] == 3
    for perm in (0, 1, 2):
        assert list(tmp_path.glob(f"help-{perm}-p1-s30-*.png")), perm


async def test_prerender_survives_unavailable_screenshots(tmp_path: Path) -> None:
    """A14：强制 UnavailableScreenshots 时预渲染照常结束（只记 warning，不抛）。"""
    stats = await help_cache.prerender_help_menu(
        commands=[_command("a")],
        screenshots=UnavailableScreenshots(),
        directory=tmp_path,
    )

    assert stats["failed"] >= 1
    assert stats["rendered"] == 0
    assert (tmp_path / "index.json").is_file()


async def test_prerender_coro_never_raises(tmp_path: Path) -> None:
    class Boom:
        async def render(self, **kwargs: object):
            raise RuntimeError("boom")

    coro = help_cache.make_prerender_coro(
        commands=lambda: [_command("a")],
        screenshots=Boom(),
        directory=tmp_path,
    )
    await coro  # 预渲染异常绝不能冒泡到启动 / 软重启


async def test_prerender_cleans_old_fingerprint_files(tmp_path: Path) -> None:
    (tmp_path / "help-0-p1-s30-oldfingerprint.png").write_bytes(PNG)
    screenshots = FakeScreenshots()

    stats = await help_cache.prerender_help_menu(
        commands=[_command("a")],
        screenshots=screenshots,
        directory=tmp_path,
    )

    assert stats["stale_removed"] >= 1
    assert not (tmp_path / "help-0-p1-s30-oldfingerprint.png").exists()
