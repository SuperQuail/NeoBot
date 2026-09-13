"""spec(4) Part D：插件 ID 冲突（R27 / D24 / A67-A69）。

冲突即拒绝 + 面板三选一 + 官方 ID 保留字；未确认替换时磁盘必须零变化
（不删、不覆盖、不产生备份）。
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from neobot_modloader.installer import PluginInstaller


def write_plugin(root: Path, name: str, *, version: str = "0.1.0", repo: str = "") -> Path:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    lines = [f'name = "{name}"', f'version = "{version}"']
    if repo:
        lines.append(f'repo = "{repo}"')
    (directory / "plugin.toml").write_text(
        "\n".join([*lines, "", "[config]", 'value = "ok"', ""]), encoding="utf-8"
    )
    (directory / "__init__.py").write_text("VALUE = 'old'\n", encoding="utf-8")
    return directory


def build_zip(name: str, version: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{name}-main/plugin.toml", f'name = "{name}"\nversion = "{version}"\n')
        archive.writestr(f"{name}-main/__init__.py", "VALUE = 'new'\n")
    return buffer.getvalue()


def fetcher_for(name: str, version: str):
    archive = build_zip(name, version)

    async def fetcher(url: str) -> bytes:
        return archive

    return fetcher


def test_probe_reports_free_id(tmp_path: Path) -> None:
    installer = PluginInstaller(plugin_dir=tmp_path / "plugins")
    report = installer.probe("demo")
    assert report["conflict"] is False
    assert report["existing"] is None


def test_probe_reports_installed_source_and_version(tmp_path: Path) -> None:
    """A67：探测已存在的 ID 时带回版本与来源。"""
    plugins = tmp_path / "plugins"
    write_plugin(plugins, "demo", version="1.2.3", repo="owner/demo")
    installer = PluginInstaller(plugin_dir=plugins)

    report = installer.probe("demo")

    assert report["conflict"] is True
    assert report["official"] is False
    assert report["existing"]["version"] == "1.2.3"
    assert report["existing"]["repo"] == "owner/demo"


def test_probe_reports_official_reserved_id(tmp_path: Path) -> None:
    """A69：官方插件 ID 是保留字。"""
    official = tmp_path / "official"
    write_plugin(official, "dashboard", version="1.0.0")
    installer = PluginInstaller(
        plugin_dir=tmp_path / "plugins", official_plugin_dirs=(official,)
    )

    report = installer.probe("dashboard")

    assert report["conflict"] is True
    assert report["official"] is True
    assert "官方插件随本体更新" in report["message"]


async def test_existing_id_is_rejected_with_zero_disk_change(tmp_path: Path) -> None:
    """A67：ID 冲突且未确认替换 -> 结构化冲突 + 磁盘零变化。"""
    plugins = tmp_path / "plugins"
    target = write_plugin(plugins, "demo", version="1.0.0", repo="owner/demo")
    original = (target / "__init__.py").read_text(encoding="utf-8")
    installer = PluginInstaller(
        plugin_dir=plugins, fetcher=fetcher_for("demo", "2.0.0")
    )

    result = await installer.install("owner/demo")

    assert result.ok is False
    assert result.conflict is not None
    assert result.conflict["kind"] == "existing_plugin"
    assert result.conflict["existing"]["version"] == "1.0.0"
    assert result.conflict["existing"]["repo"] == "owner/demo"
    assert result.conflict["requested"]["version"] == "2.0.0"
    assert "只能二选一" in result.conflict["message"]
    # 磁盘零变化：不删、不覆盖、不产生备份
    assert (target / "__init__.py").read_text(encoding="utf-8") == original
    assert (target / "plugin.toml").read_text(encoding="utf-8").find("1.0.0") >= 0
    assert not (tmp_path / ".plugin-backups").exists()


async def test_dry_run_probes_without_writing(tmp_path: Path) -> None:
    """A67：dry_run=true 只探测不写盘。"""
    plugins = tmp_path / "plugins"
    target = write_plugin(plugins, "demo", version="1.0.0")
    installer = PluginInstaller(
        plugin_dir=plugins, fetcher=fetcher_for("demo", "2.0.0")
    )

    result = await installer.install("owner/demo", dry_run=True)

    assert result.ok is True
    assert result.dry_run is True
    assert result.conflict is not None
    assert result.version == "2.0.0"
    assert (target / "__init__.py").read_text(encoding="utf-8") == "VALUE = 'old'\n"
    assert not (tmp_path / ".plugin-backups").exists()


async def test_dry_run_reports_no_conflict_for_fresh_id(tmp_path: Path) -> None:
    installer = PluginInstaller(
        plugin_dir=tmp_path / "plugins", fetcher=fetcher_for("fresh", "1.0.0")
    )

    result = await installer.install("owner/fresh", dry_run=True)

    assert result.ok is True
    assert result.dry_run is True
    assert result.conflict is None
    assert not (tmp_path / "plugins" / "fresh").exists()


async def test_explicit_replace_backs_up_and_reports_backup_path(tmp_path: Path) -> None:
    """A68：显式选择替换 -> 走既有备份路径并回显 backup_path。"""
    plugins = tmp_path / "plugins"
    target = write_plugin(plugins, "demo", version="1.0.0")
    installer = PluginInstaller(
        plugin_dir=plugins, fetcher=fetcher_for("demo", "2.0.0")
    )

    result = await installer.install("owner/demo", replace=True)

    assert result.ok is True
    assert result.backup_path is not None and result.backup_path.is_dir()
    assert (result.backup_path / "__init__.py").read_text(encoding="utf-8") == "VALUE = 'old'\n"
    assert (target / "__init__.py").read_text(encoding="utf-8") == "VALUE = 'new'\n"
    assert result.version == "2.0.0"


async def test_official_id_is_rejected(tmp_path: Path) -> None:
    """A69：目标 ID 与官方插件同名 -> 直接拒绝，文案指向「官方插件随本体更新」。"""
    official = tmp_path / "official"
    official_target = write_plugin(official, "dashboard", version="1.0.0")
    plugins = tmp_path / "plugins"
    installer = PluginInstaller(
        plugin_dir=plugins,
        official_plugin_dirs=(official,),
        fetcher=fetcher_for("dashboard", "9.9.9"),
    )

    result = await installer.install("evil/dashboard")

    assert result.ok is False
    assert result.conflict is not None
    assert result.conflict["kind"] == "official"
    assert result.conflict["reserved"] is True
    assert "官方插件随本体更新" in (result.error or "")
    assert not (plugins / "dashboard").exists()
    assert (official_target / "__init__.py").read_text(encoding="utf-8") == "VALUE = 'old'\n"
    assert not (tmp_path / ".plugin-backups").exists()


async def test_official_id_rejected_even_when_replace(tmp_path: Path) -> None:
    official = tmp_path / "official"
    write_plugin(official, "dashboard", version="1.0.0")
    installer = PluginInstaller(
        plugin_dir=tmp_path / "plugins",
        official_plugin_dirs=(official,),
        fetcher=fetcher_for("dashboard", "9.9.9"),
    )

    result = await installer.install("evil/dashboard", replace=True)

    assert result.ok is False
    assert "官方插件随本体更新" in (result.error or "")


if __name__ == "__main__":  # pragma: no cover
    import sys

    import pytest

    sys.exit(pytest.main([__file__]))
