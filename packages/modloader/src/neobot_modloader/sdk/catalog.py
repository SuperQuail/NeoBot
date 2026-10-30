"""插件元信息的版本化格式；本地候选与正式可分发条目明确分开。"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from neobot_modloader.plugins.registration import validate_plugin_name

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*/[a-z0-9][a-z0-9_-]*$")
_PLATFORMS = {"windows", "linux", "macos"}


def catalog_schema() -> dict[str, Any]:
    """仓库可导出此结构作为编辑器提示，语义约束由同版本验证器检查。"""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version",
            "id",
            "name",
            "version",
            "sdk_api",
            "status",
            "source",
            "artifact",
            "compatibility",
        ],
        "properties": {
            "schema_version": {"const": 1},
            "id": {"type": "string", "pattern": _ID.pattern},
            "name": {"type": "string"},
            "version": {"type": "string"},
            "sdk_api": {"const": 1},
            "description": {"type": "string"},
            "status": {"enum": ["local", "published"]},
            "source": {
                "type": "object",
                "properties": {
                    "repository": {"type": "string"},
                    "commit": {"type": "string", "pattern": _COMMIT.pattern},
                    "tree_sha256": {"type": "string", "pattern": _DIGEST.pattern},
                },
            },
            "artifact": {
                "type": "object",
                "required": ["sha256"],
                "properties": {"sha256": {"type": "string", "pattern": _DIGEST.pattern}, "url": {"type": "string"}},
            },
            "compatibility": {
                "type": "object",
                "required": ["neobot", "python", "platforms"],
                "properties": {
                    "neobot": {"type": "string"},
                    "python": {"type": "string"},
                    "platforms": {
                        "type": "array",
                        "items": {"enum": sorted(_PLATFORMS)},
                        "minItems": 1,
                        "uniqueItems": True,
                    },
                },
            },
            "storage": {
                "type": "object",
                "required": ["config_version", "data_version"],
                "properties": {
                    "config_version": {"type": "integer", "minimum": 1},
                    "data_version": {"type": "integer", "minimum": 1},
                },
            },
        },
    }


def _https(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parts = urlsplit(value)
    return parts.scheme == "https" and bool(parts.hostname) and not parts.username and not parts.password


def _validate_compatibility(compatibility: Any, errors: list[str]) -> None:
    if not isinstance(compatibility, dict):
        errors.append("compatibility 必须声明宿主、Python 和平台范围")
        return
    for name in ("neobot", "python"):
        value = compatibility.get(name)
        try:
            if not isinstance(value, str) or not value.strip():
                raise InvalidSpecifier()
            SpecifierSet(value)
        except InvalidSpecifier:
            errors.append(f"compatibility.{name} 版本范围无效")
    platforms = compatibility.get("platforms")
    if not isinstance(platforms, list) or not platforms:
        errors.append("compatibility.platforms 无效")
        return
    if any(not isinstance(item, str) or item not in _PLATFORMS for item in platforms):
        errors.append("compatibility.platforms 无效")
        return
    if len(set(platforms)) != len(platforms):
        errors.append("compatibility.platforms 不能重复")


def validate_entry(document: Any) -> list[str]:
    """诊断仅指出无效字段，不采信条目中的任何自报验收结果。"""
    if not isinstance(document, dict):
        return ["插件条目必须是对象"]
    errors = []
    schema = catalog_schema()
    if set(document) - set(schema["properties"]) or set(schema["required"]) - set(document):
        errors.append("插件条目的字段不符合 schema_version=1")
    for key in ("schema_version", "sdk_api"):
        if type(document.get(key)) is not int or document[key] != 1:
            errors.append(f"{key} 必须是整数 1")
    if not isinstance(document.get("id"), str) or not _ID.fullmatch(document["id"]):
        errors.append("id 必须是稳定的 publisher/name")
    try:
        validate_plugin_name(document.get("name"))
    except (TypeError, ValueError, AttributeError):
        errors.append("name 必须是有效的现有插件机器名称")
    try:
        Version(document.get("version", ""))
    except (TypeError, InvalidVersion):
        errors.append("version 必须是有效版本")
    status = document.get("status")
    if not isinstance(status, str) or status not in {"local", "published"}:
        errors.append("status 必须为 local 或 published")
    artifact = document.get("artifact")
    if (
        not isinstance(artifact, dict)
        or not isinstance(artifact.get("sha256"), str)
        or not _DIGEST.fullmatch(artifact["sha256"])
    ):
        errors.append("artifact.sha256 必须绑定最终 ZIP")
    elif status == "published" and not _https(artifact.get("url")):
        errors.append("正式条目必须提供 HTTPS 下载地址")
    source = document.get("source")
    if not isinstance(source, dict):
        errors.append("source 必须明确来源")
    elif status == "published":
        if (
            not _https(source.get("repository"))
            or not isinstance(source.get("commit"), str)
            or not _COMMIT.fullmatch(source["commit"])
        ):
            errors.append("正式来源必须绑定仓库与完整 40 位提交")
    elif not isinstance(source.get("tree_sha256"), str) or not _DIGEST.fullmatch(source["tree_sha256"]):
        errors.append("本地未发布候选必须提供实际源码树摘要")
    _validate_compatibility(document.get("compatibility"), errors)
    storage = document.get("storage")
    if storage is None:
        return errors
    valid_storage_fields = isinstance(storage, dict) and set(storage) == {"config_version", "data_version"}
    valid_storage_versions = valid_storage_fields and all(
        type(value) is int and value >= 1 for value in storage.values()
    )
    if not valid_storage_versions:
        errors.append("storage 必须明确配置和数据版本")
    return errors


def source_digest(root: Path) -> str:
    """对分发文件路径和字节取摘要，不依赖未提交工作树的虚构提交号。"""
    from .tooling.files import project_files

    digest = hashlib.sha256()
    for path in project_files(root):
        relative = path.relative_to(root).as_posix().encode()
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big") + relative)
        digest.update(len(content).to_bytes(8, "big") + content)
    return digest.hexdigest()


def _load_catalog_directory(
    directory: Path,
    entries: list[dict[str, Any]],
    names: set[str],
    identities: set[str],
) -> None:
    for path in sorted(directory.glob("*.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        errors = validate_entry(item)
        if errors:
            raise ValueError(f"{path.name}: " + "; ".join(errors))
        if directory.name == "entries" and item["status"] != "published":
            raise ValueError("未发布候选不能进入正式 entries")
        if item["name"] in names or item["id"] in identities:
            raise ValueError("条目 ID 或插件机器名称重复")
        identities.add(item["id"])
        names.add(item["name"])
        entries.append(item)


def load_catalog(repository: Path, *, include_local: bool = False) -> list[dict[str, Any]]:
    entries = []
    names = set()
    identities = set()
    directories = [repository / "entries"]
    if include_local:
        directories.append(repository / "local-candidates")
    for directory in directories:
        _load_catalog_directory(directory, entries, names, identities)
    return entries
