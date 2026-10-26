"""网页面板端口放行与有头浏览器登录（由 cli.py 拆分）。"""

from __future__ import annotations

import argparse
import asyncio
import sys

from neobot_app.core import DATA_DIR


def _add_inbound_rule(program: str, port: int) -> bool:
    """用 netsh 添加一条入站放行规则（仅 Windows，需要管理员权限）。"""
    import subprocess

    if sys.platform != "win32":
        print("firewall-open 仅支持 Windows；Linux 请使用 ufw/firewalld 放行端口。")
        return False
    rule_name = f"NeoBot Dashboard {port}"
    command = [
        "netsh",
        "advfirewall",
        "firewall",
        "add",
        "rule",
        f"name={rule_name}",
        "dir=in",
        "action=allow",
        f"program={program}",
        "protocol=TCP",
        f"localport={port}",
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=30, check=False
        )
    except Exception as exc:
        print(f"执行 netsh 失败: {exc}")
        return False
    if result.returncode == 0:
        return True
    detail = (result.stderr or result.stdout or "").strip()
    print(f"添加失败 (TCP {port}): {detail or '请确认以管理员身份运行本命令。'}")
    print("  手动命令: " + " ".join(command))
    return False


def cmd_firewall_open(args: argparse.Namespace) -> None:
    """为网页面板端口添加 Windows 防火墙入站放行规则 (需管理员权限)。"""
    program = sys.executable
    ports = list(dict.fromkeys([args.port, 9981]))
    added = 0
    for port in ports:
        if _add_inbound_rule(program, port):
            print(f"已添加放行规则: {program} -> TCP {port}")
            added += 1
    if added == 0:
        sys.exit(1)


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
        from neobot_app.browser.agent_browser._compat import (
            DRISSIONPAGE_HINT,
            ChromiumOptions,
            ChromiumPage,
            DRISSIONPAGE_AVAILABLE,
        )

        if not DRISSIONPAGE_AVAILABLE:
            print(f"错误: {DRISSIONPAGE_HINT}")
            sys.exit(1)

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
    except ImportError as exc:
        from neobot_app.browser.agent_browser._compat import DRISSIONPAGE_HINT

        print(f"错误: {DRISSIONPAGE_HINT}")
        print(f"（原始错误：{exc}）")
        sys.exit(1)
    except Exception as exc:
        print(f"错误: 启动浏览器失败: {exc}")
        sys.exit(1)
