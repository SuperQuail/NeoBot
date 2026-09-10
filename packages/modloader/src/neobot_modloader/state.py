from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from neobot_contracts.ports.logging import Logger, NullLogger

STATE_VERSION = 1


@dataclass(frozen=True, slots=True)
class PluginStateEntry:
    """单个插件的持久化状态；None 表示未显式设置。"""

    enabled: bool | None = None


class PluginStateStore:
    """插件启停状态的持久化存储。

    与 plugin.toml 的 enabled 解耦，因此官方插件（无独立 plugin.toml 配置目录）
    与第三方插件可以用同一套机制启停。文件损坏时按空状态处理并记录告警，
    绝不因为状态文件问题阻断插件系统启动。
    """

    def __init__(self, path: Path, *, logger: Logger | None = None) -> None:
        self.path = Path(path)
        self._logger = logger or NullLogger()
        self._lock = RLock()
        self._entries: dict[str, PluginStateEntry] = {}
        self._loaded = False

    def load(self, *, force: bool = False) -> None:
        with self._lock:
            if self._loaded and not force:
                return
            self._entries = {}
            self._loaded = True
            if not self.path.is_file():
                return
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
            except Exception as exc:
                self._logger.warning(f"插件状态文件读取失败，已按空状态处理: {self.path}: {exc}")
                return
            plugins = raw.get("plugins") if isinstance(raw, dict) else None
            if not isinstance(plugins, dict):
                self._logger.warning(f"插件状态文件格式异常，已按空状态处理: {self.path}")
                return
            entries: dict[str, PluginStateEntry] = {}
            for name, value in plugins.items():
                if not isinstance(name, str) or not name:
                    continue
                enabled: bool | None = None
                if isinstance(value, dict):
                    candidate = value.get("enabled")
                    if isinstance(candidate, bool):
                        enabled = candidate
                elif isinstance(value, bool):
                    enabled = value
                if enabled is not None:
                    entries[name] = PluginStateEntry(enabled=enabled)
            self._entries = entries

    def entries(self) -> dict[str, PluginStateEntry]:
        with self._lock:
            self.load()
            return dict(self._entries)

    def get(self, name: str) -> PluginStateEntry | None:
        with self._lock:
            self.load()
            return self._entries.get(name)

    def is_enabled(self, name: str, default: bool = True) -> bool:
        entry = self.get(name)
        if entry is None or entry.enabled is None:
            return default
        return entry.enabled

    def set_enabled(self, name: str, enabled: bool) -> None:
        with self._lock:
            self.load()
            self._entries[name] = PluginStateEntry(enabled=bool(enabled))
            self._write()

    def forget(self, name: str) -> None:
        with self._lock:
            self.load()
            if self._entries.pop(name, None) is None:
                return
            self._write()

    def _write(self) -> None:
        payload = {
            "version": STATE_VERSION,
            "plugins": {
                name: {"enabled": entry.enabled}
                for name, entry in sorted(self._entries.items())
                if entry.enabled is not None
            },
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temp_name = tempfile.mkstemp(
                dir=str(self.path.parent), prefix=".plugin_state-", suffix=".tmp"
            )
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    handle.write(text)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_name, self.path)
            except BaseException:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass
                raise
        except Exception as exc:
            self._logger.warning(f"插件状态文件写入失败: {self.path}: {exc}")
