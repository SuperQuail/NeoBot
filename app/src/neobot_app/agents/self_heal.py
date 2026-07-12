"""Self-healing Agent: monitors accumulated errors, diagnoses and (when safe)
attempts recovery, then notifies the admin via the background notification hub.

Architecture mirrors ProblemSolverManager/Agent (see problem_solver.py):
  SelfHealManager   — error aggregation, throttled submission, notification
  SelfHealAgent     — LLM-driven diagnostic agent with a toolset
  SelfHealToolExecutor — read errors / logs / own source code, write debug
                      reports, run_python, search_web, parse_image, and a few
                      safe repair hooks (clear drawing cooldown, trigger image
                      cleanup).

Notifications are split into two phases:
  1. submit() fires immediately  -> source="self_heal_start" («已开始工作»)
  2. heal task resolves          -> source="self_heal_result" (诊断 + debug_file)

The admin chat flow is the private conversation with `admin_account` (falls
back to chat.admin_accounts[0]).
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
import subprocess
import sys
import tempfile
import traceback as _traceback
from collections import deque
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from neobot_chat import Agent
from neobot_chat.providers.base import Provider
from neobot_chat.schema.protocol import ToolExecutor
from neobot_chat.schema.types import (
    ChatChunk,
    State,
    ToolAccessPolicy,
    ToolAccessRule,
    ToolDefinition,
    ToolGuardContext,
)
from neobot_chat.tools.toolset import ToolSpec, Toolset
from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.statistics.tracker import (
    CURRENT_CONVERSATION_ID,
    CURRENT_CONVERSATION_KIND,
    CURRENT_USAGE_MODULE,
    get_usage_tracker,
)
from neobot_app.time_context import monotonic_seconds
from neobot_app.web_search_package import WebSearchExecutor

if TYPE_CHECKING:
    from neobot_app.config.schemas.bot import BotConfig

EXPOSED_TO_MAIN_AGENT_NAME = "self_heal"
EXPOSED_TO_MAIN_AGENT_DESCRIPTION = (
    "系统自修复诊断。仅由系统在累积异常时自动唤起，不直接面向用户聊天。"
    "诊断 Bot 自身运行时异常、尝试安全修复、产出调试报告并通过通知系统告知管理员。"
)

# Source names used when publishing to BackgroundNotificationHub
START_SOURCE = "self_heal_start"
RESULT_SOURCE = "self_heal_result"

# Module-name prefix used by loguru sink for selfheal-internal loggers.
# The sink filters these out to avoid self-excitation loops.
LOGGER_PREFIX = "app.self_heal"

# ContextVar carrying the HealTask that the current LLM invocation belongs to,
# used by tool executor to read the error snapshot + chat_flow_id.
_HEAL_TASK: ContextVar["HealTask | None"] = ContextVar(
    "self_heal_task", default=None
)


def _tool_def(name: str, description: str, parameters: dict[str, Any]) -> ToolDefinition:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", **parameters},
        },
    }


def _default_resolver(
    args: dict[str, Any], context: ToolGuardContext, policy: ToolAccessPolicy
) -> ToolAccessRule:
    return ToolAccessRule(action="allow")


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


# ── Config ──────────────────────────────────────────────────────────────────


class SelfHealAgentConfig:
    """Self-heal Agent runtime config (from BotConfig.agent.self_healing)."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        admin_account: str = "",
        traceback_threshold: int = 3,
        rate_threshold: int = 10,
        rate_window_seconds: int = 60,
        min_interval_seconds: int = 300,
        buffer_size: int = 200,
        timeout_seconds: float = 300.0,
        max_tokens: int = 8192,
        reasoning_effort: str = "high",
        sandbox_debug_dir: str = "debug/self_heal",
    ) -> None:
        self.enabled = enabled
        self.admin_account = admin_account.strip() if admin_account else ""
        self.traceback_threshold = max(1, int(traceback_threshold))
        self.rate_threshold = max(1, int(rate_threshold))
        self.rate_window_seconds = max(1, int(rate_window_seconds))
        self.min_interval_seconds = max(0, int(min_interval_seconds))
        self.buffer_size = max(10, int(buffer_size))
        self.timeout_seconds = float(timeout_seconds)
        self.max_tokens = int(max_tokens)
        self.reasoning_effort = str(reasoning_effort)
        self.sandbox_debug_dir = (str(sandbox_debug_dir).strip().lstrip("/")
                                  or "debug/self_heal")

    @classmethod
    def from_schema(cls, config: Any | None) -> "SelfHealAgentConfig":
        if config is None:
            return cls()
        admin = getattr(config, "admin_account", "") or ""
        return cls(
            enabled=bool(getattr(config, "enabled", True)),
            admin_account=str(admin),
            traceback_threshold=int(getattr(config, "traceback_threshold", 3) or 3),
            rate_threshold=int(getattr(config, "rate_threshold", 10) or 10),
            rate_window_seconds=int(getattr(config, "rate_window_seconds", 60) or 60),
            min_interval_seconds=int(getattr(config, "min_interval_seconds", 300) or 300),
            buffer_size=int(getattr(config, "buffer_size", 200) or 200),
            timeout_seconds=float(getattr(config, "timeout_seconds", 300) or 300),
            max_tokens=int(getattr(config, "max_tokens", 8192) or 8192),
            reasoning_effort=str(getattr(config, "reasoning_effort", "high") or "high"),
            sandbox_debug_dir=str(getattr(config, "sandbox_debug_dir", "debug/self_heal")
                                  or "debug/self_heal"),
        )


# ── Task record ─────────────────────────────────────────────────────────────


@dataclass
class HealTask:
    """A running self-heal invocation."""

    task_id: str
    admin_account: str
    trigger_reason: str
    error_snapshot: list[dict[str, Any]] = field(default_factory=list)
    first_error_time: str = ""
    last_error_time: str = ""
    status: str = "healing"  # healing | completed | failed | timeout
    summary: str | None = None
    root_cause: str | None = None
    debug_file: str | None = None
    repaired: bool = False
    notified_final: bool = False
    created_at: float = field(default_factory=monotonic_seconds)


# ── Manager ─────────────────────────────────────────────────────────────────


