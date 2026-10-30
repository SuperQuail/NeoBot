"""Shared host registry: policies intersect, owner bypasses are context-local."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from threading import RLock

from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.speaking import SpeakingDecision, SpeakingEvaluator


@dataclass(eq=False)
class _BypassLease:
    owner: str
    active: bool = True


class SpeakingPolicyRegistry:
    def __init__(self) -> None:
        self._entries: dict[object, tuple[str, SpeakingEvaluator]] = {}
        self._lock = RLock()
        self._bypassed: ContextVar[tuple[_BypassLease, ...]] = ContextVar("speaking_policy_bypass", default=())

    def register(self, owner: str, evaluator: SpeakingEvaluator) -> Callable[[], None]:
        token = object()
        with self._lock:
            self._entries[token] = (owner, evaluator)

        def unregister() -> None:
            with self._lock:
                self._entries.pop(token, None)

        return unregister

    @property
    def has_policies(self) -> bool:
        with self._lock:
            return bool(self._entries)

    def evaluate(self, conversation: ConversationRef) -> SpeakingDecision:
        with self._lock:
            entries = tuple(self._entries.values())
        bypassed = {lease.owner for lease in self._bypassed.get() if lease.active}
        for owner, evaluator in entries:
            if owner in bypassed:
                continue
            decision = evaluator(conversation)
            if not decision.allowed:
                return decision
        return SpeakingDecision(True)

    @contextmanager
    def bypass(self, owner: str) -> Iterator[None]:
        # Context crosses OneBot receiver threads through run_coroutine_threadsafe.
        # Revoke the shared lease on exit so copied child contexts cannot retain
        # command permission after the command's direct send has finished.
        lease = _BypassLease(owner)
        token = self._bypassed.set((*self._bypassed.get(), lease))
        try:
            yield
        finally:
            lease.active = False
            self._bypassed.reset(token)
