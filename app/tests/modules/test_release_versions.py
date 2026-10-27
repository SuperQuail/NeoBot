"""发版脚本：版本号与 app 内部子包 pin 必须同步更新。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _load_versions():
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "neobot_versions_under_test", ROOT / "scripts" / "versions.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VERSIONS = _load_versions()


def test_update_version_keeps_app_internal_pins_in_sync(tmp_path: Path) -> None:
    root = tmp_path
    (root / "app").mkdir()
    root_pyproject = root / "pyproject.toml"
    root_pyproject.write_text(
        '[project]\nname = "neobot"\nversion = "2.0.2-a9"\n\n'
        '[tool.uv.workspace]\nmembers = ["app"]\n',
        encoding="utf-8",
    )
    app_pyproject = root / "app" / "pyproject.toml"
    app_pyproject.write_text(
        '[project]\nname = "neobot-app"\nversion = "2.0.2-a9"\n'
        'dependencies = [\n'
        '    "neobot-chat==2.0.2-a9",\n'
        '    "neobot-contracts==2.0.2-a9",\n'
        '    "requests>=2",\n'
        "]\n",
        encoding="utf-8",
    )

    assert VERSIONS.update_version(root_pyproject, "2.0.2-a10", root)
    assert VERSIONS.update_version(app_pyproject, "2.0.2-a10", root)

    text = app_pyproject.read_text(encoding="utf-8")
    assert 'version = "2.0.2-a10"' in text
    assert '"neobot-chat==2.0.2-a10"' in text
    assert '"neobot-contracts==2.0.2-a10"' in text
    assert "2.0.2-a9" not in text
