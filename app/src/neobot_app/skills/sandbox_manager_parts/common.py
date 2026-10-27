"""沙箱文件工具的公共 JSON 包装与下载上限常量。"""

from __future__ import annotations

import json
from typing import Any

def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024

MAX_DOWNLOAD_REDIRECTS = 3
