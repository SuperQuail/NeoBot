from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from neobot_chat.models import model_registry as _global_model_registry
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_storage.models import ModelUsageRecord
from neobot_storage.repositories.usage import SqlAlchemyUsageRepository

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
    "memory_compaction",
})


class UsageTracker:
    def __init__(self, session_factory, *, logger: Logger | None = None) -> None:
        self._session_factory = session_factory
        self._logger = logger or NullLogger()
        self._model_info: dict[str, tuple[str, Any]] = {}

    def _ensure_model_cache(self) -> None:
        if self._model_info:
            return
        for _name, registered in _global_model_registry.items():
            self._model_info[registered.model_name] = (
                registered.provider_name,
                registered.pricing,
            )

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
    ) -> None:
        if module not in _VALID_MODULES:
            self._logger.debug("unknown usage module, skipping", module=module)
            return

        self._ensure_model_cache()
        info = self._model_info.get(model_name)
        if info is None:
            self._logger.debug(
                "model info not found in registry, skipping usage record",
                model_name=model_name,
            )
            return

        provider_name, pricing = info

        effective_cache_miss = cache_miss_tokens if cache_miss_tokens > 0 else input_tokens
        cost = (
            cache_hit_tokens * pricing.cache_hit_price_per_mtokens
            + effective_cache_miss * pricing.input_price_per_mtokens
            + output_tokens * pricing.output_price_per_mtokens
        ) / 1_000_000.0

        import datetime as _dt

        record_obj = ModelUsageRecord(
            module_name=module,
            model_name=model_name,
            provider_name=provider_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hit_tokens=cache_hit_tokens,
            cache_miss_tokens=cache_miss_tokens,
            cost_cny=cost,
            conversation_kind=conversation_kind or None,
            conversation_id=conversation_id or None,
            created_at=_dt.datetime.now(_dt.timezone.utc),
        )

        async with self._session_factory() as session:
            repo = SqlAlchemyUsageRepository(session)
            await repo.add(record_obj)
            await session.commit()

        self._logger.debug(
            "usage recorded",
            module=module,
            model=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hit_tokens=cache_hit_tokens,
            cache_miss_tokens=cache_miss_tokens,
            cost=f"¥{cost:.6f}",
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