class SelfHealManager:
    """Aggregates errors from the loguru ERROR sink and dispatches a self-heal
    agent invocation when thresholds are reached.

    Lifecycle:
      * record(payload)   — called by the logging sink (on logging thread →
        handed off to the running event loop via call_soon_threadsafe by the
        sink itself; this method just collects and runs throttle logic).
      * submit(...)       — spawns a background heal task; immediately fires
        the start notification.
      * trigger_now(...)  — manual entry point (no skill wiring yet).
      * shutdown()        — cancels any running task.
    """

    def __init__(
        self,
        *,
        config: SelfHealAgentConfig | None = None,
        fallback_admin_account: str = "",
        logger: Logger | None = None,
        notification_hub: Any = None,
        sandbox_service: Any = None,
        data_dir: Path | None = None,
        source_roots: list[Path] | None = None,
        log_file: Path | None = None,
        repair_hooks: dict[str, Any] | None = None,
        web_search_config: dict | None = None,
        vision_provider: Any = None,
    ) -> None:
        self._config = config or SelfHealAgentConfig()
        self._fallback_admin = fallback_admin_account.strip() if fallback_admin_account else ""
        self._logger = logger or NullLogger()
        self._notification_hub = notification_hub
        self._sandbox = sandbox_service
        self._data_dir = data_dir
        self._log_file = log_file
        self._source_roots = source_roots or []
        self._repair_hooks = repair_hooks or {}
        self._vision_provider = vision_provider

        self._buffer: deque[dict[str, Any]] = deque(maxlen=self._config.buffer_size)
        self._last_trigger_monotonic: float = 0.0
        self._running_task: asyncio.Task[None] | None = None
        self._current_heal: HealTask | None = None
        self._agent: Any = None  # SelfHealAgent; set via set_agent
        self._orchestrator: Any = None
        self._web_search_config = web_search_config or {}

    # ── wiring ──

    def set_agent(self, agent: Any) -> None:
        self._agent = agent

    def set_orchestrator(self, orchestrator: Any) -> None:
        self._orchestrator = orchestrator
        if self._notification_hub is not None:
            self._notification_hub.set_orchestrator(orchestrator)

    def set_notification_hub(self, hub: Any) -> None:
        self._notification_hub = hub

    @property
    def enabled(self) -> bool:
        return self._config.enabled and self._agent is not None

    def resolve_admin_account(self) -> str:
        if self._config.admin_account:
            return self._config.admin_account
        return self._fallback_admin

    # ── error ingestion ──

    async def record(self, error_payload: dict[str, Any]) -> None:
        """Append an error to the ring buffer and evaluate throttles.

        Safe to call from any coroutine in the main event loop (the loguru
        sink should hand off via call_soon_threadsafe to the loop).
        """
        if not self._config.enabled:
            return
        # Skip internal self-heal logs to avoid self-excitation
        module = str(error_payload.get("module", ""))
        if module.startswith(LOGGER_PREFIX):
            return
        self._buffer.append(error_payload)
        try:
            await self._maybe_trigger()
        except Exception as exc:
            # Never let the sink's coroutine fail loudly
            self._logger.debug("self_heal trigger evaluation failed", error=str(exc))

    def _has_traceback(self) -> bool:
        return any(bool(e.get("traceback")) for e in self._buffer)

    def _traceback_count(self) -> int:
        return sum(1 for e in self._buffer if e.get("traceback"))

    def _rate_count(self) -> int:
        now_mono = monotonic_seconds()
        window = self._config.rate_window_seconds
        return sum(
            1
            for e in self._buffer
            if now_mono - float(e.get("_monotonic", 0.0)) <= window
        )

    async def _maybe_trigger(self) -> None:
        if self._agent is None:
            return
        if self._running_task is not None and not self._running_task.done():
            return  # already running → just keep accumulating
        now_mono = monotonic_seconds()
        if now_mono - self._last_trigger_monotonic < self._config.min_interval_seconds:
            return  # throttled
        if self._traceback_count() < self._config.traceback_threshold and \
                self._rate_count() < self._config.rate_threshold:
            return  # not enough signal yet

        reason_parts = []
        if self._traceback_count() >= self._config.traceback_threshold:
            reason_parts.append(
                f"{self._traceback_count()} 个未处理异常累积"
            )
        if self._rate_count() >= self._config.rate_threshold:
            reason_parts.append(
                f"{self._rate_count()} 秒内错误速率达 {self._config.rate_threshold}/"
                f"{self._config.rate_window_seconds}s"
            )
        reason = "；".join(reason_parts) or "累积异常"
        await self._dispatch(reason=reason)

    async def trigger_now(self, *, reason: str = "manual") -> str:
        """Manual trigger entry. Skips throttle but still respects running task.

        Returns JSON status string.
        """
        if not self._config.enabled:
            return _json({"ok": False, "error": "self_heal disabled"})
        if self._agent is None:
            return _json({"ok": False, "error": "self_heal agent 未配置"})
        if self._running_task is not None and not self._running_task.done():
            return _json({
                "ok": True,
                "status": "busy",
                "task_id": self._current_heal.task_id if self._current_heal else None,
            })
        await self._dispatch(reason=reason)
        if self._current_heal is not None:
            return _json({
                "ok": True,
                "status": "started",
                "task_id": self._current_heal.task_id,
            })
        return _json({"ok": False, "error": "未生成任务（无 admin account 或缺少配置）"})

    async def _dispatch(self, *, reason: str) -> None:
        admin = self.resolve_admin_account()
        if not admin:
            self._logger.warning(
                "self_heal trigger skipped: admin account 未配置"
            )
            return
        snapshot = list(self._buffer)
        if not snapshot:
            return
        first = snapshot[0].get("time", "")
        last = snapshot[-1].get("time", "")
        heal = HealTask(
            task_id=f"heal_{uuid4().hex[:12]}",
            admin_account=admin,
            trigger_reason=reason,
            error_snapshot=snapshot,
            first_error_time=first,
            last_error_time=last,
        )
        self._current_heal = heal
        self._last_trigger_monotonic = monotonic_seconds()
        self._buffer.clear()
        await self._publish_start_notification(heal)

        bg_task = asyncio.create_task(self._run_heal(heal))
        bg_task.add_done_callback(lambda _: None)
        self._running_task = bg_task

    async def _publish_start_notification(self, heal: HealTask) -> None:
        """Send the «已开始工作» notification to the admin private chat."""
        if self._notification_hub is None:
            self._logger.warning(
                "self_heal start notification skipped: notification hub 未配置",
                task_id=heal.task_id,
            )
            return
        samples = self._build_sample_summary(heal.error_snapshot, max_count=3)
        content = (
            "<这是新的必须要回答的内容>\n"
            "系统已检测到 Bot 出现持续异常，自修复 Agent 已开始工作。\n"
            f"触发原因：{heal.trigger_reason}\n"
            f"最近累积异常数：{len(heal.error_snapshot)}\n"
            f"样本异常：\n{samples}\n"
            f"样本异常时间范围：{heal.first_error_time} 至 {heal.last_error_time}\n"
            "请稍候。诊断完成后再发送最终报告。如需立即介入，请回复相应指令。\n"
            "</这是新的必须要回答的内容>"
        )
        try:
            await self._notification_hub.publish(
                source=START_SOURCE,
                kind="private",
                conversation_id=str(heal.admin_account),
                content=content,
                manager_name="self_heal",
                reasons=["self-heal start"],
                metadata={
                    "task_id": heal.task_id,
                    "trigger_reason": heal.trigger_reason,
                    "error_count": len(heal.error_snapshot),
                },
            )
        except Exception as exc:
            self._logger.warning(
                "self_heal start notification publish failed",
                task_id=heal.task_id,
                error=str(exc),
            )

    @staticmethod
    def _build_sample_summary(errors: list[dict[str, Any]], *, max_count: int) -> str:
        lines: list[str] = []
        for e in errors[:max_count]:
            module = str(e.get("module", "")).strip() or "?"
            msg = str(e.get("message", "")).strip().splitlines()
            msg_first = msg[0] if msg else ""
            if len(msg_first) > 200:
                msg_first = msg_first[:200] + "…"
            level = str(e.get("level", "")).strip() or "ERROR"
            lines.append(f"- [{level}] {module}: {msg_first}")
        return "\n".join(lines) if lines else "(无样本)"

    async def _run_heal(self, heal: HealTask) -> None:
        """Run the self-heal agent invocation in the background."""
        if self._agent is None:
            heal.status = "failed"
            return
        token = None
        token_m = None
        try:
            token = _HEAL_TASK.set(heal)
            token_m = CURRENT_USAGE_MODULE.set("agent:self_heal")
            state: State = {
                "messages": [
                    {
                        "role": "user",
                        "content": self._build_initial_prompt(heal),
                    }
                ],
            }
            result_state = await asyncio.wait_for(
                self._agent._invoke_direct(state),
                timeout=self._config.timeout_seconds,
            )

            # If the agent didn't call submit_resolution, follow-up like
            # problem_solver does.
            if heal.status == "healing":
                self._logger.info(
                    "self_heal agent 未调用 submit_resolution，重新唤起提交结论",
                    task_id=heal.task_id,
                )
                messages = result_state.get("messages", [])
                messages.append({
                    "role": "user",
                    "content": (
                        "你尚未调用 submit_resolution 提交诊断结论。请立即调用 "
                        "submit_resolution，给出 summary（必填）、repaired（bool，"
                        "默认 false）、debug_file（可选，已写报告的沙箱相对路径）、"
                        "root_cause（可选）。即使无法诊断也必须提交。"
                    ),
                })
                retry_state: State = {"messages": messages}
                retry_timeout = max(self._config.timeout_seconds * 0.5, 60)
                await asyncio.wait_for(
                    self._agent._invoke_direct(retry_state),
                    timeout=retry_timeout,
                )

            heal.status = heal.status if heal.status != "healing" else "completed"
            self._logger.info(
                "self_heal 任务完成",
                task_id=heal.task_id,
                status=heal.status,
                repaired=heal.repaired,
                has_debug_file=bool(heal.debug_file),
            )
            await self._publish_result_notification(heal)
        except asyncio.TimeoutError:
            heal.status = "timeout"
            heal.summary = heal.summary or "诊断超时"
            self._logger.warning("self_heal 任务超时", task_id=heal.task_id)
            await self._publish_result_notification(heal)
        except asyncio.CancelledError:
            heal.status = "failed"
            heal.summary = heal.summary or "任务被取消"
            raise
        except Exception as exc:
            heal.status = "failed"
            heal.summary = f"{type(exc).__name__}: {exc}"
            self._logger.warning(
                "self_heal 任务失败",
                task_id=heal.task_id,
                error=str(exc),
            )
            await self._publish_result_notification(heal)
        finally:
            if token is not None:
                _HEAL_TASK.reset(token)
            if token_m is not None:
                CURRENT_USAGE_MODULE.reset(token_m)
            if self._current_heal is heal:
                self._current_heal = None
            if self._running_task is not None and self._running_task.done():
                if self._running_task is asyncio.current_task():
                    self._running_task = None

    async def _publish_result_notification(self, heal: HealTask) -> None:
        if heal.notified_final:
            return
        heal.notified_final = True
        if self._notification_hub is None:
            self._logger.warning(
                "self_heal result notification skipped: hub 未配置",
                task_id=heal.task_id,
            )
            return

        summary = (heal.summary or "").strip() or "（agent 未提供摘要）"
        root_cause = (heal.root_cause or "").strip()
        debug_file = heal.debug_file
        repaired = "已自行修复" if heal.repaired else "未能自行修复"

        lines = [
            "<这是新的必须要回答的内容>",
            "系统自修复 Agent 已运行完毕。",
            f"触发原因：{heal.trigger_reason}",
            f"诊断摘要：{summary}",
        ]
        if root_cause:
            lines.append(f"根因：{root_cause}")
        lines.append(f"是否已自行修复：{repaired}")
        lines.append(f"调试报告：{debug_file or '未生成'}")
        if debug_file:
            lines.append(
                "请使用 file_storage / sandbox_manager 工具读取该文件并向管理员发送，"
                "使用 image_send__send 或 send_chat_file 发送。"
            )
        lines.append("</这是新的必须要回答的内容>")
        content = "\n".join(lines)

        try:
            await self._notification_hub.publish(
                source=RESULT_SOURCE,
                kind="private",
                conversation_id=str(heal.admin_account),
                content=content,
                manager_name="self_heal",
                reasons=["self-heal result"],
                metadata={
                    "task_id": heal.task_id,
                    "status": heal.status,
                    "repaired": heal.repaired,
                    "debug_file": debug_file,
                },
            )
        except Exception as exc:
            self._logger.warning(
                "self_heal result notification publish failed",
                task_id=heal.task_id,
                error=str(exc),
            )

    def _build_initial_prompt(self, heal: HealTask) -> str:
        return (
            "你被系统以自修复 Agent 身份唤醒，因为 Bot 在最近一段时间累积了一组异常。\n\n"
            "请按以下流程工作：\n"
            "1. 调用 read_errors 读取本次触发捕获的异常快照（含 traceback）。\n"
            "2. 必要时调用 read_log_tail 读取完整日志，或 read_source_code / "
            "search_source_code 定位异常代码位置。可用 search_web 查询依赖文档、"
            "已知 issue 或相似异常的解决方法。\n"
            "3. 谨慎使用安全修复工具（如 clear_drawing_cooldown / "
            "trigger_image_cleanup）。仅在确认根因、评估风险后调用。\n"
            "4. 调用 write_debug_report 将完整诊断报告写入沙箱 debug 目录，"
            "记录异常栈、根因分析、已尝试的修复动作与后续建议。返回的沙箱相对路径"
            "需要传给 submit_resolution 的 debug_file 参数。\n"
            "5. 调用 submit_resolution 提交诊断结论（summary 必填、repaired 必填、"
            "debug_file、root_cause 可选）。\n\n"
            "规则：\n"
            "- 不要直接修改源代码（你没有写源码的工具），仅做安全修复钩子可完成的事。\n"
            "- 通知会自动通过系统向管理员私聊推送，无需你写'TO:'等收件人字段。\n"
            "- 不要在聊天消息里夹杂内部技术字段（如 task_id）。\n"
            f"- 当前任务 ID: {heal.task_id}\n"
            f"- 触发原因: {heal.trigger_reason}\n"
            f"- 累积异常数: {len(heal.error_snapshot)}\n"
        )

    async def shutdown(self) -> None:
        if self._running_task is not None and not self._running_task.done():
            self._running_task.cancel()
            try:
                await self._running_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        self._running_task = None
        self._current_heal = None
        self._buffer.clear()


