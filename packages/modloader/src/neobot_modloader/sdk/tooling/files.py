"""统一的工程文件边界，供静态检查和打包共同使用。"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath, PureWindowsPath

from neobot_modloader.installer import MAX_ARCHIVE_ENTRIES, MAX_EXTRACTED_BYTES
from neobot_modloader.loading.manifest import read_manifest

from .models import ToolingError

EXCLUDED_DIRECTORIES = frozenset(
    {
        ".git",
        ".github",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        "dist",
        ".ruff_cache",
        ".pytest_cache",
        ".mypy_cache",
    }
)
_SENSITIVE_FILES = {".env", "credentials.json", "token.json", "id_rsa", "id_ed25519"}
_SENSITIVE_SUFFIXES = {".key", ".pem", ".pfx", ".p12", ".pth"}


def safe_relative_path(root: Path, relative: object, *, label: str) -> Path:
    """验证相对路径及已有父目录，不跟随符号链接或 junction。"""
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ToolingError(f"{label}: 必须是插件内相对文件路径")
    member = PurePosixPath(relative)
    if (
        member.is_absolute()
        or PureWindowsPath(relative).drive
        or any(part in {"", ".", ".."} for part in relative.split("/"))
    ):
        raise ToolingError(f"{label}: 路径不能离开插件目录")
    candidate = root / member
    for part in (candidate, *candidate.parents):
        if part == root.parent:
            break
        if part.is_symlink() or part.is_junction():
            raise ToolingError(f"{label}: 不接受符号链接或 junction")
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ToolingError(f"{label}: 路径不能离开插件目录")
    return candidate


def safe_file(root: Path, relative: object, *, label: str) -> Path:
    """仅接受已存在的工程内普通文件。"""
    candidate = safe_relative_path(root, relative, label=label)
    if not candidate.is_file():
        raise ToolingError(f"{label}: 文件不存在")
    return candidate


def _page_build_trees(root: Path, page: object, index: int) -> set[Path]:
    candidate = safe_relative_path(root, page, label=f"sdk.pages[{index}]")
    parts = candidate.relative_to(root).parts[:-1]
    trees = set()
    for depth, name in enumerate(parts):
        if name.casefold() not in EXCLUDED_DIRECTORIES:
            continue
        if name.casefold() != "dist":
            raise ToolingError(f"sdk.pages[{index}]: 页面不能位于不分发目录 {name} 内")
        trees.add(root.joinpath(*parts[: depth + 1]))
    return trees


def _declared_build_trees(root: Path) -> set[Path]:
    """声明页面所在的 dist 树属于产物，保留同树内脚本、样式及图片。"""
    metadata = read_manifest(root / "plugin.toml")
    sdk = metadata.get("sdk", {})
    if not isinstance(sdk, dict):
        raise ToolingError("sdk 必须是 table")
    pages = sdk.get("pages", [])
    if not isinstance(pages, list):
        raise ToolingError("sdk.pages 必须是相对页面入口列表")
    trees: set[Path] = set()
    for index, page in enumerate(pages):
        trees.update(_page_build_trees(root, page, index))
    return trees


class _ProjectScan:
    """按目录收集分发文件，在每次接纳文件时累积并检查安装器体积边界。"""

    def __init__(self, root: Path, output: Path | None) -> None:
        self.root = root
        self.output = output
        self.build_trees = _declared_build_trees(root)
        self.files: list[Path] = []
        self.size_bytes = 0

    def collect_directory(self, directory: Path) -> list[Path]:
        directories = []
        for path in sorted(directory.iterdir(), key=lambda item: item.name):
            relative = path.relative_to(self.root)
            declared_dist = path.name.casefold() == "dist" and any(
                path.is_relative_to(tree) for tree in self.build_trees
            )
            if path.name.casefold() in EXCLUDED_DIRECTORIES and not declared_dist:
                continue
            if path.is_symlink() or path.is_junction():
                raise ToolingError(f"{relative.as_posix()}: 不接受符号链接或 junction")
            if not path.resolve().is_relative_to(self.root.resolve()):
                raise ToolingError(f"{relative.as_posix()}: 文件越过工程边界")
            is_directory = path.is_dir()
            if is_directory and path.name.casefold().endswith(".egg-info"):
                continue
            if is_directory:
                directories.append(path)
                continue
            if self.output is not None and path.resolve() == self.output.resolve():
                continue
            if path.suffix.casefold() in {".pyc", ".pyo"} or path.name == ".gitignore":
                continue
            sensitive = path.name.casefold() in _SENSITIVE_FILES
            sensitive = sensitive or path.suffix.casefold() in _SENSITIVE_SUFFIXES
            sensitive = sensitive or (len(relative.parts) == 1 and path.name.casefold() == "config.toml")
            sensitive = sensitive or bool(re.fullmatch(r"\.env\.(?!example$|sample$|template$).+", path.name, re.I))
            if sensitive:
                raise ToolingError(f"{relative.as_posix()}: 疑似用户凭据或运行配置，不能分发")
            if not path.is_file():
                raise ToolingError(f"{relative.as_posix()}: 仅支持普通文件")
            self.files.append(path)
            self.size_bytes += path.stat().st_size
            if len(self.files) > MAX_ARCHIVE_ENTRIES or self.size_bytes > MAX_EXTRACTED_BYTES:
                raise ToolingError("工程超过安装器允许的文件数或解压体积")
        return directories


def project_files(root: Path, *, output: Path | None = None) -> list[Path]:
    """列出实际分发文件；敏感用户文件必须由作者主动移出工程。"""
    scan = _ProjectScan(root, output)
    pending = [root]
    while pending:
        directory = pending.pop()
        child_directories = scan.collect_directory(directory)
        pending.extend(child_directories)
    return sorted(scan.files, key=lambda item: item.relative_to(root).as_posix())
