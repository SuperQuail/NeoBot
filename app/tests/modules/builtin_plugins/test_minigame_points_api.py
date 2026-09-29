"""小游戏积分对外接口（spec(12) / docs/07-插件开发.md）。

覆盖三层：

1. **数据层** `MinigameService.apply_points`：加分 / 扣分 / 余额不足整笔不生效 /
   允许负分 / 场次胜场只在实际生效时累加；
2. **能力层** 四个能力（points.get / add / rank / describe）的入参校验、返回值契约、
   配置门控与单次上限；
3. **通道** 通过真实的 `DefaultPluginManager` + `PluginHandle.call` 调用，
   证明其它插件按公开路径（ctx.plugins.require(...).call(...)）确实能调到。

全部走真实 SQLite（临时目录），**不联网**。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from neobot_app.builtin_plugins import minigame
from neobot_app.builtin_plugins.minigame.config import MinigameConfig
from neobot_app.builtin_plugins.minigame.service import MinigameService
from neobot_modloader import DefaultPluginManager


class _NullLogger:
    def __init__(self) -> None:
        self.lines: list[tuple[str, str]] = []

    def debug(self, message: str = "", **kwargs: Any) -> None:
        self.lines.append(("debug", str(message)))

    def info(self, message: str = "", **kwargs: Any) -> None:
        self.lines.append(("info", str(message)))

    def warning(self, message: str = "", **kwargs: Any) -> None:
        self.lines.append(("warning", str(message)))

    def error(self, message: str = "", **kwargs: Any) -> None:
        self.lines.append(("error", str(message)))


@dataclass
class _FakeClock:
    value: datetime

    def __call__(self) -> datetime:
        return self.value

    def advance(self, **kwargs: Any) -> None:
        self.value = self.value + timedelta(**kwargs)


class _FakeMono:
    def __init__(self, value: float = 1000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


def _service(
    db: Any,
    clock: _FakeClock,
    *,
    config: MinigameConfig | None = None,
    seed: int = 20260927,
) -> MinigameService:
    return MinigameService(
        database=db,
        config=config or MinigameConfig(),
        clock=clock,
        rng=random.Random(seed),
        monotonic=_FakeMono(),
    )


@pytest.fixture
async def clock() -> _FakeClock:
    return _FakeClock(datetime(2026, 9, 27, 10, 0, 0))


@pytest.fixture
async def db(tmp_path):
    database = minigame.create_database()
    await database.bind(tmp_path / "databases")
    try:
        yield database
    finally:
        await database.close()


@pytest.fixture
async def runtime(db, clock, monkeypatch):
    """能力处理器依赖模块级单例：这里换成指向临时库的运行时。"""
    plugin = minigame.MinigamePlugin()
    plugin.config = MinigameConfig()
    plugin.service = _service(db, clock)
    plugin._logger = _NullLogger()
    monkeypatch.setattr(minigame, "_instance", plugin)
    return plugin


def _capability(name: str):
    capabilities = minigame.plugin.capabilities
    assert name in capabilities, f"未注册能力: {name}"
    return capabilities[name]


async def _call(name: str, payload: Any = None) -> dict[str, Any]:
    return await _capability(name)(payload)


# ── 数据层：apply_points ─────────────────────────────────────────


async def test_apply_points_adds_and_keeps_best_score(db, clock) -> None:
    service = _service(db, clock)

    first = await service.apply_points("2002", 5)
    assert first["applied"] == 5
    assert first["insufficient"] is False
    assert int(first["profile"]["score"]) == 5
    assert int(first["profile"]["best_score"]) == 5

    second = await service.apply_points("2002", -2)
    assert second["applied"] == -2
    assert int(second["profile"]["score"]) == 3
    assert int(second["profile"]["best_score"]) == 5, "扣分不回退最高分"


async def test_apply_points_counts_plays_and_wins_only_when_applied(db, clock) -> None:
    service = _service(db, clock)

    profile = await service.apply_points("2002", 10, play=True, win=True)
    assert (int(profile["profile"]["plays"]), int(profile["profile"]["wins"])) == (1, 1)

    rejected = await service.apply_points("2002", -50, play=True, win=True)
    assert rejected["insufficient"] is True
    assert (int(rejected["profile"]["plays"]), int(rejected["profile"]["wins"])) == (1, 1), (
        "整笔不生效时不能累加场次"
    )


async def test_apply_points_rejects_overspend_as_a_whole(db, clock) -> None:
    service = _service(db, clock)
    await service.apply_points("2002", 3)

    result = await service.apply_points("2002", -10)

    assert result["applied"] == 0
    assert result["insufficient"] is True
    assert int(result["profile"]["score"]) == 3, "余额不足时不做部分扣减，也不扣成负数"


async def test_repeated_overspend_never_goes_negative(db, clock) -> None:
    service = _service(db, clock)
    await service.apply_points("2002", 5)

    applied_total = 0
    for _ in range(10):
        result = await service.apply_points("2002", -2)
        applied_total += int(result["applied"])
    assert applied_total == -4
    assert int((await service.get_profile("2002"))["score"]) == 1


async def test_apply_points_allows_negative_when_explicitly_requested(db, clock) -> None:
    service = _service(db, clock)
    await service.apply_points("2002", 3)

    result = await service.apply_points("2002", -10, allow_negative=True)

    assert result["insufficient"] is False
    assert int(result["profile"]["score"]) == -7


async def test_apply_points_zero_is_a_noop(db, clock) -> None:
    service = _service(db, clock)
    await service.apply_points("2002", 4)

    result = await service.apply_points("2002", 0)

    assert (result["applied"], result["insufficient"]) == (0, False)
    assert int(result["profile"]["score"]) == 4


# ── 能力层：points.get ───────────────────────────────────────────


async def test_points_get_returns_profile_and_checkin_state(runtime, clock) -> None:
    await runtime.service.apply_points("2002", 12)
    await runtime.service.checkin("2002")

    data = await _call("points.get", {"user_id": "2002"})

    assert data["ok"] is True
    assert data["user_id"] == "2002"
    assert data["score"] >= 12
    assert data["streak"] == 1
    assert data["checked_in_today"] is True
    assert data["updated_at"], "附带 updated_at 便于调用方判断新鲜度"


async def test_points_get_creates_zero_account_for_unknown_user(runtime) -> None:
    data = await _call("points.get", {"user_id": 30001})

    assert data["score"] == 0
    assert data["plays"] == 0
    assert data["checked_in_today"] is False


async def test_points_get_requires_numeric_user_id(runtime) -> None:
    with pytest.raises(ValueError, match="缺少 user_id"):
        await _call("points.get", {})
    with pytest.raises(ValueError, match="数字 QQ 号"):
        await _call("points.get", {"user_id": "小明"})
    with pytest.raises(ValueError, match="数字 QQ 号"):
        await _call("points.get", {"user_id": "1" * 33})


# ── 能力层：points.add ──────────────────────────────────────────


async def test_points_add_applies_and_returns_balance(runtime) -> None:
    added = await _call("points.add", {"user_id": "2002", "delta": 10, "source": "shop"})

    assert added["ok"] is True
    assert added["applied"] == 10
    assert added["score"] == 10
    assert added["source"] == "shop"

    spent = await _call("points.add", {"user_id": "2002", "delta": -4, "source": "shop"})
    assert spent["ok"] is True
    assert spent["applied"] == -4
    assert spent["score"] == 6


async def test_points_add_reports_insufficient_without_changing_balance(runtime) -> None:
    await _call("points.add", {"user_id": "2002", "delta": 3})

    result = await _call("points.add", {"user_id": "2002", "delta": -5, "source": "shop"})

    assert result["ok"] is False
    assert result["reason"] == "insufficient"
    assert result["applied"] == 0
    assert result["score"] == 3
    assert (await _call("points.get", {"user_id": "2002"}))["score"] == 3


async def test_points_add_allow_negative_flag(runtime) -> None:
    result = await _call(
        "points.add",
        {"user_id": "2002", "delta": -5, "allow_negative": True, "note": "罚分"},
    )

    assert result["ok"] is True
    assert result["score"] == -5


async def test_points_add_rejects_bad_payloads(runtime) -> None:
    with pytest.raises(ValueError, match="缺少 delta"):
        await _call("points.add", {"user_id": "2002"})
    with pytest.raises(ValueError, match="delta 必须是整数"):
        await _call("points.add", {"user_id": "2002", "delta": "多给点"})
    # 小数不能被悄悄截断成整数；bool 也不是整数
    with pytest.raises(ValueError, match="delta 必须是整数"):
        await _call("points.add", {"user_id": "2002", "delta": 1.5})
    with pytest.raises(ValueError, match="delta 必须是整数"):
        await _call("points.add", {"user_id": "2002", "delta": True})
    with pytest.raises(ValueError, match="必须是布尔值"):
        await _call("points.add", {"user_id": "2002", "delta": 1, "allow_negative": "maybe"})


async def test_points_add_rejects_delta_above_config_limit(runtime) -> None:
    runtime.config = MinigameConfig(points_max_delta=10)

    with pytest.raises(ValueError, match="超过上限 10"):
        await _call("points.add", {"user_id": "2002", "delta": 11})
    with pytest.raises(ValueError, match="超过上限 10"):
        await _call("points.add", {"user_id": "2002", "delta": -11})

    ok = await _call("points.add", {"user_id": "2002", "delta": 10})
    assert ok["score"] == 10


async def test_points_add_can_be_disabled_by_config(runtime) -> None:
    runtime.config = MinigameConfig(points_allow_external_write=False)

    result = await _call("points.add", {"user_id": "2002", "delta": 50, "source": "shop"})

    assert result["ok"] is False
    assert result["reason"] == "disabled"
    assert result["score"] == 0
    # 读接口不受开关影响
    assert (await _call("points.get", {"user_id": "2002"}))["score"] == 0
    kinds = [kind for kind, _text in runtime._logger.lines]
    assert "warning" in kinds, "被拒的写入要留痕"


async def test_points_add_is_logged_with_source(runtime) -> None:
    await _call("points.add", {"user_id": "2002", "delta": 7, "source": "starship", "note": "跑商"})

    text = "\n".join(line for _kind, line in runtime._logger.lines)
    assert "user=2002" in text
    assert "source=starship" in text
    assert "note=跑商" in text


# ── 能力层：points.rank ─────────────────────────────────────────


async def test_points_rank_global_and_group(runtime) -> None:
    for uid, score in (("1", 30), ("2", 10), ("3", 20)):
        await runtime.service.apply_points(uid, score)
    await runtime.service.add_record(user_id="1", game_id="checkin", score=5, conversation_id="888")
    await runtime.service.add_record(user_id="2", game_id="checkin", score=3, conversation_id="888")

    global_rank = await _call("points.rank", {"page": 1, "page_size": 2})
    assert global_rank["scope"] == "global"
    assert global_rank["total"] == 3
    assert [row["user_id"] for row in global_rank["rows"]] == ["1", "3"]

    group_rank = await _call("points.rank", {"conversation_id": "888"})
    assert group_rank["scope"] == "group"
    assert group_rank["conversation_id"] == "888"
    assert [row["user_id"] for row in group_rank["rows"]] == ["1", "2"]


async def test_points_rank_validates_paging(runtime) -> None:
    with pytest.raises(ValueError, match="page 必须 >= 1"):
        await _call("points.rank", {"page": 0})
    with pytest.raises(ValueError, match="page_size 必须在 1-100"):
        await _call("points.rank", {"page_size": 101})


# ── 能力层：points.describe ─────────────────────────────────────


async def test_points_describe_lists_contract(runtime) -> None:
    data = await _call("points.describe", None)

    assert data["api"] == minigame.POINTS_API_NAME == "minigame.points"
    assert data["version"] == minigame.POINTS_API_VERSION
    assert data["capabilities"] == [
        "points.add",
        "points.describe",
        "points.get",
        "points.rank",
    ]
    assert data["allow_external_write"] is True
    assert data["max_delta"] == MinigameConfig().points_max_delta
    assert data["reject_when_insufficient"] is True


async def test_describe_reflects_config_switches(runtime) -> None:
    runtime.config = MinigameConfig(
        points_allow_external_write=False, points_max_delta=42
    )

    data = await _call("points.describe", {})

    assert data["allow_external_write"] is False
    assert data["max_delta"] == 42


# ── 通道：其它插件按公开路径调用 ─────────────────────────────────


async def test_other_plugin_calls_points_capability_through_registry(runtime) -> None:
    """真实路径：ctx.plugins.require("minigame").call("points.add", ...)。"""
    manager = DefaultPluginManager()
    manager.register(minigame.plugin, SimpleNamespace(plugin_name="minigame"))
    handle = manager.registry_view.get("minigame")
    assert handle is not None
    assert set(handle.capabilities) >= {"points.get", "points.add", "points.rank"}

    added = await handle.call("points.add", {"user_id": "2002", "delta": 8, "source": "spec12"})
    assert added["score"] == 8

    snapshot = await handle.call("points.get", {"user_id": "2002"})
    assert snapshot["score"] == 8

    with pytest.raises(KeyError, match="未导出能力"):
        await handle.call("points.mint", {"user_id": "2002", "delta": 1})


async def test_unloaded_plugin_reports_unavailable(runtime, monkeypatch) -> None:
    runtime.service = None

    with pytest.raises(RuntimeError, match="尚未加载"):
        await _call("points.get", {"user_id": "2002"})


async def test_points_write_is_not_exposed_to_the_model() -> None:
    """加分只能是插件之间的调用：模型工具表里不能出现任何写积分的工具。"""
    names = {registration.name for registration in minigame.plugin._tool_registrations}

    assert names == {
        "bottle_write",
        "bottle_pick",
        "chengyu_submit",
        "checkin",
        "fortune",
        "points",
        "help",
    }
    assert not any("add" in name or "set" in name for name in names)