# ── Tool executor ───────────────────────────────────────────────────────────


_FORBIDDEN_SOURCE_BASENAMES = {
    "config.toml",
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
}
_FORBIDDEN_SOURCE_SUFFIXES = {".key", ".pem", ".crt", ".p12", ".keystore"}


def _is_within_any_root(path: Path, roots: list[Path]) -> Path | None:
    """Return the matching root if `path` lives under one of `roots`, else None."""
    try:
        resolved = path.resolve()
    except OSError:
        return None
    for root in roots:
        try:
            root_resolved = root.resolve()
        except OSError:
            continue
        try:
            resolved.relative_to(root_resolved)
            return root_resolved
        except ValueError:
            continue
    return None


class SelfHealToolExecutor(ToolExecutor):
    """Tools available to the self-heal Agent.

    Read tools:
      - read_errors          : errors snapshot captured by the sink
      - read_log_tail        : tail of neobot.log
      - read_source_code     : read bot source files (whitelisted)
      - search_source_code   : regex search across app/packages
      - list_files / read_file / write_debug_report / list_debug_reports /
        read_debug_report : sandbox file I/O (debug reports live in sandbox)
      - run_python / parse_image : diagnosis helpers

    Repair hooks (safe subset):
      - clear_drawing_cooldown
      - trigger_image_cleanup

    Web:
      - search_web            : WebSearchExecutor (research mode)
      - read_search_result    : read indexed page
      - search_status         : web search session status

    Final:
      - submit_resolution      : commits the diagnosis (mirrors submit_solution)
    """

    REQUEST_SOURCE_DIRS = ["app", "packages"]
    SOURCE_FILE_SUFFIXES = {".py", ".ini", ".toml", ".cfg", ".md", ".rst", ".txt"}
    MAX_SOURCE_FILE_BYTES = 100 * 1024
    MAX_LOG_TAIL_LINES = 2000
    DEFAULT_LOG_TAIL_LINES = 200
    SEARCH_MAX_FILES = 200
    SEARCH_MAX_MATCHES_PER_FILE = 5
    SEARCH_MAX_MATCHES_TOTAL = 30
    SEARCH_CONTEXT_LINES = 3

    def __init__(
        self,
        *,
        logger: Logger | None = None,
        sandbox_service: Any = None,
        source_roots: list[Path] | None = None,
        log_file: Path | None = None,
        sandbox_debug_dir: str = "debug/self_heal",
        repair_hooks: dict[str, Any] | None = None,
        web_search_config: dict | None = None,
        vision_provider: Any = None,
    ) -> None:
        self._logger = logger or NullLogger()
        self._sandbox = sandbox_service
        self._source_roots = source_roots or []
        self._log_file = log_file
        self._sandbox_debug_dir = (str(sandbox_debug_dir).strip().lstrip("/")
                                   or "debug/self_heal")
        self._repair_hooks = repair_hooks or {}
        self._vision_provider = vision_provider
        ws = web_search_config or {}
        self._search = WebSearchExecutor(
            engines=ws.get("engines"),
            max_rounds=ws.get("max_rounds", 5),
            preview_pages_limit=ws.get("preview_pages_limit", 30),
            variant_result_limit=ws.get("variant_result_limit", 6),
        )

    def reset_search(self) -> None:
        self._search.reset()

    def definitions(self) -> list[ToolDefinition]:
        tools = [
            _tool_def(
                "read_errors",
                "读取触发本次自修复任务的异常快照。返回 JSON 数组，"
                "每条含 time/level/module/file/line/function/message/traceback。",
                {"properties": {}, "required": []},
            ),
            _tool_def(
                "read_log_tail",
                "读取 neobot.log 文件尾部 N 行，用于了解异常前后的完整上下文。",
                {
                    "properties": {
                        "lines": {
                            "type": "integer",
                            "description": (
                                f"读取尾部行数，默认 {self.DEFAULT_LOG_TAIL_LINES}，"
                                f"上限 {self.MAX_LOG_TAIL_LINES}"
                            ),
                        }
                    },
                    "required": [],
                },
            ),
            _tool_def(
                "read_source_code",
                "读取 Bot 自身源码文件（项目 app/、packages/ 子树）。"
                "敏感文件（.env、config.toml、密钥等）禁止读取。",
                {
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": (
                                "相对项目根的路径，如 "
                                "app/src/neobot_app/drawing/manager.py"
                            ),
                        }
                    },
                    "required": ["path"],
                },
            ),
            _tool_def(
                "search_source_code",
                "在 app/ 与 packages/ 源码树中按正则搜索。"
                "返回匹配行 + 上下文 + 文件路径。",
                {
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "Python 正则表达式",
                        },
                        "path_glob": {
                            "type": "string",
                            "description": (
                                "可选路径 glob，默认 app/**/*.py 与 packages/**/*.py"
                            ),
                        },
                    },
                    "required": ["pattern"],
                },
            ),
            _tool_def(
                "write_debug_report",
                "将诊断报告写入沙箱 debug 目录（Markdown）。"
                "返回沙箱相对路径，请将其传给 submit_resolution 的 debug_file。",
                {
                    "properties": {
                        "file_name": {
                            "type": "string",
                            "description": (
                                "文件名（不含目录），如 '2026-07-12_db_lock.md'。"
                                "若未提供则自动用时间戳生成。"
                            ),
                        },
                        "content_base64": {
                            "type": "string",
                            "description": (
                                "Markdown 报告的 UTF-8 文本的 base64 编码"
                            ),
                        },
                    },
                    "required": ["content_base64"],
                },
            ),
            _tool_def(
                "list_debug_reports",
                "列出沙箱 debug 目录下已有的诊断报告。",
                {"properties": {}, "required": []},
            ),
            _tool_def(
                "read_debug_report",
                "读取沙箱 debug 目录下已有的诊断报告，返回 base64。",
                {
                    "properties": {
                        "file_name": {"type": "string", "description": "文件名"},
                    },
                    "required": ["file_name"],
                },
            ),
            _tool_def(
                "search_web",
                "联网搜索（用于查询异常信息、依赖文档、已知 issue、相似报错）。"
                "支持 mode 进行多角度研究搜索：encyclopedia / community / news / "
                "official / video / academic。不填 mode 仅做普通关键词搜索。",
                {
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词"},
                        "num_results": {
                            "type": "integer",
                            "description": "返回结果数，默认 10",
                        },
                        "mode": {
                            "type": "string",
                            "description": (
                                "研究模式：encyclopedia/community/news/official/video/academic"
                            ),
                        },
                    },
                    "required": ["query"],
                },
            ),
            _tool_def(
                "read_search_result",
                "读取指定编号的网页搜索结果页面完整内容。",
                {
                    "properties": {
                        "indices": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "结果编号列表，如 [0, 1, 3]",
                        }
                    },
                    "required": ["indices"],
                },
            ),
            _tool_def(
                "search_status",
                "查看当前搜索会话状态。",
                {"properties": {}, "required": []},
            ),
            _tool_def(
                "submit_resolution",
                "提交诊断/修复结论，结束本次自修复任务。"
                "调用后任务标记为完成，系统自动向管理员私聊推送最终通知（包含 debug_file 路径）。",
                {
                    "properties": {
                        "summary": {
                            "type": "string",
                            "description": "诊断摘要（必填）。一两句话说明发生了什么。",
                        },
                        "repaired": {
                            "type": "boolean",
                            "description": "是否已自行修复（必填，默认 false）",
                        },
                        "root_cause": {
                            "type": "string",
                            "description": "可选根因说明",
                        },
                        "debug_file": {
                            "type": "string",
                            "description": "write_debug_report 返回的沙箱相对路径",
                        },
                    },
                    "required": ["summary"],
                },
            ),
        ]
        if self._sandbox is not None:
            tools.extend([
                _tool_def(
                    "list_files",
                    "列出沙箱目录内容。",
                    {
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "目录相对路径，默认沙箱根",
                            }
                        },
                        "required": [],
                    },
                ),
                _tool_def(
                    "read_file",
                    "读取沙箱文件内容（支持文本/二进制检测），返回文本或 base64。",
                    {
                        "properties": {
                            "path": {"type": "string", "description": "沙箱相对路径"},
                        },
                        "required": ["path"],
                    },
                ),
                _tool_def(
                    "run_python",
                    "在 Bot 的 Python 虚拟环境执行诊断代码。"
                    "代码 print() 输出会被捕获。仅用于诊断（如查询数据库、检查文件状态）。",
                    {
                        "properties": {
                            "code": {"type": "string", "description": "Python 代码"},
                            "timeout": {
                                "type": "integer",
                                "description": "超时秒数（默认 30，最大 60）",
                            },
                        },
                        "required": ["code"],
                    },
                ),
                _tool_def(
                    "parse_image",
                    "解析沙箱中图片文件内容（如图表截图、报错截图）。",
                    {
                        "properties": {
                            "image_path": {"type": "string"},
                            "requirement": {
                                "type": "string",
                                "description": "分析要求",
                            },
                        },
                        "required": ["image_path"],
                    },
                ),
            ])
        # Repair hooks are optional; include only when wired in
        if "clear_drawing_cooldown" in self._repair_hooks:
            tools.append(_tool_def(
                "clear_drawing_cooldown",
                "清除指定聊天流的绘图冷却（用于诊断后修复卡死的绘图管线）。",
                {
                    "properties": {
                        "pipeline_key": {
                            "type": "string",
                            "description": "形如 'group:123456' 或 'private:654321'",
                        }
                    },
                    "required": ["pipeline_key"],
                },
            ))
        if "trigger_image_cleanup" in self._repair_hooks:
            tools.append(_tool_def(
                "trigger_image_cleanup",
                "触发图库失效记录与磁盘文件清理（用于诊断后修复磁盘/数据库记录不一致）。",
                {"properties": {}, "required": []},
            ))
        return tools

    async def execute(self, name: str, args: dict) -> str:
        if name == "read_errors":
            return await self._execute_read_errors(args)
        if name == "read_log_tail":
            return await self._execute_read_log_tail(args)
        if name == "read_source_code":
            return await self._execute_read_source_code(args)
        if name == "search_source_code":
            return await self._execute_search_source_code(args)
        if name == "write_debug_report":
            return await self._execute_write_debug_report(args)
        if name == "list_debug_reports":
            return await self._execute_list_debug_reports(args)
        if name == "read_debug_report":
            return await self._execute_read_debug_report(args)
        if name == "search_web":
            return await self._search.execute("search", args)
        if name == "read_search_result":
            return await self._search.execute("read", args)
        if name == "search_status":
            return await self._search.execute("status", args)
        if name == "list_files":
            return await self._execute_list_files(args)
        if name == "read_file":
            return await self._execute_read_file(args)
        if name == "run_python":
            return await self._execute_run_python(args)
        if name == "parse_image":
            return await self._execute_parse_image(args)
        if name == "clear_drawing_cooldown":
            return await self._execute_repair_hook("clear_drawing_cooldown", args)
        if name == "trigger_image_cleanup":
            return await self._execute_repair_hook("trigger_image_cleanup", args)
        if name == "submit_resolution":
            return await self._execute_submit_resolution(args)
        return f"未知工具: {name}"

    # ── error snapshot ──

    async def _execute_read_errors(self, args: dict) -> str:
        task = _HEAL_TASK.get(None)
        if task is None:
            return _json({"ok": False, "error": "无活跃自修复任务上下文"})
        return _json({
            "ok": True,
            "task_id": task.task_id,
            "trigger_reason": task.trigger_reason,
            "first_error_time": task.first_error_time,
            "last_error_time": task.last_error_time,
            "error_count": len(task.error_snapshot),
            "errors": task.error_snapshot,
        })

    # ── log tail ──

    async def _execute_read_log_tail(self, args: dict) -> str:
        log_path = self._log_file
        if log_path is None or not log_path.exists():
            return _json({"ok": False, "error": "未配置或不存在日志文件"})
        try:
            lines = int(args.get("lines", self.DEFAULT_LOG_TAIL_LINES))
        except (TypeError, ValueError):
            lines = self.DEFAULT_LOG_TAIL_LINES
        lines = max(1, min(lines, self.MAX_LOG_TAIL_LINES))
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
        except OSError as exc:
            return _json({"ok": False, "error": f"读取日志失败: {exc}"})
        tail = all_lines[-lines:]
        text = "".join(tail)
        return _json({"ok": True, "lines_returned": len(tail), "log": text})

    # ── source code ──

    def _resolve_source_path(self, rel_path: str) -> Path | None:
        rel = (rel_path or "").strip().lstrip("/")
        if not rel or ".." in Path(rel).parts:
            return None
        # Reject forbidden filenames and suffixes
        candidate_name = Path(rel).name
        if candidate_name in _FORBIDDEN_SOURCE_BASENAMES:
            return None
        if Path(rel).suffix.lower() in _FORBIDDEN_SOURCE_SUFFIXES:
            return None
        if "__pycache__" in Path(rel).parts:
            return None
        # Try resolving under each root
        for root in self._source_roots:
            candidate = (root / rel).resolve()
            matched = _is_within_any_root(candidate, self._source_roots)
            if matched is None:
                continue
            # Ensure candidate still matches the chosen root prefix
            try:
                candidate.relative_to(matched)
            except ValueError:
                continue
            if candidate.is_file():
                return candidate
        return None

    async def _execute_read_source_code(self, args: dict) -> str:
        rel = str(args.get("path", "")).strip()
        if not rel:
            return _json({"ok": False, "error": "缺少 path"})
        path = self._resolve_source_path(rel)
        if path is None:
            return _json({
                "ok": False,
                "error": (
                    "路径不在白名单子树（仅允许 app/、packages/ 下的源码）或"
                    "为敏感文件（.env / config.toml / __pycache__ / 密钥等）"
                ),
            })
        try:
            size = path.stat().st_size
        except OSError as exc:
            return _json({"ok": False, "error": f"获取文件信息失败: {exc}"})
        try:
            data = path.read_bytes()
        except OSError as exc:
            return _json({"ok": False, "error": f"读取失败: {exc}"})
        if size > self.MAX_SOURCE_FILE_BYTES:
            truncated = data[-self.MAX_SOURCE_FILE_BYTES:]
            try:
                text = truncated.decode("utf-8")
            except UnicodeDecodeError:
                return _json({
                    "ok": False,
                    "error": (
                        f"文件超过 {self.MAX_SOURCE_FILE_BYTES} 字节且尾部无法以 UTF-8 解码"
                    ),
                })
            return _json({
                "ok": True,
                "path": str(path),
                "size": size,
                "truncated": True,
                "truncated_to_tail_bytes": self.MAX_SOURCE_FILE_BYTES,
                "content": text,
                "note": f"文件较大，仅返回尾部 {self.MAX_SOURCE_FILE_BYTES} 字节",
            })
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return _json({
                "ok": False,
                "error": "文件无法以 UTF-8 解码（可能为二进制）",
            })
        return _json({"ok": True, "path": str(path), "size": size, "content": text})

    async def _execute_search_source_code(self, args: dict) -> str:
        pattern = str(args.get("pattern", "")).strip()
        if not pattern:
            return _json({"ok": False, "error": "缺少 pattern"})
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return _json({"ok": False, "error": f"正则编译失败: {exc}"})
        import glob as glob_module
        path_glob = str(args.get("path_glob", "")).strip()
        if not path_glob:
            # source_roots are already e.g. <project>/app and <project>/packages
            globs = [str(root / "**" / "*.py") for root in self._source_roots]
        else:
            globs = [path_glob]
        seen_files = 0
        total_matches = 0
        results: list[dict[str, Any]] = []
        for g in globs:
            for fp in glob_module.iglob(g, recursive=True):
                if seen_files >= self.SEARCH_MAX_FILES:
                    break
                p = Path(fp)
                if not p.is_file():
                    continue
                if "__pycache__" in p.parts:
                    continue
                if p.name in _FORBIDDEN_SOURCE_BASENAMES:
                    continue
                if p.suffix.lower() in _FORBIDDEN_SOURCE_SUFFIXES:
                    continue
                seen_files += 1
                try:
                    text = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                lines = text.splitlines()
                file_matches = 0
                for idx, line in enumerate(lines):
                    if not regex.search(line):
                        continue
                    if file_matches >= self.SEARCH_MAX_MATCHES_PER_FILE:
                        break
                    start = max(0, idx - self.SEARCH_CONTEXT_LINES)
                    end = min(len(lines), idx + self.SEARCH_CONTEXT_LINES + 1)
                    results.append({
                        "path": str(p),
                        "line": idx + 1,
                        "context": "\n".join(
                            f"{(start + i + 1):>5}{'>' if (start + i) == idx else ' '} {lines[start + i]}"
                            for i in range(end - start)
                        ),
                    })
                    file_matches += 1
                    total_matches += 1
                    if total_matches >= self.SEARCH_MAX_MATCHES_TOTAL:
                        return _json({
                            "ok": True,
                            "files_scanned": seen_files,
                            "match_count": total_matches,
                            "truncated": True,
                            "matches": results,
                            "note": f"已达匹配上限 {self.SEARCH_MAX_MATCHES_TOTAL}",
                        })
        return _json({
            "ok": True,
            "files_scanned": seen_files,
            "match_count": total_matches,
            "matches": results,
        })

    # ── sandbox debug report I/O ──

    def _debug_report_dir(self) -> Path | None:
        if self._sandbox is None:
            return None
        return self._sandbox.resolve_path(self._sandbox_debug_dir)

    async def _execute_write_debug_report(self, args: dict) -> str:
        if self._sandbox is None:
            return _json({"ok": False, "error": "sandbox 未配置"})
        content_b64 = str(args.get("content_base64", "")).strip()
        if not content_b64:
            return _json({"ok": False, "error": "缺少 content_base64"})
        try:
            data = base64.b64decode(content_b64)
        except Exception as exc:
            return _json({"ok": False, "error": f"base64 解码失败: {exc}"})
        rel_dir = self._sandbox_debug_dir
        # Ensure dir exists under sandbox
        dir_path = self._sandbox.resolve_path(rel_dir)
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return _json({"ok": False, "error": f"创建 debug 目录失败: {exc}"})

        file_name = str(args.get("file_name", "")).strip()
        safe_suffix = ".md"
        if not file_name:
            from neobot_app.time_context import get_current_time_and_lunar_date
            ts = get_current_time_and_lunar_date().replace(" ", "_").replace(":", "").replace("/", "")
            # ts may include lunar info; use a simple timestamp instead
            import datetime as _dt
            ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"report_{ts}{safe_suffix}"
        else:
            # Sanitize
            cleaned = Path(file_name).name
            if not cleaned:
                file_name = f"report_{uuid4().hex[:8]}{safe_suffix}"
            else:
                file_name = cleaned
        rel_path = f"{rel_dir}/{file_name}"
        path = self._sandbox.resolve_path(rel_path)
        try:
            await self._sandbox.write_file(path, data)
        except Exception as exc:
            return _json({"ok": False, "error": f"写入报告失败: {exc}"})
        return _json({"ok": True, "debug_file": rel_path, "absolute_path": str(path)})

    async def _execute_list_debug_reports(self, args: dict) -> str:
        if self._sandbox is None:
            return _json({"ok": False, "error": "sandbox 未配置"})
        try:
            dir_path = self._sandbox.resolve_path(self._sandbox_debug_dir)
            if not dir_path.exists():
                return _json({"ok": True, "files": []})
            files = await self._sandbox.list_files(dir_path)
            return _json({"ok": True, "dir": self._sandbox_debug_dir, "files": files})
        except Exception as exc:
            return _json({"ok": False, "error": str(exc)})

    async def _execute_read_debug_report(self, args: dict) -> str:
        if self._sandbox is None:
            return _json({"ok": False, "error": "sandbox 未配置"})
        file_name = str(args.get("file_name", "")).strip()
        if not file_name:
            return _json({"ok": False, "error": "缺少 file_name"})
        rel = f"{self._sandbox_debug_dir}/{Path(file_name).name}"
        try:
            path = self._sandbox.resolve_path(rel)
            data = await self._sandbox.read_file(path)
            try:
                text = data.decode("utf-8")
                return _json({"ok": True, "file": rel, "content": text})
            except UnicodeDecodeError:
                return _json({
                    "ok": True,
                    "file": rel,
                    "content_base64": base64.b64encode(data).decode("utf-8"),
                })
        except Exception as exc:
            return _json({"ok": False, "error": str(exc)})

    # ── sandbox generic ──

    async def _execute_list_files(self, args: dict) -> str:
        if self._sandbox is None:
            return _json({"ok": False, "error": "sandbox 未配置"})
        rel = str(args.get("path", "")).strip().lstrip("/") or "."
        try:
            path = self._sandbox.resolve_path(rel)
            files = await self._sandbox.list_files(path)
            return _json({"ok": True, "files": files})
        except Exception as e:
            return _json({"ok": False, "error": str(e)})

    async def _execute_read_file(self, args: dict) -> str:
        if self._sandbox is None:
            return _json({"ok": False, "error": "sandbox 未配置"})
        rel = str(args.get("path", "")).strip().lstrip("/")
        if not rel:
            return _json({"ok": False, "error": "缺少 path"})
        try:
            from neobot_app.runtime.sandbox_service import (
                MAX_BASE64_BYTES,
                MAX_TEXT_READ_BYTES,
                detect_file_type,
            )
            path = self._sandbox.resolve_read_path(rel)
            info = detect_file_type(path)
            ftype = info["type"]
            fmt = info.get("format")
            size = info["size"]
            if ftype == "error":
                return _json({"ok": False, "error": f"无法读取: {rel}"})
            if ftype == "empty":
                return _json({"ok": True, "content_base64": "", "size": 0})
            if ftype == "image":
                return _json({
                    "ok": True,
                    "type": "image",
                    "format": fmt,
                    "size": size,
                    "note": "图片文件，请使用 parse_image 工具读取内容",
                })
            if ftype == "binary":
                return _json({
                    "ok": True,
                    "type": "binary",
                    "format": fmt,
                    "size": size,
                    "note": "二进制文件，请通过 send_chat_file 发送或使用 parse_image",
                })
            data = await self._sandbox.read_file(path)
            try:
                text = data.decode("utf-8")
                if len(data) > MAX_TEXT_READ_BYTES:
                    return _json({
                        "ok": True,
                        "content": text[:MAX_TEXT_READ_BYTES],
                        "size": len(data),
                        "truncated": True,
                    })
                return _json({"ok": True, "content": text, "size": len(data)})
            except UnicodeDecodeError:
                preview_size = min(len(data), MAX_BASE64_BYTES)
                return _json({
                    "ok": True,
                    "type": "unknown_binary",
                    "content_base64": base64.b64encode(data[:preview_size]).decode(),
                    "size": len(data),
                    "truncated": len(data) > MAX_BASE64_BYTES,
                })
        except Exception as e:
            return _json({"ok": False, "error": str(e)})

    # ── run_python / parse_image ──

    def _get_sandbox_work_dir(self) -> Path | None:
        if self._sandbox is None:
            return None
        return self._sandbox.resolve_path(".")

    async def _execute_run_python(self, args: dict) -> str:
        code = str(args.get("code", "")).strip()
        if not code:
            return _json({"ok": False, "error": "code 不能为空"})
        timeout = min(int(args.get("timeout", 30)), 60)
        script_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", encoding="utf-8", delete=False
            ) as f:
                f.write(code)
                script_path = f.name
            cwd = str(self._get_sandbox_work_dir()) if self._sandbox else None
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: subprocess.run(
                        [sys.executable, script_path],
                        capture_output=True,
                        timeout=timeout,
                        cwd=cwd,
                    ),
                ),
                timeout=timeout + 5,
            )
            output = result.stdout.decode("utf-8", errors="replace").strip()
            error = result.stderr.decode("utf-8", errors="replace").strip()
            return _json({
                "ok": True,
                "stdout": output,
                "stderr": error or None,
                "returncode": result.returncode,
            })
        except subprocess.TimeoutExpired:
            return _json({"ok": False, "error": f"Python 执行超时（{timeout}秒）"})
        except Exception as e:
            return _json({"ok": False, "error": str(e)})
        finally:
            if script_path is not None:
                Path(script_path).unlink(missing_ok=True)

    async def _execute_parse_image(self, args: dict) -> str:
        if self._vision_provider is None:
            return _json({"ok": False, "error": "vision_provider 未配置"})
        from neobot_app.runtime.sandbox_service import detect_file_type
        image_path = str(args.get("image_path", "")).strip()
        if not image_path:
            return _json({"ok": False, "error": "缺少 image_path"})
        requirement = str(args.get("requirement") or "请简洁描述这张图片的主要内容。").strip()
        try:
            if self._sandbox is not None:
                path = self._sandbox.resolve_read_path(image_path)
            else:
                path = Path(image_path)
            info = detect_file_type(path)
            if info["type"] != "image":
                return _json({
                    "ok": False,
                    "error": f"文件不是图片（检测为 {info['type']}）",
                })
            data = path.read_bytes()
            content_parts = [
                {"type": "text", "text": requirement},
                {"type": "image", "source": {
                    "type": "base64",
                    "media_type": f"image/{info.get('format', 'PNG').lower()}"
                    if info.get("format") else "image/png",
                    "data": base64.b64encode(data).decode("utf-8"),
                }},
            ]
            result = await self._vision_provider.chat([
                {"role": "user", "content": content_parts}
            ])
            text = result.get("content", "") if isinstance(result, dict) else str(result)
            return _json({"ok": True, "description": text[:2000]})
        except Exception as e:
            return _json({"ok": False, "error": str(e)})

    # ── repair hooks ──

    async def _execute_repair_hook(self, hook_name: str, args: dict) -> str:
        hook = self._repair_hooks.get(hook_name)
        if hook is None:
            return _json({"ok": False, "error": f"修复钩子 {hook_name} 未配置"})
        try:
            result = hook(args)
            if asyncio.iscoroutine(result):
                result = await result
            if isinstance(result, dict):
                return _json(result)
            return _json({"ok": True, "result": str(result)})
        except Exception as exc:
            return _json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    # ── submit resolution ──

    async def _execute_submit_resolution(self, args: dict) -> str:
        summary = str(args.get("summary", "")).strip()
        if not summary:
            return "错误：summary 不能为空"
        task = _HEAL_TASK.get(None)
        if task is None:
            return "错误：无活跃自修复任务上下文"
        task.summary = summary
        task.root_cause = str(args.get("root_cause", "")).strip() or None
        task.debug_file = str(args.get("debug_file", "")).strip() or None
        repaired_raw = args.get("repaired", False)
        try:
            task.repaired = bool(repaired_raw)
        except Exception:
            task.repaired = False
        task.status = "completed"
        return (
            "已记录诊断结论。系统将自动通过通知系统向管理员私聊推送最终通知。"
        )


