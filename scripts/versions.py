#!/usr/bin/env python3
"""批量修改项目中所有 pyproject.toml 的版本号"""

import re
import sys
import tomllib
from pathlib import Path

if __package__:
    from .semver_validation import validate_semver
else:
    from semver_validation import validate_semver


def _workspace_members(root: Path) -> list[str]:
    """读取根 pyproject.toml 的 [tool.uv.workspace].members（如 packages/*、app）。"""
    root_pyproject = root / "pyproject.toml"
    if not root_pyproject.is_file():
        return []
    with root_pyproject.open("rb") as handle:
        data = tomllib.load(handle)
    members = data.get("tool", {}).get("uv", {}).get("workspace", {}).get("members", [])
    return [str(member) for member in members or []]


def find_pyproject_files(root: Path) -> list[Path]:
    """查找工作区内的全部 pyproject.toml（根 + members 展开）。

    只覆盖 uv workspace 成员，避免误改 dev-test/Reference 下的第三方副本。
    """
    files: list[Path] = []
    root_pyproject = root / "pyproject.toml"
    if root_pyproject.is_file():
        files.append(root_pyproject)
    for pattern in _workspace_members(root):
        for member_dir in sorted(root.glob(pattern)):
            candidate = member_dir / "pyproject.toml"
            if candidate.is_file() and candidate not in files:
                files.append(candidate)
    return files


def update_version(file_path: Path, new_version: str, root: Path) -> bool:
    """更新单个文件的版本号；非法目标版本在读取文件前抛出 ValueError。"""
    new_version = validate_semver(new_version, source="目标版本")
    try:
        content = file_path.read_text(encoding="utf-8")
        # Never cross a table boundary when project.version is absent.
        pattern = (
            r'(^[ \t]*\[project\][ \t]*(?:#[^\r\n]*)?\r?\n'
            r'(?:(?!^[ \t]*\[).)*?^[ \t]*version[ \t]*=[ \t]*)"([^"\r\n]*)"'
        )
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


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("用法: python versions.py <新版本号>")
        print("示例: python versions.py 0.3.0")
        return 1

    try:
        new_version = validate_semver(argv[0], source="目标版本")
    except ValueError as error:
        print(f"✗ {error}", file=sys.stderr)
        return 1
    root = Path(__file__).parent.parent
    files = find_pyproject_files(root)

    if not files:
        print("未找到 pyproject.toml 文件")
        return 1

    print(f"找到 {len(files)} 个 pyproject.toml 文件:")
    for f in files:
        print(f"  - {f.relative_to(root)}")
    print()

    confirm = input(f"确认将版本号修改为 {new_version}? (y/N): ")
    if confirm.lower() != "y":
        print("已取消")
        return 0

    print()
    success = sum(update_version(f, new_version, root) for f in files)
    print(f"\n完成: {success}/{len(files)} 个文件已更新")
    return 0 if success == len(files) else 1


if __name__ == "__main__":
    sys.exit(main())
