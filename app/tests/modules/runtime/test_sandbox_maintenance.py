"""沙箱维护命名回归：保留 Unicode、拒绝空主名且不覆盖已有目标。"""

from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from neobot_app.runtime import sandbox_maintenance
from neobot_app.runtime.sandbox_maintenance import (
    SandboxMaintenanceManager,
    _to_snake_case,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("天天星消乐", "天天星消乐"),
        ("游戏Demo", "游戏Demo"),
        ("中文 Tool V2", "中文 Tool V2"),
        ("caféDemo", "caféDemo"),
        ("cafe\u0301Demo", "cafe\u0301Demo"),
        ("🎮", "🎮"),
        ("___", "___"),
        ("---", "---"),
        ("", ""),
        ("HelloWorld", "hello_world"),
        ("HTTPServer", "http_server"),
        ("My Tool", "my_tool"),
        ("snake_case", "snake_case"),
    ],
)
def test_to_snake_case_preserves_unicode_and_empty_conversion(name, expected):
    assert _to_snake_case(name) == expected
    assert _to_snake_case(expected) == expected


@pytest.mark.parametrize("section", ["tools", "docs", "assets"])
async def test_maintenance_preserves_unicode_names_and_storage_index(tmp_path, section):
    root = tmp_path / "sandbox"
    directory = root / section
    directory.mkdir(parents=True)
    names = [
        "天天星消乐.html",
        "中文工具.py",
        "游戏Demo.html",
        "中文 Tool V2.HTML",
        "caféDemo.txt",
        "cafe\u0301Demo.txt",
        "🎮.html",
        "HelloWorld.中文",
        "天天星消乐",
    ]
    for name in names:
        (directory / name).write_text(f"content:{name}", encoding="utf-8")
    manager = SandboxMaintenanceManager(root)

    result = await manager.run_once(force=True)

    assert result["ok"] is True
    assert result["renamed"] == []
    assert result["removed"] == []
    assert {path.name for path in directory.iterdir()} == set(names)
    index = (root / "文件存储.md").read_text(encoding="utf-8")
    for name in names:
        assert (directory / name).read_text(encoding="utf-8") == f"content:{name}"
        assert f"`{name}`" in index
    assert not (directory / ".html").exists()
    assert (await manager.run_once(force=True))["renamed"] == []


@pytest.mark.parametrize("name", ["___.html", "---.html", "!!!.html", "___", ".html", "prepared"])
async def test_maintenance_does_not_create_empty_or_hidden_names(tmp_path, name):
    directory = tmp_path / "tools"
    directory.mkdir()
    source = directory / name
    source.write_bytes(b"original")

    result = await SandboxMaintenanceManager(tmp_path).run_once(force=True)

    assert result["renamed"] == []
    assert source.read_bytes() == b"original"
    assert [path.name for path in directory.iterdir()] == [name]


async def test_maintenance_normalizes_ascii_without_changing_suffix(tmp_path):
    directory = tmp_path / "tools"
    directory.mkdir()
    (directory / "HelloWorld.HTML").write_bytes(b"content")
    (directory / "already-valid.py").write_bytes(b"valid")
    nested = directory / "nested"
    nested.mkdir()
    (nested / "NestedFile.html").write_bytes(b"nested")
    manager = SandboxMaintenanceManager(tmp_path)

    result = await manager.run_once(force=True)

    assert result["renamed"] == ["tools/HelloWorld.HTML -> hello_world.HTML"]
    assert (directory / "hello_world.HTML").read_bytes() == b"content"
    assert not (directory / "HelloWorld.HTML").exists()
    assert (directory / "already-valid.py").read_bytes() == b"valid"
    assert (nested / "NestedFile.html").read_bytes() == b"nested"
    assert (await manager.run_once(force=True))["renamed"] == []


@pytest.mark.parametrize("target_is_directory", [False, True])
async def test_maintenance_never_overwrites_existing_target(tmp_path, target_is_directory):
    directory = tmp_path / "tools"
    directory.mkdir()
    source = directory / "HelloWorld.html"
    target = directory / "hello_world.html"
    source.write_bytes(b"source")
    if target_is_directory:
        target.mkdir()
        (target / "keep.txt").write_bytes(b"target")
    else:
        target.write_bytes(b"target")

    result = await SandboxMaintenanceManager(tmp_path).run_once(force=True)

    assert result["renamed"] == []
    assert source.read_bytes() == b"source"
    target_file = target / "keep.txt" if target_is_directory else target
    assert target_file.read_bytes() == b"target"


@pytest.mark.parametrize("invalid_stem", ["", ".html", "../outside", "sub/file"])
def test_naming_rejects_invalid_converter_output(tmp_path, monkeypatch, invalid_stem):
    source = tmp_path / "HelloWorld.html"
    source.write_bytes(b"source")
    monkeypatch.setattr(sandbox_maintenance, "_to_snake_case", lambda _: invalid_stem)
    result = {"renamed": []}

    SandboxMaintenanceManager(tmp_path)._check_file_naming(source, "tools", result)

    assert source.read_bytes() == b"source"
    assert result["renamed"] == []


def test_naming_does_not_overwrite_dangling_symlink(tmp_path):
    # Mock 路径以便 Windows 无创建符号链接权限时也验证占用检查。
    source = Mock(spec=Path)
    source.name, source.stem, source.suffix = "HelloWorld.html", "HelloWorld", ".html"
    source.is_symlink.return_value = False
    target = Mock(spec=Path)
    target.exists.return_value = False
    target.is_symlink.return_value = True
    source.parent = MagicMock(spec=Path)
    source.parent.__truediv__.return_value = target
    result = {"renamed": []}

    SandboxMaintenanceManager(tmp_path)._check_file_naming(source, "tools", result)

    source.rename.assert_not_called()
    assert result["renamed"] == []


def test_naming_preserves_source_symlink(tmp_path):
    source = Mock(spec=Path)
    source.name = "HelloWorld.html"
    source.is_symlink.return_value = True
    result = {"renamed": []}

    SandboxMaintenanceManager(tmp_path)._check_file_naming(source, "tools", result)

    source.rename.assert_not_called()
    assert result["renamed"] == []
