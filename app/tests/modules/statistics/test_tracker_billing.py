"""spec(4) Part A：UsageTracker 计费策略与落库（A4、A6、A9、A10、A49、A50、A52-A54）。"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from neobot_app.statistics.billing import BillingService
from neobot_app.statistics.tracker import UsageTracker
from neobot_chat.models import ModelPricing, ModelSettings, RegisteredModel, model_registry
from neobot_storage.engine import create_engine, sqlite_url
from neobot_storage.models import Base, ModelUsageRecord


class RecordingLogger:
    """最小日志桩：记录 warning，供 A6 断言「产生一条 warning」。"""

    def __init__(self) -> None:
        self.records: list[tuple[str, str]] = []

    def _log(self, level: str, message, **_kwargs) -> None:
        self.records.append((level, str(message)))

    def debug(self, message, **kwargs) -> None:
        self._log("debug", message, **kwargs)

    def info(self, message, **kwargs) -> None:
        self._log("info", message, **kwargs)

    def warning(self, message, **kwargs) -> None:
        self._log("warning", message, **kwargs)

    def error(self, message, **kwargs) -> None:
        self._log("error", message, **kwargs)

    def bind(self, **_kwargs):
        return self

    def warnings(self) -> list[str]:
        return [message for level, message in self.records if level == "warning"]


DATA_DIR_HOLDER: dict[str, object] = {"path": None}


@pytest.fixture(autouse=True)
def _isolated_billing_dir(tmp_path):
    """每个用例一个独立的 <DATA_DIR>/Billing 目录。"""
    DATA_DIR_HOLDER["path"] = tmp_path
    yield
    DATA_DIR_HOLDER["path"] = None


@pytest.fixture(autouse=True)
def _restore_registry():
    """测试会清空全局模型注册表，结束后原样放回，避免污染其它用例。"""
    saved = tuple(model_registry.items())
    yield
    model_registry.clear()
    for name, model in saved:
        model_registry.register(model, replace=True)


@pytest.fixture(autouse=True)
def _fresh_billing_executor():
    """隔离共享线程池：上一个用例里卡死的脚本线程不会拖垮后续用例。

    进程内线程池是模块级单例（设计如此：常驻复用），卡死线程无法强杀，
    因此测试之间必须换一个全新的池，否则后续用例只会看到 fallback:timeout。
    """
    import neobot_app.statistics.billing as billing_module
    from concurrent.futures import ThreadPoolExecutor

    previous = billing_module._EXECUTOR
    billing_module._EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="billing-test")
    yield
    current = billing_module._EXECUTOR
    billing_module._EXECUTOR = previous
    current.shutdown(wait=False)


@pytest_asyncio.fixture
async def session_factory(tmp_path):
    engine = create_engine(sqlite_url(tmp_path / "usage.db"))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def make_billing(enabled: bool = True, *, timeout_ms: int = 200, logger=None):
    return BillingService(
        config=SimpleNamespace(
            billing=SimpleNamespace(
                enabled=enabled,
                timeout_ms=timeout_ms,
                reload_on_change=True,
                record_detail=True,
            )
        ),
        logger=logger or RecordingLogger(),
        data_dir=DATA_DIR_HOLDER["path"],
    )


def register_model(
    key: str,
    *,
    model_name: str = "deepseek-flash",
    billing_script: str = "",
    billing_config: dict | None = None,
    input_price: float = 1.0,
    output_price: float = 2.0,
) -> None:
    model_registry.register(
        RegisteredModel(
            name=key,
            description=key,
            provider_name="DeepSeek",
            model_name=model_name,
            base_url="https://api.deepseek.com/v1",
            api_key="sk-test",
            pricing=ModelPricing(
                input_price_per_mtokens=input_price,
                output_price_per_mtokens=output_price,
            ),
            settings=ModelSettings(),
            model_type="chat",
            billing_script=billing_script,
            billing_config=dict(billing_config or {}),
        ),
        replace=True,
    )


def write_script(name: str, body: str) -> None:
    base = Path(str(DATA_DIR_HOLDER["path"])) / "Billing"
    base.mkdir(parents=True, exist_ok=True)
    (base / f"{name}.py").write_text(body, encoding="utf-8")


async def fetch_records(session_factory) -> list[ModelUsageRecord]:
    async with session_factory() as session:
        result = await session.execute(
            select(ModelUsageRecord).order_by(ModelUsageRecord.id)
        )
        return list(result.scalars().all())


RECORD_ARGS = dict(
    module="reply_agent",
    input_tokens=1_000_000,
    output_tokens=1_000_000,
    cache_hit_tokens=0,
    cache_miss_tokens=0,
)


def expected_builtin(input_tokens=1_000_000, output_tokens=1_000_000) -> float:
    """改造前 tracker.py:72-77 的原公式（A10 对拍基准）。"""
    return (input_tokens * 1.0 + output_tokens * 2.0) / 1_000_000.0


# ── A10：默认关闭时行为与现状逐位一致 ─────────────────────────────


async def test_disabled_matches_legacy_formula(tmp_path, session_factory):
    """A10：enabled=false 时 cost_cny 与原公式逐位相同，来源为 builtin。"""
    register_model("m-plain", billing_script="per_call", billing_config={"price_per_call": 9.0})
    write_script("per_call", "def compute_cost(ctx):\n    return 9.0\n")
    tracker = UsageTracker(session_factory, logger=RecordingLogger(), billing=make_billing(False))
    await tracker.record(model_name="deepseek-flash", registered_key="m-plain", **RECORD_ARGS)
    records = await fetch_records(session_factory)
    assert len(records) == 1
    assert records[0].cost_cny == expected_builtin()
    assert records[0].cost_source == "builtin"
    assert records[0].cost_detail is None


async def test_no_billing_service_matches_legacy(tmp_path, session_factory):
    """未装配 billing（旧装配路径）时也逐位等同旧公式。"""
    register_model("m-plain")
    tracker = UsageTracker(session_factory, logger=RecordingLogger())
    await tracker.record(model_name="deepseek-flash", registered_key="m-plain", **RECORD_ARGS)
    records = await fetch_records(session_factory)
    assert records[0].cost_cny == expected_builtin()
    assert records[0].cost_source == "builtin"


# ── A4：cost_cny 仍是可 SUM 的标量 ───────────────────────────────


async def test_cost_cny_remains_scalar_and_scoped(tmp_path, session_factory):
    """A4：启用脚本后 cost_cny 仍为标量，SUM 与直接求和一致。"""
    register_model("m-call", billing_script="per_call", billing_config={"price_per_call": 0.25})
    write_script(
        "per_call",
        'def compute_cost(ctx):\n    return float(ctx["billing_config"]["price_per_call"])\n',
    )
    tracker = UsageTracker(session_factory, logger=RecordingLogger(), billing=make_billing())
    for _ in range(3):
        await tracker.record(model_name="deepseek-flash", registered_key="m-call", **RECORD_ARGS)
    records = await fetch_records(session_factory)
    async with session_factory() as session:
        total = (
            await session.execute(select(func.sum(ModelUsageRecord.cost_cny)))
        ).scalar_one()
    assert isinstance(records[0].cost_cny, float)
    assert total == pytest.approx(sum(r.cost_cny for r in records))
    assert total == pytest.approx(0.75)
    assert {r.cost_source for r in records} == {"script:per_call"}


# ── A6：脚本抛异常 ───────────────────────────────────────────────


async def test_exception_falls_back_and_still_records(tmp_path, session_factory):
    """A6：脚本抛异常 → 仍落库、金额 = 内建公式、来源 fallback:*、一条 warning。"""
    logger = RecordingLogger()
    register_model("m-boom", billing_script="boom")
    write_script("boom", 'def compute_cost(ctx):\n    raise ValueError("nope")\n')
    tracker = UsageTracker(session_factory, logger=logger, billing=make_billing(logger=logger))
    await tracker.record(model_name="deepseek-flash", registered_key="m-boom", **RECORD_ARGS)
    records = await fetch_records(session_factory)
    assert len(records) == 1
    assert records[0].cost_cny == expected_builtin()
    assert records[0].cost_source == "fallback:error"
    assert logger.warnings()


# ── A9：卡死脚本不阻塞、enabled=false 零额外耗时 ─────────────────


async def test_stuck_script_bounded_by_timeout(tmp_path, session_factory):
    """A9：enabled=true 且脚本卡死时，单次 record 额外耗时 ≤ timeout_ms + 50ms。"""
    register_model("m-slow", billing_script="slow")
    write_script(
        "slow",
        "import time\ndef compute_cost(ctx):\n    time.sleep(5)\n    return 1.0\n",
    )
    tracker = UsageTracker(
        session_factory, logger=RecordingLogger(), billing=make_billing(timeout_ms=150)
    )
    started = time.perf_counter()
    await tracker.record(model_name="deepseek-flash", registered_key="m-slow", **RECORD_ARGS)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    assert elapsed_ms <= 150 + 50
    records = await fetch_records(session_factory)
    assert records[0].cost_source == "fallback:timeout"
    assert records[0].cost_cny == expected_builtin()


async def test_disabled_is_zero_overhead(tmp_path, session_factory):
    """A9：enabled=false 时即使脚本卡死也没有额外耗时。"""
    register_model("m-slow", billing_script="slow")
    write_script(
        "slow",
        "import time\ndef compute_cost(ctx):\n    time.sleep(5)\n    return 1.0\n",
    )
    tracker = UsageTracker(
        session_factory, logger=RecordingLogger(), billing=make_billing(False, timeout_ms=150)
    )
    started = time.perf_counter()
    await tracker.record(model_name="deepseek-flash", registered_key="m-slow", **RECORD_ARGS)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    assert elapsed_ms < 150


# ── A49 / A50：按模型绑定与同名区分 ──────────────────────────────


async def test_two_models_use_their_own_scripts(tmp_path, session_factory):
    """A49：两个模型绑定不同脚本，各自按自己的脚本记账。"""
    register_model("m-a", billing_script="script_a")
    register_model("m-b", billing_script="script_b")
    write_script("script_a", "def compute_cost(ctx):\n    return 1.0\n")
    write_script("script_b", "def compute_cost(ctx):\n    return 2.0\n")
    tracker = UsageTracker(session_factory, logger=RecordingLogger(), billing=make_billing())
    await tracker.record(model_name="deepseek-flash", registered_key="m-a", **RECORD_ARGS)
    await tracker.record(model_name="deepseek-flash", registered_key="m-b", **RECORD_ARGS)
    records = await fetch_records(session_factory)
    assert [r.cost_source for r in records] == ["script:script_a", "script:script_b"]
    assert [r.cost_cny for r in records] == [pytest.approx(1.0), pytest.approx(2.0)]


async def test_same_model_name_different_keys(tmp_path, session_factory):
    """A50：同名 model_name 的两个条目分别记账（回归 §2.1 覆盖隐患）。"""
    model_registry.clear()
    register_model("key-one", model_name="deepseek-flash", billing_script="script_a")
    register_model("key-two", model_name="deepseek-flash", billing_script="script_b")
    write_script("script_a", "def compute_cost(ctx):\n    return 1.0\n")
    write_script("script_b", "def compute_cost(ctx):\n    return 2.0\n")
    tracker = UsageTracker(session_factory, logger=RecordingLogger(), billing=make_billing())
    await tracker.record(model_name="deepseek-flash", registered_key="key-one", **RECORD_ARGS)
    await tracker.record(model_name="deepseek-flash", registered_key="key-two", **RECORD_ARGS)
    records = await fetch_records(session_factory)
    assert [r.cost_cny for r in records] == [pytest.approx(1.0), pytest.approx(2.0)]
    assert [r.cost_source for r in records] == ["script:script_a", "script:script_b"]


def test_create_provider_injects_registered_key():
    """A50：create_provider 注入 provider.registered_key（区分同名条目的唯一依据）。"""
    model_registry.clear()
    register_model("key-one")
    provider = model_registry.create_provider("key-one")
    assert provider.registered_key == "key-one"
    assert provider.model == "deepseek-flash"


async def test_missing_registered_key_falls_back_to_model_name(tmp_path, session_factory):
    """兼容自定义 provider：拿不到 registered_key 时按 model_name 回落。"""
    model_registry.clear()
    register_model("only-key", model_name="deepseek-flash", billing_script="script_a")
    write_script("script_a", "def compute_cost(ctx):\n    return 1.0\n")
    tracker = UsageTracker(session_factory, logger=RecordingLogger(), billing=make_billing())
    await tracker.record(model_name="deepseek-flash", **RECORD_ARGS)
    records = await fetch_records(session_factory)
    assert records[0].cost_source == "script:script_a"


# ── A52 / A53：billing_config 与留空 ─────────────────────────────


async def test_billing_config_reaches_context(tmp_path, session_factory):
    """A52：billing_config 原样出现在 ctx；改配置后无需重建 tracker 即生效。"""
    register_model("m-cfg", billing_script="echo_cfg", billing_config={"price_per_call": 0.5})
    write_script(
        "echo_cfg",
        'def compute_cost(ctx):\n    return float(ctx["billing_config"]["price_per_call"])\n',
    )
    tracker = UsageTracker(session_factory, logger=RecordingLogger(), billing=make_billing())
    await tracker.record(model_name="deepseek-flash", registered_key="m-cfg", **RECORD_ARGS)
    # 模拟「面板保存并重载」：注册表条目被替换，tracker 缓存必须失效并读到新参数
    register_model("m-cfg", billing_script="echo_cfg", billing_config={"price_per_call": 0.75})
    await tracker.record(model_name="deepseek-flash", registered_key="m-cfg", **RECORD_ARGS)
    records = await fetch_records(session_factory)
    assert [r.cost_cny for r in records] == [pytest.approx(0.5), pytest.approx(0.75)]


async def test_empty_script_stays_builtin(tmp_path, session_factory):
    """A53：billing_script 留空时即使 enabled=true 也走固定计费。"""
    register_model("m-none", billing_script="")
    register_model("m-bound", billing_script="per_call", billing_config={"price_per_call": 3.0})
    write_script("per_call", "def compute_cost(ctx):\n    return 3.0\n")
    tracker = UsageTracker(session_factory, logger=RecordingLogger(), billing=make_billing())
    await tracker.record(model_name="deepseek-flash", registered_key="m-none", **RECORD_ARGS)
    await tracker.record(model_name="deepseek-flash", registered_key="m-bound", **RECORD_ARGS)
    records = await fetch_records(session_factory)
    assert records[0].cost_source == "builtin"
    assert records[0].cost_cny == expected_builtin()
    assert records[1].cost_source == "script:per_call"


# ── A54：负金额 ──────────────────────────────────────────────────


async def test_negative_cost_is_stored(tmp_path, session_factory):
    """A54：脚本返回负金额时原样落库，SUM 与直接求和一致。"""
    register_model("m-refund", billing_script="refund")
    write_script("refund", "def compute_cost(ctx):\n    return -0.75\n")
    tracker = UsageTracker(session_factory, logger=RecordingLogger(), billing=make_billing())
    await tracker.record(model_name="deepseek-flash", registered_key="m-refund", **RECORD_ARGS)
    records = await fetch_records(session_factory)
    async with session_factory() as session:
        total = (
            await session.execute(select(func.sum(ModelUsageRecord.cost_cny)))
        ).scalar_one()
    assert records[0].cost_cny == pytest.approx(-0.75)
    assert records[0].cost_source == "script:refund"
    assert total == pytest.approx(-0.75)


async def test_cost_detail_columns_written(tmp_path, session_factory):
    """R6：components / note 压缩成单行 JSON 落入 cost_detail。"""
    register_model("m-detail", billing_script="detail")
    write_script(
        "detail",
        'def compute_cost(ctx):\n'
        '    return {"cost_cny": 1.0, "components": {"a": 0.4, "b": 0.6}, "note": "hi"}\n',
    )
    tracker = UsageTracker(session_factory, logger=RecordingLogger(), billing=make_billing())
    await tracker.record(model_name="deepseek-flash", registered_key="m-detail", **RECORD_ARGS)
    records = await fetch_records(session_factory)
    detail = json.loads(records[0].cost_detail or "{}")
    assert detail["components"] == {"a": 0.4, "b": 0.6}
    assert detail["note"] == "hi"
    assert isinstance(records[0].created_at, datetime)
    assert records[0].created_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc)


async def test_unknown_module_is_skipped(tmp_path, session_factory):
    """既有白名单行为不变：未登记模块直接丢弃。"""
    register_model("m-plain")
    tracker = UsageTracker(session_factory, logger=RecordingLogger(), billing=make_billing())
    await tracker.record(
        module="not_a_module",
        model_name="deepseek-flash",
        input_tokens=1,
        output_tokens=1,
    )
    assert await fetch_records(session_factory) == []


async def test_unknown_model_is_skipped(tmp_path, session_factory):
    """既有行为不变：注册表里找不到同名模型则静默跳过。"""
    model_registry.clear()
    tracker = UsageTracker(session_factory, logger=RecordingLogger(), billing=make_billing())
    await tracker.record(model_name="ghost", **RECORD_ARGS)
    assert await fetch_records(session_factory) == []
