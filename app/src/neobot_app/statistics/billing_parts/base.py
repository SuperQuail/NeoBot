"""BillingService 的状态装载与面板投影。"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_app.core.paths import get_data_dir

from .core import BillingSettings, _LoadedPolicy, _ScriptStat

class BillingServiceBase:

    def __init__(
        self,
        *,
        config: Any = None,
        config_provider: Callable[[], Any] | None = None,
        logger: Logger | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self._config_fixed = config
        self._config_provider = config_provider
        self._logger = logger or NullLogger()
        self._data_dir = Path(data_dir) if data_dir is not None else get_data_dir()
        self._custom_dir = self._data_dir / "Billing"
        try:
            self._custom_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:  # pragma: no cover - 目录不可写时只告警
            self._logger.warning("计费脚本目录创建失败", dir=str(self._custom_dir), error=str(exc))
        self._policies: dict[str, _LoadedPolicy] = {}
        self._stats: dict[str, _ScriptStat] = {}
        self._errors: dict[str, str] = {}
        #: 绑定了名字但文件不存在的脚本（用于区分 fallback:missing 与 fallback:error）
        self._missing: set[str] = set()
        self._lock = threading.RLock()
        self._inflight = 0
        self._inflight_lock = threading.Lock()
        self.sync_templates()

    # ------------------------------------------------------------------
    # 基础属性
    # ------------------------------------------------------------------

    @property
    def custom_dir(self) -> Path:
        return self._custom_dir

    def current_config(self) -> Any:
        if self._config_provider is not None:
            try:
                return self._config_provider()
            except Exception:  # pragma: no cover - 配置代理异常时退回固定配置
                return self._config_fixed
        return self._config_fixed

    @property
    def settings(self) -> BillingSettings:
        """每次现取 [billing]，改配置无需重启（R4/Q13）。"""
        return BillingSettings.from_config(self.current_config())

    # ------------------------------------------------------------------
    # 面板
    # ------------------------------------------------------------------

    def script_status(self, name: str) -> dict[str, Any] | None:
        record = self._stats.get(str(name or "").strip())
        return record.to_dict() if record is not None else None

    def describe(self) -> dict[str, Any]:
        """GET /api/config/billing 的主体。"""
        settings = self.settings
        return {
            "enabled": settings.enabled,
            "timeout_ms": settings.timeout_ms,
            "reload_on_change": settings.reload_on_change,
            "record_detail": settings.record_detail,
            "directory": str(self._custom_dir),
            "scripts": self.available_scripts(),
            "templates": self.template_names(),
            "policies": {name: self._stats[name].to_dict() for name in sorted(self._stats)},
            "errors": dict(self._errors),
        }
