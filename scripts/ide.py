#!/usr/bin/env python3
"""自动修复 IDE 源代码根目录配置"""

import json
import tomllib
from pathlib import Path
from xml.etree import ElementTree as ET


def get_src_dirs(project_root: Path) -> list[Path]:
    """获取所有 src 目录"""
    pyproject_path = project_root / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        config = tomllib.load(f)

    workspace_members = (
        config.get("tool", {}).get("uv", {}).get("workspace", {}).get("members", [])
    )
    src_dirs = []

    for member in workspace_members:
        if "*" in member:
            pattern = member.replace("*", "")
            base_dir = project_root / pattern.rstrip("/")
            if base_dir.exists():
                for pkg_dir in base_dir.iterdir():
                    if pkg_dir.is_dir():
                        src = pkg_dir / "src"
                        if src.exists():
                            src_dirs.append(src.relative_to(project_root))
        else:
            src = project_root / member / "src"
            if src.exists():
                src_dirs.append(src.relative_to(project_root))

    return sorted(src_dirs)


def fix_pycharm(project_root: Path, src_dirs: list[Path]):
    """修复 PyCharm 配置"""
    idea_dir = project_root / ".idea"
    iml_files = list(idea_dir.glob("*.iml"))

    if not iml_files:
        print("✗ 未找到 .iml 文件")
        return

    iml_path = iml_files[0]
    tree = ET.parse(iml_path)
    root = tree.getroot()

    component = None
    for comp in root.findall("component"):
        if comp.get("name") == "NewModuleRootManager":
            component = comp
            break

    if component is None:
        component = ET.Element("component")
        component.set("name", "NewModuleRootManager")
        root.append(component)

    content = component.find("content")
    if content is None:
        content = ET.Element("content")
        content.set("url", "file://$MODULE_DIR$")
        component.append(content)

    for sf in content.findall("sourceFolder"):
        content.remove(sf)

    for src_dir in src_dirs:
        sf = ET.Element("sourceFolder")
        sf.set("url", f"file://$MODULE_DIR$/{src_dir}")
        sf.set("isTestSource", "false")
        content.insert(0, sf)

    ET.indent(root, space="  ")
    tree.write(iml_path, encoding="utf-8", xml_declaration=True)
    print(f"✓ PyCharm: 已更新 {len(src_dirs)} 个源代码目录")


def fix_zed(project_root: Path, src_dirs: list[Path]):
    """修复 Zed 配置"""
    zed_dir = project_root / ".zed"
    zed_dir.mkdir(exist_ok=True)

    settings_path = zed_dir / "settings.json"

    config = {
        "lsp": {
            "pyright": {
                "settings": {
                    "python.pythonPath": ".venv/bin/python",
                    "python.analysis.extraPaths": [
                        str(src_dir) for src_dir in src_dirs
                    ],
                }
            }
        }
    }

    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    print(f"✓ Zed: 已更新 {len(src_dirs)} 个源代码目录")


def main():
    project_root = Path(__file__).parent.parent
    src_dirs = get_src_dirs(project_root)

    if not src_dirs:
        print("✗ 未找到任何 src 目录")
        return

    print("请选择要修复的 IDE:")
    print("1. PyCharm")
    print("2. Zed")
    print("3. 全部")

    choice = input("请输入选项 (1/2/3): ").strip()

    if choice == "1":
        fix_pycharm(project_root, src_dirs)
    elif choice == "2":
        fix_zed(project_root, src_dirs)
    elif choice == "3":
        fix_pycharm(project_root, src_dirs)
        fix_zed(project_root, src_dirs)
    else:
        print("✗ 无效选项")
        return

    print("\n源代码目录:")
    for src_dir in src_dirs:
        print(f"  - {src_dir}")


if __name__ == "__main__":
    main()
