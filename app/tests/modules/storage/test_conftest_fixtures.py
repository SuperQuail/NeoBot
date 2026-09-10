"""conftest 的共享 fixture 必须真的可用。

storage_engine 之前写成 `engine = await create_engine(...)`，而 create_engine 是
同步函数（返回 AsyncEngine）；由于一直没有任何测试使用它，这个错误长期隐藏。
"""

from __future__ import annotations


async def test_storage_engine_and_uow_factory_are_usable(
    storage_engine, storage_uow_factory
) -> None:
    assert storage_engine is not None

    async with storage_uow_factory() as uow:
        assert uow is not None
        assert hasattr(uow, "commit")


async def test_make_sandbox_fixture_is_usable(make_sandbox, tmp_path) -> None:
    sandbox = make_sandbox()

    target = sandbox.resolve_path("hello.txt")
    await sandbox.write_file(target, b"hi")

    assert await sandbox.read_file(target) == b"hi"
