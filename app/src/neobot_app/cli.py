"""neobot CLI — 启动机器人或执行快捷操作。"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from pathlib import Path

from neobot_app.bootstrap import create_application
from neobot_app.core import DATA_DIR
from neobot_app.runtime.application import ConnectionTimeoutError


async def run() -> None:
    application = create_application()
    loop = asyncio.get_running_loop()

    def request_stop() -> None:
        application.request_stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, request_stop)
        except NotImplementedError:
            if sig == signal.SIGINT:
                signal.signal(
                    signal.SIGINT,
                    lambda _signum, _frame: loop.call_soon_threadsafe(request_stop),
                )

    await application.run_forever()


def cmd_run(args: argparse.Namespace) -> None:
    """启动机器人主程序。"""
    try:
        asyncio.run(run())
    except ConnectionTimeoutError as exc:
        print(f"错误: {exc}")
    except KeyboardInterrupt:
        sys.exit(0)


def cmd_open_web(args: argparse.Namespace) -> None:
    """启动有头浏览器供手动登录认证，会话持久化供后续无头复用。"""
    profile_dir = DATA_DIR / "browser" / "profiles" / "manual_login"
    profile_dir.mkdir(parents=True, exist_ok=True)
    url = args.url or "https://www.bing.com"

    print(f"启动浏览器: {url}")
    print(f"用户数据目录: {profile_dir}")
    print()
    print("请在浏览器中完成登录后关闭窗口。")
    print("登录状态将保存在上述目录，后续无头浏览器将复用此会话。")
    print()

    try:
        from DrissionPage import ChromiumOptions, ChromiumPage

        # 自动检测浏览器路径（Chrome > Edge > Chromium）
        from neobot_app.browser.agent_browser.manager import _find_chrome_binary
        browser_path = _find_chrome_binary()
        if browser_path:
            print(f"使用浏览器: {browser_path}")
        else:
            print("警告: 未检测到浏览器，将使用 DrissionPage 默认浏览器")

        options = ChromiumOptions()
        if browser_path:
            options.set_browser_path(browser_path)
        options.set_argument("--user-data-dir", str(profile_dir))
        options.no_imgs(False)
        options.headless(False)
        options.set_argument("--no-first-run")
        options.set_argument("--no-default-browser-check")

        page = ChromiumPage(addr_or_opts=options)
        page.get(url)

        print("浏览器已启动。完成登录后关闭浏览器窗口或按 Ctrl+C 退出。")
        # 保持进程运行直到用户中断，同时定期检查浏览器是否已关闭
        try:
            while True:
                asyncio.run(asyncio.sleep(2))
                # 检查页面是否已关闭
                try:
                    _ = page.url
                except Exception:
                    print("浏览器窗口已关闭。")
                    break
        except KeyboardInterrupt:
            print("\n正在关闭浏览器…")
        finally:
            try:
                page.quit()
            except Exception:
                pass

        print("会话已保存。")
    except ImportError:
        print("错误: 需要安装 DrissionPage: pip install DrissionPage")
        sys.exit(1)
    except Exception as exc:
        print(f"错误: 启动浏览器失败: {exc}")
        sys.exit(1)


def cmd_install_browser(args: argparse.Namespace) -> None:
    """下载内嵌 Chromium（仅 Linux/macOS 或无 Chrome/Edge 时使用）。"""
    import platform
    if platform.system() == "Windows":
        from neobot_app.browser.agent_browser.manager import _find_chrome_binary
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
        from playwright._impl._driver import compute_driver_executable, get_driver_dir
    except ImportError:
        print("请先安装 playwright: pip install playwright")
        print("或通过 CHROME_PATH 环境变量指定已安装的浏览器路径。")
        sys.exit(1)

    try:
        import subprocess
        driver_path = get_driver_dir()
        driver_exe = compute_driver_executable()
        cli = Path(driver_path) / driver_exe
        result = subprocess.run(
            [str(cli), "install", "chromium"],
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


async def _run_sandbox_cleanup() -> int:
    """独立运行沙箱清理，不启动 Bot 主程序。返回 exit code。"""
    from neobot_app.bootstrap._config import build_config
    from neobot_app.bootstrap._runtime import build_sandbox_components

    print("正在加载配置…")
    config = build_config()
    sandbox_cfg = getattr(config.agent, "sandbox", None)
    if not sandbox_cfg or not sandbox_cfg.enabled:
        print("错误: 沙箱功能未启用 (agent.sandbox.enabled = false)")
        return 1

    print("正在构建沙箱组件…")
    components = build_sandbox_components(
        config=config,
        data_dir=DATA_DIR,
    )

    temp_cleaner = components.get("temp_cleaner")
    maintenance = components.get("sandbox_maintenance_manager")

    if temp_cleaner is None and maintenance is None:
        print("错误: 沙箱组件未成功构建")
        return 1

    exit_code = 0

    # 1. 临时文件清理
    if temp_cleaner is not None:
        print(f"\n[1/2] 清理临时文件: {temp_cleaner.temp_dir}")
        result = temp_cleaner.run_once()
        print(f"  过期文件: {result['files_removed']}")
        print(f"  空目录:   {result['dirs_removed']}")
        print(f"  嵌套修复: {result['nests_fixed']}")

    # 2. 沙箱维护
    if maintenance is not None:
        print(f"\n[2/2] 沙箱持久化维护…")
        result = await maintenance.run_once(force=True)
        if result.get("skipped"):
            print("  跳过（无文件变更）")
        else:
            print(f"  完成, 详情:")
            for key, value in result.items():
                if key in ("ok", "skipped"):
                    continue
                print(f"  {key}: {value}")
        if result.get("errors"):
            print(f"  错误: {result['errors']}")
            exit_code = 1

    print("\n沙箱清理完成。")
    return exit_code


def cmd_sandbox_clean(args: argparse.Namespace) -> None:
    """独立执行沙箱清理。"""
    try:
        exit_code = asyncio.run(_run_sandbox_cleanup())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n用户中断")
        sys.exit(130)


def main() -> None:
    parser = argparse.ArgumentParser(description="NeoBot — QQ 机器人")
    parser.add_argument(
        "--version", action="version",
        version="%(prog)s 1.0.0",
    )

    sub = parser.add_subparsers(title="子命令", dest="command")

    # `neobot install-browser`
    sub.add_parser(
        "install-browser", help="下载内嵌 Chromium 浏览器",
        description="通过 Playwright 下载 Chromium 浏览器到本地缓存，"
                    "供 DrissionPage 无头模式使用。只需执行一次。",
    )

    # `neobot open_web [url]`
    open_web = sub.add_parser(
        "open_web", help="启动有头浏览器供手动登录认证",
        description="启动有头 Chromium 浏览器，用户完成登录后关闭窗口，"
                    "会话持久化供后续无头模式复用。",
    )
    open_web.add_argument("url", nargs="?", default=None,
                          help="要打开的网址 (默认 bing.com)")

    # `neobot sandbox_CP`
    sub.add_parser(
        "sandbox_CP", help="独立执行沙箱清理（临时文件 + 维护），不启动 Bot",
        description="执行一次完整的沙箱临时文件清理和持久化文件维护，完成后退出。",
    )

    args = parser.parse_args()

    if args.command == "install-browser":
        cmd_install_browser(args)
    elif args.command == "open_web":
        cmd_open_web(args)
    elif args.command == "sandbox_CP":
        cmd_sandbox_clean(args)
    else:
        # 无子命令 → 启动机器人
        cmd_run(args)


if __name__ == "__main__":
    main()
