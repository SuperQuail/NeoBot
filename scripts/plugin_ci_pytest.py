"""宿主记录 pytest 的真实执行结果，覆盖显式 strict=False 的 XPASS。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


class _Results:
    def __init__(self) -> None:
        self.path: Path | None = None
        self.passed_items: set[str] = set()
        self.incomplete_items: set[str] = set()
        self.counts = {
            name: 0
            for name in (
                "collected",
                "passed",
                "skipped",
                "failures",
                "errors",
                "xfailed",
                "xpassed",
                "deselected",
            )
        }

    def pytest_addoption(self, parser) -> None:
        parser.addoption("--neobot-result-file", action="store", help="宿主验收结果 JSON 路径")

    def pytest_configure(self, config) -> None:
        value = config.getoption("--neobot-result-file")
        if value:
            self.path = Path(value)

    def pytest_collection_finish(self, session) -> None:
        self.counts["collected"] = len(session.items)

    def pytest_deselected(self, items) -> None:
        self.counts["deselected"] += len(items)

    def pytest_collectreport(self, report) -> None:
        if report.failed:
            self.counts["errors"] += 1

    def pytest_runtest_logreport(self, report) -> None:
        was_xfail = hasattr(report, "wasxfail")
        if was_xfail or report.failed or report.skipped:
            self.incomplete_items.add(report.nodeid)
        if was_xfail:
            key = "xpassed" if report.passed else "xfailed"
            self.counts[key] += 1
            return
        if report.skipped:
            self.counts["skipped"] += 1
        elif report.failed:
            key = "failures" if report.when == "call" else "errors"
            self.counts[key] += 1
        elif report.when == "call" and report.passed and not isinstance(report, pytest.SubtestReport):
            # 子报告沿用父 nodeid，成功子测试不能再增加父项通过数。
            self.passed_items.add(report.nodeid)

    def pytest_sessionfinish(self, session, exitstatus) -> None:
        if self.path is not None:
            self.counts["passed"] = len(self.passed_items - self.incomplete_items)
            result = {**self.counts, "exitstatus": int(exitstatus)}
            self.path.write_text(json.dumps(result) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    raise SystemExit(pytest.main(sys.argv[1:], plugins=[_Results()]))
