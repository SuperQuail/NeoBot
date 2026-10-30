"""显式离线验收目录，不用隐藏标记或跳过结果替代必需业务测试。"""

from pathlib import Path
from typing import Any

from .files import safe_relative_path
from .models import ToolingError


def read_test_suite(root: Path, metadata: dict[str, Any], *, required: bool = False) -> Path | None:
    sdk = metadata.get("sdk", {})
    declaration = sdk.get("tests") if isinstance(sdk, dict) else None
    if declaration is not None and (not isinstance(declaration, dict) or set(declaration) != {"path"}):
        raise ToolingError("sdk.tests 必须是只包含 path 的 table")
    path = safe_relative_path(root, declaration["path"] if declaration is not None else "tests", label="sdk.tests.path")
    if path.is_dir():
        return path
    if required or declaration is not None:
        raise ToolingError("缺少声明的离线业务测试目录，不能完成插件验收")
    return None
