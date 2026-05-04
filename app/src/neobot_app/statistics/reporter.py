from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from neobot_app.core.constants import DATA_DIR
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_storage.models import ModelUsageRecord
from neobot_storage.repositories.usage import SqlAlchemyUsageRepository

REPORT_DIR = DATA_DIR / "费用统计"

_INTERVALS: dict[str, timedelta | None] = {
    "全部历史": None,
    "最近1个月": timedelta(days=30),
    "最近1周": timedelta(days=7),
    "最近1天": timedelta(days=1),
    "最近1小时": timedelta(hours=1),
}


class UsageReportService:
    def __init__(self, session_factory, *, logger: Logger | None = None) -> None:
        self._session_factory = session_factory
        self._logger = logger or NullLogger()

    async def generate_all_reports(self) -> None:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        for label, delta in _INTERVALS.items():
            try:
                content = await self._build_report(delta)
                filename = f"费用统计-{label}.md"
                (REPORT_DIR / filename).write_text(content, encoding="utf-8")
                self._logger.debug("usage report written", file=filename)
            except Exception as exc:
                self._logger.warning(
                    "failed to generate usage report",
                    label=label,
                    error=str(exc),
                )

    async def _build_report(self, since: timedelta | None) -> str:
        cutoff = None
        if since is not None:
            cutoff = datetime.now(timezone.utc) - since

        async with self._session_factory() as session:
            repo = SqlAlchemyUsageRepository(session)
            records = await repo.stats_since(cutoff)

        return self._format_markdown(records, since)

    @staticmethod
    def _format_markdown(records: list[ModelUsageRecord], since: timedelta | None) -> str:
        label = "全部历史" if since is None else _describe_delta(since)
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        total_calls = len(records)
        total_input = sum(r.input_tokens for r in records)
        total_output = sum(r.output_tokens for r in records)
        total_cost = sum(r.cost_usd for r in records)

        by_module: dict[str, dict] = defaultdict(
            lambda: {"calls": 0, "input": 0, "output": 0, "cost": 0.0}
        )
        for r in records:
            g = by_module[r.module_name]
            g["calls"] += 1
            g["input"] += r.input_tokens
            g["output"] += r.output_tokens
            g["cost"] += r.cost_usd

        by_model: dict[tuple, dict] = defaultdict(
            lambda: {"calls": 0, "input": 0, "output": 0, "cost": 0.0}
        )
        for r in records:
            key = (r.model_name, r.provider_name)
            g = by_model[key]
            g["calls"] += 1
            g["input"] += r.input_tokens
            g["output"] += r.output_tokens
            g["cost"] += r.cost_usd

        by_conv: dict[str, dict] = defaultdict(
            lambda: {"calls": 0, "input": 0, "output": 0, "cost": 0.0}
        )
        for r in records:
            kind = r.conversation_kind or "无上下文"
            g = by_conv[kind]
            g["calls"] += 1
            g["input"] += r.input_tokens
            g["output"] += r.output_tokens
            g["cost"] += r.cost_usd

        lines = []
        lines.append(f"# 模型调用费用统计报告 - {label}")
        lines.append(f"生成时间: {now_str}")
        lines.append("")

        lines.append("## 总览")
        lines.append("")
        lines.append(f"- 总调用次数: {total_calls}")
        lines.append(f"- 总输入 Token: {total_input:,}")
        lines.append(f"- 总输出 Token: {total_output:,}")
        lines.append(f"- 总费用: ${total_cost:.6f}")
        lines.append("")

        lines.append("## 按模块统计")
        lines.append("")
        lines.append("| 模块 | 调用次数 | 输入 Token | 输出 Token | 费用(USD) |")
        lines.append("|------|---------|-----------|-----------|----------|")
        for module in sorted(by_module):
            g = by_module[module]
            lines.append(
                f"| {module} | {g['calls']} | {g['input']:,} | "
                f"{g['output']:,} | ${g['cost']:.6f} |"
            )
        lines.append("")

        lines.append("## 按模型统计")
        lines.append("")
        lines.append("| 模型 | 提供商 | 调用次数 | 输入 Token | 输出 Token | 费用(USD) |")
        lines.append("|------|--------|---------|-----------|-----------|----------|")
        for (model, provider) in sorted(by_model):
            g = by_model[(model, provider)]
            lines.append(
                f"| {model} | {provider} | {g['calls']} | {g['input']:,} | "
                f"{g['output']:,} | ${g['cost']:.6f} |"
            )
        lines.append("")

        lines.append("## 按会话类型统计")
        lines.append("")
        lines.append("| 会话类型 | 调用次数 | 输入 Token | 输出 Token | 费用(USD) |")
        lines.append("|---------|---------|-----------|-----------|----------|")
        for kind in sorted(by_conv):
            g = by_conv[kind]
            lines.append(
                f"| {kind} | {g['calls']} | {g['input']:,} | "
                f"{g['output']:,} | ${g['cost']:.6f} |"
            )
        lines.append("")

        return "\n".join(lines)


def _describe_delta(td: timedelta) -> str:
    total_hours = int(td.total_seconds() / 3600)
    if total_hours == 1:
        return "1小时"
    if total_hours < 24:
        return f"{total_hours}小时"
    days = total_hours // 24
    if days == 1:
        return "1天"
    if days < 7:
        return f"{days}天"
    if days == 7:
        return "1周"
    if days < 30:
        return f"{days // 7}周"
    if days == 30:
        return "1个月"
    return f"{days}天"