# ── Agent ───────────────────────────────────────────────────────────────────


def _build_system_prompt(
    config: SelfHealAgentConfig, *, peer_descriptions: str = ""
) -> str:
    return (
        "你是系统的自修复 Agent。当 Bot 在运行期间累积了持续异常时，系统会自动唤起你。\n\n"
        "你的职责：\n"
        "1. 诊断异常根因（使用 read_errors + read_log_tail + read_source_code / "
        "search_source_code + search_web）。\n"
        "2. 在确认根因且评估风险后，调用安全修复工具（clear_drawing_cooldown / "
        "trigger_image_cleanup）。没有适合工具时不要强行修改，仅做诊断。\n"
        "3. 调用 write_debug_report 将完整诊断报告写入沙箱 debug 目录。\n"
        "4. 调用 submit_resolution 提交结论，系统会自动通过通知系统向管理员私聊"
        "推送最终通知。\n\n"
        "重要规则：\n"
        "- 你无法修改 Bot 自身源码，仅有少量安全修复钩子。请现实地评估能做什么。\n"
        "- 修复失败也要明确通过 submit_resolution 的 repaired=false 告知。\n"
        "- 不要在报告里夹带多余的 task_id 之类的内部字段——这些由系统自动填充。\n"
        "- 不需要负责把消息发送给管理员；系统会自动通过通知系统完成。\n"
        "- 完成诊断后请用简洁的中文摘要提交。\n"
        f"- 诊断超时时间：{config.timeout_seconds} 秒\n"
        f"{peer_descriptions}\n"
    )


