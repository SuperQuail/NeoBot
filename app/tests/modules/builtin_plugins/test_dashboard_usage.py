"""面板用量图表接口：/api/series/usage 的聚合结果。"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from neobot_app.builtin_plugins.dashboard.config import DashboardConfig
from neobot_app.builtin_plugins.dashboard.server import DashboardServer
from neobot_app.panel_auth import PanelPasswordStore
from neobot_storage import create_engine
from neobot_storage.models import Base, ModelUsageRecord

from test_dashboard_api import PASSWORD, _FakeAdapter, _FakeControl, _free_port, _login


class _NullLogger:
    def debug(self, *args, **kwargs) -> None: ...
    def info(self, *args, **kwargs) -> None: ...
    def warning(self, *args, **kwargs) -> None: ...
    def error(self, *args, **kwargs) -> None: ...
    def exception(self, *args, **kwargs) -> None: ...


class _Services:
    def __init__(self, mapping: dict) -> None:
        self._mapping = mapping

    def get(self, name: str, default=None):
        return self._mapping.get(name, default)


def _record(*, model: str, provider: str, module: str, tokens: int, cost: float, at: dt.datetime):
    return ModelUsageRecord(
        module_name=module,
        model_name=model,
        provider_name=provider,
        input_tokens=tokens,
        output_tokens=tokens // 2,
        cache_hit_tokens=0,
        cache_miss_tokens=tokens,
        cost_cny=cost,
        created_at=at,
    )


@pytest.fixture()
async def usage_panel(tmp_path: Path):
    engine = create_engine(f"sqlite+aiosqlite:///{(tmp_path / 'usage.sqlite3').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = dt.datetime.now(dt.timezone.utc)
    async with session_factory() as session:
        session.add_all(
            [
                _record(
                    model="deepseek-v4-pro",
                    provider="DeepSeek",
                    module="chat",
                    tokens=1000,
                    cost=0.5,
                    at=now - dt.timedelta(minutes=30),
                ),
                _record(
                    model="deepseek-v4-flash-max",
                    provider="DeepSeek",
                    module="agent",
                    tokens=2000,
                    cost=0.25,
                    at=now - dt.timedelta(hours=5),
                ),
                _record(
                    model="deepseek-v4-flash-max",
                    provider="DeepSeek",
                    module="agent",
                    tokens=500,
                    cost=0.05,
                    at=now - dt.timedelta(days=3),
                ),
            ]
        )
        await session.commit()

    config_path = tmp_path / "config.toml"
    config_path.write_text('version = "0.6.0"\n', encoding="utf-8")
    env_path = tmp_path / ".env"
    env_path.write_text("DeepSeek_APIKey=sk-super-secret\n", encoding="utf-8")
    data_dir = tmp_path / "data"
    PanelPasswordStore(data_dir / "auth.json").set_password(PASSWORD)

    server = DashboardServer(
        plugin_name="dashboard",
        config=DashboardConfig(host="127.0.0.1", port=_free_port()),
        data_dir=data_dir,
        logger=_NullLogger(),
        adapter=_FakeAdapter(),
        plugin_control=_FakeControl(),
        services=_Services({"usage_session_factory": session_factory}),
        config_path=config_path,
        env_path=env_path,
        backup_dir=tmp_path / "backup",
    )
    await server.start()
    try:
        yield f"http://127.0.0.1:{server.bound_port}"
    finally:
        await server.stop()
        await engine.dispose()


async def test_series_usage_aggregates_cost_and_tokens(usage_panel) -> None:
    base = usage_panel
    token, _ = await _login(base)
    async with httpx.AsyncClient() as client:
        response = await client.get(
            base + "/api/series/usage?hours=24&bucket=hour", headers={"X-Token": token}
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["available"] is True
    assert payload["bucket"] == "hour"
    assert payload["currency"] == "CNY"
    assert payload["totals"]["calls"] == 2
    assert payload["totals"]["input_tokens"] == 3000
    assert payload["totals"]["output_tokens"] == 1500
    assert payload["totals"]["cost_cny"] == pytest.approx(0.75)
    assert len(payload["points"]) == 2
    assert {item["model_name"] for item in payload["models"]} == {
        "deepseek-v4-pro",
        "deepseek-v4-flash-max",
    }
    top = payload["models"][0]
    assert top["model_name"] == "deepseek-v4-pro"
    assert top["provider_name"] == "DeepSeek"
    assert {item["module_name"] for item in payload["modules"]} == {"chat", "agent"}


async def test_series_usage_supports_day_bucket(usage_panel) -> None:
    base = usage_panel
    token, _ = await _login(base)
    async with httpx.AsyncClient() as client:
        response = await client.get(
            base + "/api/series/usage?hours=96&bucket=day", headers={"X-Token": token}
        )

    payload = response.json()
    assert payload["bucket"] == "day"
    assert payload["totals"]["calls"] == 3
    assert all(len(point["at"]) == 10 for point in payload["points"])


async def test_series_usage_without_database_reports_unavailable(tmp_path: Path) -> None:
    from test_dashboard_api import _start_panel

    server, _, base, _ = await _start_panel(tmp_path)
    try:
        token, _ = await _login(base)
        async with httpx.AsyncClient() as client:
            response = await client.get(
                base + "/api/series/usage", headers={"X-Token": token}
            )
        payload = response.json()
        assert payload["available"] is False
        assert payload["points"] == []
    finally:
        await server.stop()
