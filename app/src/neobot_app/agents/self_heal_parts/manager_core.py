"""任务状态、错误聚合与派发节流。"""

from __future__ import annotations

import asyncio
from collections import deque
from pathlib import Path
from typing import Any
from uuid import uuid4

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.time_context import monotonic_seconds, today_local

from .models import (
    HealTask,
    LOGGER_PREFIX,
    SelfHealAgentConfig,
    _json,
)


class SelfHealManagerCoreMixin:
    """任务状态、错误聚合与派发节流。"""

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
        self._fallback_admin = (
            fallback_admin_account.strip() if fallback_admin_account else ""
        )
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
        self._trigger_date_today: str = ""
        self._trigger_count_today: int = 0
        self._closed = False
        self._dispatch_skip: tuple[str, str] | None = None

    # ── wiring ──

    # ── 提示词规范化：实现 agent_prompt_parts() 即被分析页自动收集 ──

    agent_name = "自修复 Agent"
    agent_note = "系统提示词 + 该 Agent 自带工具；peer 描述在运行时按需装配"

    def agent_prompt_parts(self) -> list[tuple[str, str, str]]:
        from neobot_app.agents.self_heal import _build_system_prompt
        from neobot_app.analysis.prompt_analysis import tools_to_text

        prompt = _build_system_prompt(
            self._config, prompt_store=getattr(self, "_prompt_store", None)
        )
        parts = [("系统提示词", "system", prompt)]
        agent = getattr(self, "_agent", None)
        definitions = list(getattr(agent, "tool_definitions", []) or []) if agent else []
        if definitions:
            parts.append(
                (f"工具定义（{len(definitions)} 个）", "tools", tools_to_text(definitions))
            )
        return parts

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
        return not self._closed and self._config.enabled and self._agent is not None

    def resolve_admin_account(self) -> str:
        if self._config.admin_account:
            return self._config.admin_account
        return self._fallback_admin

    # ── error ingestion ──

    async def record(self, error_payload: dict[str, Any]) -> None:
        """把一条错误追加进环形缓冲区并评估节流条件。

        可在主事件循环中的任意协程内安全调用（loguru sink 应通过
        call_soon_threadsafe 转交到事件循环）。
        """
        if self._closed or not self._config.enabled:
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
            self._logger.debug("自修复触发条件评估失败", error=str(exc))

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
        if (
            self._traceback_count() < self._config.traceback_threshold
            and self._rate_count() < self._config.rate_threshold
        ):
            return  # not enough signal yet

        reason_parts = []
        if self._traceback_count() >= self._config.traceback_threshold:
            reason_parts.append(f"{self._traceback_count()} 个未处理异常累积")
        if self._rate_count() >= self._config.rate_threshold:
            reason_parts.append(
                f"{self._rate_count()} 秒内错误速率达 {self._config.rate_threshold}/"
                f"{self._config.rate_window_seconds}s"
            )
        reason = "；".join(reason_parts) or "累积异常"
        await self._dispatch(reason=reason)

    def _daily_trigger_count(self) -> int:
        today = str(today_local())
        if self._trigger_date_today != today:
            self._trigger_date_today = today
            self._trigger_count_today = 0
        return self._trigger_count_today

    async def trigger_now(self, *, reason: str = "manual") -> str:
        """手动触发入口。跳过节流，但仍会检查是否有任务正在运行。

        返回 JSON 状态字符串。
        """
        if self._closed:
            return _json({"ok": False, "error": "self_heal closed"})
        if not self._config.enabled:
            return _json({"ok": False, "error": "self_heal disabled"})
        if self._agent is None:
            return _json({"ok": False, "error": "self_heal agent 未配置"})
        if self._running_task is not None and not self._running_task.done():
            return _json(
                {
                    "ok": True,
                    "status": "busy",
                    "task_id": self._current_heal.task_id
                    if self._current_heal
                    else None,
                }
            )
        started = await self._dispatch(reason=reason)
        if started and self._current_heal is not None:
            return _json(
                {
                    "ok": True,
                    "status": "started",
                    "task_id": self._current_heal.task_id,
                }
            )
        return _json(
            {
                "ok": False,
                "error": "触发被拒绝（已有任务在运行、已达每日上限或缺少配置）",
            }
        )

    async def _dispatch(self, *, reason: str) -> bool:
        """当没有任务在运行且今日预算允许时，启动一个修复任务。

        启动成功返回 True，否则返回 False。
        """
        if self._closed:
            return False
        if self._running_task is not None and not self._running_task.done():
            self._logger.debug(
                "self_heal dispatch skipped: 已有任务运行中",
                reason=reason,
            )
            return False
        if self._daily_trigger_count() >= self._config.daily_limit:
            self._record_dispatch_skip("daily_limit", str(today_local()))
            return False
        admin = self.resolve_admin_account()
        if not admin:
            self._record_dispatch_skip("admin_missing")
            return False
        snapshot = list(self._buffer)
        if not snapshot:
            return False
        self._dispatch_skip = None
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
        self._trigger_count_today += 1
        self._current_heal = heal
        self._last_trigger_monotonic = monotonic_seconds()
        self._buffer.clear()

        bg_task = asyncio.create_task(self._run_heal(heal))
        bg_task.add_done_callback(lambda _: None)
        self._running_task = bg_task
        await self._publish_start_notification(heal)
        return True

    def _record_dispatch_skip(self, reason: str, period: str = "") -> None:
        state = (reason, period)
        if self._dispatch_skip == state:
            return
        self._dispatch_skip = state
        self._logger.info(
            "自修复暂未触发：今日额度已用尽" if reason == "daily_limit" else "自修复暂未触发：未配置管理员",
            event="self_heal.skipped",
            reason=reason,
            limit=self._config.daily_limit,
        )
