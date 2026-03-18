#!/usr/bin/env python3
"""批量修改项目中所有 pyproject.toml 的版本号"""

import re
import sys
from pathlib import Path


def find_pyproject_files(root: Path) -> list[Path]:
    """查找所有 pyproject.toml 文件"""
    return list(root.glob("**/pyproject.toml"))


def update_version(file_path: Path, new_version: str, root: Path) -> bool:
    """更新单个文件的版本号"""
    try:
        content = file_path.read_text(encoding="utf-8")
        pattern = r'(^\[project\].*?^version\s*=\s*)"([^"]+)"'
        match = re.search(pattern, content, re.MULTILINE | re.DOTALL)

        if match:
            old_version = match.group(2)
            new_content = content[:match.start(2)] + new_version + content[match.end(2):]
            file_path.write_text(new_content, encoding="utf-8")
            print(f"✓ {file_path.relative_to(root)}: {old_version} → {new_version}")
            return True
        else:
            print(f"⊘ {file_path.relative_to(root)}: 未找到 project.version")
            return False
    except Exception as e:
        print(f"✗ {file_path.relative_to(root)}: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python versions.py <新版本号>")
        print("示例: python versions.py 0.3.0")
        sys.exit(1)

    new_version = sys.argv[1]
    root = Path(__file__).parent.parent
    files = find_pyproject_files(root)

    if not files:
        print("未找到 pyproject.toml 文件")
        sys.exit(1)

    print(f"找到 {len(files)} 个 pyproject.toml 文件:")
    for f in files:
        print(f"  - {f.relative_to(root)}")
    print()

    confirm = input(f"确认将版本号修改为 {new_version}? (y/N): ")
    if confirm.lower() != "y":
        print("已取消")
        sys.exit(0)

    print()
    success = sum(update_version(f, new_version, root) for f in files)
    print(f"\n完成: {success}/{len(files)} 个文件已更新")
