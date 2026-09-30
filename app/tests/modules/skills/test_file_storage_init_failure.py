"""FileStorageSkill 初始化失败的回归测试（fix(12) §4.4）。

旧实现把 `asyncio.ensure_future(_init())` 包在 `except Exception: pass` 里：
初始化协程抛错时调用方无异常、应用日志无记录，只在 stderr 出现 asyncio 的
"Task exception was never retrieved"，表现为「持久化目录建好了，但
文件存储.md / TODO.md 永远不生成」且完全不可观测。

修复后：fire-and-forget 任务自带 try/except 并 logger.exception；
无运行中事件循环时同步跑完，不再依赖 `asyncio.get_event_loop()` 的隐式建环。
"""

from __future__ import annotations

from pathlib import Path

import loguru

from neobot_app.skills.file_storage_skill import (
    _PERSISTENT_DIRS,
    _STORAGE_DOC,
    _TODO_DOC,
    FileStorageSkill,
)

_REQUIRED_DOCS = (_STORAGE_DOC, _TODO_DOC)


def _make_skill(sandbox=None) -> FileStorageSkill:
    return FileStorageSkill(sandbox_service=sandbox)


def test_init_creates_dirs_and_docs_without_event_loop(make_sandbox, tmp_path: Path) -> None:
    """无运行中事件循环时也必须真正建目录 + 建文档（旧实现会静默什么都不做）。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)

    skill._ensure_dirs_and_docs()

    root = sandbox.resolve_path("")
    for directory in _PERSISTENT_DIRS:
        assert (root / directory).is_dir(), f"目录未创建: {directory}"
    for doc in _REQUIRED_DOCS:
        path = sandbox.resolve_path(doc)
        assert path.is_file(), f"索引文档未创建: {doc}"
        assert path.read_text(encoding="utf-8").strip()


async def test_init_failure_is_logged_not_swallowed(make_sandbox) -> None:
    """写文档失败时必须留下 ERROR 日志（旧实现是 `except Exception: pass`）。"""
    sandbox = make_sandbox()

    async def _boom(path: Path, data: bytes) -> None:
        raise RuntimeError("sandbox write failed")

    sandbox.write_file = _boom  # type: ignore[method-assign]
    records: list[str] = []
    sink_id = loguru.logger.add(lambda message: records.append(message), format="{message}")

    try:
        skill = _make_skill(sandbox)
        skill._ensure_dirs_and_docs()
        # fire-and-forget：给任务一个调度窗口
        import asyncio

        for _ in range(50):
            await asyncio.sleep(0.02)
            if records:
                break
    finally:
        loguru.logger.remove(sink_id)

    assert records, "初始化失败没有留下任何日志（旧行为）"
    assert any("文件存储初始化失败" in record for record in records)


def test_init_requires_sandbox(make_sandbox) -> None:
    """没有 sandbox_service 时不应创建任何文件（保持既有早退语义）。"""
    skill = _make_skill(None)

    skill._ensure_dirs_and_docs()  # 不抛异常即可

    assert not any(Path(name).exists() for name in _REQUIRED_DOCS)


def test_no_production_caller_yet() -> None:
    """记录事实：v1.0.0 里 `_ensure_dirs_and_docs` 没有任何生产调用方。

    本轮只修「静默失败」（一旦被调用不得无声吞异常）。若后续把它接入启动/首次使用
    流程，本用例应改为断言"接入点存在"——避免"改了日志却永远不会执行"的假修复。
    """
    import subprocess

    result = subprocess.run(
        ["git", "grep", "-n", "_ensure_dirs_and_docs", "--", "app/src", "packages"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    callers = [
        line
        for line in (result.stdout or "").splitlines()
        if "def _ensure_dirs_and_docs" not in line
    ]
    assert callers == [], (
        "初始化入口已被接入生产路径，请把本用例改为断言接入点存在："
        + "; ".join(callers)
    )
