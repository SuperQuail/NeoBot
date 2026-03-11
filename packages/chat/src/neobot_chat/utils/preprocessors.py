from __future__ import annotations

from neobot_chat.schema.protocol import StatePreprocessor
from neobot_chat.schema.types import State


def compose_preprocessors(
    *preprocessors: StatePreprocessor | None,
) -> StatePreprocessor | None:
    """按顺序组合多个预处理器。"""

    active = [pre for pre in preprocessors if pre is not None]
    if not active:
        return None

    def _composed(state: State) -> State:
        for preprocessor in active:
            state = preprocessor(state)
        return state

    return _composed
