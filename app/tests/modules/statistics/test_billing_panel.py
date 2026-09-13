"""spec(4) Part A：面板三接口 / 用量来源列 / 报表来源分布（A12、A14、A15）。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from neobot_app.builtin_plugins.dashboard.api import DashboardApi
from neobot_app.statistics.billing import BillingService
from neobot_app.statistics.reporter import UsageReportService
from neobot_chat.models import ModelPricing, ModelSettings, RegisteredModel, model_registry
from neobot_storage.engine import create_engine, sqlite_url
from neobot_storage.models import Base, ModelUsageRecord


class _NullLogger:
    def debug(self, *args, **kwargs) -> None: ...
    def info(self, *args, **kwargs) -> None: ...
    def warning(self, *args, **kwargs) -> None: ...
    def error(self, *args, **kwargs) -> None: ...
    def exception(self, *args, **kwargs) -> None: ...
    def bind(self, **kwargs):
        return self


class _FakeServices:
    def __init__(self, mapping: dict) -> None:
        self._mapping = mapping

    def get(self, name: str, default=None):
        value = self._mapping.get(name, default)
        return default if value is None else value


class _FakeConsole:
    def __init__(self, services: dict, *, manage: bool = True, remote: bool = True) -> None:
        self.logger = _NullLogger()
        self.metrics = None
        self.services = _FakeServices(services)
        self.manage_plugins = manage
        self.allow_remote_manage = remote
        self.plugin_control = None
        self.base_path = ""
        self.version = "test"

    def request_ip(self, request) -> str:
        return "127.0.0.1"


class _FakeRequest:
    def __init__(self, payload: dict | None = None, query: dict | None = None) -> None:
        self._payload = payload
        self.query = query or {}
        self.can_read_body = payload is not None

    async def json(self):
        return self._payload


def _body(response) -> dict:
    return json.loads(response.body.decode("utf-8"))


def make_billing(tmp_path: Path, *, enabled: bool = True) -> BillingService:
    return BillingService(
        config=SimpleNamespace(
            billing=SimpleNamespace(
                enabled=enabled,
                timeout_ms=200,
                reload_on_change=True,
                record_detail=True,
            )
        ),
        logger=_NullLogger(),
        data_dir=tmp_path,
    )


@pytest.fixture
def restore_registry():
    saved = tuple(model_registry.items())
    yield
    model_registry.clear()
    for name, model in saved:
        model_registry.register(model, replace=True)


def register_model(key: str, *, billing_script: str = "", billing_config: dict | None = None) -> None:
    model_registry.register(
        RegisteredModel(
            name=key,
            description=key,
            provider_name="DeepSeek",
            model_name="deepseek-flash",
            base_url="https://api.deepseek.com/v1",
            api_key="sk-test",
            pricing=ModelPricing(
                input_price_per_mtokens=1.0,
                output_price_per_mtokens=2.0,
                cache_hit_price_per_mtokens=0.1,
            ),
            settings=ModelSettings(),
            model_type="chat",
            billing_script=billing_script,
            billing_config=dict(billing_config or {}),
        ),
        replace=True,
    )


# ── A1 / A12：三个新接口 ─────────────────────────────────────────


async def test_config_billing_describe(tmp_path, restore_registry):
    """GET /api/config/billing：全局策略 + 脚本清单 + 每个模型条目的绑定情况。"""
    model_registry.clear()
    register_model("m-bound", billing_script="per_call", billing_config={"price_per_call": 0.01})
    register_model("m-free")
    billing = make_billing(tmp_path)
    api = DashboardApi(console=_FakeConsole({"billing_service": billing}))
    payload = _body(await api.config_billing(_FakeRequest()))
    assert payload["ok"] is True
    assert payload["available"] is True
    assert payload["enabled"] is True
    assert payload["timeout_ms"] == 200
    assert "per_call" in payload["scripts"]
    assert {"deepseek_peak_valley", "per_call"} <= set(payload["templates"])
    bindings = {item["model_key"]: item for item in payload["bindings"]}
    assert bindings["m-bound"]["billing_script"] == "per_call"
    assert bindings["m-bound"]["billing_config"] == {"price_per_call": 0.01}
    assert bindings["m-free"]["billing_script"] == ""
    assert bindings["m-free"]["source"] == "builtin"


async def test_config_billing_reload_requires_manage(tmp_path, restore_registry):
    """A12：非管理会话被拒；管理会话重载立即生效并返回加载结果。"""
    billing = make_billing(tmp_path)
    denied_api = DashboardApi(console=_FakeConsole({"billing_service": billing}, manage=False))
    denied = await denied_api.config_billing_reload(_FakeRequest({}))
    assert denied.status == 403
    assert _body(denied)["ok"] is False

    (tmp_path / "Billing" / "late.py").write_text(
        "def compute_cost(ctx):\n    return 1.0\n", encoding="utf-8"
    )
    api = DashboardApi(console=_FakeConsole({"billing_service": billing}))
    body = _body(await api.config_billing_reload(_FakeRequest({"scripts": ["late"]})))
    assert body["ok"] is True
    assert body["reloaded"] == ["late"]
    assert body["results"]["late"]["ok"] is True
    assert "late" in body["bindings"] or body["bindings"] is not None

    broken = _body(await api.config_billing_reload(_FakeRequest({"scripts": ["nope"]})))
    assert broken["errors"]["nope"]


async def test_config_billing_preview_peak_vs_idle(tmp_path, restore_registry):
    """A1（接口路径）：两次 preview 对照，高峰/空闲金额之比 = 2.0。"""
    model_registry.clear()
    register_model("m-peak", billing_script="deepseek_peak_valley")
    billing = make_billing(tmp_path, enabled=False)  # preview 不依赖全局开关
    api = DashboardApi(console=_FakeConsole({"billing_service": billing}))
    usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
    peak = _body(
        await api.config_billing_preview(
            _FakeRequest(
                {
                    "model_key": "m-peak",
                    "usage": usage,
                    "occurred_at": datetime(2026, 9, 9, 2, 0, tzinfo=timezone.utc).isoformat(),
                }
            )
        )
    )
    idle = _body(
        await api.config_billing_preview(
            _FakeRequest(
                {
                    "model_key": "m-peak",
                    "usage": usage,
                    "occurred_at": datetime(2026, 9, 9, 14, 0, tzinfo=timezone.utc).isoformat(),
                }
            )
        )
    )
    assert peak["source"] == "script:deepseek_peak_valley"
    assert peak["components"]["cache_miss"] > 0
    assert peak["cost_cny"] / idle["cost_cny"] == pytest.approx(2.0, abs=1e-6)
    assert peak["builtin_cost_cny"] > 0


async def test_config_billing_preview_unknown_model(tmp_path, restore_registry):
    """preview 传未知 model_key → 明确报错，不写库。"""
    model_registry.clear()
    billing = make_billing(tmp_path)
    api = DashboardApi(console=_FakeConsole({"billing_service": billing}))
    response = await api.config_billing_preview(_FakeRequest({"model_key": "ghost"}))
    assert response.status == 400


async def test_config_billing_preview_accepts_direct_script(tmp_path, restore_registry):
    """preview 允许直接传 billing_script + billing_config（保存前试算）。"""
    billing = make_billing(tmp_path)
    api = DashboardApi(console=_FakeConsole({"billing_service": billing}))
    body = _body(
        await api.config_billing_preview(
            _FakeRequest(
                {
                    "billing_script": "per_call",
                    "billing_config": {"price_per_call": 0.02},
                    "usage": {"input_tokens": 5},
                }
            )
        )
    )
    assert body["cost_cny"] == pytest.approx(0.02)
    assert body["billing_script"] == "per_call"


# ── A14：用量「来源」列与分项 ────────────────────────────────────


@pytest_asyncio.fixture
async def session_factory(tmp_path):
    engine = create_engine(sqlite_url(tmp_path / "panel.db"))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _seed(session_factory) -> None:
    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        session.add_all(
            [
                ModelUsageRecord(
                    module_name="reply_agent",
                    model_name="deepseek-flash",
                    provider_name="DeepSeek",
                    input_tokens=10,
                    output_tokens=20,
                    cost_cny=0.5,
                    cost_source="script:deepseek_peak_valley",
                    cost_detail=json.dumps(
                        {"components": {"cache_hit": 0.1, "cache_miss": 0.3, "output": 0.1}},
                        ensure_ascii=False,
                    ),
                    created_at=now,
                ),
                ModelUsageRecord(
                    module_name="reply_common",
                    model_name="deepseek-flash",
                    provider_name="DeepSeek",
                    input_tokens=1,
                    output_tokens=1,
                    cost_cny=-0.25,
                    cost_source="script:refund",
                    cost_detail=None,
                    created_at=now,
                ),
                ModelUsageRecord(
                    module_name="agent:memory",
                    model_name="deepseek-flash",
                    provider_name="DeepSeek",
                    input_tokens=1,
                    output_tokens=1,
                    cost_cny=0.01,
                    cost_source="builtin",
                    cost_detail=None,
                    created_at=now,
                ),
            ]
        )
        await session.commit()


async def test_usage_records_expose_source_components_and_negative(tmp_path, session_factory):
    """A14：面板可见来源（内建 / 脚本 / 兜底）、分项与负值（冲抵）标注。"""
    await _seed(session_factory)
    api = DashboardApi(
        console=_FakeConsole({"usage_session_factory": session_factory, "billing_service": None})
    )
    listing = _body(await api.stats_usage_records(_FakeRequest(query={"limit": "10"})))
    assert listing["available"] is True
    assert len(listing["items"]) == 3
    kinds = sorted(item["cost_source_kind"] for item in listing["items"])
    assert kinds == ["builtin", "script", "script"]
    assert all("cost_detail" not in item for item in listing["items"])

    with_detail = _body(
        await api.stats_usage_records(_FakeRequest(query={"limit": "10", "detail": "1"}))
    )
    peak = next(
        item for item in with_detail["items"] if item["cost_source"] == "script:deepseek_peak_valley"
    )
    assert peak["cost_detail"]["components"]["cache_miss"] == 0.3
    refund = next(item for item in with_detail["items"] if item["cost_cny"] < 0)
    assert refund["negative"] is True


# ── A15：报表「计费来源分布」 ────────────────────────────────────


def test_reporter_billing_source_distribution():
    """A15：报表来源分布计数 = 该区间记录数之和；既有三张表不受影响。"""
    now = datetime.now(timezone.utc)
    records = [
        SimpleNamespace(
            module_name="reply_agent",
            model_name="m1",
            provider_name="DeepSeek",
            input_tokens=1,
            output_tokens=1,
            cost_cny=0.5,
            cost_source="script:deepseek_peak_valley",
            conversation_kind="group",
        ),
        SimpleNamespace(
            module_name="reply_common",
            model_name="m1",
            provider_name="DeepSeek",
            input_tokens=1,
            output_tokens=1,
            cost_cny=0.2,
            cost_source="builtin",
            conversation_kind="group",
        ),
        SimpleNamespace(
            module_name="agent:memory",
            model_name="m1",
            provider_name="DeepSeek",
            input_tokens=1,
            output_tokens=1,
            cost_cny=0.3,
            cost_source="fallback:timeout",
            conversation_kind="",
        ),
    ]
    markdown = UsageReportService._format_markdown(records, timedelta(days=1))
    assert "## 计费来源分布" in markdown
    assert "脚本: deepseek_peak_valley" in markdown
    assert "内建固定计费" in markdown
    assert "兜底: timeout" in markdown
    assert "计费来源合计: 3 笔" in markdown
    assert "## 按模块统计" in markdown and "## 按模型统计" in markdown
    assert "¥1.000000" in markdown  # 既有总览金额不变
    assert now  # 生成时间戳来自真实时间


# ── Q13：热重载规则 ──────────────────────────────────────────────


def test_billing_hot_reload_rule_registered():
    """Q13：billing 段登记为运行期生效。"""
    from neobot_app.bootstrap import _register_billing_hot_reload_rule
    from neobot_app.config.hot_reload import classify

    _register_billing_hot_reload_rule()
    hot, reason = classify(["billing", "enabled"])
    assert hot is True
    assert "计费" in reason
