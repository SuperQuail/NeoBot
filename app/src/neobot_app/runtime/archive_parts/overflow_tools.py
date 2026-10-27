"""压缩的工具循环、提示词与快照：模型逐页读全文、压缩写回与失败回滚。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from neobot_app.time_context import get_current_time_and_lunar_date, monotonic_seconds

from .constants import (
    AUTO_COMPRESSION_USAGE_KIND,
    MAX_OVERFLOW_PROMPT_CHARS,
    MAX_TOOL_FAILURES,
    _ARCHIVE_PROMPT_OMITTED,
)
from .helpers import (
    _bounded_archive_text,
    _bounded_tool_result,
    _is_tool_failure,
    _request_chars,
    _trim_tool_history,
    _tunable,
)


class OverflowToolMixin:
    """档案压缩的模型工具循环与快照/回滚。"""

    async def _direct_rewrite_without_tools(
        self, table_name: str, key: str, value: str, limit: int
    ) -> bool:
        """工具循环没写成功/没压到目标时，直接让模型输出压缩文本并写回。"""
        max_prompt_chars = _tunable("MAX_OVERFLOW_PROMPT_CHARS", MAX_OVERFLOW_PROMPT_CHARS)
        if self._provider is None or len(value) > max_prompt_chars:
            return False
        from neobot_app.runtime.compact import compact_archive_record

        candidate = await compact_archive_record(
            self._provider,
            value,
            target_chars=limit,
            table_name=table_name,
            key=key,
            timeout=self._next_call_timeout(max(1.0, self._summary_budget_seconds)),
        )
        if candidate is None:
            self._logger.warning(
                "档案压缩兜底直写未产生有效候选",
                table_name=table_name,
                key=key,
                chars_before=len(value),
                target_chars=limit,
            )
            return False
        current = await self._archive.get(table_name, key)
        if current is None:
            return False
        setter = getattr(self._archive, "set_if_version", None)
        if not callable(setter):
            return False
        try:
            await setter(
                table_name,
                key,
                candidate,
                list(getattr(current, "tags", None) or []),
                int(getattr(current, "version", 0) or 0),
            )
        except Exception as exc:
            self._logger.warning(
                "档案压缩兜底直写落库失败",
                table_name=table_name,
                key=key,
                error=f"{type(exc).__name__}: {exc}",
            )
            return False
        self._logger.info(
            "档案压缩兜底直写成功",
            table_name=table_name,
            key=key,
            chars_before=len(value),
            chars_after=len(candidate),
            target_chars=limit,
        )
        return True

    async def _run_overflow_tool_loop(
        self,
        prompt: str,
        *,
        table_name: str,
        key: str,
        usage_kind: str = AUTO_COMPRESSION_USAGE_KIND,
    ) -> tuple[int, int]:
        """压缩专用的模型工具循环，返回 (成功工具调用数, 失败工具调用数)。"""
        chat_messages: list[dict] = [
            {
                "role": "system",
                "content": (
                    "You compress a single chat archive record that exceeded its storage "
                    "limit. Rewrite it with the archive tools: keep every durable fact, "
                    "drop redundancy. If only part of the record was injected, read the "
                    "rest with read_archive(offset=...) before writing anything back. "
                    "After saving, verify the returned total_chars against the target; "
                    "never claim success while it is still over the target. When you are "
                    "done, respond without tool calls."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        tools = self._tool_definitions if self._tool_definitions else None
        tool_failures = 0
        tool_successes = 0
        deadline = monotonic_seconds() + self._summary_budget_seconds

        for iteration in range(self._max_tool_rounds):
            remaining = deadline - monotonic_seconds()
            if remaining <= 1.0:
                self._logger.warning(
                    "档案超限压缩超出单次时长预算，已中止",
                    table_name=table_name,
                    key=key,
                    budget_seconds=int(self._summary_budget_seconds),
                )
                break
            call_timeout = self._next_call_timeout(remaining)
            try:
                response = await asyncio.wait_for(
                    self._provider.chat(chat_messages, tools=tools),
                    timeout=call_timeout,
                )
            except asyncio.TimeoutError:
                self._logger.warning(
                    "档案超限压缩模型调用超时，本次调用不会计入用量统计",
                    table_name=table_name,
                    key=key,
                    timeout_seconds=int(call_timeout),
                    request_chars=_request_chars(chat_messages),
                    round=iteration + 1,
                )
                break
            await self._record_usage(
                response,
                # 手动（archive_manual）与自动（archive_overflow）单列，
                # 便于在「用量统计」里区分运维成本（spec(4) §4.10.3 / A42）。
                conversation_kind=usage_kind,
                conversation_id=f"{table_name}:{key}",
            )
            chat_messages.append(response)

            tool_calls = response.get("tool_calls")
            if not tool_calls or self._tool_executor is None:
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
            _trim_tool_history(chat_messages)

            if tool_failures >= MAX_TOOL_FAILURES:
                self._logger.warning(
                    "档案超限压缩因工具连续失败而中止",
                    table_name=table_name,
                    key=key,
                    tool_failures=tool_failures,
                )
                break
        return tool_successes, tool_failures

    def _build_overflow_compression_prompt(
        self,
        *,
        table_name: str,
        key: str,
        value: str,
        limit: int,
        trigger: str = "auto",
        target_chars: int | None = None,
    ) -> str:
        """构造「压缩单条超限档案」的提示词（要求保留事实、只丢冗余）。

        ``trigger`` 区分两条触发路径（spec(4) §4.10.3）：
        - ``"auto"``：写路径超限自动压缩，目标 = min(max_total_chars, 10000)；
        - ``"manual"``：面板 / 批量手动触发，目标 = 本次请求的目标，必须写明这是
          「运维主动要求的目标」，且要求压缩后自证 ``total_chars <= target``。
        """
        current_time = get_current_time_and_lunar_date()
        target = limit if target_chars is None else int(target_chars)
        manual = str(trigger or "auto") == "manual"
        manual_note = (
            "This compression was explicitly requested by the operator from the management "
            "panel. The target below is a hard requirement for THIS run: the rewritten "
            f"record MUST be <= {target} characters.\n"
            if manual
            else ""
        )
        from neobot_app.runtime.compact import archive_compact_guide

        return (
            f"Current time: {current_time}\n"
            f"{archive_compact_guide()}\n"
            f"trigger: {trigger}\n"
            f"The archive record below exceeded its storage limit and must be compressed now.\n"
            f"table_name: {table_name}\n"
            f"key: {key}\n"
            f"current_chars: {len(value)}\n"
            f"target_chars: {target}\n"
            f"hard_limit: {limit}\n"
            f"{manual_note}"
            f"Compression rules:\n"
            f"- Call archive_crud__save_archive with table_name='{table_name}', "
            f"key='{key}' and the FULL compressed record.\n"
            f"- Base the rewrite on the FULL record, never on a partial view. If the record "
            f"below contains the marker {_ARCHIVE_PROMPT_OMITTED.strip()!r} (only head and tail "
            f"were injected), you MUST first read the whole record page by page with "
            f"read_archive(offset=...) before writing anything back: offset=0 is the first "
            f"page, positive offsets move forward, negative offsets read from the tail "
            f"(-1 is the newest page, 500 characters per page).\n"
            f"- Keep every durable fact (names, dates, numbers, preferences, decisions, "
            f"unresolved items); merge duplicates and drop repetition/verbose wording.\n"
            f"- Never invent facts that are not in the original record.\n"
            f"- The compressed record MUST be <= {target} characters; "
            f"aim for roughly {max(target // 2, 1)} characters.\n"
            f"- After saving, check the total_chars returned by save_archive: it MUST be "
            f"<= {target}. If it is still larger, keep compressing and save again; if you "
            f"cannot reach it, say so honestly in your final answer. Never claim the record "
            f"is compressed while total_chars > {target}.\n"
            f"- Do not touch any other archive record.\n"
            f"\nRecord to compress:\n{_bounded_archive_text(value)}"
        )

    async def _save_compression_snapshot(
        self,
        table_name: str,
        key: str,
        *,
        value: str,
        item: Any,
        source: str,
        operator_ip: str | None,
    ) -> int | None:
        """压缩前留痕（写失败只告警，不阻断压缩本身）。"""
        saver = getattr(self._archive, "save_snapshot", None)
        if not callable(saver):
            return None
        try:
            snapshot_id = await saver(
                table_name,
                key,
                value,
                total_chars=len(value),
                version=int(getattr(item, "version", 0) or 0),
                reason=str(source or "auto"),
                operator_ip=operator_ip,
            )
        except Exception as exc:
            self._logger.warning(
                "压缩前快照写入失败，本次压缩继续（不影响原文）",
                table_name=table_name,
                key=key,
                error=str(exc) or type(exc).__name__,
            )
            return None
        return int(snapshot_id) if snapshot_id else None

    async def _restore_compression_original(
        self, table_name: str, key: str, original: str
    ) -> bool:
        """压缩失败 / 未达标时把档案内容回滚成压缩前的原文，返回是否已还原。

        走 ``set_if_version``（面板路径）：一是不触发容量治理，避免「回滚 → 再次超限
        → 再压缩」的循环；二是带乐观锁，不会覆盖并发的人工编辑（冲突时保留快照）。
        内容本来就等于原文（模型根本没写）时直接算还原成功。
        """
        try:
            current = await self._archive.get(table_name, key)
        except Exception as exc:
            self._logger.warning(
                "压缩失败后读取档案以回滚原文失败（保留快照）",
                table_name=table_name,
                key=key,
                error=str(exc) or type(exc).__name__,
            )
            return False
        if current is None:
            # 条目已被并发删除：不敢凭空重建，保留快照以便人工恢复。
            return False
        if str(getattr(current, "value", "") or "") == original:
            return True
        setter = getattr(self._archive, "set_if_version", None)
        if not callable(setter):
            return False
        try:
            await setter(
                table_name,
                key,
                original,
                list(getattr(current, "tags", None) or []),
                int(getattr(current, "version", 0) or 0),
            )
        except Exception as exc:
            self._logger.warning(
                "压缩失败后回滚原文失败（保留快照供人工恢复）",
                table_name=table_name,
                key=key,
                error=str(exc) or type(exc).__name__,
            )
            return False
        self._logger.info(
            "档案压缩未达标，已回滚为压缩前原文",
            table_name=table_name,
            key=key,
            chars=len(original),
        )
        return True

    async def _drop_compression_snapshot(self, snapshot_id: int | None) -> None:
        """压缩失败 / 未达标时删除本次快照（R19 / §4.10.4）。"""
        if not snapshot_id:
            return
        deleter = getattr(self._archive, "delete_snapshot", None)
        if not callable(deleter):
            return
        try:
            await deleter(int(snapshot_id))
        except Exception as exc:
            self._logger.warning(
                "压缩失败后删除快照失败（不影响原文）",
                snapshot_id=int(snapshot_id),
                error=str(exc) or type(exc).__name__,
            )
