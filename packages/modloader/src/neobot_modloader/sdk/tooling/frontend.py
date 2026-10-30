"""前端工程的显式声明；读取阶段不执行脚本，也不要求页面已构建。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .files import safe_file, safe_relative_path
from .models import ToolingError

_PNPM_VERSION = re.compile(r"pnpm@[0-9]+\.[0-9]+\.[0-9]+")


def read_frontend(root: Path, metadata: dict[str, Any]) -> Path | None:
    """校验同一套构建输入，供静态检查与本地／CI runner 共同调用。"""
    sdk = metadata.get("sdk", {})
    if not isinstance(sdk, dict):
        raise ToolingError("sdk 必须是 table")
    if "frontend" not in sdk:
        if (root / "frontend" / "package.json").is_file():
            raise ToolingError("sdk.frontend: frontend 工程必须显式声明构建目录")
        return None
    declaration = sdk["frontend"]
    if not isinstance(declaration, dict) or set(declaration) != {"path"}:
        raise ToolingError("sdk.frontend 必须是仅包含 path 的 table")
    directory = safe_relative_path(root, declaration["path"], label="sdk.frontend.path")
    if not directory.is_dir():
        raise ToolingError("sdk.frontend.path: 工程目录不存在")
    package = safe_file(root, f"{declaration['path']}/package.json", label="package.json")
    safe_file(root, f"{declaration['path']}/pnpm-lock.yaml", label="pnpm-lock.yaml")
    try:
        document = json.loads(package.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ToolingError("package.json: 无法读取 JSON") from exc
    if not isinstance(document, dict):
        raise ToolingError("package.json 必须是对象")
    manager = document.get("packageManager")
    if not isinstance(manager, str) or not _PNPM_VERSION.fullmatch(manager):
        raise ToolingError("package.json packageManager 必须锁定 pnpm@x.y.z")
    scripts = document.get("scripts")
    if not isinstance(scripts, dict):
        raise ToolingError("package.json scripts 必须声明 verify 和 build")
    for name in ("verify", "build"):
        script = scripts.get(name)
        if not isinstance(script, str) or not script.strip():
            raise ToolingError(f"package.json scripts.{name} 必须是非空命令")
    pages = sdk.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ToolingError("sdk.pages: 前端工程必须声明构建后的页面入口")
    for index, page in enumerate(pages):
        safe_relative_path(root, page, label=f"sdk.pages[{index}]")
    return directory
