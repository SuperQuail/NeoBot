#!/usr/bin/env python3
"""网页面板 / 星舰前端产物体检：升级后“插件还是旧版”时的第一诊断。

回答三个问题（只读，不改任何文件）：

1. 我这个解释器加载的是**哪一份** neobot_app（路径 + 版本 + 文件时间）；
2. 该副本里 dashboard / starship 的 web/index.html 引用了哪些产物，哪些**引用但缺失**；
3. 目录里有没有**存在却没被引用**的产物 —— 那是上一代残留（覆盖式解压 / 跳过已存在文件
   的典型症状：旧 index.html 还在，于是页面自然还是旧版）。

用法::

    # 在部署环境里跑：问“我现在加载的是哪一份”（需要能 import neobot_app）
    python scripts/check_web_assets.py

    # 检查解压出来的 wheel / 交付目录（不 import，直接看文件）
    python scripts/check_web_assets.py --package-dir .venv/Lib/site-packages/neobot_app
    python scripts/check_web_assets.py --web-root app/src/neobot_app/builtin_plugins/starship/web

退出码：0 = 引用齐全且无残留；1 = 有引用但缺失（页面会白屏 / 报资源缺失）；
2 = 只有残留（说明目录混了新旧两代，页面可能仍是旧版）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

#: 需要体检的插件（插件名 -> 包内相对目录）
PLUGINS = ("dashboard", "starship")

#: index.html 里引用产物的写法（Vite 输出 ./assets/xxx）
_ASSET_REF = re.compile(r"""(?:src|href)\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_ASSET_SUFFIXES = (".js", ".css", ".mjs")


def referenced_assets(index_html: Path) -> list[str]:
    """index.html 引用到的产物文件名（相对 web/ 的路径，如 assets/index-xxx.js）。"""
    try:
        text = index_html.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    found: list[str] = []
    for raw in _ASSET_REF.findall(text):
        value = raw.strip()
        if not value.lower().endswith(_ASSET_SUFFIXES):
            continue
        value = value.split("?", 1)[0].split("#", 1)[0]
        if value.startswith("./"):
            value = value[2:]
        value = value.lstrip("/")
        if value not in found:
            found.append(value)
    return found


def _chunk_texts(index_html: Path, refs: list[str]) -> list[str]:
    """index.html 直接引用的 JS/CSS 的内容（动态 chunk 的名字只出现在这些文件里）。

    starship 的 main.ts 里有 `await import('./game')`，Vite 会把它拆成独立的
    game-*.js，入口 chunk 里以字符串形式引用它（可能是 `./game-xxxx.js`，也可能带
    `assets/` 前缀）—— 因此「没写进 index.html」不等于「残留」。
    """
    texts: list[str] = []
    for name in refs:
        path = index_html.parent / name
        if path.suffix.lower() not in (".js", ".css", ".mjs") or not path.is_file():
            continue
        try:
            texts.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return texts


def asset_files(web_root: Path) -> list[Path]:
    assets_dir = web_root / "assets"
    if not assets_dir.is_dir():
        return []
    return sorted(path for path in assets_dir.rglob("*") if path.is_file())


def report(web_root: Path, *, label: str) -> int:
    """体检一个 web/ 目录；返回该目录的问题级别（0/1/2）。"""
    print(f"\n== {label} ==")
    print(f"   web 目录 : {web_root}")
    if not web_root.is_dir():
        print("   [!] 目录不存在 —— 插件没有前端产物（冻结/打包时漏收集数据文件？）")
        return 1
    index_html = web_root / "index.html"
    if not index_html.is_file():
        print("   [!] web/index.html 缺失 —— 页面会直接报「前端资源缺失」")
        return 1
    print(f"   index.html: {_stamp(index_html)}")  # 页面按它引用产物：它旧，页面就旧

    refs = referenced_assets(index_html)
    files = asset_files(web_root)
    present = {path.relative_to(web_root).as_posix(): path for path in files}

    missing = [name for name in refs if name not in present]
    texts = _chunk_texts(index_html, refs)
    referenced = set(refs) | {
        name for name in present if any(name.rsplit("/", 1)[-1] in text for text in texts)
    }
    leftovers = [name for name in present if name not in referenced]

    if refs:
        for name in refs:
            mark = "[OK]" if name in present else "[!]"
            path = present.get(name)
            print(f"   {mark} 引用 {name}" + (f"  ({_stamp(path)})" if path else "  —— 文件不存在"))
    else:
        print("   [!] index.html 里没有解析到任何产物引用（格式变了？请人工看一眼）")

    if leftovers:
        print("   [!] 存在但没有任何产物引用的文件（上一代残留，覆盖式解压常见）：")
        for name in leftovers:
            print(f"        {name}  ({_stamp(present[name])})")
    if missing:
        print("   [!] 有引用但缺失：页面会白屏 / 报资源缺失")
        return 1
    if leftovers:
        print(
            "   [!] 结论：目录里混了新旧两代产物 —— 覆盖式解压 / 解压时跳过已存在文件的典型症状。"
            "页面按 index.html 引用加载，若 index.html 还是旧的，看到的就是旧版"
        )
        return 2
    print("   [OK] 引用齐全、无残留：这份 web/ 是一套自洽的产物")
    return 0


def _stamp(path: Path | None) -> str:
    if path is None:
        return "?"
    try:
        stat = path.stat()
    except OSError:
        return "?"
    from datetime import datetime

    return f"{datetime.fromtimestamp(stat.st_mtime):%Y-%m-%d %H:%M:%S}, {stat.st_size} B"


def check_package_dir(package_dir: Path) -> int:
    print(f"== 包目录: {package_dir} ==")
    builtin = package_dir / "builtin_plugins"
    if not builtin.is_dir():
        print("   [!] 不是 neobot_app 包目录（缺少 builtin_plugins/）")
        return 1
    worst = 0
    for name in PLUGINS:
        level = report(builtin / name / "web", label=f"{name} 插件")
        worst = max(worst, level)
    return worst


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="网页面板 / 星舰前端产物体检")
    parser.add_argument("--package-dir", type=Path, help="neobot_app 包目录（含 builtin_plugins/）")
    parser.add_argument("--web-root", type=Path, help="直接指定某个插件的 web/ 目录")
    args = parser.parse_args(argv)

    if args.web_root is not None:
        return report(args.web_root.resolve(), label="指定目录")
    if args.package_dir is not None:
        return check_package_dir(args.package_dir.resolve())

    # 默认：问当前解释器加载的是哪一份
    try:
        import neobot_app
        from neobot_app.builtin_plugins import builtin_plugin_dirs
    except Exception as exc:  # pragma: no cover - 部署环境不可导入时给出提示
        print(f"[!] 无法 import neobot_app（{type(exc).__name__}: {exc}）")
        print("    当前解释器不是 NeoBot 的运行环境；请在部署用的解释器/venv 里执行，")
        print("    或者改用 --package-dir / --web-root 直接检查目录。")
        return 1

    package_dir = Path(neobot_app.__file__).resolve().parent
    print(f"== 当前解释器加载的 neobot_app: {package_dir} ==")
    try:
        from importlib.metadata import version

        print(f"   neobot-app 版本: {version('neobot-app')}")
    except Exception:
        print("   neobot-app 版本: （读不到 dist-info）")
    dirs = tuple(Path(path) for path in builtin_plugin_dirs())
    if not dirs:
        print("   [!] 没有官方插件目录")
        return 1
    worst = 0
    for name in PLUGINS:
        worst = max(worst, report(dirs[0] / name / "web", label=f"{name} 插件"))
    return worst


if __name__ == "__main__":
    sys.exit(main())
