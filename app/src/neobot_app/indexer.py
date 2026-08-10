"""通用资源索引抽象:启动期 / `neobot init` 扫描注册表。

背景:很多资源(模型库索引、图库、表情包等)只能在启动 bot 后才能生成或
重新扫描。这里抽象出统一的 IndexTask 注册表:
- 启动时(bootstrap)静默执行一次 run_init(幂等)
- `neobot init [--force]` 命令独立重扫所有已注册任务并打印报告

新增一个可扫描资源时,只需注册一个 IndexTask:
    runner.register(IndexTask("vision_detect", "扫描 ONNX 模型目录", scan=...))
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class IndexTask:
    """一个可扫描/可再生的资源索引任务。

    Attributes:
        name: 唯一任务名
        description: 人类可读描述(用于 init 输出)
        scan: 扫描函数,scan(force: bool) -> ScanReport
    """

    name: str
    description: str
    scan: Callable[[bool], Any]


class IndexRunner:
    """资源索引任务注册表与执行器。"""

    def __init__(self) -> None:
        self._tasks: dict[str, IndexTask] = {}

    def register(self, task: IndexTask) -> None:
        if task.name in self._tasks:
            raise ValueError(f"索引任务已注册: {task.name}")
        self._tasks[task.name] = task

    def names(self) -> list[str]:
        return list(self._tasks)

    async def run(self, *, force: bool = False) -> list[Any]:
        """顺序执行所有已注册任务(幂等)。"""
        reports: list[Any] = []
        for task in self._tasks.values():
            result = task.scan(force)
            if asyncio.iscoroutine(result):
                result = await result
            reports.append({"task": task.name, "description": task.description, "report": result})
        return reports

    def run_sync(self, *, force: bool = False) -> list[Any]:
        """同步执行所有任务;异步任务会被跳过并计入 skipped。"""
        reports: list[Any] = []
        for task in self._tasks.values():
            result = task.scan(force)
            if asyncio.iscoroutine(result):
                result.close()
                reports.append(
                    {"task": task.name, "description": task.description, "skipped": True}
                )
                continue
            reports.append({"task": task.name, "description": task.description, "report": result})
        return reports

    def describe(self) -> str:
        lines = [f"- {task.name}: {task.description}" for task in self._tasks.values()]
        return "\n".join(lines) or "(没有已注册的索引任务)"


def build_init_runner(*, vision_detect_service: Any = None) -> IndexRunner:
    """收集默认的索引任务(随服务装配扩展)。"""
    runner = IndexRunner()
    if vision_detect_service is not None:
        runner.register(
            IndexTask(
                name="vision_detect",
                description="扫描 ONNX 模型目录并维护 models.toml 索引",
                scan=vision_detect_service.refresh,
            )
        )
    return runner
