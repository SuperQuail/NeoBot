"""ReplyEvent 状态机测试：合法/非法转换、terminal 语义、completed_at 记录。"""

from __future__ import annotations

import pytest

from neobot_app.reply.event import ReplyEvent, ReplyState


def _walk(event: ReplyEvent, *states: ReplyState) -> ReplyEvent:
    """按合法链逐级推进状态，供需要中间态的前置场景使用。"""
    for state in states:
        event.transition(state)
    return event


def test_transition_full_legal_chain_pending_to_completed():
    """PENDING→BUILDING_PROMPT→GENERATING→SENDING→COMPLETED 的完整合法链必须逐级成功。"""
    event = ReplyEvent()
    for state in (
        ReplyState.BUILDING_PROMPT,
        ReplyState.GENERATING,
        ReplyState.SENDING,
        ReplyState.COMPLETED,
    ):
        event.transition(state)
        assert event.state == state


def test_transition_sending_back_to_generating_allowed():
    """私聊重新生成场景：SENDING→GENERATING 是合法回退转换。"""
    event = _walk(event := ReplyEvent(), ReplyState.BUILDING_PROMPT, ReplyState.GENERATING, ReplyState.SENDING)
    event.transition(ReplyState.GENERATING)
    assert event.state == ReplyState.GENERATING


def test_transition_generating_to_completed_allowed():
    """回复管线结束场景：GENERATING 直接进入 COMPLETED 必须合法并写入 completed_at。"""
    event = _walk(event := ReplyEvent(), ReplyState.BUILDING_PROMPT, ReplyState.GENERATING)
    event.transition(ReplyState.COMPLETED)
    assert event.state == ReplyState.COMPLETED
    assert event.completed_at is not None
    assert event.is_terminal is True


def test_transition_pending_to_sending_raises():
    """PENDING 直接跳转 SENDING（跳过中间态）必须抛 RuntimeError 且状态不变。"""
    event = ReplyEvent()
    with pytest.raises(RuntimeError, match="PENDING -> SENDING"):
        event.transition(ReplyState.SENDING)
    assert event.state == ReplyState.PENDING


def test_transition_after_terminal_raises():
    """COMPLETED 终态后再转换到任何状态必须抛 RuntimeError。"""
    event = _walk(
        event := ReplyEvent(),
        ReplyState.BUILDING_PROMPT,
        ReplyState.GENERATING,
        ReplyState.SENDING,
        ReplyState.COMPLETED,
    )
    for state in (ReplyState.PENDING, ReplyState.GENERATING, ReplyState.CANCELLED, ReplyState.FAILED):
        with pytest.raises(RuntimeError):
            event.transition(state)
        assert event.state == ReplyState.COMPLETED


def test_transition_pending_to_failed_allowed():
    """PENDING 直接失败（如事件分发前异常）必须合法，可进入 FAILED 终态。"""
    event = ReplyEvent()
    event.transition(ReplyState.FAILED)
    assert event.state == ReplyState.FAILED


def test_transition_pending_to_cancelled_allowed():
    """PENDING 直接取消（如生命周期被插件 consume）必须合法，可进入 CANCELLED 终态。"""
    event = ReplyEvent()
    event.transition(ReplyState.CANCELLED)
    assert event.state == ReplyState.CANCELLED


def test_transition_terminal_sets_completed_at():
    """进入任一终态（COMPLETED/FAILED/CANCELLED）时必须写入 completed_at。"""
    terminal_paths = {
        ReplyState.COMPLETED: (ReplyState.BUILDING_PROMPT, ReplyState.GENERATING, ReplyState.SENDING),
        ReplyState.FAILED: (ReplyState.BUILDING_PROMPT, ReplyState.GENERATING),
        ReplyState.CANCELLED: (ReplyState.BUILDING_PROMPT, ReplyState.GENERATING),
    }
    for terminal, path in terminal_paths.items():
        event = ReplyEvent()
        _walk(event, *path)
        event.transition(terminal)
        assert event.completed_at is not None


def test_transition_non_terminal_keeps_completed_at_none():
    """非终态转换（GENERATING/SENDING）不得写入 completed_at。"""
    event = _walk(event := ReplyEvent(), ReplyState.BUILDING_PROMPT, ReplyState.GENERATING, ReplyState.SENDING)
    assert event.completed_at is None


def test_is_terminal_true_for_terminal_states():
    """三个终态 must be reported as terminal. COMPLETED/FAILED/CANCELLED 均为终态。"""
    for terminal in (ReplyState.COMPLETED, ReplyState.FAILED, ReplyState.CANCELLED):
        event = ReplyEvent()
        if terminal == ReplyState.COMPLETED:
            _walk(event, ReplyState.BUILDING_PROMPT, ReplyState.GENERATING, ReplyState.SENDING)
        event.transition(terminal)
        assert event.is_terminal is True


def test_is_terminal_false_for_active_states():
    """PENDING/GENERATING/SENDING 等非终态不得被报告为 terminal。"""
    event = ReplyEvent()
    assert event.is_terminal is False
    event.transition(ReplyState.BUILDING_PROMPT)
    event.transition(ReplyState.GENERATING)
    assert event.is_terminal is False
    event.transition(ReplyState.SENDING)
    assert event.is_terminal is False


def test_transition_does_not_mutate_other_fields():
    """转换只改 state/completed_at，不得影响 generated_text/error 等业务字段。"""
    event = _walk(event := ReplyEvent(), ReplyState.BUILDING_PROMPT, ReplyState.GENERATING, ReplyState.SENDING)
    event.generated_text = "你好"
    event.error = None
    event.transition(ReplyState.COMPLETED)
    assert event.generated_text == "你好"
    assert event.error is None


def test_event_id_default_unique_per_instance():
    """未显式指定 event_id 时每个实例必须生成不同的默认 ID。"""
    first = ReplyEvent()
    second = ReplyEvent()
    assert first.event_id
    assert first.event_id != second.event_id
