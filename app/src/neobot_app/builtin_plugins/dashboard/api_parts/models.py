"""模型库、provider 列表与模型测试接口。"""

from __future__ import annotations

import json
from typing import Any

from aiohttp import web

from ..config_manager import ConfigConflictError, ConfigValidationError, models_view
from ..model_probe import list_provider_models
from ._common import _json_ok, _json_error


class ModelsMixin:
    def _models_config(self) -> Any:
        """读取模型库：以 config.toml 为准，读不到时退回运行中的配置。

        面板编辑的是文件，若优先用运行中的配置对象，保存后（未重载）列表不会更新，
        刷新页面也看不到新模型，因此这里以文件解析结果为主。
        """
        try:
            instance = self._config_manager().instance()
            if hasattr(instance, "models"):
                return instance
        except Exception as exc:
            self.logger.warning(f"读取 config.toml 失败，改用运行中配置: {exc}")
        config_obj = self._config_proxy()
        if config_obj is not None and hasattr(config_obj, "models"):
            return config_obj
        return None

    async def config_models(self, request: web.Request) -> web.Response:
        try:
            payload = models_view(self._models_config())
        except Exception as exc:
            return _json_error(f"读取模型注册表失败: {exc}", status=500)
        # 把 .env 里的自定义平台合并进供应商候选（面板添加供应商后立即可选）
        try:
            env_platforms = {str(item.get("name") or "") for item in self._env_manager().platforms()}
            merged = set(payload.get("provider_options") or []) | {name for name in env_platforms if name}
            payload["provider_options"] = sorted(merged, key=str.casefold)
            payload["platforms"] = self._env_manager().platforms()
        except Exception as exc:
            self.logger.warning(f"读取平台列表失败: {exc}")
        payload["can_manage"] = self.console.manage_plugins
        try:
            payload["revision"] = self._config_manager().revision()
        except Exception:
            payload["revision"] = ""
        return _json_ok(payload)

    async def models_provider_models(self, request: web.Request) -> web.Response:
        """拉取某个供应商的可用模型列表（供模型编辑时选择）。"""
        denied = self._require_manage(request, action="拉取供应商模型列表")
        if denied is not None:
            return denied
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        from neobot_app.config.schemas.env import EnvConfig

        provider = str(payload.get("provider") or "").strip()
        if not provider:
            return _json_error("请先选择供应商", status=400)
        platform = EnvConfig.get_api_platform_config(provider)
        if not platform or not platform.url:
            return _json_error(f"供应商 {provider} 未配置 URL（请在环境变量中填写 {provider}_URL）", status=400)
        try:
            timeout = float(payload.get("timeout") or 20.0)
        except (TypeError, ValueError):
            timeout = 20.0
        result = await list_provider_models(
            base_url=platform.url or "",
            api_key=platform.api_key or "",
            use_system_proxy=bool(payload.get("use_system_proxy", False)),
            timeout=max(3.0, min(timeout, 60.0)),
        )
        data = result.to_dict()
        data["provider"] = provider
        self.logger.info(
            f"面板拉取供应商模型 ip={self.console.request_ip(request)} "
            f"provider={provider} ok={result.ok} count={len(result.models)}"
        )
        return _json_ok(data)

    async def models_library_save(self, request: web.Request) -> web.Response:
        """模型库条目新增/更新/删除（只改 config.toml 的 [models.registry]）。"""
        denied = self._require_manage(request, action="修改模型库")
        if denied is not None:
            return denied
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        action = str(payload.get("action") or "upsert").strip().lower()
        if action not in {"upsert", "delete"}:
            return _json_error("action 只能是 upsert 或 delete", status=400)
        manager = self._config_manager()
        resolved: dict[str, Any] = {}
        try:
            if action == "delete":
                document = manager.update_models(
                    delete=str(payload.get("model_ref") or ""),
                    expected_revision=payload.get("revision"),
                )
            else:
                document = manager.update_models(
                    upsert=payload.get("entry") or payload.get("config") or {},
                    expected_revision=payload.get("revision"),
                    resolved=resolved,
                )
        except ConfigConflictError as exc:
            return _json_error(str(exc), status=409)
        except ConfigValidationError as exc:
            return _json_error(str(exc), status=400, errors=exc.errors)
        except Exception as exc:
            return _json_error(f"保存模型库失败: {exc}", status=500)
        response = await self._finish_config_write(
            request, document, payload, "模型库已保存"
        )
        if resolved.get("model_ref"):
            try:
                body = json.loads(response.body.decode("utf-8"))
            except Exception:
                return response
            body["saved_model_ref"] = resolved["model_ref"]
            return web.json_response(body)
        return response

    async def models_test(self, request: web.Request) -> web.Response:
        """测试模型连通性：网络是否可达、鉴权是否通过、模型名是否存在。

        传 `model_ref` 测试模型库中已保存的条目（引用名，不是发给供应商的模型名）；
        传 `entry` 测试尚未保存的草稿。
        代理行为跟随条目的 `use_system_proxy`（默认直连）。
        """
        denied = self._require_manage(request, action="测试模型连通性")
        if denied is not None:
            return denied
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        from neobot_app.config.schemas.env import EnvConfig

        from ..model_probe import probe_model

        entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else None
        model_ref = str(payload.get("model_ref") or "").strip()
        if entry is None:
            config_obj = self._models_config()
            models_config = getattr(config_obj, "models", None) if config_obj else None
            definition = (
                models_config.get(model_ref) if models_config is not None else None
            )
            if definition is None:
                return _json_error(f"模型库中不存在引用名 {model_ref}", status=404)
            entry = {
                "provider": getattr(definition, "provider", ""),
                "model_name": getattr(definition, "model_name", ""),
                "use_system_proxy": bool(
                    getattr(definition, "use_system_proxy", False)
                ),
            }
        provider = str(entry.get("provider") or "").strip()
        model_name = str(entry.get("model_name") or "").strip()
        use_system_proxy = bool(entry.get("use_system_proxy", False))
        platform = EnvConfig.get_api_platform_config(provider) if provider else None
        try:
            timeout = float(payload.get("timeout") or 20.0)
        except (TypeError, ValueError):
            timeout = 20.0
        timeout = max(3.0, min(timeout, 120.0))

        result = await probe_model(
            provider=provider,
            model_name=model_name,
            base_url=(platform.url if platform else "") or "",
            api_key=(platform.api_key if platform else "") or "",
            use_system_proxy=use_system_proxy,
            timeout=timeout,
        )
        data = result.to_dict()
        data.update(
            {
                "model_ref": model_ref,
                "provider": provider,
                "model_name": model_name,
                "has_credentials": bool(platform and platform.url and platform.api_key),
            }
        )
        self.logger.info(
            f"面板测试模型 ip={self.console.request_ip(request)} model_ref={model_ref or '-'} "
            f"ok={result.ok} status={result.status} proxy={use_system_proxy}"
        )
        return _json_ok(data)

    async def models_assignments_save(self, request: web.Request) -> web.Response:
        """调用方 -> 模型 key 分配（只改 config.toml 的 [models.assignments]）。"""
        denied = self._require_manage(request, action="修改模型分配")
        if denied is not None:
            return denied
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        assignments = payload.get("assignments")
        if not isinstance(assignments, dict):
            return _json_error("assignments 必须是对象", status=400)
        try:
            document = self._config_manager().update_models(
                assignments=assignments,
                expected_revision=payload.get("revision"),
            )
        except ConfigConflictError as exc:
            return _json_error(str(exc), status=409)
        except ConfigValidationError as exc:
            return _json_error(str(exc), status=400, errors=exc.errors)
        except Exception as exc:
            return _json_error(f"保存模型分配失败: {exc}", status=500)
        return await self._finish_config_write(request, document, payload, "模型分配已保存")

    async def _finish_config_write(
        self,
        request: web.Request,
        document: dict[str, Any],
        payload: dict[str, Any],
        message: str,
    ) -> web.Response:
        """写配置后的统一收尾：可选重载 + 返回最新配置与模型视图。"""
        document["can_manage"] = self.console.manage_plugins
        document["message"] = message
        if payload.get("reload"):
            reload_result = await self._reload_config(with_changes=True)
            document["applied"] = bool(reload_result.get("ok"))
            document["message"] = str(reload_result.get("message") or message)
            if reload_result.get("changes"):
                document["changes"] = reload_result["changes"]
            if reload_result.get("needs_restart_parts"):
                document["needs_restart_parts"] = reload_result["needs_restart_parts"]
        try:
            document["models"] = models_view(self._models_config())
        except Exception:
            document["models"] = None
        self.logger.info(
            f"面板修改配置 ip={self.console.request_ip(request)} action={message}"
        )
        return _json_ok(document)
