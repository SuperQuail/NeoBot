"""日志、任务、服务与插件列表接口。"""

from __future__ import annotations

from typing import Any

from aiohttp import web
from ._common import _json_ok, _json_error, _status_text


class SystemMixin:
    # ------------------------------------------------------------------
    # 日志 / 任务 / 服务
    # ------------------------------------------------------------------

    async def logs(self, request: web.Request) -> web.Response:
        limit = self._int_arg(request, "limit", 200, minimum=1, maximum=2000)
        since = self._int_arg(request, "since", 0, minimum=0, maximum=10**9)
        return _json_ok(self.metrics.logs(since=since, limit=limit))

    async def tasks(self, request: web.Request) -> web.Response:
        payload: dict[str, Any] = {"scheduled": [], "background": []}
        manager = self._service("scheduled_task_manager")
        lister = getattr(manager, "list_tasks", None) if manager is not None else None
        if callable(lister):
            try:
                value = lister()
                if hasattr(value, "__await__"):
                    value = await value
                payload["scheduled"] = value if isinstance(value, list) else []
            except Exception as exc:
                payload["scheduled_error"] = str(exc)
        elif manager is not None:
            # 显式报错而不是静默留空：接口改名/缺失时面板会直接显示原因，
            # 不会让「定时任务列表恒为空」这种问题再次无声无息。
            payload["scheduled_error"] = "scheduled_task_manager 未提供 list_tasks 接口"
        drawing = self._service("drawing_manager")
        status = getattr(drawing, "list_active", None) if drawing is not None else None
        if callable(status):
            try:
                payload["background"] = status()
            except Exception as exc:
                payload["background_error"] = str(exc)
        return _json_ok(payload)

    async def services(self, request: web.Request) -> web.Response:
        registry = self.console.services
        describe = getattr(registry, "describe", None) if registry is not None else None
        items: list[dict[str, Any]] = []
        if callable(describe):
            try:
                items = describe()
            except Exception:
                items = []
        return _json_ok({"items": items, "plugin_runtime": self._plugin_control() is not None})

    # ------------------------------------------------------------------
    # 插件管理
    # ------------------------------------------------------------------

    def _plugin_summary(self) -> dict[str, int]:
        control = self._plugin_control()
        if control is None:
            return {"total": 0, "loaded": 0, "error": 0}
        try:
            snapshots = control.snapshot()
        except Exception:
            return {"total": 0, "loaded": 0, "error": 0}
        return {
            "total": len(snapshots),
            "loaded": sum(1 for item in snapshots if item.state == "running"),
            "error": sum(1 for item in snapshots if item.state == "error"),
        }

    def _plugin_payload(self, snapshot: Any) -> dict[str, Any]:
        return {
            "id": snapshot.name,
            "name": snapshot.name,
            "version": snapshot.version,
            "status": _status_text(snapshot),
            "state": snapshot.state,
            "enabled": snapshot.enabled,
            "description": snapshot.description,
            "author": snapshot.author,
            "source": snapshot.source,
            "official": snapshot.official,
            "manageable": snapshot.manageable,
            "kind": snapshot.kind,
            "path": str(snapshot.path) if snapshot.path else "",
            "error": snapshot.error,
            "repo": snapshot.repo,
            "branch": snapshot.branch,
            "homepage": snapshot.homepage,
            "license": snapshot.license,
            "tags": list(snapshot.tags),
            "dependencies": list(snapshot.dependencies),
            "python_dependencies": list(snapshot.python_dependencies),
            "missing_python_dependencies": list(snapshot.missing_python_dependencies),
            "hot_reload": bool(getattr(snapshot, "hot_reload", True)),
            "config_hot_reload": bool(getattr(snapshot, "config_hot_reload", True)),
            "hot_reloadable": bool(getattr(snapshot, "hot_reloadable", True)),
            "config_path": str(self._plugin_config_path(snapshot.name) or ""),
            # 依赖体系：前置插件、反向依赖与自动禁用原因
            "dependency_issues": list(getattr(snapshot, "dependency_issues", ()) or ()),
            "dependents": list(getattr(snapshot, "dependents", ()) or ()),
            "disabled_reason": getattr(snapshot, "disabled_reason", None),
            "auto_disabled": bool(getattr(snapshot, "auto_disabled", False)),
            # 配置校验告警：非空表示已存值非法、运行时已回落默认值
            "config_error": getattr(snapshot, "config_error", None),
            # 命令重名导致的自动改名：原 /x -> 实际 /plugin__x（spec(4) R26）
            "command_renames": [
                {
                    "requested": f"/{requested}",
                    "actual": f"/{actual}",
                    "message": f"原 /{requested} → 实际 /{actual}（重名）",
                }
                for requested, actual in (
                    getattr(snapshot, "command_renames", ()) or ()
                )
            ],
        }

    async def extensions(self, request: web.Request) -> web.Response:
        """面板 HTTP 扩展：依赖面板的插件挂到同一端口上的页面入口。"""
        describe = getattr(self.console, "describe_extensions", None)
        items: list[dict[str, Any]] = []
        if callable(describe):
            try:
                items = list(describe())
            except Exception:
                items = []
        return _json_ok({"items": items})

    async def plugins(self, request: web.Request) -> web.Response:
        control = self._plugin_control()
        if control is None:
            return _json_ok(
                {
                    "items": [],
                    "manage_enabled": False,
                    "hot_reload": False,
                    "error": "插件运行时不可用",
                }
            )
        try:
            snapshots = control.snapshot()
        except Exception as exc:
            return _json_error(f"读取插件列表失败: {exc}", status=500)
        return _json_ok(
            {
                "items": [self._plugin_payload(item) for item in snapshots],
                "manage_enabled": self._can_manage(request),
                "hot_reload": True,
                "installer": bool(getattr(control, "installer_available", False)),
                "console_plugin": self.console.plugin_name,
                "proxy": self._installer_proxy(control),
                "proxy_modes": ["system", "none", "custom"],
            }
        )
