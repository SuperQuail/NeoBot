from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Mapping

from neobot_chat.models import model_registry as _global_model_registry
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_storage._retry import retry_on_lock
from neobot_storage.models import ModelUsageRecord
from neobot_storage.repositories.usage import SqlAlchemyUsageRepository

from neobot_app.statistics.billing import (
    SOURCE_BUILTIN,
    BillingService,
    build_billing_context,
    builtin_cost,
)

CURRENT_USAGE_MODULE: ContextVar[str] = ContextVar("current_usage_module", default="")
CURRENT_CONVERSATION_KIND: ContextVar[str] = ContextVar("current_conversation_kind", default="")
CURRENT_CONVERSATION_ID: ContextVar[str] = ContextVar("current_conversation_id", default="")

_VALID_MODULES = frozenset({
    "reply_agent",
    "reply_common",
    "agent:memory",
    "agent:chat_interaction",
    "agent:image_parse",
    "agent:willingness",
    "agent:scheduled_task",
    "agent:problem_solver",
    "agent:self_heal",
    "memory_compaction",
})


@dataclass(frozen=True, slots=True)
class ModelEntry:
    """按**注册 key** 建索引的模型条目快照（spec(4) §4.1.1 / D19）。

    按 model_name 建索引时，默认模型库 4 个 chat 条目（model_name 都是
    ``deepseek-flash``）会互相覆盖，导致「按模型绑定计价脚本」（R21）失效。
    """

    key: str
    provider_name: str
    model_name: str
    model_type: str
    pricing: Any
    settings: Any
    billing_script: str
    billing_config: Mapping[str, Any]


class UsageTracker:
    def __init__(
        self,
        session_factory,
        *,
        logger: Logger | None = None,
        billing: BillingService | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._logger = logger or NullLogger()
        self._billing = billing
        self._model_info: dict[str, ModelEntry] = {}
        self._model_info_by_name: dict[str, str] = {}
        self._cache_stamp: tuple[tuple[str, int], ...] | None = None
        #: 持有注册表实例的强引用：避免 id() 被回收复用造成缓存误判
        self._cache_refs: tuple[Any, ...] = ()

    @property
    def billing(self) -> BillingService | None:
        return self._billing

    def _ensure_model_cache(self) -> None:
        """注册表条目集合 / 实例变化即重建（改价、换脚本无需重启）。"""
        items = _global_model_registry.items()
        stamp = tuple((name, id(model)) for name, model in items)
        if self._cache_stamp is not None and stamp == self._cache_stamp:
            return
        self._cache_refs = tuple(model for _name, model in items)

        model_info: dict[str, ModelEntry] = {}
        by_name: dict[str, str] = {}
        for name, registered in items:
            model_info[name] = ModelEntry(
                key=name,
                provider_name=registered.provider_name,
                model_name=registered.model_name,
                model_type=str(getattr(registered, "model_type", "chat") or "chat"),
                pricing=registered.pricing,
                settings=registered.settings,
                billing_script=str(getattr(registered, "billing_script", "") or ""),
                billing_config=dict(getattr(registered, "billing_config", None) or {}),
            )
            # 同名条目以最后注册者为准，兼容历史行为（调用方拿不到注册 key 时的回落）
            by_name[registered.model_name] = name
        self._model_info = model_info
        self._model_info_by_name = by_name
        self._cache_stamp = stamp

    def _lookup(self, registered_key: str, model_name: str) -> ModelEntry | None:
        key = str(registered_key or "").strip()
        if key:
            entry = self._model_info.get(key)
            if entry is not None:
                return entry
        fallback_key = self._model_info_by_name.get(str(model_name or ""))
        if fallback_key is None:
            return None
        return self._model_info.get(fallback_key)

    async def record(
        self,
        *,
        module: str,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        cache_hit_tokens: int = 0,
        cache_miss_tokens: int = 0,
        conversation_kind: str = "",
        conversation_id: str = "",
        registered_key: str = "",
    ) -> None:
        if module not in _VALID_MODULES:
            self._logger.debug("未知的用量统计模块，已跳过", module=module)
            return

        self._ensure_model_cache()
        entry = self._lookup(registered_key, model_name)
        if entry is None:
            self._logger.debug(
                "模型信息未在注册表中找到，跳过用量记录",
                model_name=model_name,
            )
            return

        import datetime as _dt

        occurred_at = _dt.datetime.now(_dt.timezone.utc)
        fallback = builtin_cost(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hit_tokens=cache_hit_tokens,
            cache_miss_tokens=cache_miss_tokens,
            pricing=entry.pricing,
        )
        cost = fallback
        source = SOURCE_BUILTIN
        detail: str | None = None
        elapsed_ms = 0.0

        # 唯一入队/求值入口（spec(4) §4.1-D4）：只在这里插一层「计费策略」。
        # ``enabled=false`` 时连 ctx 都不组装，保证零额外开销（A9）。
        if self._billing is not None and entry.billing_script and self._billing.settings.enabled:
            ctx = build_billing_context(
                model_key=entry.key,
                model_name=entry.model_name,
                provider=entry.provider_name,
                model_type=entry.model_type,
                module=module,
                usage={
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cache_hit_tokens": cache_hit_tokens,
                    "cache_miss_tokens": cache_miss_tokens,
                },
                pricing=entry.pricing,
                settings=entry.settings,
                billing_config=entry.billing_config,
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
                occurred_at=occurred_at,
            )
            outcome = await self._billing.compute_cost(
                script_name=entry.billing_script,
                ctx=ctx,
                fallback_cost=fallback,
            )
            cost = outcome.cost_cny
            source = outcome.source
            detail = outcome.detail_json
            elapsed_ms = outcome.elapsed_ms

        record_obj = ModelUsageRecord(
            module_name=module,
            model_name=model_name,
            provider_name=entry.provider_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hit_tokens=cache_hit_tokens,
            cache_miss_tokens=cache_miss_tokens,
            cost_cny=cost,
            cost_source=source,
            cost_detail=detail,
            conversation_kind=conversation_kind or None,
            conversation_id=conversation_id or None,
            created_at=occurred_at,
        )

        async with self._session_factory() as session:
            repo = SqlAlchemyUsageRepository(session)

            async def _flush() -> None:
                await repo.add(record_obj)
                await session.commit()

            await retry_on_lock(_flush, on_retry=session.rollback)

        self._logger.debug(
            "用量已记录",
            module=module,
            model=model_name,
            model_key=entry.key,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hit_tokens=cache_hit_tokens,
            cache_miss_tokens=cache_miss_tokens,
            cost=f"¥{cost:.6f}",
            cost_source=source,
            billing_ms=round(elapsed_ms, 3),
        )


_tracker: UsageTracker | None = None


def get_usage_tracker() -> UsageTracker:
    if _tracker is None:
        raise RuntimeError("UsageTracker has not been initialized")
    return _tracker


def initialize_usage_tracker(tracker: UsageTracker) -> None:
    global _tracker
    if _tracker is not None:
        raise RuntimeError("UsageTracker is already initialized")
    _tracker = tracker
