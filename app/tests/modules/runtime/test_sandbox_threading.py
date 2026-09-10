"""沙箱文件操作必须真正离开事件循环。

sandbox_service 里的 read_file/write_file/delete_file/list_files/move_file/
copy_file 原先声明为 async 但内部零 await：同步磁盘 IO（含 rmtree/move/copyfile）
实际跑在事件循环线程上，慢盘或大目录会卡住整个 Bot。
"""

from __future__ import annotations

import threading

import pytest


async def test_file_ops_run_in_worker_thread(make_sandbox) -> None:
    sandbox = make_sandbox()
    loop_thread = threading.get_ident()
    threads_seen: list[int] = []

    original_write = sandbox._write_file_sync
    original_read = sandbox._read_file_sync

    def _write_spy(path, data):
        threads_seen.append(threading.get_ident())
        return original_write(path, data)

    def _read_spy(path):
        threads_seen.append(threading.get_ident())
        return original_read(path)

    sandbox._write_file_sync = _write_spy
    sandbox._read_file_sync = _read_spy

    target = sandbox.resolve_path("note.txt")
    await sandbox.write_file(target, b"hello")
    assert await sandbox.read_file(target) == b"hello"

    assert threads_seen, "同步实现没有被调用"
    assert all(ident != loop_thread for ident in threads_seen), (
        "文件操作仍在事件循环线程上执行"
    )


async def test_directory_ops_are_offloaded(make_sandbox) -> None:
    sandbox = make_sandbox()
    loop_thread = threading.get_ident()
    threads_seen: list[int] = []

    original_list = sandbox._list_files_sync
    original_delete = sandbox._delete_file_sync

    def _list_spy(path, pattern=None):
        threads_seen.append(threading.get_ident())
        return original_list(path, pattern)

    def _delete_spy(path):
        threads_seen.append(threading.get_ident())
        return original_delete(path)

    sandbox._list_files_sync = _list_spy
    sandbox._delete_file_sync = _delete_spy

    folder = sandbox.resolve_path("sub")
    await sandbox.write_file(folder / "a.txt", b"x")
    listing = await sandbox.list_files(folder)
    assert [item["name"] for item in listing] == ["a.txt"]

    await sandbox.delete_file(folder)
    with pytest.raises(FileNotFoundError):
        await sandbox.read_file(folder / "a.txt")

    assert threads_seen
    assert all(ident != loop_thread for ident in threads_seen)


async def test_permission_errors_still_propagate(make_sandbox) -> None:
    """线程化不能吞掉异常：越界路径仍要抛 PermissionError。"""
    sandbox = make_sandbox()

    with pytest.raises(PermissionError):
        await sandbox.read_file(sandbox.resolve_path("..") / "outside.txt")
