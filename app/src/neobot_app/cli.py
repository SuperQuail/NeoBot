"""neobot CLI — 启动机器人或执行快捷操作。"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
from pathlib import Path
from typing import Any

# This branch must precede bootstrap/config imports: the frozen executable is
# also a lazy stdio LSP worker, not a second Bot service.
from neobot_app.agent_tools.lsp_defaults import PYTHON_LSP_WORKER_FLAG

if PYTHON_LSP_WORKER_FLAG in sys.argv[1:]:
    if sys.argv[1:] != [PYTHON_LSP_WORKER_FLAG]:
        raise SystemExit("The internal Python LSP worker accepts no additional arguments")
    from neobot_app.agent_tools.lsp_defaults import run_python_lsp_worker

    run_python_lsp_worker()
    raise SystemExit(0)

from neobot_app.bootstrap import (
    create_application,
    enable_core_reuse,
    get_cached_core,
)
from neobot_app.bootstrap._standby_runtime import STOP_TIMEOUT_SECONDS, StandbyController
from neobot_app.config.loader.manager import ConfigLoadError
from neobot_app.core import APP_VERSION, DATA_DIR
from neobot_app.runtime.instance_lease import InstanceAlreadyRunning, InstanceLease
from neobot_app.runtime.application import ConnectionTimeoutError
from neobot_app.utils.http import sanitize_no_proxy_environment
from neobot_app.cli_parts.doctor import cmd_doctor, cmd_install_browser
from neobot_app.cli_parts.init import cmd_init
from neobot_app.cli_parts.network import cmd_firewall_open, cmd_open_web
from neobot_app.cli_parts.sandbox import cmd_sandbox_clean


async def run() -> bool:
    with InstanceLease(DATA_DIR):
        return await _run_instance()


async def _run_instance() -> bool:
    """运行一轮；只有所有旧运行时与核心清理确认完成，才允许进程重启。"""
    loop = asyncio.get_running_loop()
    state: dict[str, Any] = {"application": None, "stopping": False, "controller": None}

    def request_stop() -> None:
        # A normal process stop always wins, even if restart was requested first.
        state["stopping"] = True
        controller = state["controller"]
        if controller is not None:
            controller.request_shutdown()
        elif state["application"] is not None:
            state["application"].request_stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, request_stop)
        except NotImplementedError:
            if sig == signal.SIGINT:
                signal.signal(
                    signal.SIGINT,
                    lambda _signum, _frame: loop.call_soon_threadsafe(request_stop),
                )

    # 面板的退出端点走核心信号（`process_stop`）：它跨代际存活，待机态 / 切换中
    # 也收得到。在旧版装配里这个服务不存在，那就只有 SIGINT/SIGTERM 一条路，
    # 与本次改动前一致。
    stop_watcher: asyncio.Task[None] | None = None

    async def watch_stop() -> None:
        signal = get_cached_core("process_stop")
        if signal is None:
            return
        await signal.wait()
        request_stop()

    enable_core_reuse()
    stop_watcher = asyncio.create_task(watch_stop(), name="neobot-process-stop-watch")
    application = create_application(owns_plugins=False)
    standby_service = get_cached_core("standby_service")
    if standby_service is None:
        # Legacy standalone/test assembly has no core watcher.
        state["application"] = application
        try:
            await application.run_forever()
            return not state["stopping"] and application.restart_requested
        finally:
            state["application"] = None
    logger_factory = get_cached_core("logger_factory")
    logger = logger_factory.get_logger("app.standby") if logger_factory else None
    restart_signal = get_cached_core("process_restart")
    controller = StandbyController(
        standby_service=standby_service,
        runtime_factory=lambda: create_application(owns_plugins=False),
        adapter=get_cached_core("adapter"),
        initial_application=application,
        logger=logger,
        restart_signal=restart_signal,
    )
    state["controller"] = controller
    standby_service.set_hooks(
        on_enter=controller.enter,
        on_resume=controller.resume,
        on_onebot_change=controller.set_onebot,
    )
    plugin_runtime = get_cached_core("plugin_runtime")
    control_server = None
    from neobot_modloader.runtime import PluginRuntime

    if isinstance(plugin_runtime, PluginRuntime):
        from neobot_app.runtime.local_control import LocalControlServer

        control_server = LocalControlServer(
            plugin_runtime, data_dir=DATA_DIR, version=APP_VERSION, request_stop=request_stop
        )

    async def startup() -> None:
        try:
            if plugin_runtime is not None and not controller.exiting:
                await plugin_runtime.load_registered()
                if not controller.exiting:
                    await plugin_runtime.start_all()
            if not controller.exiting:
                ok, detail = await controller.start()
                if not ok:
                    standby_service.record_failure(detail)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            standby_service.record_failure(f"启动失败：{type(exc).__name__}: {exc}")

    try:
        if control_server is not None:
            await control_server.start()
        startup_task = asyncio.create_task(startup(), name="neobot-core-startup")
        restart_requested = await run_entry_loop(
            controller=controller,
            standby_service=standby_service,
            restart_signal=restart_signal,
            state=state,
            startup_task=startup_task,
        )
    finally:
        try:
            state["application"] = None
            if control_server is not None:
                await control_server.begin_shutdown()
            if stop_watcher is not None:
                stop_watcher.cancel()
                await asyncio.gather(stop_watcher, return_exceptions=True)
            # Do not rely on asyncio.run's cancellation drain to own core shutdown.
            # In particular, a timeout is a report, NEVER permission to exec early.
            if plugin_runtime is not None:

                async def stop_core() -> None:
                    await plugin_runtime.stop_all()
                    registry = getattr(plugin_runtime, "agent_registry", None)
                    if registry is not None:
                        await registry.close()

                await _drain_shutdown_task(asyncio.create_task(stop_core()), "core plugins")
        finally:
            if control_server is not None:
                await control_server.close()
    # SIGINT/SIGTERM can arrive during the last core cleanup await too.
    return not state["stopping"] and restart_requested


async def _drain_shutdown_task(task: asyncio.Task, phase: str, timeout: float | None = None) -> Any:
    if timeout is None:
        timeout = STOP_TIMEOUT_SECONDS
    done, _ = await asyncio.wait((task,), timeout=timeout)
    if not done:
        print(
            f"优雅关闭仍在等待 {phase}；不会启动新进程。若持续卡住，需手动处理或显式强制重启。",
            file=sys.stderr,
        )
    return await asyncio.shield(task)


async def run_entry_loop(
    *,
    controller: Any,
    standby_service: Any,
    restart_signal: Any = None,
    state: dict[str, Any],
    poll_interval: float = 0.5,
    startup_task: asyncio.Task | None = None,
) -> bool:
    """Monitor process intent concurrently with startup, run_forever and standby.

    The restart watcher only resolves the current controller, never a captured
    runtime. The process remains alive (with truthful diagnostics) if graceful
    cleanup is stuck; returning True would incorrectly authorize execv.
    """

    async def watch_restart() -> None:
        await restart_signal.wait()
        controller.request_shutdown()

    #: 优雅关闭的观察窗口来自装配层（可配置）；控制器缺失时回落到模块默认值。
    stop_timeout = float(getattr(controller, "stop_timeout", STOP_TIMEOUT_SECONDS))
    watcher = (
        asyncio.create_task(watch_restart(), name="neobot-process-restart-watch")
        if restart_signal is not None
        else None
    )
    runtime_task: asyncio.Task | None = None
    runtime: Any = None
    legacy_restart = False
    last_failure = ""
    shutdown_confirmed = False
    try:
        while True:
            legacy_restart = legacy_restart or bool(runtime is not None and runtime.restart_requested)
            restart = legacy_restart or bool(restart_signal is not None and restart_signal.requested)
            if state.get("stopping") or restart:
                controller.request_shutdown()
                if startup_task is not None and not startup_task.done():
                    if not startup_task.cancelling():
                        startup_task.cancel()
                    # Retain the task; cancellation-resistant plugin startup
                    # must finish before core teardown begins.
                    failure = "startup 清理仍在进行；若优雅关闭卡住需手动处理或显式强制重启。"
                else:
                    ok, failure = await controller.shutdown()
                    if ok and (runtime_task is None or runtime_task.done()):
                        if runtime_task is not None:
                            await runtime_task
                        shutdown_confirmed = True
                        return not state.get("stopping", False) and restart
                if failure != last_failure:
                    print(failure, file=sys.stderr)
                    last_failure = failure
            else:
                if runtime_task is not None and runtime_task.done():
                    await runtime_task
                    state["application"] = None
                    runtime_task = None
                    if controller.application in (None, runtime) and not standby_service.is_standby():
                        state["stopping"] = True
                        continue
                if runtime_task is None:
                    current = controller.application
                    if current is not None:
                        runtime = current
                        state["application"] = current
                        runtime_task = asyncio.create_task(current.run_forever(), name="neobot-run-forever")
            waiting = [task for task in (runtime_task, startup_task, watcher) if task is not None and not task.done()]
            if waiting:
                await asyncio.wait(waiting, timeout=poll_interval, return_when=asyncio.FIRST_COMPLETED)
            else:
                await asyncio.sleep(poll_interval)
    finally:
        state["application"] = None
        if not shutdown_confirmed:
            controller.request_shutdown()
        if watcher is not None:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
        if startup_task is not None:
            if not startup_task.done():
                startup_task.cancel()
            try:
                await _drain_shutdown_task(startup_task, "startup", stop_timeout)
            except asyncio.CancelledError:
                if not startup_task.cancelled():
                    raise
        if runtime_task is not None and not runtime_task.done():
            controller.request_shutdown()
            await _drain_shutdown_task(runtime_task, "runtime", stop_timeout)
        if not shutdown_confirmed:
            while True:
                await _drain_shutdown_task(
                    asyncio.create_task(controller.wait_for_idle()),
                    "runtime transition",
                    stop_timeout,
                )
                ok, detail = await controller.shutdown()
                if ok:
                    break
                if not controller.lifecycle_status()["pending"]:
                    raise RuntimeError(detail)


def cmd_run(args: argparse.Namespace) -> None:
    """启动机器人；重启时先回收旧循环，再以原启动参数替换进程。"""
    try:
        restart_requested = asyncio.run(run())
    except InstanceAlreadyRunning as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except ConfigLoadError as exc:
        print(f"配置加载失败，无法启动机器人：\n{exc}")
        print("请补充上述缺失的环境变量（或禁用对应功能）后重新启动。")
        sys.exit(1)
    except ConnectionTimeoutError as exc:
        print(f"错误: {exc}")
    except KeyboardInterrupt:
        sys.exit(0)
    else:
        if restart_requested:
            # asyncio.run 已取消剩余任务、关闭异步生成器/default executor 和 loop。
            if getattr(sys, "frozen", False):
                # PyInstaller 新顶层实例须重新解包，不能复用旧 onefile 的临时目录。
                os.environ["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
                argv = [sys.executable, *sys.argv[1:]]
            else:
                # 保留解释器 flags 以及 -m / 脚本 / console entry 启动方式。
                argv = [sys.executable, *sys.orig_argv[1:]]
            if sys.platform == "win32":
                import subprocess

                # CRT _wexecv 会拼接 argv 而不转义，含空格参数须自行引用：
                # https://learn.microsoft.com/cpp/c-runtime-library/exec-wexec-functions
                argv = [subprocess.list2cmdline([arg]) for arg in argv]
            os.execv(sys.executable, argv)


# ── VC++ 运行库检测与安装(onnxruntime 1114 最常见根因) ──

_VC_DLLS = [
    "vcruntime140.dll",
    "vcruntime140_1.dll",
    "msvcp140.dll",
    "msvcp140_1.dll",
    "msvcp140_2.dll",
    "msvcp140_atomic_wait.dll",
]
_VC_MIN_VERSION = (14, 40, 0, 0)  # VC++ 2015-2022 redist 新版基线
_VC_SYSTEM32 = Path(r"C:\Windows\System32")
VC_REDIST_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe"


def _file_version_win(path: str) -> str:
    """ctypes WinAPI 读取文件版本。"""
    import ctypes
    import struct

    try:
        size = ctypes.windll.version.GetFileVersionInfoSizeW(path, None)
        if not size:
            return ""
        buf = ctypes.create_string_buffer(size)
        if not ctypes.windll.version.GetFileVersionInfoW(path, 0, size, buf):
            return ""
        ptr = ctypes.c_void_p()
        total = ctypes.c_uint()
        if not ctypes.windll.version.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(total)):
            return ""
        data = ctypes.string_at(ptr, total.value)
        if len(data) < 16:
            return ""
        ms, ls = struct.unpack_from("<II", data, 8)
        return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
    except Exception:
        return ""


def _vc_runtime_issues() -> list[str]:
    """Windows 下检查 VC++ 运行库,返回问题描述列表(空 = 正常)。"""
    import platform

    if platform.system() != "Windows":
        return []
    issues: list[str] = []
    system32 = _VC_SYSTEM32
    for dll in _VC_DLLS:
        path = system32 / dll
        if not path.exists():
            issues.append(f"缺失 {dll}(VC++ 运行库不完整)")
            continue
        version = _file_version_win(str(path))
        try:
            parsed = tuple(int(p) for p in version.split(".")) if version else ()
        except ValueError:
            parsed = ()
        if parsed and parsed < _VC_MIN_VERSION:
            issues.append(f"{dll} 版本过旧: {version}(建议 ≥14.40)")
    return issues


def _ask_install_vc_redist() -> str:
    """询问是否在线下载安装 VC++ 运行库,返回 "online" / ""(跳过)。"""
    try:
        answer = input("是否在线下载最新版 VC++ 运行库并安装(约 25 MB,需管理员,可能弹出 UAC)? [y/N] ").strip().lower()
        return "online" if answer in ("y", "yes") else ""
    except (EOFError, KeyboardInterrupt):
        print("(非交互环境,跳过安装)")
        return ""


def _download_vc_redist() -> Path | None:
    """在线下载最新 VC++ redist 到临时目录。"""
    import tempfile
    import urllib.request

    target = Path(tempfile.gettempdir()) / "vc_redist.x64.exe"
    print(f"在线下载: {VC_REDIST_URL}")
    try:
        urllib.request.urlretrieve(VC_REDIST_URL, target)
        print(f"已下载: {target} ({target.stat().st_size / 1024 / 1024:.1f} MB)")
        return target
    except Exception as exc:
        print(f"下载失败: {exc}")
        return None


def _install_vc_redist(package: Path) -> bool:
    """提权静默安装 VC++ redist(UAC 弹窗);装完返回是否已生效。"""
    import subprocess

    print(f"执行: Start-Process '{package}' /install /quiet /norestart(触发 UAC)")
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "Start-Process -FilePath "
                    f"'{package}' -ArgumentList '/install','/quiet','/norestart' "
                    "-Verb RunAs -Wait"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        return result.returncode == 0
    except Exception as exc:
        print(f"安装调用失败: {exc}")
        return False


def _ensure_vc_runtime_fixed() -> bool:
    """onnx 不可用时优先处理 VC++ 运行库(Windows):检测 → 在线下载 → 安装。

    Returns: True 表示运行库问题已解决(可重新探测 onnxruntime)。
    """
    import platform

    if platform.system() != "Windows":
        return False
    issues = _vc_runtime_issues()
    if not issues:
        return False
    print("检测到 VC++ 运行库问题(onnxruntime/torch DLL 初始化失败 1114 的最常见根因):")
    for item in issues:
        print(f"         - {item}")
    print(f"         将在线下载最新版 VC++ 运行库: {VC_REDIST_URL}")
    choice = _ask_install_vc_redist()
    if not choice:
        print(
            f"         跳过。可稍后手动下载安装: {VC_REDIST_URL}"
            "(右键管理员运行)或 scripts/onnx_deploy_check.py --install-redist"
        )
        return False
    installer = _download_vc_redist()
    if installer is None:
        print(f"         下载失败。请手动下载并安装: {VC_REDIST_URL}(以管理员身份运行 vc_redist.x64.exe)")
        return False
    if not _install_vc_redist(installer):
        print(f"         安装失败,请手动下载安装: {VC_REDIST_URL}(以管理员身份运行,可能需重启后生效)")
        return False
    leftover = _vc_runtime_issues()
    if leftover:
        print("         安装完成但运行库仍存在问题(可能需要重启后生效):")
        for item in leftover:
            print(f"           - {item}")
        return False
    print("         VC++ 运行库已更新完成")
    return True


def main() -> None:
    # 启动期加固（先于任何 httpx 客户端构造）：把 NO_PROXY 里 "[::1]" 这类带方括号的
    # IPv6 字面量还原成 "::1"。httpx 只识别不带方括号的形态，带方括号的会被当成域名
    # 通配条目并生成非法的 URLPattern，导致装配阶段直接抛 httpx.InvalidURL 而整体启动失败。
    renormalized = sanitize_no_proxy_environment()
    if renormalized:
        print(
            "[启动] 已规范化 NO_PROXY 中的 IPv6 字面量（去掉方括号）: " + ", ".join(renormalized),
            file=sys.stderr,
        )

    parser = argparse.ArgumentParser(prog="neobot", description="NeoBot — QQ 机器人")
    parser.add_argument(
        # 版本号动态取自包元数据（neobot_app.core.APP_VERSION → importlib.metadata），
        # 不再硬编码：升级版本时只需改 pyproject.toml，CLI 自动跟随。
        "--version",
        action="version",
        version=f"%(prog)s {APP_VERSION}",
    )

    sub = parser.add_subparsers(title="子命令", dest="command")

    # `neobot install-browser`
    sub.add_parser(
        "install-browser",
        help="下载内嵌 Chromium 浏览器",
        description="通过 Playwright 下载 Chromium 浏览器到本地缓存，供 DrissionPage 无头模式使用。只需执行一次。",
    )

    # `neobot open_web [url]`
    open_web = sub.add_parser(
        "open_web",
        help="启动有头浏览器供手动登录认证",
        description="启动有头 Chromium 浏览器，用户完成登录后关闭窗口，会话持久化供后续无头模式复用。",
    )
    open_web.add_argument("url", nargs="?", default=None, help="要打开的网址 (默认 bing.com)")

    # `neobot sandbox_CP`
    sub.add_parser(
        "sandbox_CP",
        help="独立执行沙箱清理（临时文件 + 维护），不启动 Bot",
        description="执行一次完整的沙箱临时文件清理和持久化文件维护，完成后退出。",
    )

    # `neobot firewall-open`
    firewall_parser = sub.add_parser(
        "firewall-open",
        help="放行网页面板端口（Windows 防火墙，需管理员）",
        description="为当前 Python 程序添加网页面板端口的入站放行规则，"
        "解决'内网可访问、外网不可用'的问题。需以管理员身份运行。",
    )
    firewall_parser.add_argument(
        "--port",
        type=int,
        default=9981,
        help="网页面板端口 (默认 9981)",
    )

    # `neobot doctor`
    sub.add_parser(
        "doctor",
        help="依赖体检：列出关键第三方库的版本与缺失符号，不启动 Bot",
        description="检查 DrissionPage / httpx / sqlalchemy / aiohttp / loguru 的版本，"
        "逐个验证项目真正用到的符号是否存在，并打印模块路径与解释器信息。"
        "新环境部署报 ImportError / AttributeError 时先跑它。",
    )

    # `neobot init [--force]`
    init_parser = sub.add_parser(
        "init",
        help="重新扫描并建立资源索引（模型库等），不启动 Bot",
        description="扫描模型目录等可再生资源并重建索引（如 data/vision_detect/models.toml），"
        "通常在放入新模型后执行；启动 Bot 时也会自动执行。",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="强制重建索引骨架（不会覆盖已填写的模型描述）",
    )

    args = parser.parse_args()

    if args.command == "install-browser":
        cmd_install_browser(args)
    elif args.command == "open_web":
        cmd_open_web(args)
    elif args.command == "sandbox_CP":
        cmd_sandbox_clean(args)
    elif args.command == "firewall-open":
        cmd_firewall_open(args)
    elif args.command == "init":
        cmd_init(args)
    elif args.command == "doctor":
        cmd_doctor(args)
    else:
        # 无子命令 → 启动机器人
        cmd_run(args)


if __name__ == "__main__":
    main()
