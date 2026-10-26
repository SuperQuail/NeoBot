"""空轮次/未发送正文的判定与收尾处理。"""
from __future__ import annotations

import json
from neobot_app.reply.event import ReplyEvent, ReplyState

#: 空轮次成因：输出预算被思维链吃光（finish_reason=length）。
EMPTY_TURN_TRUNCATED = "truncated"
#: 空轮次成因：模型没给正文也没调工具，且不是长度截断。
EMPTY_TURN_NO_OUTPUT = "empty"
def _extract_finish_reason(response: object) -> str:
    """读取 provider 透出的结束原因（缺失时返回空串）。"""
    if not isinstance(response, dict):
        return ""
    extensions = response.get("extensions")
    if not isinstance(extensions, dict):
        return ""
    value = extensions.get("finish_reason")
    return value.strip() if isinstance(value, str) else ""
def _extract_usage_summary(response: object) -> dict[str, object]:
    """取出这一轮的 output / reasoning token 数（缺失时为 None）。

    空轮次判定与日志观测共用同一套取值，避免两处口径漂移。
    """
    extensions = response.get("extensions") if isinstance(response, dict) else None
    usage = extensions.get("usage") if isinstance(extensions, dict) else None
    usage = usage if isinstance(usage, dict) else {}
    details = usage.get("completion_tokens_details")
    details = details if isinstance(details, dict) else {}
    return {
        "output_tokens": usage.get("output_tokens"),
        "reasoning_tokens": details.get("reasoning_tokens"),
    }
def _classify_empty_turn(response: object) -> str:
    """给「正文为空且没有工具调用」的一轮定性。

    两种情况都会导致回复丢失，必须区分记录：
    - EMPTY_TURN_TRUNCATED：finish_reason=length，输出预算被思维链吃光；
    - EMPTY_TURN_NO_OUTPUT：其它原因的空输出。
    """
    if _extract_finish_reason(response).casefold() == "length":
        return EMPTY_TURN_TRUNCATED
    return EMPTY_TURN_NO_OUTPUT

class EmptyTurnMixin:
    @staticmethod
    def _tool_failure_key(name: str, args: object) -> str:
        """同工具 + 同参数的失败指纹（参数不可序列化时退化为 repr）。"""
        try:
            payload = json.dumps(
                args, ensure_ascii=False, sort_keys=True, default=str
            )
        except (TypeError, ValueError, RecursionError):
            payload = repr(args)
        return f"{name}|{payload}"
    @staticmethod
    def _tool_repeat_failure_hint(name: str, failures: int) -> str:
        """软提示：说明重复失败，但仍允许继续调用（工具不会被永久摘除）。"""
        return (
            f"注意：{name} 用相同参数已连续失败 {failures} 次。"
            "若判断是环境或权限问题，请不要再重复尝试，改用其它工具或直接向用户说明；"
            "如果确认问题已经修复，可以继续调用。"
        )
    @staticmethod
    def _build_empty_turn_error(
        reason: str, finish_reason: str, output_tokens: object
    ) -> str:
        if reason == EMPTY_TURN_TRUNCATED:
            return (
                "模型输出被输出上限截断：本轮没有正文也没有工具调用"
                f"（finish_reason=length, output_tokens={output_tokens}）"
            )
        return (
            "模型返回空输出：本轮没有正文也没有工具调用"
            f"（finish_reason={finish_reason or '未提供'}）"
        )
    def _handle_unsent_prose(
        self,
        event: ReplyEvent,
        text: str,
        response: object,
        *,
        queue_key: str,
        iteration: int,
        review_pending: bool,
    ) -> None:
        """没有工具调用的正文不发送：agent 模式下发言只能走 send_reply/cancel。

        第一轮已经通过 reminder 把纠正提示发给模型；这里只做最终取消与审计，
        不再把「没调工具」记成错误（错误信息对模型下一次修复没有意义）。
        """
        if review_pending:
            stage = "ai_reply_check_without_tool_call"
        else:
            stage = "unsent_prose_detected"
        # 不把“没调工具”写成事件错误：它已经通过 reminder 发回给模型，
        # 再记 FAILED 只会污染观测，对下一次语言修复没有任何信息价值。
        if not event.is_terminal:
            try:
                event.transition(ReplyState.CANCELLED)
            except RuntimeError:
                pass

        self._logger.info(
            "模型多次输出正文但没有工具调用，已取消本轮（不发送草稿）",
            event_id=event.event_id,
            queue_key=queue_key,
            iteration=iteration,
            review_pending=review_pending,
            reply_text=text,
        )
        self._record_debug(
            stage,
            event,
            queue_key=queue_key,
            iteration=iteration,
            reply_text=text,
            review_pending=review_pending,
            finish_reason=_extract_finish_reason(response) or None,
        )
    def _handle_empty_turn(
        self,
        event: ReplyEvent,
        response: object,
        *,
        queue_key: str,
        iteration: int,
    ) -> None:
        """空轮次不再静默结束：区分成因、留痕，并把事件置为 FAILED。

        这里刻意不做重试：实测重试大概率拿不到有效输出，只会再多烧一轮
        input token。也不发兜底回复（避免群聊刷屏）。要保证的只有一件事——
        「模型没产出导致回复丢失」一定留下可检索的记录，而不是 COMPLETED。
        """
        finish_reason = _extract_finish_reason(response)
        reason = _classify_empty_turn(response)
        counters = _extract_usage_summary(response)
        output_tokens = counters["output_tokens"]
        reasoning_tokens = counters["reasoning_tokens"]

        event.error = self._build_empty_turn_error(
            reason, finish_reason, output_tokens
        )
        if not event.is_terminal:
            try:
                event.transition(ReplyState.FAILED)
            except RuntimeError:
                pass

        self._logger.warning(
            "模型空轮次：该轮没有正文也没有工具调用，回复未发出",
            event_id=event.event_id,
            queue_key=queue_key,
            iteration=iteration,
            reason=reason,
            finish_reason=finish_reason or None,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
        )
        self._record_debug(
            "empty_turn_detected",
            event,
            queue_key=queue_key,
            iteration=iteration,
            reason=reason,
            finish_reason=finish_reason or None,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
        )
        if reason == EMPTY_TURN_TRUNCATED:
            # 超限截断是成本问题，单独留一条便于直接检索/统计。
            self._record_debug(
                "empty_turn_truncated",
                event,
                queue_key=queue_key,
                iteration=iteration,
                finish_reason=finish_reason,
                output_tokens=output_tokens,
                reasoning_tokens=reasoning_tokens,
            )
