"""调用量、延迟、用量与计费接口。"""

from __future__ import annotations

from typing import Any

from aiohttp import web
from ._common import _json_ok, _json_error, _parse_cost_detail


class StatsMixin:
    async def series_usage(self, request: web.Request) -> web.Response:
        """用量图表：按小时/天汇总金额与 Token，并给出模型/模块排行。"""
        hours = self._int_arg(request, "hours", 24, minimum=1, maximum=24 * 365)
        bucket = str(request.query.get("bucket") or "hour").strip().lower()
        if bucket not in {"hour", "day"}:
            bucket = "hour"
        session_factory = self._service("usage_session_factory")
        if session_factory is None:
            return _json_ok(
                {
                    "available": False,
                    "bucket": bucket,
                    "hours": hours,
                    "points": [],
                    "models": [],
                    "modules": [],
                    "totals": {},
                }
            )
        try:
            import datetime as _dt

            from neobot_storage.repositories.usage import SqlAlchemyUsageRepository

            cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=hours)
            async with session_factory() as session:
                repo = SqlAlchemyUsageRepository(session)
                points = await repo.series_since(cutoff, bucket=bucket)
                models = await repo.breakdown_by_model_since(cutoff, limit=12)
                modules = await repo.breakdown_by_module_since(cutoff, limit=12)
        except Exception as exc:
            self.logger.warning(f"读取用量图表失败: {exc}")
            return _json_ok(
                {
                    "available": False,
                    "bucket": bucket,
                    "hours": hours,
                    "points": [],
                    "models": [],
                    "modules": [],
                    "totals": {},
                    "error": str(exc),
                }
            )
        totals = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_cny": 0.0}
        for point in points:
            totals["calls"] += int(point["calls"])
            totals["input_tokens"] += int(point["input_tokens"])
            totals["output_tokens"] += int(point["output_tokens"])
            totals["cost_cny"] += float(point["cost_cny"])
        totals["cost_cny"] = round(totals["cost_cny"], 6)
        return _json_ok(
            {
                "available": True,
                "bucket": bucket,
                "hours": hours,
                "currency": "CNY",
                "points": points,
                "models": models,
                "modules": modules,
                "totals": totals,
            }
        )

    async def stats_usage(self, request: web.Request) -> web.Response:
        hours = self._int_arg(request, "hours", 24, minimum=1, maximum=24 * 365)
        session_factory = self._service("usage_session_factory")
        if session_factory is None:
            return _json_ok({"available": False, "items": [], "totals": {}})
        try:
            from neobot_storage.repositories.usage import SqlAlchemyUsageRepository

            import datetime as _dt

            cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=hours)
            async with session_factory() as session:
                repo = SqlAlchemyUsageRepository(session)
                records = await repo.stats_since(cutoff)
        except Exception as exc:
            self.logger.warning(f"读取模型用量失败: {exc}")
            return _json_ok({"available": False, "items": [], "totals": {}, "error": str(exc)})
        by_module: dict[str, dict[str, float]] = {}
        totals = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_cny": 0.0}
        for record in records:
            group = by_module.setdefault(
                str(record.module_name), {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_cny": 0.0}
            )
            group["calls"] += 1
            group["input_tokens"] += int(record.input_tokens or 0)
            group["output_tokens"] += int(record.output_tokens or 0)
            group["cost_cny"] += float(record.cost_cny or 0.0)
            totals["calls"] += 1
            totals["input_tokens"] += int(record.input_tokens or 0)
            totals["output_tokens"] += int(record.output_tokens or 0)
            totals["cost_cny"] += float(record.cost_cny or 0.0)
        items = [
            {"module": module, **values}
            for module, values in sorted(
                by_module.items(), key=lambda item: item[1]["cost_cny"], reverse=True
            )
        ]
        totals["cost_cny"] = round(totals["cost_cny"], 6)
        return _json_ok({"available": True, "hours": hours, "totals": totals, "items": items})

    # ------------------------------------------------------------------
    # 计费（spec(4) Part A）
    # ------------------------------------------------------------------

    def _billing_service(self) -> Any:
        return self._service("billing_service")

    @staticmethod
    def _billing_model_targets() -> list[tuple[str, str, dict[str, Any]]]:
        """模型库当前每个条目的 (key, billing_script, billing_config)。"""
        try:
            from neobot_chat.models import model_registry
        except Exception:  # pragma: no cover - 聊天包不可用时面板其余功能仍可用
            return []
        targets: list[tuple[str, str, dict[str, Any]]] = []
        try:
            items = model_registry.items()
        except Exception:  # pragma: no cover
            return []
        for key, model in items:
            config = getattr(model, "billing_config", None)
            targets.append(
                (
                    str(key),
                    str(getattr(model, "billing_script", "") or ""),
                    dict(config) if isinstance(config, dict) else {},
                )
            )
        return targets

    async def config_billing(self, request: web.Request) -> web.Response:
        """GET /api/config/billing：全局策略 + 可用脚本 + 每个模型条目的绑定情况。"""
        service = self._billing_service()
        if service is None:
            return _json_ok(
                {
                    "available": False,
                    "enabled": False,
                    "scripts": [],
                    "templates": [],
                    "policies": {},
                    "bindings": [],
                    "errors": {},
                }
            )
        data = service.describe()
        data["bindings"] = service.bindings(self._billing_model_targets())
        data["available"] = True
        return _json_ok(data)

    async def config_billing_reload(self, request: web.Request) -> web.Response:
        """POST /api/config/billing/reload：显式重载计价脚本（需管理权限）。"""
        denied = self._require_manage(request, action="重载计费脚本")
        if denied is not None:
            return denied
        service = self._billing_service()
        if service is None:
            return _json_error("计费服务不可用（用量组件未装配）", status=503)
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        raw_names = payload.get("scripts")
        names: list[str] | None = None
        if isinstance(raw_names, list):
            names = [str(item) for item in raw_names if str(item).strip()]
        elif isinstance(raw_names, str) and raw_names.strip():
            names = [raw_names]
        try:
            result = service.reload_scripts(names)
        except Exception as exc:  # pragma: no cover - 重载本身不应抛错
            return _json_error(f"重载计费脚本失败: {exc}", status=500)
        result["bindings"] = service.bindings(self._billing_model_targets())
        result["settings"] = service.settings.to_dict()
        return _json_ok(result)

    async def config_billing_preview(self, request: web.Request) -> web.Response:
        """POST /api/config/billing/preview：只读试算，不写库（A1）。"""
        service = self._billing_service()
        if service is None:
            return _json_error("计费服务不可用（用量组件未装配）", status=503)
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))

        import datetime as _dt

        from neobot_app.statistics.billing import (
            build_billing_context,
            builtin_cost,
        )

        model_key = str(payload.get("model_key") or "").strip()
        model = None
        if model_key:
            try:
                from neobot_chat.models import model_registry

                model = model_registry.get(model_key)
            except Exception:
                model = None
            if model is None:
                return _json_error(f"模型库中不存在模型条目: {model_key}")

        script = payload.get("billing_script")
        script_name = (
            str(script).strip()
            if script is not None
            else str(getattr(model, "billing_script", "") or "").strip()
        )
        raw_config = payload.get("billing_config")
        if isinstance(raw_config, dict):
            billing_config = {str(k): v for k, v in raw_config.items()}
        else:
            model_config = getattr(model, "billing_config", None)
            billing_config = dict(model_config) if isinstance(model_config, dict) else {}

        raw_usage = payload.get("usage")
        usage: dict[str, Any] = {}
        if isinstance(raw_usage, dict):
            for name in (
                "input_tokens",
                "output_tokens",
                "cache_hit_tokens",
                "cache_miss_tokens",
                "completion_tokens_details",
            ):
                if name in raw_usage:
                    usage[name] = raw_usage[name]
        for name in ("input_tokens", "output_tokens", "cache_hit_tokens", "cache_miss_tokens"):
            if name not in usage:
                try:
                    usage[name] = int(payload.get(name) or 0)
                except (TypeError, ValueError):
                    usage[name] = 0

        occurred_at = None
        raw_time = payload.get("occurred_at")
        if isinstance(raw_time, str) and raw_time.strip():
            try:
                occurred_at = _dt.datetime.fromisoformat(raw_time.strip())
            except ValueError:
                return _json_error("occurred_at 不是合法的 ISO8601 时间")

        pricing = getattr(model, "pricing", None)
        settings = getattr(model, "settings", None)
        context = build_billing_context(
            model_key=model_key,
            model_name=str(getattr(model, "model_name", "") or ""),
            provider=str(getattr(model, "provider_name", "") or ""),
            model_type=str(getattr(model, "model_type", "chat") or "chat"),
            module=str(payload.get("module") or "preview"),
            usage=usage,
            pricing=pricing,
            settings=settings,
            billing_config=billing_config,
            conversation_kind=str(payload.get("conversation_kind") or ""),
            conversation_id=str(payload.get("conversation_id") or ""),
            occurred_at=occurred_at,
        )
        builtin = builtin_cost(
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            cache_hit_tokens=int(usage.get("cache_hit_tokens") or 0),
            cache_miss_tokens=int(usage.get("cache_miss_tokens") or 0),
            pricing=pricing,
        )
        timeout_ms = payload.get("timeout_ms")
        try:
            outcome = service.preview(
                script_name=script_name,
                ctx=context,
                fallback_cost=builtin,
                timeout_ms=int(timeout_ms) if timeout_ms is not None else None,
            )
        except Exception as exc:  # pragma: no cover - preview 自身不应抛错
            return _json_error(f"试算失败: {exc}", status=500)
        payload_out = outcome.to_payload()
        payload_out.update(
            {
                "model_key": model_key,
                "billing_script": script_name,
                "billing_config": billing_config,
                "builtin_cost_cny": builtin,
                "enabled": service.settings.enabled,
                "occurred_at": context["occurred_at"],
                "local_time": context["local_time"],
                "tzname": context["tzname"],
            }
        )
        return _json_ok(payload_out)

    async def stats_usage_records(self, request: web.Request) -> web.Response:
        """GET /api/stats/usage/records：最近若干条原始记录（来源 / 可选分项）。"""
        hours = self._int_arg(request, "hours", 24, minimum=1, maximum=24 * 365)
        limit = self._int_arg(request, "limit", 20, minimum=1, maximum=200)
        with_detail = str(request.query.get("detail") or "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        session_factory = self._service("usage_session_factory")
        if session_factory is None:
            return _json_ok({"available": False, "items": []})
        try:
            import datetime as _dt

            from neobot_storage.repositories.usage import SqlAlchemyUsageRepository

            cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=hours)
            async with session_factory() as session:
                repo = SqlAlchemyUsageRepository(session)
                records = await repo.stats_since(cutoff)
        except Exception as exc:
            self.logger.warning(f"读取用量明细失败: {exc}")
            return _json_ok({"available": False, "items": [], "error": str(exc)})

        items: list[dict[str, Any]] = []
        for record in records[:limit]:
            source = str(getattr(record, "cost_source", "") or "builtin")
            item: dict[str, Any] = {
                "at": record.created_at.isoformat() if record.created_at else "",
                "module": str(record.module_name or ""),
                "model_name": str(record.model_name or ""),
                "provider_name": str(record.provider_name or ""),
                "input_tokens": int(record.input_tokens or 0),
                "output_tokens": int(record.output_tokens or 0),
                "cache_hit_tokens": int(record.cache_hit_tokens or 0),
                "cache_miss_tokens": int(record.cache_miss_tokens or 0),
                "cost_cny": float(record.cost_cny or 0.0),
                "cost_source": source,
                "cost_source_kind": (
                    "script"
                    if source.startswith("script:")
                    else ("fallback" if source.startswith("fallback:") else "builtin")
                ),
                "negative": float(record.cost_cny or 0.0) < 0,
            }
            if with_detail:
                item["cost_detail"] = _parse_cost_detail(getattr(record, "cost_detail", None))
            items.append(item)
        return _json_ok({"available": True, "hours": hours, "items": items})