class SelfHealAgent:
    """LLM-backed self-heal agent. Mirrors ProblemSolverAgent structure."""

    def __init__(
        self,
        provider: Provider,
        *,
        config: SelfHealAgentConfig | None = None,
        logger: Logger | None = None,
        manager: SelfHealManager | None = None,
        sandbox_service: Any = None,
        data_dir: Path | None = None,
        source_roots: list[Path] | None = None,
        log_file: Path | None = None,
        repair_hooks: dict[str, Any] | None = None,
        web_search_config: dict | None = None,
        vision_provider: Any = None,
        peer_descriptions: str = "",
    ) -> None:
        cfg = config or SelfHealAgentConfig()
        self.description = EXPOSED_TO_MAIN_AGENT_DESCRIPTION
        self._manager = manager
        executor = SelfHealToolExecutor(
            logger=logger,
            sandbox_service=sandbox_service,
            source_roots=source_roots,
            log_file=log_file,
            sandbox_debug_dir=cfg.sandbox_debug_dir,
            repair_hooks=repair_hooks or {},
            web_search_config=web_search_config,
            vision_provider=vision_provider,
        )
        self._toolset = Toolset(
            executor=executor,
            specs=[
                ToolSpec(definition=d, access_resolver=_default_resolver)
                for d in executor.definitions()
            ],
            policy=ToolAccessPolicy(),
        )
        self.tool_definitions = self._toolset.definitions()

        async def _record_usage(model_name, input_tokens, output_tokens):
            await get_usage_tracker().record(
                module=CURRENT_USAGE_MODULE.get(""),
                model_name=model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                conversation_kind=CURRENT_CONVERSATION_KIND.get(""),
                conversation_id=CURRENT_CONVERSATION_ID.get(""),
            )

        self._agent = Agent(
            provider,
            toolset=self._toolset,
            description=self.description,
            system_prompt=_build_system_prompt(cfg, peer_descriptions=peer_descriptions),
            on_model_usage=_record_usage,
            max_iterations=30,
            command_timeout=int(cfg.timeout_seconds),
            logger=logger or NullLogger(),
        )

    def _build_toolset(self, executor: SelfHealToolExecutor) -> Toolset:
        specs = [
            ToolSpec(definition=d, access_resolver=_default_resolver)
            for d in executor.definitions()
        ]
        return Toolset(executor=executor, specs=specs, policy=ToolAccessPolicy())

    async def _invoke_direct(self, state: State) -> State:
        """Direct invocation (called by SelfHealManager from a background task)."""
        self._toolset.executor.reset_search()
        token_m = CURRENT_USAGE_MODULE.set("agent:self_heal")
        try:
            return await self._agent.invoke(state)
        finally:
            CURRENT_USAGE_MODULE.reset(token_m)

    async def stream_invoke(self, state: State):
        token_m = CURRENT_USAGE_MODULE.set("agent:self_heal")
        try:
            async for chunk in self._agent.stream_invoke(state):
                yield chunk
        finally:
            CURRENT_USAGE_MODULE.reset(token_m)

    async def close(self) -> None:
        try:
            await self._agent.close()
        except Exception:
            pass


# ── Builder ─────────────────────────────────────────────────────────────────


def build_self_heal_agent(
    provider: Provider,
    *,
    config: SelfHealAgentConfig | Any = None,
    logger: Logger | None = None,
    manager: SelfHealManager | None = None,
    sandbox_service: Any = None,
    data_dir: Path | None = None,
    source_roots: list[Path] | None = None,
    log_file: Path | None = None,
    repair_hooks: dict[str, Any] | None = None,
    web_search_config: dict | None = None,
    vision_provider: Any = None,
    peer_descriptions: str = "",
) -> SelfHealAgent:
    cfg = (
        config if isinstance(config, SelfHealAgentConfig)
        else SelfHealAgentConfig.from_schema(config)
    )
    provider.max_tokens = cfg.max_tokens
    agent = SelfHealAgent(
        provider=provider,
        config=cfg,
        logger=logger,
        manager=manager,
        sandbox_service=sandbox_service,
        data_dir=data_dir,
        source_roots=source_roots,
        log_file=log_file,
        repair_hooks=repair_hooks or {},
        web_search_config=web_search_config,
        vision_provider=vision_provider,
        peer_descriptions=peer_descriptions,
    )
    if manager is not None:
        manager.set_agent(agent)
    return agent