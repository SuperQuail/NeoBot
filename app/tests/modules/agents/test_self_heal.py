"""BUG-0038 防护测试: self-heal 单飞、每日预算、源码 glob 越界限制。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from neobot_app.agents.self_heal import (
    SelfHealAgentConfig,
    SelfHealManager,
    SelfHealToolExecutor,
)


class _FakeHub:
    def __init__(self, delay: float = 0.0) -> None:
        self.delay = delay
        self.published = 0

    async def publish(self, **kwargs) -> None:
        self.published += 1
        if self.delay:
            await asyncio.sleep(self.delay)


class _FakeAgent:
    def __init__(self) -> None:
        self.close_calls = 0

    async def _invoke_direct(self, state) -> dict:
        return {"messages": []}

    async def close(self) -> None:
        self.close_calls += 1


def _payload(time: str = "t0") -> dict:
    return {"time": time, "module": "test", "message": "boom", "traceback": "tb"}


def _make_manager(daily_limit: int = 5, hub_delay: float = 0.0) -> SelfHealManager:
    cfg = SelfHealAgentConfig(
        enabled=True, admin_account="10001", daily_limit=daily_limit
    )
    manager = SelfHealManager(config=cfg, notification_hub=_FakeHub(delay=hub_delay))
    manager.set_agent(_FakeAgent())
    return manager


class _ReadOnlyBudgetProvider:
    """max_tokens 只读的 provider（原生视觉包装器线上崩溃时的行为）。"""

    def __init__(self) -> None:
        self._budget = 200000

    @property
    def max_tokens(self) -> int:
        return self._budget


def test_build_self_heal_agent_survives_readonly_provider_budget() -> None:
    """provider.max_tokens 只读时装配不得崩溃，只降级告警。

    线上事故：主模型开启原生视觉后 provider 变成 NativeVisionFallbackProvider，
    max_tokens 成为只读属性，`provider.max_tokens = cfg.max_tokens` 让 Bot 启动即崩。
    """
    from neobot_app.agents.self_heal import build_self_heal_agent

    logger = _RecordingLogger()
    provider = _ReadOnlyBudgetProvider()

    agent = build_self_heal_agent(provider, logger=logger)

    assert agent is not None
    assert any("max_tokens 只读" in w for w in logger.warnings)
    assert provider.max_tokens == 200000


def test_build_self_heal_agent_survives_native_vision_wrapper() -> None:
    """真实回归：主模型开启原生视觉（默认开启）时 self-heal 装配不得崩溃。"""
    from unittest.mock import Mock

    from neobot_chat.providers.native_vision import NativeVisionFallbackProvider

    from neobot_app.agents.self_heal import build_self_heal_agent

    class _PlainProvider:
        def __init__(self, name: str, budget: int) -> None:
            self.model = name
            self.max_tokens = budget
            self.native_vision = True

    primary = _PlainProvider("main", 200000)
    fallback = _PlainProvider("vision", 4096)
    wrapped = NativeVisionFallbackProvider(primary, fallback, logger=Mock())

    agent = build_self_heal_agent(wrapped, logger=_RecordingLogger())

    assert agent is not None
    assert wrapped.max_tokens == 200000
    assert primary.max_tokens == 200000
    assert fallback.max_tokens == 4096


def test_build_self_heal_agent_wiring_uses_configured_agent_model(monkeypatch) -> None:
    """自修复必须走 agent_model.self_heal 指定的模型，而不是复用主回复 provider。

    复用主 provider 会同时丢掉配置的模型编号、并把预算覆盖写进共享实例（主模型被压低）。
    """
    from types import SimpleNamespace

    from neobot_app.bootstrap import _providers as providers_mod
    from neobot_app.bootstrap._runtime import build_self_heal_agent_wiring

    made: list = []
    names: list[str] = []

    def _fake_create(name: str):
        names.append(name)
        provider = SimpleNamespace(max_tokens=None)
        made.append(provider)
        return provider

    monkeypatch.setattr(providers_mod, "create_provider", _fake_create)

    config = SimpleNamespace(
        agent_model=SimpleNamespace(self_heal=1),
        models=SimpleNamespace(
            assignments=SimpleNamespace(agent_model_1="self-heal-model"),
            get=lambda key: object() if key == "self-heal-model" else None,
        ),
        agent=SimpleNamespace(self_healing=None),
    )

    class _Factory:
        def __init__(self) -> None:
            self.logger = _RecordingLogger()

        def get_logger(self, _name: str) -> _RecordingLogger:
            return self.logger

    factory = _Factory()
    shared = SimpleNamespace(max_tokens=None)

    agent = build_self_heal_agent_wiring(
        config=config,
        manager=_make_manager(),
        provider=shared,
        provider_logger=factory.logger,
        sandbox_service=None,
        logger_factory=factory,
        data_dir=Path("."),
        source_roots=[],
        log_file=None,
    )

    assert agent is not None
    assert names == ["self-heal-model"]
    # 预算覆盖落在专属实例上；共享的主回复 provider 未被触碰。
    assert made and made[0].max_tokens == 8192
    assert shared.max_tokens is None
    assert agent._agent.provider is made[0]


# ── 回归: 主 provider 不可用时的降级（AttributeError 崩溃修复） ──


class _RecordingLogger:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warning(self, message: str, **_kwargs) -> None:
        self.warnings.append(message)

    def debug(self, *_a, **_k) -> None:
        pass

    def info(self, *_a, **_k) -> None:
        pass

    def error(self, *_a, **_k) -> None:
        pass


def test_build_self_heal_agent_returns_none_without_provider() -> None:
    """provider 为 None（主模型配置错误）时不得抛 AttributeError，只降级并告警。"""
    from neobot_app.agents.self_heal import build_self_heal_agent

    logger = _RecordingLogger()

    agent = build_self_heal_agent(None, logger=logger)

    assert agent is None
    assert logger.warnings and "provider 不可用" in logger.warnings[0]


def test_build_self_heal_agent_wiring_skips_without_provider() -> None:
    """装配入口在 provider 不可用时直接跳过，不触碰 manager。"""
    from types import SimpleNamespace

    from neobot_app.bootstrap._runtime import build_self_heal_agent_wiring

    class _Factory:
        def __init__(self) -> None:
            self.logger = _RecordingLogger()

        def get_logger(self, _name: str) -> _RecordingLogger:
            return self.logger

    factory = _Factory()
    manager = _make_manager()

    result = build_self_heal_agent_wiring(
        config=SimpleNamespace(),
        manager=manager,
        provider=None,
        provider_logger=factory.logger,
        sandbox_service=None,
        logger_factory=factory,
        data_dir=Path("."),
        source_roots=[],
        log_file=None,
    )

    assert result is None
    assert factory.logger.warnings and "跳过装配" in factory.logger.warnings[0]
    assert manager._agent is not None  # 未被替换/清空


async def test_concurrent_trigger_starts_single_heal() -> None:
    manager = _make_manager(hub_delay=0.05)
    heal_starts = []

    async def _stub_run_heal(heal):
        heal_starts.append(heal.task_id)
        heal.status = "completed"
        await asyncio.sleep(0.05)

    manager._run_heal = _stub_run_heal  # type: ignore[method-assign]
    await manager.record(_payload("t1"))
    await manager.record(_payload("t2"))

    r1 = asyncio.create_task(manager.trigger_now(reason="r1"))
    r2 = asyncio.create_task(manager.trigger_now(reason="r2"))
    out = await asyncio.gather(r1, r2)

    assert len(heal_starts) == 1
    statuses = sorted(json.loads(o)["status"] for o in out)
    assert statuses == ["busy", "started"]


async def test_daily_limit_blocks_overflow() -> None:
    manager = _make_manager(daily_limit=2)
    heal_starts = []

    async def _stub_run_heal(heal):
        heal_starts.append(heal.task_id)
        heal.status = "completed"

    manager._run_heal = _stub_run_heal  # type: ignore[method-assign]

    async def trigger_once(tag: str) -> dict:
        await manager.record(_payload(tag))
        return json.loads(await manager.trigger_now(reason="manual"))

    r1 = await trigger_once("a")
    await manager._running_task
    r2 = await trigger_once("b")
    await manager._running_task
    r3 = await trigger_once("c")

    assert r1["ok"] is True
    assert r2["ok"] is True
    assert r3["ok"] is False
    assert "上限" in r3["error"]
    assert len(heal_starts) == 2


async def test_daily_budget_resets_on_new_day() -> None:
    manager = _make_manager(daily_limit=5)
    heal_starts = []

    async def _stub_run_heal(heal):
        heal_starts.append(heal.task_id)
        heal.status = "completed"

    manager._run_heal = _stub_run_heal  # type: ignore[method-assign]
    manager._trigger_date_today = "2000-01-01"
    manager._trigger_count_today = 100

    await manager.record(_payload())
    result = json.loads(await manager.trigger_now(reason="manual"))
    await manager._running_task

    assert result["ok"] is True
    assert len(heal_starts) == 1
    assert manager._trigger_count_today == 1


def _make_executor(tmp_path: Path) -> SelfHealToolExecutor:
    app_root = tmp_path / "app"
    pkg_root = tmp_path / "packages"
    (app_root / "src").mkdir(parents=True)
    (pkg_root / "src").mkdir(parents=True)
    (app_root / "src" / "manager.py").write_text(
        "def heal():\n    return 'fixed'\n", encoding="utf-8"
    )
    (pkg_root / "src" / "core.py").write_text("VERSION = '1.0'\n", encoding="utf-8")
    return SelfHealToolExecutor(source_roots=[app_root, pkg_root])


async def test_search_source_code_rejects_absolute_glob(tmp_path) -> None:
    outside = tmp_path / ".." / "secret.txt"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text("sk-lives-here\n", encoding="utf-8")
    executor = _make_executor(tmp_path)
    out = await executor._execute_search_source_code(
        {
            "pattern": "sk-",
            "path_glob": str(outside.resolve()),
        }
    )
    data = json.loads(out)
    assert data["ok"] is False
    assert "越界" in data["error"]


async def test_search_source_code_rejects_parent_traversal(tmp_path) -> None:
    executor = _make_executor(tmp_path)
    out = await executor._execute_search_source_code(
        {
            "pattern": "heal",
            "path_glob": "../**/*.py",
        }
    )
    data = json.loads(out)
    assert data["ok"] is False
    assert "越界" in data["error"]


async def test_search_source_code_rejects_out_of_root_glob(tmp_path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "secret.env").write_text("KEY=123\n", encoding="utf-8")
    executor = _make_executor(tmp_path)
    out = await executor._execute_search_source_code(
        {
            "pattern": "KEY",
            "path_glob": "data/**/*.env",
        }
    )
    data = json.loads(out)
    assert data["ok"] is False
    assert "越界" in data["error"]


async def test_search_source_code_accepts_in_root_glob(tmp_path) -> None:
    executor = _make_executor(tmp_path)
    out = await executor._execute_search_source_code(
        {
            "pattern": "heal",
            "path_glob": "app/**/*.py",
        }
    )
    data = json.loads(out)
    assert data["ok"] is True
    assert data["match_count"] == 1
    assert "manager.py" in data["matches"][0]["path"]


async def test_search_source_code_default_globs_scan_both_roots(tmp_path) -> None:
    executor = _make_executor(tmp_path)
    out = await executor._execute_search_source_code({"pattern": "VERSION"})
    data = json.loads(out)
    assert data["ok"] is True
    assert data["match_count"] == 1


class _FakeFailingAgent:
    """假自修复 Agent：_invoke_direct 直接抛错。"""

    async def _invoke_direct(self, state) -> dict:
        raise RuntimeError("heal exploded")


class _FakeBlockingAgent:
    """假自修复 Agent：_invoke_direct 阻塞等待 release 事件。"""

    def __init__(self) -> None:
        self.release = asyncio.Event()

    async def _invoke_direct(self, state) -> dict:
        await self.release.wait()
        return {"messages": []}


async def test_shutdown_is_idempotent_and_clears_state() -> None:
    """连续调用 shutdown() 不得抛错，且清空运行任务与错误缓冲。"""
    manager = _make_manager()
    await manager.record(_payload("t1"))
    assert len(manager._buffer) == 1

    await manager.shutdown()
    assert manager._running_task is None
    assert manager._current_heal is None
    assert len(manager._buffer) == 0

    await manager.shutdown()
    assert manager._running_task is None


async def test_shutdown_cancels_running_heal_task() -> None:
    """shutdown() 必须取消正在运行的自修复任务并复位全部状态。"""
    manager = _make_manager()
    manager._agent = _FakeBlockingAgent()  # type: ignore[assignment]
    await manager.record(_payload("t1"))

    result = json.loads(await manager.trigger_now(reason="manual"))
    assert result["ok"] is True
    running = manager._running_task
    assert running is not None and not running.done()

    await manager.shutdown()
    assert running.cancelled()
    assert manager._running_task is None
    assert manager._current_heal is None
    assert len(manager._buffer) == 0


async def test_run_heal_exception_marks_failed_and_recovers_state() -> None:
    """_run_heal 抛错后任务必须标记 failed、记录摘要并清空当前任务引用。"""
    manager = _make_manager()
    manager._agent = _FakeFailingAgent()  # type: ignore[assignment]
    await manager.record(_payload("t1"))

    result = json.loads(await manager.trigger_now(reason="boom"))
    assert result["ok"] is True
    heal = manager._current_heal
    assert heal is not None

    await manager._running_task
    assert heal.status == "failed"
    assert "RuntimeError" in heal.summary
    assert manager._current_heal is None


async def test_run_heal_completion_clears_running_task() -> None:
    """自修复任务结束后 manager._running_task 必须恢复为 None。"""
    manager = _make_manager()
    manager._agent = _FakeFailingAgent()  # type: ignore[assignment]
    await manager.record(_payload("t1"))

    result = json.loads(await manager.trigger_now(reason="boom"))
    assert result["ok"] is True
    assert manager._running_task is not None

    await manager._running_task
    assert manager._running_task is None


async def test_shutdown_closes_attached_agent_once() -> None:
    manager = _make_manager()
    agent = _FakeAgent()
    manager.set_agent(agent)

    await manager.shutdown()
    await manager.shutdown()

    assert agent.close_calls == 1
    assert manager._agent is None
    assert manager.enabled is False
