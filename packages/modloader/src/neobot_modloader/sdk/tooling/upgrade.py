"""停机维护期升级最终包，配置、数据和代码作为一次切换恢复。"""

from __future__ import annotations

import asyncio
import hashlib
import shutil
import tempfile
import uuid
from contextlib import ExitStack
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any

from neobot_contracts.ports.plugin import PluginState
from neobot_modloader.installer import MAX_ARCHIVE_BYTES, PluginInstaller
from neobot_modloader.loading.manifest import read_manifest
from neobot_modloader.plugins.registration import validate_plugin_name
from neobot_modloader.runtime import PluginRuntime
from neobot_modloader.sdk.migrations import migrate_storage
from neobot_modloader.sdk.storage import StorageLease, StorageVersion, read_storage, stored_version

from .models import ToolingError, ToolReport
from .smoke import _Adapter, _LoggerFactory, _close_runtime
from .validation import check_project
from .upgrade_host import upgrade_host_plan


@dataclass(frozen=True)
class UpgradeReport(ToolReport):
    backup_paths: tuple[str, ...] = ()
    restored: bool = False
    migrations: tuple[str, ...] = ()


@dataclass(frozen=True)
class _CandidatePlugin:
    """已安装且通过静态检查的候选，代码目录在外层暂存期内有效。"""

    path: Path
    metadata: dict[str, Any]
    storage: StorageVersion


def _owned(root: Path, name: str) -> Path:
    path = root / name
    if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(root.resolve()):
        raise ToolingError("升级路径不在声明的插件或数据目录内")
    return path


def _copy_data(source: Path, target: Path) -> None:
    if not source.exists():
        target.mkdir(parents=True)
        return
    for item in source.rglob("*"):
        if item.is_symlink() or item.is_junction():
            raise ToolingError("维护期数据快照不支持符号链接或 junction")
    shutil.copytree(source, target)


def _runtime(plugin_dir: Path, data_root: Path, builtin_dirs: tuple[Path, ...]) -> PluginRuntime:
    return PluginRuntime(
        plugin_dir=plugin_dir,
        data_dir=data_root,
        builtin_plugin_dirs=builtin_dirs,
        adapter=_Adapter(),
        logger_factory=_LoggerFactory(),
        host_version=version("neobot-modloader"),
    )


async def _verify(
    plugin_dir: Path, data_root: Path, name: str, lease: StorageLease, builtin_dirs: tuple[Path, ...] = ()
) -> None:
    runtime = _runtime(plugin_dir, data_root, builtin_dirs)
    runtime._storage_leases[name] = lease
    with ExitStack() as plans:
        try:
            plan = plans.enter_context(upgrade_host_plan(runtime, plugin_dir / name, name))
            for entry in plan:
                result = await runtime._activate_loaded_plugin(entry, start=True, auto_install_dependencies=False)
                record = runtime.manager.get_record(entry.name)
                if (
                    not result.ok
                    or record is None
                    or record.state is not PluginState.RUNNING
                    or record.error is not None
                ):
                    raise ToolingError(f"新版本启动验收失败 ({entry.name}): {result.error or result.state}")
                if runtime.plugin_config_error(entry.name):
                    raise ToolingError(f"迁移后的配置未通过插件模型校验: {entry.name}")
        finally:
            # 外层维护事务持有租约；先停插件，再清除仍可能被卸载钩子导入的模块。
            runtime._storage_leases.pop(name, None)
            cleanup = asyncio.create_task(_close_runtime(runtime))
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                await asyncio.shield(cleanup)
                raise


