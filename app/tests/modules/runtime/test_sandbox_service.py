"""SandboxService.list_files 路径隔离与 glob 越界防护测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from neobot_app.runtime.sandbox_service import MAX_TEXT_READ_BYTES, SandboxService


def _make_sandbox(tmp_path) -> tuple[SandboxService, object]:
    root = tmp_path / "sandbox"
    root.mkdir(parents=True)
    (root / "a.txt").write_text("in-root", encoding="utf-8")
    (root / "sub").mkdir()
    (root / "sub" / "b.txt").write_text("in-sub", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir(parents=True)
    (outside / "leak.txt").write_text("secret", encoding="utf-8")
    (outside / "leak.md").write_text("secret", encoding="utf-8")
    return SandboxService(sandbox_root=root), outside


async def test_list_files_traversal_pattern_skips_outside(tmp_path):
    sandbox, outside = _make_sandbox(tmp_path)
    root = tmp_path / "sandbox"
    files = await sandbox.list_files(root, pattern="../outside/*.txt")
    assert files == []
    files = await sandbox.list_files(root, pattern="../../outside/*.txt")
    assert files == []


async def test_list_files_traversal_from_subdir_skips_outside(tmp_path):
    sandbox, outside = _make_sandbox(tmp_path)
    sub = tmp_path / "sandbox" / "sub"
    files = await sandbox.list_files(sub, pattern="../../outside/*.txt")
    assert files == []
    files = await sandbox.list_files(sub, pattern="../*.txt")
    assert {f["name"] for f in files} == {"a.txt"}
    files = await sandbox.list_files(sub, pattern="*.txt")
    assert {f["name"] for f in files} == {"b.txt"}


async def test_list_files_absolute_pattern_skips_outside(tmp_path):
    sandbox, outside = _make_sandbox(tmp_path)
    root = tmp_path / "sandbox"
    files = await sandbox.list_files(root, pattern=str(outside / "*.txt"))
    assert files == []


async def test_list_files_normal_pattern_still_works(tmp_path):
    sandbox, _ = _make_sandbox(tmp_path)
    root = tmp_path / "sandbox"
    files = await sandbox.list_files(root, pattern="*.txt")
    assert {f["name"] for f in files} == {"a.txt"}
    files = await sandbox.list_files(root, pattern="**/*.txt")
    assert {f["name"] for f in files} == {"a.txt", "b.txt"}
    assert {f["path"].replace("\\", "/") for f in files} == {"a.txt", "sub/b.txt"}


async def test_list_files_with_pattern_on_allowed_read_dir(tmp_path):
    root = tmp_path / "sandbox"
    root.mkdir(parents=True)
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    (gallery / "g_1.png").write_bytes(b"png-data")
    (gallery / "g_2.png").write_bytes(b"png-data")
    sandbox = SandboxService(sandbox_root=root, allowed_read_dirs=[gallery])
    files = await sandbox.list_files(gallery, pattern="*.png")
    assert {f["name"] for f in files} == {"g_1.png", "g_2.png"}
    assert {f["path"] for f in files} == {"g_1.png", "g_2.png"}


async def test_list_files_without_pattern_works(tmp_path):
    sandbox, _ = _make_sandbox(tmp_path)
    root = tmp_path / "sandbox"
    files = await sandbox.list_files(root)
    names = {f["name"] for f in files}
    assert names == {"a.txt", "sub"}


async def test_write_read_roundtrip_preserves_bytes(tmp_path):
    """Arrange 沙箱与一段 768 字节的二进制载荷，Act write_file 到多层子目录再 read_file，
    Assert 字节内容逐字节一致且父目录被自动创建。"""
    sandbox, _ = _make_sandbox(tmp_path)
    root = tmp_path / "sandbox"
    payload = bytes(range(256)) * 3
    target = root / "deep" / "nested" / "blob.bin"

    await sandbox.write_file(target, payload)

    assert target.is_file()
    data = await sandbox.read_file(target)
    assert data == payload


async def test_delete_file_removes_directory_tree_recursively(tmp_path):
    """Arrange 沙箱内一棵三层目录树，Act delete_file 删除目录节点，
    Assert 整棵子树消失而沙箱根下其他文件不受影响。"""
    sandbox, _ = _make_sandbox(tmp_path)
    root = tmp_path / "sandbox"
    tree = root / "tree"
    (tree / "a" / "b").mkdir(parents=True)
    (tree / "a" / "b" / "c.txt").write_text("c", encoding="utf-8")
    (tree / "top.txt").write_text("t", encoding="utf-8")

    await sandbox.delete_file(tree)

    assert not tree.exists()
    assert (root / "a.txt").is_file()


async def test_delete_file_rejects_path_outside_sandbox(tmp_path):
    """Arrange 沙箱外存在文件，Act delete_file 指向该越界路径，
    Assert 抛出 PermissionError 且外部文件保持原样。"""
    sandbox, outside = _make_sandbox(tmp_path)
    victim = outside / "leak.txt"

    with pytest.raises(PermissionError):
        await sandbox.delete_file(victim)

    assert victim.is_file()


async def test_read_file_truncates_to_max_text_read_bytes(tmp_path):
    """Arrange 一个 2×MAX_TEXT_READ_BYTES 的文本文件，Act read_file 读取，
    Assert 返回内容不超过 MAX_TEXT_READ_BYTES 字节。"""
    sandbox, _ = _make_sandbox(tmp_path)
    root = tmp_path / "sandbox"
    big = root / "big.txt"
    big.write_bytes(b"x" * (MAX_TEXT_READ_BYTES * 2))

    data = await sandbox.read_file(big)

    assert len(data) <= MAX_TEXT_READ_BYTES


async def test_list_files_returns_sandbox_relative_display_paths(tmp_path):
    """Arrange 沙箱根含 a.txt 与 sub/b.txt，Act 不带 pattern 分别列出根与子目录，
    Assert 文件 path 为相对沙箱根的展示路径，目录项 path 为空且 is_dir=True。"""
    sandbox, _ = _make_sandbox(tmp_path)
    root = tmp_path / "sandbox"

    entries = await sandbox.list_files(root)
    by_name = {entry["name"]: entry for entry in entries}

    assert by_name["a.txt"]["path"] == "a.txt"
    assert by_name["a.txt"]["size"] > 0
    assert by_name["sub"]["is_dir"] is True
    assert by_name["sub"]["path"] == ""

    sub_entries = await sandbox.list_files(root / "sub")
    assert sub_entries[0]["name"] == "b.txt"
    assert Path(sub_entries[0]["path"]).as_posix() == "sub/b.txt"
