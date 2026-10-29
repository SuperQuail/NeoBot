"""Conversation-level outbound speech policy contract."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from neobot_contracts.models import ConversationRef


@dataclass(frozen=True, slots=True)
class SpeakingDecision:
    allowed: bool
    reason: str = ""


class SpeechBlocked(Exception):
    """A send was denied before delivery; never a successful send response."""


SpeakingEvaluator = Callable[[ConversationRef], SpeakingDecision]


class SpeakingPolicy(Protocol):
    @property
    def has_policies(self) -> bool: ...
    def register(self, owner: str, evaluator: SpeakingEvaluator) -> Callable[[], None]: ...
    def evaluate(self, conversation: ConversationRef) -> SpeakingDecision: ...
    def bypass(self, owner: str) -> AbstractContextManager[None]: ...
