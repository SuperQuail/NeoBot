"""回复钩子（插件扩展点）失败时必须留痕。

原实现对 pre/post reply hook 的异常 `except Exception: pass`：插件钩子抛错
时既没有日志也没有事件，外部无法区分「钩子没生效」和「钩子抛异常被吞」。
"""

from __future__ import annotations

from types import SimpleNamespace

from neobot_app.reply.orchestrator import ReplyOrchestrator, _hook_name


class _RecordingLogger:
    def __init__(self) -> None:
        self.warnings: list[tuple[str, dict]] = []

    def warning(self, message: str, **kw) -> None:
        self.warnings.append((message, kw))

    def info(self, message: str, **kw) -> None:
        pass

    def debug(self, message: str, **kw) -> None:
        pass

    def error(self, message: str, **kw) -> None:
        pass

    def exception(self, message: str, **kw) -> None:
        pass


def _make_orchestrator() -> ReplyOrchestrator:
    orchestrator = ReplyOrchestrator.__new__(ReplyOrchestrator)
    orchestrator._pre_reply_hooks = []
    orchestrator._post_reply_hooks = []
    orchestrator._logger = _RecordingLogger()
    return orchestrator


def _event():
    return SimpleNamespace(event_id="e1")


async def test_pre_hook_failure_is_logged_and_skipped() -> None:
    orchestrator = _make_orchestrator()

    async def broken(event):
        raise ValueError("boom")

    orchestrator._pre_reply_hooks.append(broken)

    assert await orchestrator._apply_pre_reply_hooks(_event()) is None
    message, context = orchestrator._logger.warnings[0]
    assert "pre_reply hook" in message
    assert context["hook"] == _hook_name(broken)
    assert context["error_type"] == "ValueError"
    assert context["error"] == "boom"


async def test_pre_hook_continues_to_next_hook_after_failure() -> None:
    orchestrator = _make_orchestrator()

    async def broken(event):
        raise RuntimeError("nope")

    async def short_circuit(event):
        return "canned reply"

    orchestrator._pre_reply_hooks.extend([broken, short_circuit])

    assert await orchestrator._apply_pre_reply_hooks(_event()) == "canned reply"


async def test_post_hook_failure_keeps_original_text() -> None:
    orchestrator = _make_orchestrator()

    async def broken(event, text):
        raise KeyError("missing")

    orchestrator._post_reply_hooks.append(broken)

    assert await orchestrator._apply_post_reply_hooks(_event(), "原始文本") == "原始文本"
    message, context = orchestrator._logger.warnings[0]
    assert "post_reply hook" in message
    assert context["error_type"] == "KeyError"


async def test_post_hook_success_still_replaces_text() -> None:
    orchestrator = _make_orchestrator()

    async def rewriter(event, text):
        return f"[改写] {text}"

    orchestrator._post_reply_hooks.append(rewriter)

    assert await orchestrator._apply_post_reply_hooks(_event(), "abc") == "[改写] abc"
    assert orchestrator._logger.warnings == []
