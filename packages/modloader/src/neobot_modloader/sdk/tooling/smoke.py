"""对最终 ZIP 使用真实安装器与运行时进行有边界的冒烟验收。"""

from __future__ import annotations

import asyncio
import hashlib
import tempfile
import tomllib
from importlib.metadata import version
from pathlib import Path
from typing import Any

from neobot_contracts.ports.logging import NullLogger
from neobot_contracts.ports.plugin import PluginState
from neobot_modloader.installer import MAX_ARCHIVE_BYTES, PluginInstaller
from neobot_modloader.runtime import PluginRuntime
from neobot_modloader.state import PluginStateStore

from .models import ToolingError, ToolReport
from .validation import check_project


class _Adapter:
    """只收集合成出站消息，不连接真实 QQ。"""

    def __init__(self) -> None:
        self.messages: list[Any] = []

    async def send(self, conversation: Any, message: Any) -> str:
        self.messages.append(message)
        return "sdk-smoke-message"


class _LoggerFactory:
    def get_logger(self, name: str) -> NullLogger:
        return NullLogger()


async def _close_runtime(runtime: PluginRuntime) -> None:
    """结束所有已注册代，卸载后模块缓存也必须释放。"""
    for name in reversed(list(runtime.manager.names())):
        record = runtime.manager.get_record(name)
        previous_error = record.error if record is not None else None
        try:
            result = await runtime.unload_plugin(name, force=True)
        except SystemExit as exc:
            raise ToolingError(f"cleanup: 插件 {name} 请求退出: {exc.code!r}") from exc
        if runtime.manager.get_record(name) is not None:
            raise ToolingError(f"cleanup: 插件 {name} 未成功卸载")
        if not result.ok or (result.error is not None and previous_error is None):
            raise ToolingError(f"cleanup: {result.error}")
    from neobot_modloader.sdk.storage import close_runtime_storage

    close_runtime_storage(runtime)


async def _join_cleanup(runtime: PluginRuntime) -> None:
    task = asyncio.create_task(asyncio.wait_for(_close_runtime(runtime), timeout=10.0))
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        await asyncio.shield(task)
        raise


def _ensure_state(runtime: PluginRuntime, name: str, expected: PluginState, stage: str) -> None:
    record = runtime.manager.get_record(name)
    if record is not None and record.state is expected and record.error is None:
        return
    snapshot = next((item for item in runtime.snapshot_plugins() if item.name == name), None)
    detail = record.error if record is not None else None
    if detail is None and snapshot is not None:
        detail = snapshot.error or snapshot.disabled_reason or snapshot.state
    raise ToolingError(f"{stage}: {detail or '插件未注册'}")


async def _run_installed(
    root: Path,
    archive: bytes,
    config: Path | None,
    checks: list[str],
    not_applicable: list[str],
) -> None:
    async def fetcher(url: str) -> bytes:
        return archive

    installer = PluginInstaller(plugin_dir=root / "plugins", fetcher=fetcher)
    installed = await installer.install("sdk-smoke/package")
    if not installed.ok or installed.path is None:
        raise ToolingError(f"install: {installed.error}")
    checks.append("install")
    static = check_project(installed.path)
    if not static.ok:
        raise ToolingError("installed-check: " + "; ".join(static.errors))
    state = PluginStateStore(root / "plugin_state.json")
    state.set_enabled(installed.name, True)
    runtime = PluginRuntime(
        plugin_dir=root / "plugins",
        data_dir=root / "data",
        adapter=_Adapter(),
        logger_factory=_LoggerFactory(),
        installer=installer,
        state_store=state,
        host_version=version("neobot-modloader"),
    )
    try:
        external = runtime.plugin_config_path(installed.name)
        if external is None or external.resolve().is_relative_to(installed.path.resolve()):
            raise ToolingError("external_config: 配置没有位于插件代码目录外")
        payload = config.read_bytes() if config is not None else "# SDK 冒烟验收配置\n".encode()
        tomllib.loads(payload.decode("utf-8-sig"))
        external.parent.mkdir(parents=True, exist_ok=True)
        external.write_bytes(payload)
        runtime.load_all()
        await runtime.load_registered()
        await runtime.start_all()
        _ensure_state(runtime, installed.name, PluginState.RUNNING, "start")
        if runtime.plugin_config_error(installed.name):
            raise ToolingError("start: 样例配置未通过插件模型校验")
        checks.append("start")
        stopped = await runtime.stop_plugin(installed.name)
        if not stopped.ok:
            raise ToolingError(f"stop: {stopped.error}")
        _ensure_state(runtime, installed.name, PluginState.STOPPED, "stop")
        checks.append("stop")
        restarted = await runtime.start_plugin(installed.name)
        if not restarted.ok:
            raise ToolingError(f"restart: {restarted.error}")
        _ensure_state(runtime, installed.name, PluginState.RUNNING, "restart")
        checks.append("restart")
        snapshot = next(item for item in runtime.snapshot_plugins() if item.name == installed.name)
        if snapshot.hot_reload:
            reloaded = await runtime.reload_plugin_result(installed.name)
            if not reloaded.ok:
                raise ToolingError(f"reload: {reloaded.error}")
            _ensure_state(runtime, installed.name, PluginState.RUNNING, "reload")
            checks.append("reload")
        else:
            not_applicable.append("reload")
        if external.read_bytes() != payload or (installed.path / "config.toml").exists():
            raise ToolingError("external_config: 配置被修改或写入插件代码目录")
        checks.append("external_config")
    finally:
        await _join_cleanup(runtime)


async def smoke_package(path: Path, *, config: Path | None = None, timeout: float = 30.0) -> ToolReport:
    """会执行包内代码；模拟服务不构成进程或网络沙箱，也不验证数据库迁移。"""
    package = Path(path).resolve()
    checks: list[str] = []
    not_applicable: list[str] = []
    digest = ""
    errors: list[str] = []
    try:
        if timeout <= 0:
            raise ToolingError("timeout 必须大于零")
        if not package.is_file() or package.stat().st_size > MAX_ARCHIVE_BYTES:
            raise ToolingError("ZIP 不存在或超过安装器压缩体积上限")
        archive = package.read_bytes()
        if len(archive) > MAX_ARCHIVE_BYTES:
            raise ToolingError("ZIP 超过安装器压缩体积上限")
        digest = hashlib.sha256(archive).hexdigest()
        with tempfile.TemporaryDirectory(prefix="neobot-sdk-smoke-") as directory:
            async with asyncio.timeout(timeout):
                await _run_installed(Path(directory), archive, config, checks, not_applicable)
    except asyncio.CancelledError:
        raise
    except SystemExit as exc:
        errors.append(f"插件请求退出: {exc.code!r}")
    except Exception as exc:
        errors.append("smoke: 运行超时" if isinstance(exc, TimeoutError) else str(exc))
    return ToolReport(
        "smoke",
        not errors,
        tuple(checks),
        tuple(errors),
        str(package),
        digest,
        executes_plugin=True,
        not_applicable=tuple(not_applicable),
        unverified=("real_services", "database_migration", "business_behavior"),
    )
