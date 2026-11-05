"""只读取磁盘声明，不导入插件入口的静态验收。"""

from __future__ import annotations

import ast
import json
import tokenize
from pathlib import Path
from typing import Any

from packaging.requirements import Requirement

from neobot_modloader.loading.manifest import read_dependencies, read_manifest, read_python_dependencies
from neobot_modloader.plugins.registration import validate_plugin_name
from neobot_modloader.sdk.contract import validate_contract
from neobot_modloader.sdk.migrations import read_migrations
from neobot_modloader.sdk.storage import read_storage

from .files import project_files, safe_file, safe_relative_path
from .frontend import read_frontend
from .models import ToolingError, ToolReport
from .suite import read_test_suite
from .view_assets import check_view_assets

CONTRACT_FILENAME = "plugin.contract.json"


def contract_path(root: Path, metadata: dict[str, Any], *, must_exist: bool = True) -> Path:
    sdk = metadata.get("sdk", {})
    if not isinstance(sdk, dict):
        raise ToolingError("plugin.toml: sdk 必须是 table")
    if "sdk" in metadata and (type(sdk.get("version")) is not int or sdk["version"] != 1):
        raise ToolingError("plugin.toml: sdk.version 必须为整数 1")
    relative = sdk.get("contract", CONTRACT_FILENAME)
    if must_exist:
        return safe_file(root, relative, label="sdk.contract")
    return safe_relative_path(root, relative, label="sdk.contract")


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ToolingError("契约 JSON 包含重复字段")
        result[key] = value
    return result


def read_contract(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_json_object)


def _pages(root: Path, metadata: dict[str, Any], distributed: set[Path]) -> bool:
    pages = metadata.get("sdk", {}).get("pages", [])
    if not isinstance(pages, list):
        raise ToolingError("sdk.pages 必须是相对页面入口列表")
    for index, entry in enumerate(pages):
        safe_file(root, entry, label=f"sdk.pages[{index}]")
        check_view_assets(root, entry, distributed)
    return bool(pages)


def _project_contract_errors(root: Path, metadata: dict[str, Any]) -> tuple[Path, list[str]]:
    """静态契约先做结构校验，再核对清单身份和实际分发的页面声明。"""
    target = contract_path(root, metadata)
    contract = read_contract(target)
    errors = validate_contract(contract)
    entries = []
    plugin = {}
    if isinstance(contract, dict):
        entries = [view.get("entry") for view in contract.get("views", []) if isinstance(view, dict)]
        plugin = contract.get("plugin", {})
    pages = metadata.get("sdk", {}).get("pages", [])
    if entries and set(entries) != set(pages):
        errors.append("views.entry 必须与 sdk.pages 的页面入口一致")
    for key in ("name", "version"):
        if plugin.get(key) != metadata.get(key):
            errors.append(f"plugin.{key} 与 plugin.toml 不一致")
    return target, errors


def check_project(path: Path, *, output: Path | None = None) -> ToolReport:
    """校验包内契约与文件，不探测业务函数或运行期网络。"""
    root = Path(path).resolve()
    checks: list[str] = []
    not_applicable: list[str] = []
    try:
        if root.is_file() and root.suffix == ".py":
            with tokenize.open(root) as handle:
                ast.parse(handle.read(), filename=str(root))
            return ToolReport("check", True, ("legacy_entry",), path=str(root), not_applicable=("contract", "package"))
        if not root.is_dir():
            raise ToolingError("插件工程目录不存在")
        entry = safe_file(root, "__init__.py", label="entry")
        with tokenize.open(entry) as handle:
            ast.parse(handle.read(), filename=str(entry))
        checks.append("entry")
        metadata = read_manifest(root / "plugin.toml")
        storage = read_storage(metadata)
        migrations = read_migrations(root, metadata)
        if migrations and storage is None:
            raise ToolingError("声明迁移时必须同时声明 sdk.storage")
        read_test_suite(root, metadata)
        validate_plugin_name(metadata.get("name") or root.name)
        read_dependencies(metadata.get("dependencies", []))
        for index, requirement in enumerate(read_python_dependencies(metadata)):
            try:
                Requirement(requirement)
            except ValueError as exc:
                raise ToolingError(f"python_dependencies[{index}]: 需求格式无效") from exc
        checks.append("manifest")
        if read_frontend(root, metadata) is not None:
            checks.append("frontend")
        distributed = set(project_files(root, output=output))
        checks.append("files")
        if "sdk" in metadata or (root / CONTRACT_FILENAME).exists():
            target, errors = _project_contract_errors(root, metadata)
            if errors:
                return ToolReport(
                    "check", False, tuple(checks), tuple(f"{target.name}: {error}" for error in errors), str(root)
                )
            checks.append("contract")
        else:
            not_applicable.append("contract")
        if _pages(root, metadata, distributed):
            checks.append("pages")
        else:
            not_applicable.append("pages")
        return ToolReport("check", True, tuple(checks), path=str(root), not_applicable=tuple(not_applicable))
    except (OSError, ValueError, SyntaxError, TypeError, RecursionError) as exc:
        return ToolReport("check", False, tuple(checks), (str(exc),), str(root))
