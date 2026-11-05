"""把插件源码保存合并为现有运行时的事务重载，不持有第二套插件生命周期。"""

from __future__ import annotations

import asyncio
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from neobot_contracts.ports.plugin import PluginState

if TYPE_CHECKING:
    from neobot_modloader.runtime import PluginRuntime

_IGNORED_DIRECTORIES = frozenset({"__pycache__", "node_modules", "venv", "build", "dist", "plugins_data"})
_READY = frozenset({PluginState.LOADED, PluginState.RUNNING})


@dataclass(frozen=True, slots=True)
class _Target:
    name: str
    path: Path
    generation: tuple[str, ...]
    record: object


@dataclass(slots=True)
class _Observation:
    target: _Target
    fingerprint: str
    pending: str | None = None
    changed_at: float = 0.0


def _fingerprint(path: Path) -> str:
    """只读源码与根契约；网页资源由页面自身的 revision 轮询刷新。"""
    digest = hashlib.sha256()
    if path.is_symlink():
        raise OSError("不监测符号链接插件")
    if path.suffix == ".py" and not path.is_dir():
        digest.update(path.read_bytes())
        return digest.hexdigest()
    if not path.is_dir() or not (path / "__init__.py").is_file():
        raise FileNotFoundError(f"插件入口暂不可用: {path}")
    root = path.resolve()
    for directory, children, files in os.walk(root, followlinks=False, onerror=_raise_scan_error):
        current = Path(directory)
        children[:] = sorted(
            child
            for child in children
            if child not in _IGNORED_DIRECTORIES and not child.startswith(".") and not (current / child).is_symlink()
        )
        for filename in sorted(files):
            asset = current / filename
            if asset.is_symlink() or filename.startswith("."):
                continue
            if asset.suffix != ".py" and not (current == root and filename in {"plugin.toml", "plugin.contract.json"}):
                continue
            relative = asset.relative_to(root).as_posix().encode()
            contents = asset.read_bytes()
            # 长度前缀保证不同文件名/内容组合不会得到相同字节串。
            digest.update(len(relative).to_bytes(8))
            digest.update(relative)
            digest.update(len(contents).to_bytes(8))
            digest.update(contents)
    return digest.hexdigest()


def _raise_scan_error(error: OSError) -> None:
    raise error


def _scan(targets: list[_Target]) -> dict[str, str | OSError]:
    results: dict[str, str | OSError] = {}
    for target in targets:
        try:
            results[target.name] = _fingerprint(target.path)
        except OSError as error:
            results[target.name] = error
    return results


