"""沙箱文件工具的公共 JSON 包装与下载上限常量。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024

MAX_DOWNLOAD_REDIRECTS = 3


def display_result_path(path: str | Path, base: Path, sandbox_root: Path) -> str:
    """结果里的路径：沙箱内按相对路径展示，沙箱外的根（排除工作区等）保留绝对路径。

    模型会把工具输出原样回填给 read_file 等工具；相对路径会被解析回当前聊天
    的临时目录，所以沙箱之外的结果必须保持绝对路径。
    """
    candidate = Path(path)
    try:
        base.relative_to(sandbox_root)
    except ValueError:
        return str(candidate)
    try:
        return str(candidate.relative_to(base)) if candidate != base else candidate.name
    except ValueError:
        return str(candidate)
