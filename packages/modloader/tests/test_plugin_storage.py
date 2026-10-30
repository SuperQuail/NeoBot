"""存储版本与维护期锁应在真实文件上生效。"""

import pytest

from neobot_modloader.sdk.storage import (
    StorageError,
    StorageLease,
    StorageVersion,
    read_storage,
    stored_version,
    write_storage,
)
from runtime_regression_helpers import make_plugin, make_runtime, start_runtime


def test_storage_lease_blocks_second_owner_and_releases(tmp_path):
    first = StorageLease(tmp_path, "demo")
    try:
        with pytest.raises(StorageError, match="退出宿主"):
            StorageLease(tmp_path, "demo")
    finally:
        first.close()
    with StorageLease(tmp_path, "demo"):
        pass


def test_storage_versions_are_written_outside_plugin_code(tmp_path):
    expected = StorageVersion(1, 2)
    write_storage(tmp_path, expected)
    assert stored_version(tmp_path, StorageVersion()) == expected
    assert read_storage({"sdk": {"storage": {"config_version": 1, "data_version": 2}}}) == expected


async def test_declared_storage_plugin_keeps_host_lease(tmp_path):
    plugin = make_plugin(tmp_path / "plugins", "demo")
    manifest = plugin / "plugin.toml"
    manifest.write_text(
        manifest.read_text() + "\n[sdk]\nversion = 1\n[sdk.storage]\nconfig_version = 1\ndata_version = 1\n"
    )
    runtime = make_runtime(tmp_path)
    await start_runtime(runtime)
    try:
        with pytest.raises(StorageError, match="退出宿主"):
            StorageLease(runtime.data_dir, "demo")
    finally:
        await runtime.stop_all()
        for lease in runtime._storage_leases.values():
            lease.close()
