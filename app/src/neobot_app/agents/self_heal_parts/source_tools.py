"""源码读取/搜索工具：白名单校验与源码 glob 越界限制。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any



from .models import (
    _json,
)


_FORBIDDEN_SOURCE_BASENAMES = {
    "config.toml",
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
}
_FORBIDDEN_SOURCE_SUFFIXES = {".key", ".pem", ".crt", ".p12", ".keystore"}


def _is_within_any_root(path: Path, roots: list[Path]) -> Path | None:
    """若 `path` 位于某个 `roots` 之下，返回匹配的根目录；否则返回 None。"""
    try:
        resolved = path.resolve()
    except OSError:
        return None
    for root in roots:
        try:
            root_resolved = root.resolve()
        except OSError:
            continue
        try:
            resolved.relative_to(root_resolved)
            return root_resolved
        except ValueError:
            continue
    return None


def _common_project_root(roots: list[Path]) -> Path | None:
    """返回所有 `roots` 的最深公共祖先目录；若不存在则返回 None。"""
    if not roots:
        return None
    try:
        parts_list = [root.resolve().parts for root in roots]
    except OSError:
        return None
    common = list(parts_list[0])
    for parts in parts_list[1:]:
        i = 0
        while i < len(common) and i < len(parts) and common[i] == parts[i]:
            i += 1
        del common[i:]
    if not common:
        return None
    return Path(*common)


class SelfHealToolSourceMixin:
    """源码读取与搜索工具。"""

    def _resolve_source_path(self, rel_path: str) -> Path | None:
        rel = (rel_path or "").strip().lstrip("/")
        if not rel or ".." in Path(rel).parts:
            return None
        # Reject forbidden filenames and suffixes
        candidate_name = Path(rel).name
        if candidate_name in _FORBIDDEN_SOURCE_BASENAMES:
            return None
        if Path(rel).suffix.lower() in _FORBIDDEN_SOURCE_SUFFIXES:
            return None
        if "__pycache__" in Path(rel).parts:
            return None
        # Try resolving under each root
        for root in self._source_roots:
            candidate = (root / rel).resolve()
            matched = _is_within_any_root(candidate, self._source_roots)
            if matched is None:
                continue
            # Ensure candidate still matches the chosen root prefix
            try:
                candidate.relative_to(matched)
            except ValueError:
                continue
            if candidate.is_file():
                return candidate
        return None

    async def _execute_read_source_code(self, args: dict) -> str:
        rel = str(args.get("path", "")).strip()
        if not rel:
            return _json({"ok": False, "error": "缺少 path"})
        path = self._resolve_source_path(rel)
        if path is None:
            return _json(
                {
                    "ok": False,
                    "error": (
                        "路径不在白名单子树（仅允许 app/、packages/ 下的源码）或"
                        "为敏感文件（.env / config.toml / __pycache__ / 密钥等）"
                    ),
                }
            )
        try:
            size = path.stat().st_size
        except OSError as exc:
            return _json({"ok": False, "error": f"获取文件信息失败: {exc}"})
        try:
            data = path.read_bytes()
        except OSError as exc:
            return _json({"ok": False, "error": f"读取失败: {exc}"})
        if size > self.MAX_SOURCE_FILE_BYTES:
            truncated = data[-self.MAX_SOURCE_FILE_BYTES :]
            try:
                text = truncated.decode("utf-8")
            except UnicodeDecodeError:
                return _json(
                    {
                        "ok": False,
                        "error": (
                            f"文件超过 {self.MAX_SOURCE_FILE_BYTES} 字节且尾部无法以 UTF-8 解码"
                        ),
                    }
                )
            return _json(
                {
                    "ok": True,
                    "path": str(path),
                    "size": size,
                    "truncated": True,
                    "truncated_to_tail_bytes": self.MAX_SOURCE_FILE_BYTES,
                    "content": text,
                    "note": f"文件较大，仅返回尾部 {self.MAX_SOURCE_FILE_BYTES} 字节",
                }
            )
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return _json(
                {
                    "ok": False,
                    "error": "文件无法以 UTF-8 解码（可能为二进制）",
                }
            )
        return _json({"ok": True, "path": str(path), "size": size, "content": text})

    def _confine_glob(self, path_glob: str) -> str | None:
        """当项目相对 glob 保持在某个源码根目录内时，将其锚定到项目根。
        返回锚定后的 glob 字符串；否则返回 None。"""
        p = Path(path_glob)
        if p.is_absolute() or ".." in p.parts or not self._source_roots:
            return None
        prefix: list[str] = []
        for part in p.parts:
            if any(c in part for c in "*?["):
                break
            prefix.append(part)
        project_root = _common_project_root(self._source_roots)
        if project_root is None:
            return None
        try:
            base = project_root.joinpath(*prefix).resolve()
        except OSError:
            return None
        if _is_within_any_root(base, self._source_roots) is None:
            return None
        return str(project_root.joinpath(*p.parts))

    async def _execute_search_source_code(self, args: dict) -> str:
        pattern = str(args.get("pattern", "")).strip()
        if not pattern:
            return _json({"ok": False, "error": "缺少 pattern"})
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return _json({"ok": False, "error": f"正则编译失败: {exc}"})
        import glob as glob_module

        path_glob = str(args.get("path_glob", "")).strip()
        if not path_glob:
            # source_roots are already e.g. <project>/app and <project>/packages
            globs = [str(root / "**" / "*.py") for root in self._source_roots]
        else:
            anchored = self._confine_glob(path_glob)
            if anchored is None:
                return _json(
                    {
                        "ok": False,
                        "error": (
                            "path_glob 越界：仅允许项目内源码子树（app/、packages/）"
                            "内的相对 glob，禁止绝对路径与 ../"
                        ),
                    }
                )
            globs = [anchored]
        seen_files = 0
        total_matches = 0
        results: list[dict[str, Any]] = []
        for g in globs:
            for fp in glob_module.iglob(g, recursive=True):
                if seen_files >= self.SEARCH_MAX_FILES:
                    break
                p = Path(fp)
                if not p.is_file():
                    continue
                if "__pycache__" in p.parts:
                    continue
                if p.name in _FORBIDDEN_SOURCE_BASENAMES:
                    continue
                if p.suffix.lower() in _FORBIDDEN_SOURCE_SUFFIXES:
                    continue
                if _is_within_any_root(p, self._source_roots) is None:
                    continue
                seen_files += 1
                try:
                    text = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                lines = text.splitlines()
                file_matches = 0
                for idx, line in enumerate(lines):
                    if not regex.search(line):
                        continue
                    if file_matches >= self.SEARCH_MAX_MATCHES_PER_FILE:
                        break
                    start = max(0, idx - self.SEARCH_CONTEXT_LINES)
                    end = min(len(lines), idx + self.SEARCH_CONTEXT_LINES + 1)
                    results.append(
                        {
                            "path": str(p),
                            "line": idx + 1,
                            "context": "\n".join(
                                f"{(start + i + 1):>5}{'>' if (start + i) == idx else ' '} {lines[start + i]}"
                                for i in range(end - start)
                            ),
                        }
                    )
                    file_matches += 1
                    total_matches += 1
                    if total_matches >= self.SEARCH_MAX_MATCHES_TOTAL:
                        return _json(
                            {
                                "ok": True,
                                "files_scanned": seen_files,
                                "match_count": total_matches,
                                "truncated": True,
                                "matches": results,
                                "note": f"已达匹配上限 {self.SEARCH_MAX_MATCHES_TOTAL}",
                            }
                        )
        return _json(
            {
                "ok": True,
                "files_scanned": seen_files,
                "match_count": total_matches,
                "matches": results,
            }
        )

