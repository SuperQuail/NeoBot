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


# ── 工作区排除（agent.sandbox.excluded_workspaces） ──────────────────


def _make_excluded_sandbox(tmp_path) -> tuple[SandboxService, Path, Path]:
    root = tmp_path / "sandbox"
    root.mkdir(parents=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "note.txt").write_text("hello", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir(parents=True)
    (outside / "leak.txt").write_text("secret", encoding="utf-8")
    return (
        SandboxService(sandbox_root=root, excluded_workspaces=[workspace]),
        workspace,
        outside,
    )


def test_excluded_workspaces_property_is_canonical_and_deduplicated(tmp_path):
    """Arrange 同一工作区用两种写法传入，Act 读取生效列表，
    Assert 归一后只剩一份。"""
    root = tmp_path / "sandbox"
    root.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    sandbox = SandboxService(
        sandbox_root=root,
        excluded_workspaces=[workspace, Path(f"{workspace}/")],
    )

    assert sandbox.excluded_workspaces == (workspace.resolve(),)


async def test_excluded_workspace_allows_read_write_through_resolver(tmp_path):
    """Arrange 一个排除工作区，Act 用绝对路径解析并写入不存在的子目录文件再读回，
    Assert 解析落在工作区内、父目录被自动创建、内容一致。"""
    sandbox, workspace, _ = _make_excluded_sandbox(tmp_path)
    target = workspace / "deep" / "out.txt"

    resolved = sandbox.resolve_agent_path(
        str(target), owner="alice", chat_flow_id="group:1", write=True
    )
    assert resolved == target.resolve()

    await sandbox.write_file(resolved, b"payload")

    assert target.read_bytes() == b"payload"
    assert await sandbox.read_file(target) == b"payload"


async def test_excluded_workspace_allows_delete_move_copy_and_list(tmp_path):
    """Arrange 工作区内已有文件，Act 依次移动、复制、列目录、删除，
    Assert 四项操作都成功且文件系统状态符合预期。"""
    sandbox, workspace, _ = _make_excluded_sandbox(tmp_path)
    src = workspace / "note.txt"
    moved = workspace / "moved.txt"
    copied = workspace / "copy.txt"

    await sandbox.move_file(src, moved)
    assert moved.is_file() and not src.exists()

    await sandbox.copy_file(moved, copied)
    assert copied.read_text(encoding="utf-8") == "hello"

    entries = await sandbox.list_files(workspace)
    assert {entry["name"] for entry in entries} >= {"moved.txt", "copy.txt"}

    await sandbox.delete_file(copied)
    assert not copied.exists()


async def test_paths_outside_excluded_workspace_stay_denied(tmp_path):
    """Arrange 排除工作区之外的另一个目录，Act 尝试解析与删除其中的文件，
    Assert 仍然 PermissionError 且文件原样保留。"""
    sandbox, _, outside = _make_excluded_sandbox(tmp_path)

    with pytest.raises(PermissionError):
        sandbox.resolve_agent_path(
            str(outside / "leak.txt"), owner="alice", chat_flow_id="group:1", write=True
        )
    with pytest.raises(PermissionError):
        await sandbox.delete_file(outside / "leak.txt")

    assert (outside / "leak.txt").is_file()


async def test_excluded_workspace_symlink_inside_allowed_outside_denied(tmp_path):
    """Arrange 工作区内两个指向不同位置的符号链接，Act 分别解析，
    Assert 指回工作区内部的放行（归一到真实文件），指向外部的拒绝。"""
    sandbox, workspace, outside = _make_excluded_sandbox(tmp_path)
    inside_link = workspace / "inside-link.txt"
    outside_link = workspace / "outside-link.txt"
    try:
        inside_link.symlink_to(workspace / "note.txt")
        outside_link.symlink_to(outside / "leak.txt")
    except OSError:
        pytest.skip("host does not grant symlink creation")

    resolved = sandbox.resolve_agent_path(
        str(inside_link), owner="alice", chat_flow_id="group:1"
    )
    assert resolved == (workspace / "note.txt").resolve()

    with pytest.raises(PermissionError):
        sandbox.resolve_agent_path(
            str(outside_link), owner="alice", chat_flow_id="group:1"
        )


async def test_excluded_workspace_sibling_prefix_directory_denied(tmp_path):
    """Arrange 与工作区同名前缀的兄弟目录（workspace-evil），Act 尝试读写其中的文件，
    Assert 逐段包含判断正确拒绝，文件保持原样。"""
    sandbox, _, _ = _make_excluded_sandbox(tmp_path)
    evil = tmp_path / "workspace-evil"
    evil.mkdir()
    (evil / "x.txt").write_text("x", encoding="utf-8")

    with pytest.raises(PermissionError):
        sandbox.resolve_agent_path(
            str(evil / "x.txt"), owner="alice", chat_flow_id="group:1", write=True
        )
    with pytest.raises(PermissionError):
        await sandbox.delete_file(evil / "x.txt")

    assert (evil / "x.txt").is_file()


async def test_excluded_workspace_root_cannot_be_deleted_or_moved(tmp_path):
    """Arrange 一个排除工作区，Act 直接把工作区根交给删除与移动，
    Assert 两者都被拒绝，工作区内容原样保留。"""
    sandbox, workspace, _ = _make_excluded_sandbox(tmp_path)
    moved_target = tmp_path / "moved-workspace"

    with pytest.raises(PermissionError):
        await sandbox.delete_file(workspace)
    with pytest.raises(PermissionError):
        await sandbox.move_file(workspace, moved_target)

    assert workspace.is_dir()
    assert (workspace / "note.txt").is_file()
    assert not moved_target.exists()


async def test_readonly_whitelist_wins_inside_excluded_workspace(tmp_path):
    """Arrange 只读目录落在排除工作区内部，Act 尝试写/删该目录里的文件，
    Assert 只读白名单优先：读放行、写与删都被拒绝，内容不变。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    assets = workspace / "assets"
    assets.mkdir()
    (assets / "a.png").write_bytes(b"png")
    sandbox = SandboxService(
        sandbox_root=tmp_path / "sandbox",
        allowed_read_dirs=[assets],
        excluded_workspaces=[workspace],
    )

    assert sandbox.is_path_allowed(assets / "a.png")
    with pytest.raises(PermissionError):
        sandbox.resolve_agent_path(
            str(assets / "a.png"), owner="alice", chat_flow_id="group:1", write=True
        )
    with pytest.raises(PermissionError):
        await sandbox.write_file(assets / "a.png", b"changed")
    with pytest.raises(PermissionError):
        await sandbox.delete_file(assets / "a.png")

    assert (assets / "a.png").read_bytes() == b"png"


async def test_external_symlink_into_excluded_workspace_resolves_inside(tmp_path):
    """Arrange 工作区外一个指向工作区内文件的符号链接，Act 解析该链接，
    Assert 按 realpath 语义落到工作区内（目标仍在工作区内，不算越界）。"""
    sandbox, workspace, outside = _make_excluded_sandbox(tmp_path)
    bridge = outside / "bridge.txt"
    try:
        bridge.symlink_to(workspace / "note.txt")
    except OSError:
        pytest.skip("host does not grant symlink creation")

    resolved = sandbox.resolve_agent_path(
        str(bridge), owner="alice", chat_flow_id="group:1", write=True
    )

    assert resolved == (workspace / "note.txt").resolve()
