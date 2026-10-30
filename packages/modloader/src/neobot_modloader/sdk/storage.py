"""声明插件配置/业务数据版本，并用操作系统锁拒绝在线改写持久数据。"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from neobot_modloader.plugins.registration import validate_plugin_name

STATE_FILE = ".neobot-storage.json"


class StorageError(ValueError):
    """存储版本或维护期条件不满足。"""


@dataclass(frozen=True)
class StorageVersion:
    config_version: int = 0
    data_version: int = 0


def read_storage(metadata: dict[str, Any]) -> StorageVersion | None:
    sdk = metadata.get("sdk", {})
    raw = sdk.get("storage") if isinstance(sdk, dict) else None
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) != {"config_version", "data_version"}:
        raise StorageError("sdk.storage 必须声明 config_version 与 data_version")
    if any(type(value) is not int or value < 1 for value in raw.values()):
        raise StorageError("存储版本必须是大于零的整数")
    return StorageVersion(**raw)


def stored_version(data_dir: Path, fallback: StorageVersion) -> StorageVersion:
    path = data_dir / STATE_FILE
    if not path.is_file():
        return fallback
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {"config_version", "data_version"}:
        raise StorageError("插件存储版本记录损坏，请先恢复备份")
    if any(type(value) is not int or value < 1 for value in raw.values()):
        raise StorageError("插件存储版本记录无效")
    return StorageVersion(**raw)


def write_storage(data_dir: Path, value: StorageVersion) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    temporary = data_dir / (STATE_FILE + ".new")
    temporary.write_text(json.dumps(asdict(value), sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(data_dir / STATE_FILE)


class StorageLease:
    """锁在数据目录外，目录切换不会使运行中的宿主丢掉锁。"""

    def __init__(self, data_root: Path, name: str) -> None:
        validate_plugin_name(name)
        self.data_root = data_root.resolve()
        self.name = name
        locks = self.data_root / ".locks"
        locks.mkdir(parents=True, exist_ok=True)
        self.path = locks / f"{name}.lock"
        self._handle = self.path.open("a+b")
        if self.path.stat().st_size == 0:
            self._handle.write(b"\0")
            self._handle.flush()
        self._handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._handle.close()
            raise StorageError("插件数据仍被宿主占用，请退出宿主后执行维护期升级") from exc

    def close(self) -> None:
        if self._handle.closed:
            return
        self._handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self._handle.close()

    def __enter__(self) -> StorageLease:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()


def prepare_runtime_storage(runtime: Any, name: str, path: Path) -> None:
    """存储声明插件只在版本一致时加载，锁保持到宿主运行时释放。"""
    from neobot_modloader.loading.manifest import read_manifest

    if not path.is_dir():
        return
    declared = read_storage(read_manifest(path / "plugin.toml"))
    if declared is None:
        return
    data_dir = runtime._plugin_data_dir(name)
    if data_dir.resolve().is_relative_to(path.resolve()):
        raise StorageError("配置与业务数据必须位于插件代码目录外")
    if name not in runtime._storage_leases:
        runtime._storage_leases[name] = StorageLease(runtime.data_dir, name)
    current = stored_version(data_dir, declared)
    if current != declared:
        raise StorageError("插件配置或数据版本不匹配，请退出宿主后执行维护期升级")
    if not (data_dir / STATE_FILE).is_file():
        write_storage(data_dir, declared)


def close_runtime_storage(runtime: Any) -> None:
    """全部插件卸载后才释放宿主租约，阻止仍持有插件上下文时做维护升级。"""
    if runtime.manager.names():
        raise StorageError("请先卸载全部插件，再关闭存储租约")
    for lease in runtime._storage_leases.values():
        lease.close()
    runtime._storage_leases.clear()
