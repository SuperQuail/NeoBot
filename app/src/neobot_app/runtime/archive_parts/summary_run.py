"""单次自动总结的执行：模型工具循环、预算/超时控制、部分成功清账与用量统计。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from neobot_app.time_context import monotonic_seconds

from .constants import (
    DEFAULT_SUMMARY_CALL_TIMEOUT_SECONDS,
    MAX_TOOL_FAILURES,
    PROVIDER_TIMEOUT_MARGIN_SECONDS,
)
from .helpers import (
    _bounded_tool_result,
    _is_tool_failure,
    _request_chars,
    _trim_tool_history,
)


class SummaryRunMixin:
    """一次总结的模型调用循环（不持有计数器锁）。"""

    async def _summarize_and_reset(
        self,
        *,
        conversation_kind: str,
        conversation_id: str,
        counter_key: str,
        messages: list[Any],
        snapshot_count: int,
    ) -> bool:
        """执行一次总结。返回 True 表示计数器已复位（含空消息），False 表示保留待重试。

        并发协议：总结占位在方法内统一持有（record_message 与 flush_all 共用），
        模型调用期间不持计数器锁；成功/失败都在短锁内基于库内最新状态合并，
        绝不回写快照。snapshot_count 是快照对应的 count，用来算出总结期间新到的
        消息条数——这些消息必须保留到下一轮，不能被成功路径清零。
        """
        if not self._begin_summary(counter_key):
            return False
        try:
            return await self._run_summary(
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
                counter_key=counter_key,
                messages=messages,
                snapshot_count=snapshot_count,
            )
        finally:
            self._end_summary(counter_key)

    def _next_call_timeout(self, remaining: float) -> float:
        """算出本轮模型调用的超时，并保证不超出总预算。

        默认跟随总结模型自身的请求超时（再留一点余量让 httpx 先超时并返回可读错误，
        而不是被外层 wait_for 在模型仍正常推理时掐断）。开启思考、推理强度拉满的模型
        单次调用经常超过 60 秒，用固定 60 秒会稳定超时并反复重试，每次都要重发完整
        上下文，既浪费时间又烧 token。配置 model_call_timeout_seconds 可显式覆盖。
        """
        limit = self._model_call_timeout_seconds
        if limit <= 0.0:
            provider_timeout = getattr(self._provider, "timeout", None)
            try:
                limit = float(provider_timeout) + PROVIDER_TIMEOUT_MARGIN_SECONDS
            except (TypeError, ValueError):
                limit = DEFAULT_SUMMARY_CALL_TIMEOUT_SECONDS
        return max(1.0, min(limit, remaining))

    async def _commit_partial_success(
        self,
        counter_key: str,
        *,
        conversation_kind: str,
        conversation_id: str,
        snapshot_count: int,
        message_count: int,
        tool_successes: int,
        round_index: int,
        reason: str,
    ) -> None:
        """写入过内容后中止：按部分成功清账，不重跑整批消息。

        档案是增量 append 语义，重跑会把同一批事实再写一遍；而重试本身还要把同一批
        消息再烧一遍 token，且大概率以同样的方式再次中止。但必须留下可排查的告警，
        否则"模型没处理完就被销账"是完全静默的。
        """
        await self._commit_success(counter_key, snapshot_count=snapshot_count)
        self._logger.warning(
            "档案自动总结在写入部分内容后中止，按部分成功清账不再重试",
            conversation_kind=conversation_kind,
            conversation_id=conversation_id,
            message_count=message_count,
            round=round_index,
            tool_calls_succeeded=tool_successes,
            reason=reason,
        )

    async def _run_summary(
        self,
        *,
        conversation_kind: str,
        conversation_id: str,
        counter_key: str,
        messages: list[Any],
        snapshot_count: int,
    ) -> bool:
        if not messages:
            await self._commit_success(counter_key, snapshot_count=snapshot_count)
            return True

        prompt = self._build_summary_prompt(
            conversation_kind=conversation_kind,
            conversation_id=conversation_id,
            messages=messages,
        )

        try:
            chat_messages: list[dict] = [
                {
                    "role": "system",
                    "content": (
                        "You maintain chat archives for a chat bot. "
                        "Update records incrementally: use patch_archive to append only the new facts, "
                        "never rewrite a whole record unless you are compressing the strict-length summary. "
                        "When you are done, simply respond without tool calls."
                    ),
                },
                {"role": "user", "content": prompt},
            ]
            tools = self._tool_definitions if self._tool_definitions else None
            tool_failures = 0
            tool_successes = 0
            # 单次总结的总时长预算：工具轮次再多也不能把一次总结拖成数十分钟。
            deadline = monotonic_seconds() + self._summary_budget_seconds

            for _iteration in range(self._max_tool_rounds):
                remaining = deadline - monotonic_seconds()
                if remaining <= 1.0:
                    if tool_successes:
                        # 预算耗尽但已经写过档案：同上，清账优于重跑。
                        await self._commit_partial_success(
                            counter_key,
                            conversation_kind=conversation_kind,
                            conversation_id=conversation_id,
                            snapshot_count=snapshot_count,
                            message_count=len(messages),
                            tool_successes=tool_successes,
                            round_index=_iteration + 1,
                            reason="budget_exhausted",
                        )
                        return True
                    self._logger.warning(
                        "档案自动总结超出单次时长预算，已中止并进入冷却",
                        conversation_kind=conversation_kind,
                        conversation_id=conversation_id,
                        budget_seconds=int(self._summary_budget_seconds),
                    )
                    await self._defer_after_failure(counter_key)
                    return False
                call_timeout = self._next_call_timeout(remaining)
                try:
                    response = await asyncio.wait_for(
                        self._provider.chat(chat_messages, tools=tools),
                        timeout=call_timeout,
                    )
                except asyncio.TimeoutError:
                    # 超时请求不会返回 usage：这次调用在本地用量统计里完全不存在，
                    # 但服务端已经按实际生成计费。必须留下可排查的痕迹，
                    # 否则账单与「费用统计」的差额永远找不到来源。
                    self._logger.warning(
                        "档案自动总结模型调用超时，本次调用不会计入用量统计",
                        conversation_kind=conversation_kind,
                        conversation_id=conversation_id,
                        timeout_seconds=int(call_timeout),
                        request_chars=_request_chars(chat_messages),
                        messages_count=len(chat_messages),
                        round=_iteration + 1,
                        tool_calls_succeeded=tool_successes,
                    )
                    if tool_successes:
                        await self._commit_partial_success(
                            counter_key,
                            conversation_kind=conversation_kind,
                            conversation_id=conversation_id,
                            snapshot_count=snapshot_count,
                            message_count=len(messages),
                            tool_successes=tool_successes,
                            round_index=_iteration + 1,
                            reason="model_call_timeout",
                        )
                        return True
                    raise
                await self._record_usage(
                    response,
                    conversation_kind=conversation_kind,
                    conversation_id=conversation_id,
                )
                chat_messages.append(response)

                tool_calls = response.get("tool_calls")
                if not tool_calls:
                    break

                if self._tool_executor is None:
                    break

                for tc in tool_calls:
                    name = tc["function"]["name"]
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        args = {}
                    try:
                        result = await self._tool_executor(name, args)
                    except Exception as tool_exc:
                        result = f"Tool error: {tool_exc}"
                    if _is_tool_failure(result):
                        tool_failures += 1
                    else:
                        tool_successes += 1
                    chat_messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": _bounded_tool_result(result),
                    })
                # 每轮都收紧一次：工具返回是上下文膨胀的唯一来源，
                # 不收紧时后续每一轮都要重发全部历史工具返回。
                _trim_tool_history(chat_messages)

                if tool_failures >= MAX_TOOL_FAILURES:
                    self._logger.warning(
                        "档案自动总结因工具连续失败而中止",
                        conversation_kind=conversation_kind,
                        conversation_id=conversation_id,
                        tool_failures=tool_failures,
                    )
                    break

            if tool_failures and not tool_successes:
                # 全程没有任何工具成功 = 什么都没写进去，保留计数器并进入冷却。
                failures = await self._defer_after_failure(counter_key)
                self._logger.warning(
                    "档案自动总结未写入任何内容，进入冷却后重试",
                    conversation_kind=conversation_kind,
                    conversation_id=conversation_id,
                    tool_failures=tool_failures,
                    consecutive_failures=failures,
                )
                return False

            await self._commit_success(counter_key, snapshot_count=snapshot_count)
            if tool_failures:
                # 部分工具失败仍按"至少写入过内容"清账：档案是增量 append 语义，
                # 重跑同一批消息可能重复写入事实。但必须留下可排查的告警，
                # 否则"模型没处理完就被销账"是完全静默的。
                self._logger.warning(
                    "档案自动总结存在工具失败，已按部分成功清账",
                    conversation_kind=conversation_kind,
                    conversation_id=conversation_id,
                    message_count=len(messages),
                    tool_failures=tool_failures,
                    tool_calls_succeeded=tool_successes,
                )
            self._logger.info(
                "档案已更新",
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
                message_count=len(messages),
                tool_calls_succeeded=tool_successes,
            )
            return True
        except Exception as exc:
            failures = await self._defer_after_failure(counter_key)
            self._logger.warning(
                "档案自动总结失败，进入冷却后重试",
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
                error=str(exc) or type(exc).__name__,
                consecutive_failures=failures,
            )

    async def _record_usage(
        self,
        response: Any,
        *,
        conversation_kind: str,
        conversation_id: str,
    ) -> None:
        """把一次总结调用的 token 用量计入统计（统计失败不影响总结流程）。

        档案总结此前完全不记录用量，成本在统计里是黑盒；记录后可在
        「统计与计费」中直接看到 agent:memory 的消耗。
        """
        try:
            extensions = response.get("extensions") if isinstance(response, dict) else None
            usage = (extensions or {}).get("usage") or {}
            input_tokens = int(usage.get("input_tokens") or 0)
            output_tokens = int(usage.get("output_tokens") or 0)
            if not input_tokens and not output_tokens:
                return
            from neobot_app.statistics.tracker import get_usage_tracker

            await get_usage_tracker().record(
                module="agent:memory",
                model_name=getattr(self._provider, "model", "") or "",
                registered_key=getattr(self._provider, "registered_key", ""),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_hit_tokens=int(usage.get("cache_hit_tokens") or 0),
                cache_miss_tokens=int(usage.get("cache_miss_tokens") or 0),
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
            )
        except Exception as exc:
            # 计费/用量数据一旦丢失无法恢复，必须留痕（此前是静默 return，
            # 统计面板与账单少计且事后无法定位）。
            self._logger.warning(
                "档案总结用量记录失败，本次消耗未计入统计",
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
                input_tokens=locals().get("input_tokens", 0),
                output_tokens=locals().get("output_tokens", 0),
                error=str(exc) or type(exc).__name__,
            )
