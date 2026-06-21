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


_MAINTENANCE_SYSTEM_PROMPT = (
    "你是一个沙箱文件维护助手，负责检查和清理沙箱中的文件。\n\n"
    "## 核心规则\n"
    "1. **清理前必须先阅读 sandbox/文件存储.md 了解当前存储规范**\n"
    "2. 如文件存储.md 不存在，先检查 sandbox/ 目录结构，按默认规范创建文件存储.md\n"
    "3. 清理完成后必须调用 file_storage__update_storage_doc 更新索引\n\n"
    "## 默认存储规范（文件存储.md 不存在时参考）\n"
    "- tools/ — 可复用的工具脚本、程序\n"
    "- docs/ — 文档、参考资料、说明文件\n"
    "- assets/ — 静态资源（图片、字体、模板等）\n"
    "- temp/ — 临时文件，按 chat_flow_id 分子目录，可随时清理\n"
    "- gift/ — 礼物文件，由 gift skill 管理，勿手动编辑\n"
    "- 文件命名统一使用 snake_case，中文名保留原样\n"
    "- 根目录只保留 文件存储.md、TODO.md 和持久化目录\n\n"
    "## 维护流程\n"
    "1. 先调用 sandbox_maintenance__check_capacity 了解容量\n"
    "2. 调用 sandbox_maintenance__scan_temp_files 检查临时文件\n"
    "3. 调用 sandbox_maintenance__get_maintenance_status 查看状态\n"
    "4. 阅读 sandbox/文件存储.md 了解当前规范\n"
    "5. 根据需要清理过期临时文件、垃圾文件、错放文件\n"
    "6. 调用 sandbox_maintenance__trigger_maintenance 整理持久化文件\n"
    "7. 完成后调用 file_storage__update_storage_doc 更新索引\n\n"
    "## 注意\n"
    "- 只做文件清理和整理，不实现新工具，不处理 TODO\n"
    "- 输出简洁明了，完成每步后汇报结果"
)


async def _run_sandbox_cleanup() -> int:
    """独立启动 AI agent 执行沙箱维护清理。不依赖运行中的 Bot。"""
    from dataclasses import dataclass

    from neobot_app.assembly.agents import resolve_agent_model_name
    from neobot_app.bootstrap._config import build_config
    from neobot_app.bootstrap._runtime import build_sandbox_components
    from neobot_app.core import DATA_DIR

    print("沙箱维护 Agent 启动中…")
    print()

    # 1. 加载配置
    config = build_config()
    sandbox_cfg = getattr(config.agent, "sandbox", None)
    if not sandbox_cfg or not sandbox_cfg.enabled:
        print("错误: 沙箱功能未启用 (agent.sandbox.enabled = false)")
        return 1

    # 2. 构建沙箱组件
    sandbox = build_sandbox_components(config=config, data_dir=DATA_DIR)
    sandbox_service = sandbox["sandbox_service"]
    if sandbox_service is None:
        print("错误: sandbox_service 未构建成功")
        return 1

    print(f"沙箱目录: {DATA_DIR / 'sandbox'}")
    print()

    # 3. 创建 AI Provider
    model_name = resolve_agent_model_name(config, "main_agent", default_index=0)
    from neobot_chat.models import create_provider
    try:
        provider = create_provider(model_name)
    except Exception as exc:
        print(f"错误: 无法创建 provider ({model_name}): {exc}")
        return 1
    print(f"AI 模型: {model_name}")

    # 4. 构建 SkillManager（仅沙箱相关技能）
    from neobot_app.skills.base import SkillManager
    from neobot_app.skills.sandbox_manager_skill import SandboxManagerSkill
    from neobot_app.skills.sandbox_maintenance_skill import SandboxMaintenanceSkill
    from neobot_app.skills.file_storage_skill import FileStorageSkill

    mgr = SkillManager()
    mgr.register(SandboxManagerSkill(
        sandbox_service=sandbox_service,
        sandbox_lock=sandbox["sandbox_lock"],
        hold_max_minutes=120,
    ))
    mgr.register(SandboxMaintenanceSkill(
        maintenance_manager=sandbox["sandbox_maintenance_manager"],
        sandbox_service=sandbox_service,
        temp_cleaner=sandbox["temp_cleaner"],
    ))
    mgr.register(FileStorageSkill(
        sandbox_service=sandbox_service,
    ))

    # 5. 将 SkillManager 包装为 ToolExecutor → Toolset
    from neobot_chat.tools.toolset import ToolSpec, Toolset

    @dataclass(frozen=True)
    class _SkillToolExecutor:
        _mgr: SkillManager

        def definitions(self):
            return self._mgr.get_tools()

        async def execute(self, name: str, args: dict) -> str:
            return await self._mgr.execute(name, args)

        async def close(self) -> None:
            pass

    def _always_allow(_args, _ctx, _policy):
        from neobot_chat.schema.types import ToolAccessRule
        return ToolAccessRule(action="allow")

    tool_defs = mgr.get_tools()
    specs = [ToolSpec(definition=d, access_resolver=_always_allow) for d in tool_defs]
    toolset = Toolset(executor=_SkillToolExecutor(mgr), specs=specs)
    print(f"已加载 {len(tool_defs)} 个工具")
    print()

    # 6. 创建 Agent
    from neobot_chat.runtime.agent import Agent

    agent = Agent(
        provider=provider,
        toolset=toolset,
        system_prompt=_MAINTENANCE_SYSTEM_PROMPT,
        max_iterations=30,
        command_timeout=120,
    )

    # 7. 执行维护
    print("正在执行沙箱维护…")
    print("─" * 50)
    state = {
        "messages": [
            {
                "role": "user",
                "content": (
                    "请执行一次完整的沙箱维护清理。\n"
                    "按系统提示中的维护流程逐步操作，完成每步后汇报结果。"
                ),
            },
        ],
    }
    try:
        result = await agent.invoke(state)
    except Exception as exc:
        print(f"\n错误: Agent 执行失败: {exc}")
        return 1
    finally:
        try:
            await provider.close()
        except Exception:
            pass

    # 8. 输出结果
    messages = result.get("messages", [])
    for msg in messages:
        role = msg.get("role", "")
        if role == "assistant":
            content = msg.get("content")
            if content:
                print(content)
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    print(f"\n[工具] {tc['function']['name']}")
        elif role == "tool":
            content = msg.get("content", "")
            # 截断过长输出
            if len(content) > 200:
                content = content[:200] + "…"
            print(f"  -> {content}")

    print("─" * 50)
    print("\n沙箱维护完成。")
    return 0


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