class PluginHotReloader:
    """定期在线程读取已加载插件，稳定保存后串行调用运行时重载。

    不自动启用未加载/停用的插件，不安装依赖，不根据删除事件卸载仍工作的旧代。
    stop 等待在途事务结束，保证宿主停止插件前候选加载与回滚已经完成。
    """

    def __init__(
        self,
        runtime: PluginRuntime,
        *,
        poll_interval: float = 1.0,
        debounce: float = 0.3,
        names: set[str] | None = None,
    ) -> None:
        if poll_interval <= 0 or debounce < 0:
            raise ValueError("poll_interval 必须为正数，debounce 不能为负数")
        self.runtime = runtime
        self.poll_interval = poll_interval
        self.debounce = debounce
        self.names = names
        self.results: dict[str, dict[str, object]] = {}
        self._observations: dict[str, _Observation] = {}
        self._scan_errors: dict[str, str] = {}
        self._poll_lock = asyncio.Lock()
        self._stopping = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def _targets(self) -> list[_Target]:
        targets = []
        for name, path in tuple(self.runtime._loaded_paths.items()):
            if self.names is not None and name not in self.names:
                continue
            record = self.runtime.manager.get_record(name)
            if record is None or record.state not in _READY:
                continue
            if not self.runtime._loaded_flags.get(name, (True, True))[0]:
                continue
            targets.append(_Target(name, path, self.runtime._loaded_modules.get(name, ()), record))
        return targets

    def _still_current(self, target: _Target) -> bool:
        record = self.runtime.manager.get_record(target.name)
        return (
            (self.names is None or target.name in self.names)
            and record is target.record
            and record.state in _READY
            and self.runtime._loaded_paths.get(target.name) == target.path
            and self.runtime._loaded_modules.get(target.name, ()) == target.generation
            and self.runtime._loaded_flags.get(target.name, (True, True))[0]
        )

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stopping.clear()
        self._observations.clear()
        self._scan_errors.clear()
        await self.poll_once()
        self._task = asyncio.create_task(self._run(), name="plugin-hot-reload")

    async def stop(self) -> None:
        self._stopping.set()
        task = self._task
        if task is not None and task is not asyncio.current_task():
            # shield 防止调用方取消时中断插件运行时的卸载/回滚清理。
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                await task
                raise
        if task is self._task:
            self._task = None

    async def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=self.poll_interval)
            except TimeoutError:
                try:
                    await self.poll_once()
                except Exception as error:
                    self.runtime.logger.warning(f"插件源码监测失败，将在下一轮重试: {error}")

    async def poll_once(self, *, now: float | None = None) -> None:
        """完成一轮扫描；显式时间仅用于确定性验证连续保存的合并行为。"""
        async with self._poll_lock:
            targets = self._targets()
            scans = await asyncio.to_thread(_scan, targets)
            timestamp = asyncio.get_running_loop().time() if now is None else now
            names = {target.name for target in targets}
            for name in self._observations.keys() - names:
                self._observations.pop(name, None)
                self._scan_errors.pop(name, None)
            for target in targets:
                if self._stopping.is_set():
                    break
                if not self._still_current(target):
                    continue
                fingerprint = scans[target.name]
                if isinstance(fingerprint, OSError):
                    message = str(fingerprint)
                    if self._scan_errors.get(target.name) != message:
                        self.runtime.logger.warning(f"插件源码暂不可读，保留当前版本 ({target.name}): {message}")
                        self._scan_errors[target.name] = message
                    continue
                self._scan_errors.pop(target.name, None)
                observation = self._observations.get(target.name)
                if observation is None or observation.target.path != target.path:
                    self._observations[target.name] = _Observation(target, fingerprint)
                    continue
                # 前置重载会重建依赖方的 record；保留同一路径的指纹，避免把
                # 联动恢复期间的新保存误当成新代基线。手动重载后至多补读一次。
                observation.target = target
                if fingerprint == observation.fingerprint:
                    observation.pending = None
                    continue
                if observation.pending != fingerprint:
                    observation.pending = fingerprint
                    observation.changed_at = timestamp
                if timestamp - observation.changed_at < self.debounce:
                    continue
                # 每份内容只尝试一次；失败后等下一次保存，防止错误源码无限重试。
                observation.fingerprint = fingerprint
                observation.pending = None
                record = self.runtime.manager.get_record(target.name)
                sequence = int(self.results.get(target.name, {}).get("sequence", 0)) + 1
                self.results[target.name] = {"sequence": sequence, "status": "reloading"}
                try:
                    outcome = await self.runtime.reload_plugin_result(
                        target.name,
                        start=record.state is PluginState.RUNNING,
                        auto_install_dependencies=False,
                        _expected=(target.record, record.state),
                    )
                except Exception as error:
                    self.results[target.name] = {"sequence": sequence, "status": "failed", "error": str(error)}
                    self.runtime.logger.error(f"插件自动重载失败 ({target.name}): {error}")
                    continue
                self.results[target.name] = {
                    "sequence": sequence,
                    "status": "succeeded" if outcome.ok else "failed",
                    "error": outcome.error if not outcome.ok else None,
                }
                if outcome.ok:
                    self.runtime.logger.info(f"插件源码已自动重载: {target.name}")
                else:
                    self.runtime.logger.error(f"插件自动重载失败 ({target.name}): {outcome.error}")
                # 自己造成的代际变化不能吞掉加载期间的后续保存。
                current = self.runtime.manager.get_record(target.name)
                if current is not None:
                    observation.target = _Target(
                        target.name,
                        self.runtime._loaded_paths.get(target.name, target.path),
                        self.runtime._loaded_modules.get(target.name, ()),
                        current,
                    )
