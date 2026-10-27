"""依赖体检与浏览器安装子命令（由 cli.py 拆分）。"""

from __future__ import annotations

import argparse
import sys


def cmd_doctor(args: argparse.Namespace) -> None:
    """依赖体检：不启动 Bot，只回答「装的是哪一版、缺哪个符号」。"""
    from neobot_app.doctor import collect_dependency_report, format_report

    report = collect_dependency_report()
    print(format_report(report))
    unhealthy = [row for row in report["dependencies"] if not row["ok"]]
    sys.exit(1 if unhealthy else 0)


def cmd_install_browser(args: argparse.Namespace) -> None:
    """下载内嵌 Chromium（仅 Linux/macOS 或无 Chrome/Edge 时使用）。"""
    import platform
    if platform.system() == "Windows":
        # 这条路会顺带 import DrissionPage：依赖版本不对时给出可执行的提示，
        # 而不是抛一句 cannot import name 'ChromiumPage'。
        try:
            from neobot_app.browser.agent_browser.manager import _find_chrome_binary
        except Exception as exc:  # noqa: BLE001 - 导入期失败统一转成可读提示
            from neobot_app.browser.agent_browser._compat import DRISSIONPAGE_HINT

            print(f"错误: 浏览器组件不可用：{DRISSIONPAGE_HINT}")
            print(f"（原始错误：{type(exc).__name__}: {exc}）")
            sys.exit(1)
        existing = _find_chrome_binary()
        if existing:
            print(f"已检测到浏览器: {existing}")
            print("Windows 上通常无需额外下载，可直接使用 Edge/Chrome。")
            return

    print("正在下载内嵌 Chromium 浏览器…")
    print("（只需执行一次，下载约 150MB）")
    print("需要安装 playwright: pip install playwright")
    print()
    try:
        __import__("playwright")
    except ImportError:
        print("请先安装 playwright: pip install playwright")
        print("或通过 CHROME_PATH 环境变量指定已安装的浏览器路径。")
        sys.exit(1)

    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=False, text=True,
        )
        if result.returncode != 0:
            print(f"错误: 下载失败 (return code {result.returncode})")
            sys.exit(1)

        from neobot_app.browser.agent_browser.manager import _playwright_chromium_path
        found = _playwright_chromium_path()
        if found:
            print(f"\n内嵌 Chromium 已就绪: {found}")
        else:
            print("\nChromium 已下载，但路径自动检测未命中。"
                  "请通过环境变量 CHROME_PATH 指定路径。")
    except Exception as exc:
        print(f"错误: 下载浏览器失败: {exc}")
        sys.exit(1)
