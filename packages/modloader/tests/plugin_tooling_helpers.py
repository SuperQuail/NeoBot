"""插件工具链回归使用的合成工程与契约。"""

import json
from pathlib import Path


def make_project(root: Path, name: str = "sample", *, body: str = "") -> Path:
    path = root / name
    path.mkdir(parents=True)
    (path / "plugin.toml").write_text(
        f'name = "{name}"\nversion = "0.1.0"\n[sdk]\nversion = 1\ncontract = "plugin.contract.json"\n',
        encoding="utf-8",
    )
    (path / "__init__.py").write_text(
        f"from neobot_modloader import Plugin\nplugin = Plugin({name!r}, version='0.1.0')\n" + body,
        encoding="utf-8",
    )
    write_contract(path, name)
    return path


def write_contract(path: Path, name: str, **changes: object) -> dict:
    contract = {
        "schema_version": 1,
        "plugin": {"name": name, "version": "0.1.0", "description": ""},
        "config": None,
        "actions": [],
        "resources": [],
        "guides": [],
    }
    contract.update(changes)
    (path / "plugin.contract.json").write_text(json.dumps(contract), encoding="utf-8")
    return contract
