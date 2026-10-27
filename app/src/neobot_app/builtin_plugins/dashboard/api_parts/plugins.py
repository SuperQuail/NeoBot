"""插件安装、启停、更新与探测接口。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from aiohttp import web

from ..config_manager import ConfigConflictError, ConfigValidationError
from ..plugin_config import PluginConfigEditor, apply_field_descriptions, read_manifest_comments
from ._common import _json_ok, _json_error, installed_name, _operation_response


class PluginsMixin:
    def _installer_proxy(self, control: Any) -> dict[str, Any]:
        getter = getattr(control, "installer_proxy", None)
        if callable(getter):
            try:
                return dict(getter())
            except Exception:
                return {}
        return {}

    def _plugin_config_path(self, name: str) -> Path | None:
        """插件配置文件路径（插件数据目录下的 config.toml）。"""
        control = self._plugin_control()
        if control is None:
            return None
        getter = getattr(control, "plugin_config_path", None)
        if not callable(getter):
            return None
        try:
            return getter(name)
        except Exception:
            return None

    def _plugin_config_editor(self, control: Any, name: str) -> PluginConfigEditor | None:
        path = self._plugin_config_path(name)
        if path is None:
            return None
        defaults: dict[str, Any] = {}
        getter = getattr(control, "plugin_config_defaults", None)
        if callable(getter):
            try:
                defaults = dict(getter(name))
            except Exception:
                defaults = {}
        # 字段说明来自插件自带 plugin.toml 的 [config] 注释（生成的配置也带注释）
        return PluginConfigEditor(
            path,
            defaults=defaults,
            comments=self._plugin_field_comments(control, name),
        )

    def _plugin_field_comments(self, control: Any, name: str) -> dict[str, str]:
        """插件 plugin.toml 里 [config] 各键的注释（失败时返回空字典）。"""
        getter = getattr(control, "plugin_manifest_path", None)
        if not callable(getter):
            return {}
        try:
            manifest = getter(name)
        except Exception:
            return {}
        try:
            return read_manifest_comments(manifest)
        except Exception:
            return {}

    def _with_field_comments(
        self, schema: list[dict[str, Any]], comments: dict[str, str]
    ) -> list[dict[str, Any]]:
        """给 pydantic 生成的 schema 补上 plugin.toml 注释（不覆盖已有说明）。"""
        if not schema or not comments:
            return schema
        return apply_field_descriptions(schema, comments)

    def _plugin_config_meta(
        self, snapshot: Any, name: str, document: dict[str, Any]
    ) -> dict[str, Any]:
        """插件配置文档的公共元信息（官方与第三方插件一致）。"""
        official = bool(getattr(snapshot, "official", False))
        hot_reload = bool(getattr(snapshot, "hot_reload", True))
        document.update(
            {
                "name": name,
                "version": str(getattr(snapshot, "version", "") or ""),
                "official": official,
                "manage_enabled": self.console.manage_plugins,
                "can_reload": hot_reload,
                "hot_reload": hot_reload,
                "config_hot_reload": bool(
                    getattr(snapshot, "config_hot_reload", True)
                ),
                "config_error": getattr(snapshot, "config_error", None),
                "message": "插件配置保存在插件数据目录，与插件代码和启停状态分离",
            }
        )
        return document

    async def plugins_proxy_save(self, request: web.Request) -> web.Response:
        """插件下载代理设置：写入 config.toml 的 [plugins] 并立即生效。"""
        denied = self._require_manage(request, action="修改插件代理设置")
        if denied is not None:
            return denied
        control = self._plugin_control()
        if control is None:
            return _json_error("插件运行时不可用", status=503)
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        setter = getattr(control, "set_installer_proxy", None)
        if not callable(setter):
            return _json_error("插件安装器不可用", status=503)
        mode = str(payload.get("mode") or "system").strip().lower()
        host = str(payload.get("host") or "127.0.0.1").strip()
        try:
            port = int(payload.get("port") or 7890)
        except (TypeError, ValueError):
            return _json_error("代理端口必须是数字", status=400)
        try:
            settings = setter(mode=mode, host=host, port=port)
        except Exception as exc:
            return _json_error(f"代理设置无效: {exc}", status=400)
        if payload.get("persist", True):
            try:
                self._config_manager().update_plugins_proxy(
                    mode=mode,
                    host=host,
                    port=port,
                    expected_revision=payload.get("revision"),
                )
            except ConfigConflictError as exc:
                return _json_error(str(exc), status=409)
            except ConfigValidationError as exc:
                return _json_error(str(exc), status=400, errors=exc.errors)
            except Exception as exc:
                return _json_error(f"保存代理设置失败: {exc}", status=500)
        return _json_ok(
            {
                "message": f"插件下载代理已切换为{settings.get('description') or mode}",
                "proxy": settings,
            }
        )

    async def plugin_toggle(self, request: web.Request) -> web.Response:
        """兼容无请求体的反转，也支持明确目标与旧状态校验。"""
        denied = self._require_manage(request)
        if denied is not None:
            return denied
        control = self._plugin_control()
        if control is None:
            return _json_error("插件运行时不可用", status=503)
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc), status=400)
        for field in ("enabled", "expected_enabled"):
            if field in payload and not isinstance(payload[field], bool):
                return _json_error(f"{field} 必须是布尔值", status=400)
        name = request.match_info["name"]
        snapshot = self._find_snapshot(control, name)
        if snapshot is None:
            return _json_error(f"插件不存在: {name}", status=404)
        if name == self.console.plugin_name:
            return _json_error(
                "不能从面板内部停用面板自身；如需关闭网页面板，"
                "请把 data/plugin_state.json 里 dashboard 的 enabled 改为 false 后重启 NeoBot",
                status=400,
            )
        lock = self._plugin_toggle_locks.setdefault(name, asyncio.Lock())
        async with lock:
            snapshot = self._find_snapshot(control, name)
            if snapshot is None:
                return _json_error(f"插件不存在: {name}", status=404)
            current_enabled = bool(snapshot.enabled)
            if "expected_enabled" in payload and payload["expected_enabled"] != current_enabled:
                return _json_error(
                    "插件启停状态已被其他操作修改，请刷新后重试",
                    status=409,
                    name=name,
                    enabled=current_enabled,
                )
            target_enabled = payload.get("enabled", not current_enabled)
            result = await control.set_enabled(name, target_enabled)
            return _operation_response(result, f"{'已启用' if target_enabled else '已停用'} {name}")

    async def plugin_reload(self, request: web.Request) -> web.Response:
        denied = self._require_manage(request)
        if denied is not None:
            return denied
        control = self._plugin_control()
        if control is None:
            return _json_error("插件运行时不可用", status=503)
        name = request.match_info["name"]
        if name == self.console.plugin_name:
            return _json_error("面板自身不支持热重载（会中断当前连接），请重启 NeoBot", status=400)
        result = await control.reload(name)
        return _operation_response(result, f"{name} 已重载")

    async def plugin_update(self, request: web.Request) -> web.Response:
        denied = self._require_manage(request)
        if denied is not None:
            return denied
        control = self._plugin_control()
        if control is None:
            return _json_error("插件运行时不可用", status=503)
        name = request.match_info["name"]
        snapshot = self._find_snapshot(control, name)
        if snapshot is None:
            return _json_error(f"插件不存在: {name}", status=404)
        if snapshot.official:
            return _json_error("官方插件随本体更新，不能在面板内更新", status=400)
        if not snapshot.repo:
            return _json_error(f"插件 {name} 未声明 repo，无法更新", status=400)
        runtime = self._service("plugin_runtime")
        installer = getattr(runtime, "installer", None) if runtime is not None else None
        if installer is None:
            return _json_error("插件安装器不可用", status=503)
        result = await installer.update(name, repo=snapshot.repo, branch=snapshot.branch)
        if not result.ok:
            return _json_error(result.error or "更新失败", status=400)
        outcome = await control.reload(name)
        if outcome.ok:
            return _json_ok({"message": f"{name} 已更新至 {result.version} 并重载"})
        return _json_error(
            f"已更新至 {result.version}，但重载失败: {outcome.error or outcome.state}",
            status=500,
        )

    async def plugin_uninstall(self, request: web.Request) -> web.Response:
        denied = self._require_manage(request)
        if denied is not None:
            return denied
        control = self._plugin_control()
        if control is None:
            return _json_error("插件运行时不可用", status=503)
        name = request.match_info["name"]
        if name == self.console.plugin_name:
            return _json_error("不能卸载面板自身", status=400)
        result = await control.uninstall(name)
        return _operation_response(result, f"{name} 已卸载")

    async def plugins_install(self, request: web.Request) -> web.Response:
        """安装第三方插件；dry_run=true 只探测不写盘（spec(4) R27/D24）。

        * 目标 ID 已存在且未显式 replace -> **拒绝**并回结构化冲突（409，磁盘零变化）；
        * 目标 ID 命中官方插件目录 -> 直接拒绝（保留字，400）；
        * replace=true -> 走既有备份路径，响应回显 backup_path；
        * dry_run=true -> 只探测：不删、不覆盖、不产生备份。
        """
        denied = self._require_manage(request)
        if denied is not None:
            return denied
        control = self._plugin_control()
        if control is None:
            return _json_error("插件运行时不可用", status=503)
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        repo = str(payload.get("repo") or "").strip()
        branch = str(payload.get("branch") or "").strip() or None
        dry_run = bool(payload.get("dry_run"))
        replace = bool(payload.get("replace"))
        if not repo:
            return _json_error("请填写 GitHub 仓库地址")
        result = await control.install(
            repo, branch=branch, replace=replace, dry_run=dry_run
        )
        conflict = getattr(result, "conflict", None)
        if dry_run:
            if not getattr(result, "ok", False):
                return _json_error(
                    str(getattr(result, "error", "") or "探测失败"),
                    status=400,
                    conflict=conflict,
                )
            name = str(getattr(result, "name", "") or "")
            return _json_ok(
                {
                    "dry_run": True,
                    "name": name,
                    "version": getattr(result, "version", ""),
                    "conflict": conflict,
                    "message": (
                        str(conflict.get("message"))
                        if isinstance(conflict, dict) and conflict.get("message")
                        else f"探测完成：{name} 可安装"
                    ),
                }
            )
        return _operation_response(result, f"已安装 {installed_name(result)}")

    async def plugins_probe(self, request: web.Request) -> web.Response:
        """按插件 ID 探测冲突（只读）：面板安装前的冲突态查询。"""
        control = self._plugin_control()
        if control is None:
            return _json_error("插件运行时不可用", status=503)
        name = str(request.query.get("name") or "").strip()
        if not name:
            return _json_error("缺少 name 参数")
        prober = getattr(control, "probe", None)
        if not callable(prober):
            return _json_ok({"conflict": False, "existing": None, "official": False})
        try:
            return _json_ok(dict(prober(name)))
        except Exception as exc:
            return _json_error(f"冲突探测失败: {exc}", status=500)

    async def plugins_check_updates(self, request: web.Request) -> web.Response:
        control = self._plugin_control()
        if control is None:
            return _json_error("插件运行时不可用", status=503)
        try:
            checks = await control.check_updates()
        except Exception as exc:
            return _json_error(f"检查更新失败: {exc}", status=500)
        items = [
            {
                "name": item.name,
                "current_version": item.current_version,
                "remote_version": item.remote_version,
                "status": item.status,
                "error": item.error,
            }
            for item in checks
        ]
        available = [item for item in items if item["status"] == "available"]
        return _json_ok(
            {
                "items": items,
                "available": len(available),
                "message": (
                    f"{len(available)} 个插件可更新"
                    if available
                    else "全部插件均为最新"
                ),
            }
        )
