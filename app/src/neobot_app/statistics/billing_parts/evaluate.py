"""BillingService 的脚本求值、槽位节流与结果解释。"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Iterable, Mapping

from .constants import (
    SOURCE_BUILTIN,
    SOURCE_MISSING,
    SOURCE_ERROR,
    SOURCE_TIMEOUT,
    BILLING_MAX_INFLIGHT,
)
from .core import (
    BillingSettings,
    _coerce_int,
    BillingOutcome,
    _ScriptStat,
    _serialize_detail,
    _to_finite_float,
)

class EvaluateMixin:

    def bindings(self, targets: Iterable[tuple[str, str, Mapping[str, Any]]]) -> list[dict[str, Any]]:
        """面板用：每个模型条目的绑定情况（model_key → 脚本 / 是否可用 / 最近耗时）。"""
        items: list[dict[str, Any]] = []
        for model_key, script, config in targets:
            name = str(script or "").strip()
            if not name:
                items.append({
                    "model_key": model_key,
                    "billing_script": "",
                    "billing_config": dict(config or {}),
                    "source": SOURCE_BUILTIN,
                    "available": True,
                    "error": "",
                })
                continue
            status = self._stats.get(name)
            policy = self.ensure_policy(name) if self.settings.enabled else None
            error = self._errors.get(name, "")
            items.append({
                "model_key": model_key,
                "billing_script": name,
                "billing_config": dict(config or {}),
                "source": f"script:{name}" if policy is not None else (
                    SOURCE_MISSING if name in self._missing else SOURCE_ERROR
                ),
                "available": policy is not None,
                "error": error,
                "loaded_at": status.loaded_at if status else "",
                "last_eval_ms": round(status.last_eval_ms, 4) if status else 0.0,
                "eval_count": status.eval_count if status else 0,
            })
        return items

    # ------------------------------------------------------------------
    # 求值
    # ------------------------------------------------------------------

    def _acquire_slot(self) -> bool:
        with self._inflight_lock:
            if self._inflight >= BILLING_MAX_INFLIGHT:
                return False
            self._inflight += 1
            return True

    def _release_slot(self) -> None:
        with self._inflight_lock:
            if self._inflight > 0:
                self._inflight -= 1

    def _track_future(self, future: Any) -> None:
        """把「槽位」绑定到**任务真正结束**：脚本超时后线程仍占用线程池，

        只有等它结束（或提交前被取消）才归还槽位，从而兑现「池内任务上限」的兜底。
        """
        future.add_done_callback(lambda _fut: self._release_slot())

    def _eval_source_for_missing(self, name: str) -> str:
        return SOURCE_MISSING if name in self._missing else SOURCE_ERROR

    def _record_eval(self, name: str, outcome: BillingOutcome) -> None:
        with self._lock:
            record = self._stats.setdefault(name, _ScriptStat(name=name))
            record.last_eval_ms = outcome.elapsed_ms
            record.last_source = outcome.source
            record.eval_count += 1
            if not outcome.is_script:
                record.fallback_count += 1

    async def compute_cost(
        self,
        *,
        script_name: str,
        ctx: Mapping[str, Any],
        fallback_cost: float,
    ) -> BillingOutcome:
        """求值入口：任何失败都回落到 fallback_cost，**从不抛异常**（R3）。"""
        # 线程池是模块级单例：测试会替换门面的 _EXECUTOR，这里必须走门面取用。
        from neobot_app.statistics.billing import get_billing_executor
        settings = self.settings
        name = str(script_name or "").strip()
        if not settings.enabled or not name:
            return BillingOutcome(cost_cny=fallback_cost, source=SOURCE_BUILTIN)

        policy = self.ensure_policy(name)
        if policy is None:
            outcome = self._fallback(
                settings,
                self._eval_source_for_missing(name),
                fallback_cost,
                self._errors.get(name, ""),
            )
            self._record_eval(name, outcome)
            return outcome

        if not self._acquire_slot():
            self._logger.warning(
                "计费脚本并发已达上限，回落到内建公式",
                script=name,
                limit=BILLING_MAX_INFLIGHT,
            )
            outcome = self._fallback(
                settings, SOURCE_ERROR, fallback_cost, "billing pool saturated"
            )
            self._record_eval(name, outcome)
            return outcome

        started = time.perf_counter()
        tracked = False
        try:
            loop = asyncio.get_running_loop()
            future = loop.run_in_executor(get_billing_executor(), policy.compute, ctx)
            # 槽位在**任务真正结束**时归还（超时后线程仍在跑，槽位不释放）
            self._track_future(future)
            tracked = True
            result = await asyncio.wait_for(future, timeout=settings.timeout_seconds)
        except (asyncio.TimeoutError, TimeoutError):
            elapsed = (time.perf_counter() - started) * 1000.0
            self._logger.warning(
                "计费脚本求值超时，回落到内建公式",
                script=name,
                timeout_ms=settings.timeout_ms,
                elapsed_ms=round(elapsed, 3),
            )
            outcome = self._fallback(
                settings,
                SOURCE_TIMEOUT,
                fallback_cost,
                f"timeout after {settings.timeout_ms}ms",
                elapsed_ms=elapsed,
            )
            self._record_eval(name, outcome)
            return outcome
        except Exception as exc:
            elapsed = (time.perf_counter() - started) * 1000.0
            if not tracked:  # pragma: no cover - 线程池/事件循环异常时才走到
                self._release_slot()
            self._logger.warning(
                "计费脚本求值异常，回落到内建公式",
                script=name,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            outcome = self._fallback(
                settings,
                SOURCE_ERROR,
                fallback_cost,
                f"{type(exc).__name__}: {exc}",
                elapsed_ms=elapsed,
            )
            self._record_eval(name, outcome)
            return outcome

        elapsed = (time.perf_counter() - started) * 1000.0
        outcome = self._interpret(
            result,
            script_name=name,
            fallback_cost=fallback_cost,
            settings=settings,
            elapsed_ms=elapsed,
        )
        self._record_eval(name, outcome)
        return outcome

    def preview(
        self,
        *,
        script_name: str,
        ctx: Mapping[str, Any],
        fallback_cost: float = 0.0,
        timeout_ms: int | None = None,
    ) -> BillingOutcome:
        """只读试算（同步）：不写库、不改任何状态；超时同样兜底（§4.4 preview）。

        与 ``compute_cost`` 的差别：**不检查** ``[billing].enabled``——保存配置前
        必须能先试算脚本（A1 的两次对照即走这里）。
        """
        # 线程池是模块级单例：测试会替换门面的 _EXECUTOR，这里必须走门面取用。
        from neobot_app.statistics.billing import get_billing_executor

        settings = self.settings
        name = str(script_name or "").strip()
        if not name:
            return BillingOutcome(cost_cny=fallback_cost, source=SOURCE_BUILTIN)
        policy = self.ensure_policy(name)
        if policy is None:
            outcome = self._fallback(
                settings,
                self._eval_source_for_missing(name),
                fallback_cost,
                self._errors.get(name, ""),
            )
            self._record_eval(name, outcome)
            return outcome

        limit_ms = max(
            1, _coerce_int(timeout_ms, settings.timeout_ms) if timeout_ms else settings.timeout_ms
        )
        if not self._acquire_slot():
            outcome = self._fallback(
                settings, SOURCE_ERROR, fallback_cost, "billing pool saturated"
            )
            self._record_eval(name, outcome)
            return outcome
        started = time.perf_counter()
        future = get_billing_executor().submit(policy.compute, ctx)
        self._track_future(future)
        try:
            result = future.result(timeout=limit_ms / 1000.0)
        except BaseException as exc:
            elapsed = (time.perf_counter() - started) * 1000.0
            timed_out = isinstance(exc, TimeoutError)
            outcome = self._fallback(
                settings,
                SOURCE_TIMEOUT if timed_out else SOURCE_ERROR,
                fallback_cost,
                f"timeout after {limit_ms}ms" if timed_out else f"{type(exc).__name__}: {exc}",
                elapsed_ms=elapsed,
            )
            self._record_eval(name, outcome)
            return outcome
        elapsed = (time.perf_counter() - started) * 1000.0
        outcome = self._interpret(
            result,
            script_name=name,
            fallback_cost=fallback_cost,
            settings=settings,
            elapsed_ms=elapsed,
        )
        self._record_eval(name, outcome)
        return outcome

    def _fallback(
        self,
        settings: BillingSettings,
        source: str,
        fallback_cost: float,
        error: str,
        *,
        elapsed_ms: float = 0.0,
    ) -> BillingOutcome:
        detail = None
        if settings.record_detail and error:
            detail = _serialize_detail({"error": error})
        return BillingOutcome(
            cost_cny=fallback_cost,
            source=source,
            detail_json=detail,
            elapsed_ms=elapsed_ms,
            error=error,
        )

    def _interpret(
        self,
        result: Any,
        *,
        script_name: str,
        fallback_cost: float,
        settings: BillingSettings,
        elapsed_ms: float,
    ) -> BillingOutcome:
        components: dict[str, float] | None = None
        note = ""
        source = f"script:{script_name}"

        if isinstance(result, Mapping):
            cost = _to_finite_float(result.get("cost_cny"))
            if cost is None:
                return self._fallback(
                    settings,
                    SOURCE_ERROR,
                    fallback_cost,
                    "脚本返回值缺少合法的 cost_cny",
                    elapsed_ms=elapsed_ms,
                )
            raw_components = result.get("components")
            if isinstance(raw_components, Mapping):
                cleaned = {
                    str(key): number
                    for key, number in (
                        (key, _to_finite_float(item)) for key, item in raw_components.items()
                    )
                    if number is not None
                }
                components = cleaned or None
            raw_note = result.get("note")
            if isinstance(raw_note, str):
                note = raw_note.strip()
            raw_source = result.get("source")
            if isinstance(raw_source, str) and raw_source.strip():
                source = f"script:{raw_source.strip()}"
        else:
            cost = _to_finite_float(result)
            if cost is None:
                return self._fallback(
                    settings,
                    SOURCE_ERROR,
                    fallback_cost,
                    "脚本返回值不是有限数值",
                    elapsed_ms=elapsed_ms,
                )

        detail = None
        if settings.record_detail:
            payload: dict[str, Any] = {}
            if components:
                payload["components"] = components
            if note:
                payload["note"] = note
            if payload:
                detail = _serialize_detail(payload)
        return BillingOutcome(
            cost_cny=cost,
            source=source,
            components=components,
            note=note,
            detail_json=detail,
            elapsed_ms=elapsed_ms,
        )