class _Upgrade:
    def __init__(self, plugin_root: Path, data_root: Path, name: str, builtin_dirs: tuple[Path, ...]) -> None:
        self.plugin_root = plugin_root
        self.data_root = data_root
        self.name = name
        self.builtin_dirs = builtin_dirs
        self.code = _owned(plugin_root, name)
        self.data = _owned(data_root, name)
        transaction = name + "-" + uuid.uuid4().hex
        self.code_backup = plugin_root.parent / ".plugin-upgrades" / transaction / "code"
        self.data_backup = data_root.parent / ".plugin-upgrades" / transaction / "data"
        self.checks: list[str] = []
        self.applied: tuple[str, ...] = ()
        self.data_swapped = False
        self.restored = False

    async def restore(self, lease: StorageLease) -> None:
        if self.data_backup.exists() or self.data_swapped:
            if self.data.exists():
                self.data.rename(self.data_backup.with_name("failed-data"))
            if self.data_backup.exists():
                self.data_backup.rename(self.data)
        if self.code_backup.exists():
            if self.code.exists():
                self.code.rename(self.code_backup.with_name("failed-code"))
            self.code_backup.rename(self.code)
            await _verify(self.plugin_root, self.data_root, self.name, lease, self.builtin_dirs)
        self.restored = True
        self.checks.append("rollback")

    async def _prepare_candidate(self, directory: Path, archive: bytes) -> _CandidatePlugin:
        async def fetcher(url: str) -> bytes:
            return archive

        installer = PluginInstaller(plugin_dir=directory / "plugins", fetcher=fetcher)
        installed = await installer.install("sdk-maintenance/package", expected_name=self.name)
        if not installed.ok or installed.path is None:
            raise ToolingError(f"候选包安装失败: {installed.error}")
        report = check_project(installed.path)
        if not report.ok:
            raise ToolingError("候选包无效: " + "; ".join(report.errors))
        metadata = read_manifest(installed.path / "plugin.toml")
        target = read_storage(metadata)
        if target is None:
            raise ToolingError("新版本必须明确声明 sdk.storage")
        self.checks.append("candidate")
        return _CandidatePlugin(installed.path, metadata, target)

    async def _stage_data(self, candidate: _CandidatePlugin, staged_data: Path, previous: StorageVersion) -> None:
        _copy_data(self.data, staged_data)
        self.applied = await migrate_storage(
            candidate.path, staged_data, candidate.metadata, previous, candidate.storage
        )
        self.checks.append("migrations")

    async def _switch_and_verify(self, candidate: Path, staged_data: Path, lease: StorageLease) -> None:
        self.code_backup.parent.mkdir(parents=True, exist_ok=True)
        self.data_backup.parent.mkdir(parents=True, exist_ok=True)
        # 切换开始后，包括取消在内的失败都必须等代码与数据回滚完成再向外传播。
        try:
            self.code.rename(self.code_backup)
            candidate.rename(self.code)
            if self.data.exists():
                self.data.rename(self.data_backup)
            staged_data.rename(self.data)
            self.data_swapped = True
            self.checks.append("switch")
            await _verify(self.plugin_root, self.data_root, self.name, lease, self.builtin_dirs)
            self.checks.append("start")
        except BaseException:
            task = asyncio.create_task(self.restore(lease))
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                await asyncio.shield(task)
            raise

    async def run(self, archive: bytes, lease: StorageLease) -> None:
        old_metadata = read_manifest(self.code / "plugin.toml")
        previous = read_storage(old_metadata)
        if previous is None:
            raise ToolingError("维护期升级只支持声明 sdk.storage 的历史版本；未声明存储的旧插件需先制定迁移方案")
        if old_metadata.get("name") != self.name or stored_version(self.data, previous) != previous:
            raise ToolingError("历史版本清单与插件身份或已记录的数据版本不一致，请先恢复匹配的历史版本")
        self.checks.append("maintenance_lease")
        with tempfile.TemporaryDirectory(prefix=".upgrade-code-", dir=self.plugin_root.parent) as code_tmp:
            candidate = await self._prepare_candidate(Path(code_tmp), archive)
            runtime = _runtime(self.plugin_root, self.data_root, self.builtin_dirs)
            with upgrade_host_plan(runtime, self.code, self.name):
                pass
            with upgrade_host_plan(runtime, candidate.path, self.name):
                pass
            self.checks.append("dependencies")
            with tempfile.TemporaryDirectory(prefix=".upgrade-data-", dir=self.data_root.parent) as data_tmp:
                staged_data = Path(data_tmp) / self.name
                await self._stage_data(candidate, staged_data, previous)
                await self._switch_and_verify(candidate.path, staged_data, lease)
        self.checks.append("external_data")


async def upgrade_package(
    path: Path,
    *,
    plugin_dir: Path,
    data_dir: Path,
    name: str,
    timeout: float = 30.0,
    builtin_plugin_dirs: tuple[Path, ...] = (),
) -> UpgradeReport:
    """宿主退出后执行；启动验证使用模拟适配器，不承诺在线无中断升级。"""
    checks: tuple[str, ...] = ()
    errors: list[str] = []
    digest = ""
    upgrade: _Upgrade | None = None
    try:
        validate_plugin_name(name)
        if timeout <= 0:
            raise ToolingError("timeout 必须大于零")
        package = Path(path).resolve()
        if not package.is_file() or package.stat().st_size > MAX_ARCHIVE_BYTES:
            raise ToolingError("升级包不存在或超过体积上限")
        archive = package.read_bytes()
        if len(archive) > MAX_ARCHIVE_BYTES:
            raise ToolingError("升级包超过体积上限")
        digest = hashlib.sha256(archive).hexdigest()
        plugin_root, data_root = plugin_dir.resolve(), data_dir.resolve()
        if not plugin_root.is_dir() or not (plugin_root / name).is_dir():
            raise ToolingError("未找到已安装的历史插件目录")
        if data_root.is_relative_to(plugin_root):
            raise ToolingError("配置与业务数据必须位于插件代码目录外")
        data_root.mkdir(parents=True, exist_ok=True)
        upgrade = _Upgrade(plugin_root, data_root, name, tuple(Path(item).resolve() for item in builtin_plugin_dirs))
        with StorageLease(data_root, name) as lease:
            async with asyncio.timeout(timeout):
                await upgrade.run(archive, lease)
    except asyncio.CancelledError:
        raise
    except SystemExit as exc:
        errors.append(f"插件请求退出: {exc.code!r}")
    except Exception as exc:
        errors.append("维护期升级超时" if isinstance(exc, TimeoutError) else str(exc))
    backup_paths: tuple[str, ...] = ()
    restored = False
    migrations: tuple[str, ...] = ()
    if upgrade is not None:
        checks = tuple(upgrade.checks)
        backup_paths = tuple(str(item) for item in (upgrade.code_backup, upgrade.data_backup) if item.exists())
        restored = upgrade.restored
        migrations = upgrade.applied
    return UpgradeReport(
        "upgrade",
        not errors,
        checks,
        tuple(errors),
        str(plugin_dir / name),
        digest,
        True,
        unverified=("real_services", "online_upgrade", "post_commit_data_restore"),
        backup_paths=backup_paths,
        restored=restored,
        migrations=migrations,
    )
