"""定位已声明的包内页面，资源访问只限于该页面的分发目录。"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, Any

from neobot_modloader.loading.manifest import read_manifest

from .actions import ActionError
from .runtime import describe_runtime_surface

if TYPE_CHECKING:
    from neobot_modloader.runtime import PluginRuntime

_PUBLIC_SUFFIXES = frozenset(
    {
        ".html",
        ".htm",
        ".css",
        ".js",
        ".mjs",
        ".json",
        ".svg",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".gif",
        ".ico",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".txt",
    }
)


def _relative_file(root: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    if (
        not relative
        or "\\" in relative
        or "\0" in relative
        or path.is_absolute()
        or PureWindowsPath(relative).drive
        or any(part in {".", ".."} or part.startswith(".") for part in path.parts)
    ):
        raise ValueError("页面路径必须在分发目录内")
    target = root.joinpath(*path.parts).resolve()
    target.relative_to(root.resolve())
    if not target.is_file():
        raise ValueError("页面文件不存在")
    return target


def resolve_view_file(root: Path, entry: str, relative: str = "") -> Path:
    """静态验收与运行时共用入口目录、文件类型和路径边界。"""
    page = _relative_file(root, entry)
    if page.suffix.lower() not in {".html", ".htm"}:
        raise ValueError("页面入口必须是 HTML")
    target = _relative_file(page.parent, relative or page.name)
    if target.suffix.lower() not in _PUBLIC_SUFFIXES:
        raise ValueError("资源类型不可公开")
    return target


def _descriptions(runtime: PluginRuntime, name: str) -> tuple[Path, list[dict[str, Any]]]:
    surface = describe_runtime_surface(runtime, name)
    snapshot = runtime.control.get(name)
    if snapshot is None or snapshot.path is None or not Path(snapshot.path).is_dir():
        raise ActionError("view_not_found", "插件没有可用页面")
    root = Path(snapshot.path).resolve()
    contract = surface.get("contract")
    views = contract.get("views", []) if contract is not None else []
    if not views:
        return root, []
    try:
        manifest = read_manifest(root / "plugin.toml")
        pages = manifest.get("sdk", {}).get("pages", [])
        for view in views:
            entry = view["entry"]
            if entry not in pages:
                raise ValueError("页面入口未正确分发")
            resolve_view_file(root, entry)
    except (OSError, ValueError, TypeError, KeyError):
        raise ActionError("contract_invalid", "插件页面声明与包内文件不一致") from None
    return root, views


def _view_revision(directory: Path, module_names: Iterable[str]) -> str:
    """页面版本同时绑定当前插件代和可公开的包内资源字节。"""
    revision = hashlib.sha256("\n".join(module_names).encode())
    for asset in sorted(directory.rglob("*")):
        if not asset.is_file() or asset.suffix.lower() not in _PUBLIC_SUFFIXES:
            continue
        if not asset.resolve().is_relative_to(directory):
            continue
        revision.update(asset.relative_to(directory).as_posix().encode())
        revision.update(asset.read_bytes())
    return revision.hexdigest()[:16]


def describe_runtime_views(runtime: PluginRuntime, name: str) -> list[dict[str, Any]]:
    """读取公开页面描述；身份和契约仍由统一 surface 判定。"""
    root, views = _descriptions(runtime, name)
    results = []
    for view in views:
        module_names = runtime._loaded_modules.get(name, ())
        directory = _relative_file(root, view["entry"]).parent
        revision = _view_revision(directory, module_names)
        results.append({**{key: view[key] for key in ("id", "title", "entry", "anchors")}, "revision": revision})
    return results


def resolve_runtime_view_asset(runtime: PluginRuntime, name: str, view_id: str, relative: str) -> Path:
    """页面只能读取入口同目录的静态资源，不能借用链接访问代码与配置。"""
    root, views = _descriptions(runtime, name)
    view = next((item for item in views if item["id"] == view_id), None)
    if view is None:
        raise ActionError("view_not_found", "插件页面不存在")
    try:
        return resolve_view_file(root, view["entry"], relative)
    except (OSError, ValueError, TypeError):
        raise ActionError("view_asset_not_found", "页面资源不存在") from None
