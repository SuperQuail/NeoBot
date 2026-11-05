"""清单声明的维护期迁移，只在暂存的配置和业务数据上执行。"""

from __future__ import annotations

import importlib.util
import inspect
import sys
import tomllib
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .storage import StorageError, StorageVersion, write_storage


@dataclass(frozen=True)
class MigrationStep:
    kind: str
    before: int
    after: int
    entry: Path


@dataclass(frozen=True)
class MigrationContext:
    data_dir: Path
    config_path: Path
    kind: str
    from_version: int
    to_version: int


def read_migrations(root: Path, metadata: dict[str, Any]) -> tuple[MigrationStep, ...]:
    from .tooling.files import safe_file

    sdk = metadata.get("sdk", {})
    if not isinstance(sdk, dict):
        raise StorageError("sdk 必须是 table")
    raw = sdk.get("migrations", [])
    if not isinstance(raw, list):
        raise StorageError("sdk.migrations 必须是迁移列表")
    result = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict) or set(item) != {"kind", "from", "to", "entry"}:
            raise StorageError("每条迁移必须声明 kind/from/to/entry")
        kind, before, after = item["kind"], item["from"], item["to"]
        valid_kind = kind in {"config", "data"}
        valid_versions = type(before) is int and type(after) is int and 1 <= before < after
        if not valid_kind or not valid_versions:
            raise StorageError("迁移类型或版本范围无效")
        if (kind, before) in seen:
            raise StorageError("同一存储版本不能有多条迁移出口")
        entry = safe_file(root, item["entry"], label="sdk.migrations.entry")
        if entry.suffix != ".py":
            raise StorageError("迁移入口必须是 Python 文件")
        seen.add((kind, before))
        result.append(MigrationStep(kind, before, after, entry))
    return tuple(result)


def _migration_chain(steps: tuple[MigrationStep, ...], kind: str, current: int, target: int) -> Iterable[MigrationStep]:
    """逐步寻找出口；前一步执行后才检查下一步，保持迁移失败的原有时序。"""
    while current < target:
        step = next((item for item in steps if item.kind == kind and item.before == current), None)
        if step is None or step.after > target:
            raise StorageError(f"缺少 {kind} 从版本 {current} 到 {target} 的迁移链")
        yield step
        current = step.after


async def _run_migration(step: MigrationStep, data_dir: Path, current: int) -> None:
    module_name = "neobot_migration_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(module_name, step.entry)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        migrate = module.migrate
        context = MigrationContext(data_dir, data_dir / "config.toml", step.kind, current, step.after)
        result = migrate(context)
        if inspect.isawaitable(result):
            await result
    finally:
        sys.modules.pop(module_name, None)


async def migrate_storage(
    root: Path, data_dir: Path, metadata: dict[str, Any], before: StorageVersion, after: StorageVersion
) -> tuple[str, ...]:
    steps = read_migrations(root, metadata)
    applied = []
    versions = (
        ("config", before.config_version, after.config_version),
        ("data", before.data_version, after.data_version),
    )
    for kind, current, target in versions:
        if current > target:
            raise StorageError("不支持存储版本降级，请使用对应的完整备份恢复")
        for step in _migration_chain(steps, kind, current, target):
            await _run_migration(step, data_dir, current)
            applied.append(f"{kind}:{current}->{step.after}")
            current = step.after
    config = data_dir / "config.toml"
    if config.is_file():
        tomllib.loads(config.read_text(encoding="utf-8-sig"))
    write_storage(data_dir, after)
    return tuple(applied)
