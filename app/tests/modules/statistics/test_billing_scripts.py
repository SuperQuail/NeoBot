"""spec(4) Part A：计价脚本加载器 / 求值 / 模板同步（A1-A3、A7、A8、A11、A13、A16、A51）。"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from types import MappingProxyType, SimpleNamespace
from typing import Any

import pytest

from neobot_app.statistics.billing import (
    BillingService,
    build_billing_context,
    builtin_cost,
)
from neobot_chat.models import ModelPricing

BEIJING = timezone(timedelta(hours=8))


class RecordingLogger:
    """最小日志桩：记录 warning，供 A6/A8 断言「产生一条 warning」。"""

    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict]] = []

    def _log(self, level: str, message: Any, **kwargs: Any) -> None:
        self.records.append((level, str(message), kwargs))

    def debug(self, message: Any, **kwargs: Any) -> None:
        self._log("debug", message, **kwargs)

    def info(self, message: Any, **kwargs: Any) -> None:
        self._log("info", message, **kwargs)

    def warning(self, message: Any, **kwargs: Any) -> None:
        self._log("warning", message, **kwargs)

    def error(self, message: Any, **kwargs: Any) -> None:
        self._log("error", message, **kwargs)

    def bind(self, **_kwargs: Any) -> "RecordingLogger":
        return self

    def warnings(self) -> list[str]:
        return [message for level, message, _ in self.records if level == "warning"]


def make_config(*, enabled: bool = True, timeout_ms: int = 200, record_detail: bool = True):
    return SimpleNamespace(
        billing=SimpleNamespace(
            enabled=enabled,
            timeout_ms=timeout_ms,
            reload_on_change=True,
            record_detail=record_detail,
        )
    )


def make_service(tmp_path, *, enabled: bool = True, timeout_ms: int = 200, logger=None):
    return BillingService(
        config=make_config(enabled=enabled, timeout_ms=timeout_ms),
        logger=logger or RecordingLogger(),
        data_dir=tmp_path,
    )


def write_script(tmp_path, name: str, body: str, *, package: bool = False) -> None:
    target = tmp_path / "Billing"
    target.mkdir(parents=True, exist_ok=True)
    if package:
        (target / name).mkdir(parents=True, exist_ok=True)
        (target / name / "__init__.py").write_text(body, encoding="utf-8")
    else:
        (target / f"{name}.py").write_text(body, encoding="utf-8")


def context(**overrides):
    payload = dict(
        model_key="m1",
        model_name="deepseek-flash",
        provider="DeepSeek",
        model_type="chat",
        module="reply_agent",
        usage={"input_tokens": 1_000_000, "output_tokens": 1_000_000, "cache_hit_tokens": 0, "cache_miss_tokens": 0},
        pricing=ModelPricing(
            input_price_per_mtokens=1.0,
            output_price_per_mtokens=2.0,
            cache_hit_price_per_mtokens=0.1,
        ),
        settings=None,
        billing_config={},
        occurred_at=datetime(2026, 9, 9, 2, 0, tzinfo=timezone.utc),
    )
    payload.update(overrides)
    return build_billing_context(**payload)


# ── A1 / A2：峰谷定价 ─────────────────────────────────────────────


def test_peak_valley_ratio_is_two(tmp_path):
    """A1：同一模型同一用量，高峰与空闲金额之比 = 2.0 ± 1e-6。"""
    service = make_service(tmp_path)
    peak = service.preview(
        script_name="deepseek_peak_valley",
        ctx=context(occurred_at=datetime(2026, 9, 9, 2, 0, tzinfo=timezone.utc)),
    )
    idle = service.preview(
        script_name="deepseek_peak_valley",
        ctx=context(occurred_at=datetime(2026, 9, 9, 14, 0, tzinfo=timezone.utc)),
    )
    assert peak.source == "script:deepseek_peak_valley"
    assert idle.source == "script:deepseek_peak_valley"
    assert peak.cost_cny > 0
    assert idle.cost_cny == pytest.approx(peak.cost_cny * 0.5, rel=1e-9)
    assert peak.cost_cny / idle.cost_cny == pytest.approx(2.0, abs=1e-6)
    assert peak.components and "cache_miss" in peak.components
    assert "高峰" in peak.note and "空闲" in idle.note


@pytest.mark.parametrize(
    ("beijing_time", "is_peak"),
    [
        (datetime(2026, 9, 11, 18, 0, tzinfo=BEIJING), False),  # 周五 18:00 整 → 空闲
        (datetime(2026, 9, 12, 10, 0, tzinfo=BEIJING), False),  # 周六 → 空闲
        (datetime(2026, 9, 14, 9, 0, tzinfo=BEIJING), True),    # 周一 09:00 整 → 高峰
        (datetime(2026, 9, 9, 12, 0, tzinfo=BEIJING), False),   # 12:00 整 → 空闲
        (datetime(2026, 9, 9, 14, 0, tzinfo=BEIJING), True),    # 14:00 整 → 高峰
        (datetime(2026, 9, 9, 10, 0, tzinfo=BEIJING), True),    # 周三 10:00 → 高峰
        (datetime(2026, 9, 9, 22, 0, tzinfo=BEIJING), False),   # 周三 22:00 → 空闲
    ],
)
def test_peak_valley_boundaries(tmp_path, beijing_time, is_peak):
    """A2：12:00/14:00/18:00 整点与周末边界。"""
    service = make_service(tmp_path)
    usage = {"input_tokens": 0, "output_tokens": 1_000_000}
    pricing = ModelPricing(output_price_per_mtokens=1.0)
    peak_ctx = context(
        usage=usage,
        pricing=pricing,
        occurred_at=datetime(2026, 9, 9, 2, 0, tzinfo=timezone.utc),
    )
    peak_cost = service.preview(script_name="deepseek_peak_valley", ctx=peak_ctx).cost_cny
    got = service.preview(
        script_name="deepseek_peak_valley",
        ctx=context(usage=usage, pricing=pricing, occurred_at=beijing_time),
    )
    assert got.cost_cny == pytest.approx(peak_cost if is_peak else peak_cost * 0.5)


# ── A3：四种入口组合 ──────────────────────────────────────────────

FUNC_BODY = "def compute_cost(ctx):\n    return 1.5\n"
CLASS_BODY = (
    "class BillingPolicy:\n"
    "    def __init__(self, config=None, logger=None):\n"
    "        self.calls = 0\n"
    "    def compute(self, ctx):\n"
    "        self.calls += 1\n"
    "        return {\"cost_cny\": 2.5, \"components\": {\"x\": 2.5}, \"note\": \"cls\"}\n"
)


@pytest.mark.parametrize("package", [False, True])
@pytest.mark.parametrize("style", ["func", "class"])
def test_entry_styles(tmp_path, package, style):
    """A3：.py 与 <name>/__init__.py、函数式与类式均可加载生效。"""
    name = f"entry_{style}_{int(package)}"
    write_script(tmp_path, name, FUNC_BODY if style == "func" else CLASS_BODY, package=package)
    service = make_service(tmp_path)
    outcome = service.preview(script_name=name, ctx=context())
    assert outcome.source == f"script:{name}"
    assert outcome.cost_cny == pytest.approx(1.5 if style == "func" else 2.5)


# ── A7 / A8 / A9：兜底 ───────────────────────────────────────────


async def test_timeout_falls_back(tmp_path):
    """A7：脚本超时不返回 → 回落内建公式，且不阻塞超过 timeout_ms + 50ms。"""
    write_script(tmp_path, "slow", "import time\ndef compute_cost(ctx):\n    time.sleep(3)\n    return 99.0\n")
    service = make_service(tmp_path, timeout_ms=120)
    ctx = context()
    fallback = builtin_cost(
        input_tokens=1_000_000, output_tokens=1_000_000, cache_hit_tokens=0, cache_miss_tokens=0,
        pricing=ModelPricing(input_price_per_mtokens=1.0, output_price_per_mtokens=2.0),
    )
    started = time.perf_counter()
    outcome = await service.compute_cost(script_name="slow", ctx=ctx, fallback_cost=fallback)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    assert outcome.source == "fallback:timeout"
    assert outcome.cost_cny == pytest.approx(fallback)
    assert elapsed_ms <= 120 + 50


def test_missing_script_source(tmp_path):
    """A8：绑定了不存在的脚本 → fallback:missing，不抛异常。"""
    service = make_service(tmp_path)
    outcome = service.preview(script_name="not_there", ctx=context(), fallback_cost=3.0)
    assert outcome.source == "fallback:missing"
    assert outcome.cost_cny == pytest.approx(3.0)


def test_broken_script_source_and_warning(tmp_path):
    """A8：语法/运行错误 → fallback:error + 一条 warning，不抛异常。"""
    logger = RecordingLogger()
    write_script(tmp_path, "broken", "this is not python !!!\n")
    service = make_service(tmp_path, logger=logger)
    outcome = service.preview(script_name="broken", ctx=context(), fallback_cost=4.0)
    assert outcome.source == "fallback:error"
    assert outcome.cost_cny == pytest.approx(4.0)
    assert logger.warnings()


def test_missing_entry_point_is_error(tmp_path):
    """缺少 compute_cost / BillingPolicy → 加载失败（fallback:error）。"""
    write_script(tmp_path, "noentry", "VALUE = 1\n")
    service = make_service(tmp_path)
    outcome = service.preview(script_name="noentry", ctx=context(), fallback_cost=1.0)
    assert outcome.source == "fallback:error"


def test_invalid_return_values(tmp_path):
    """NaN / Inf / None / dict 缺 cost_cny → 一律非法。"""
    service = make_service(tmp_path)
    cases = {
        "nanval": "def compute_cost(ctx):\n    return float(\"nan\")\n",
        "infval": "def compute_cost(ctx):\n    return float(\"inf\")\n",
        "noneval": "def compute_cost(ctx):\n    return None\n",
        "nodict": "def compute_cost(ctx):\n    return {\"components\": {\"a\": 1}}\n",
    }
    for name, body in cases.items():
        write_script(tmp_path, name, body)
        outcome = service.preview(script_name=name, ctx=context(), fallback_cost=7.0)
        assert outcome.source == "fallback:error", name
        assert outcome.cost_cny == pytest.approx(7.0)


def test_string_and_component_salvage(tmp_path):
    """字符串金额接受；components 含非数值项时丢弃分项但保留金额。"""
    service = make_service(tmp_path)
    write_script(tmp_path, "strcost", "def compute_cost(ctx):\n    return \"1.25\"\n")
    assert service.preview(script_name="strcost", ctx=context()).cost_cny == pytest.approx(1.25)
    write_script(
        tmp_path,
        "badcomp",
        "def compute_cost(ctx):\n"
        "    return {\"cost_cny\": 9.0, \"components\": {\"a\": \"x\", \"b\": 1.0}}\n",
    )
    outcome = service.preview(script_name="badcomp", ctx=context())
    assert outcome.cost_cny == pytest.approx(9.0)
    assert outcome.components == {"b": 1.0}


def test_negative_cost_allowed(tmp_path):
    """A54 的脚本侧：负金额合法并原样返回，来源仍为 script:<name>。"""
    write_script(tmp_path, "refund", "def compute_cost(ctx):\n    return -0.5\n")
    service = make_service(tmp_path)
    outcome = service.preview(script_name="refund", ctx=context())
    assert outcome.cost_cny == pytest.approx(-0.5)
    assert outcome.source == "script:refund"


# ── A11：mtime 重载 ──────────────────────────────────────────────


async def test_reload_on_change_uses_new_logic(tmp_path):
    """A11：只改脚本文件内容 → 下一次求值即用新逻辑，无需重启。"""
    write_script(tmp_path, "changing", "def compute_cost(ctx):\n    return 1.0\n")
    service = make_service(tmp_path)
    first = await service.compute_cost(script_name="changing", ctx=context(), fallback_cost=0.0)
    assert first.cost_cny == pytest.approx(1.0)

    path = tmp_path / "Billing" / "changing.py"
    path.write_text("def compute_cost(ctx):\n    return 2.0\n", encoding="utf-8")
    # 显式推进 mtime_ns：Windows 上同一 tick 内两次写入可能拿到相同的纳秒时间戳
    future = time.time() + 5
    os.utime(path, (future, future))
    second = await service.compute_cost(script_name="changing", ctx=context(), fallback_cost=0.0)
    assert second.cost_cny == pytest.approx(2.0)


# ── A13：模板同步 ────────────────────────────────────────────────


def test_templates_synced_and_user_edits_preserved(tmp_path):
    """A13：两个模板存在；用户改过之后不被覆盖；删掉后会重新种下。"""
    make_service(tmp_path, enabled=False)
    billing_dir = tmp_path / "Billing"
    assert (billing_dir / "deepseek_peak_valley.py").exists()
    assert (billing_dir / "per_call.py").exists()

    user_edit = "# 我自己改过的峰谷脚本\nVALUE = 1\n"
    (billing_dir / "deepseek_peak_valley.py").write_text(user_edit, encoding="utf-8")
    make_service(tmp_path, enabled=False)  # 模拟再次启动
    assert (billing_dir / "deepseek_peak_valley.py").read_text(encoding="utf-8") == user_edit

    (billing_dir / "per_call.py").unlink()
    make_service(tmp_path, enabled=False)
    assert (billing_dir / "per_call.py").exists()


# ── A16：纯函数与只读 ctx ────────────────────────────────────────


async def test_context_is_readonly_and_pure(tmp_path):
    """A16：ctx 是只读映射，脚本无法改写；同一 ctx 重复求值结果恒等。"""
    write_script(
        tmp_path,
        "pure",
        "def compute_cost(ctx):\n"
        "    return {\"cost_cny\": ctx[\"usage\"][\"output_tokens\"] / 1e6, \"note\": ctx[\"billing_config\"].get(\"tag\", \"\")}\n",
    )
    service = make_service(tmp_path)
    ctx = context(billing_config={"tag": "abc"})
    assert isinstance(ctx, MappingProxyType)
    with pytest.raises(TypeError):
        ctx["model_key"] = "hacked"  # type: ignore[index]
    first = await service.compute_cost(script_name="pure", ctx=ctx, fallback_cost=0.0)
    second = await service.compute_cost(script_name="pure", ctx=ctx, fallback_cost=0.0)
    assert first.cost_cny == second.cost_cny
    assert first.note == "abc"
    assert ctx["model_key"] == "m1"


# ── A51：按次计费 ───────────────────────────────────────────────


def test_per_call_template_is_token_independent(tmp_path):
    """A51：金额恒为 price_per_call，与 token 数无关；同脚本不同价各自正确。"""
    service = make_service(tmp_path)
    cheap = service.preview(
        script_name="per_call",
        ctx=context(billing_config={"price_per_call": 0.01}, usage={"input_tokens": 1}),
    )
    pricey = service.preview(
        script_name="per_call",
        ctx=context(
            billing_config={"price_per_call": 0.02},
            usage={"input_tokens": 999_999, "output_tokens": 999_999},
        ),
    )
    assert cheap.cost_cny == pytest.approx(0.01)
    assert pricey.cost_cny == pytest.approx(0.02)
    assert cheap.components == {"per_call": 0.01}


def test_cost_detail_truncation_is_bounded(tmp_path):
    """§4.2：cost_detail 序列化超过 8192 字符即截断为合法 JSON，绝不因分项过大落库失败。"""
    from neobot_app.statistics.billing import MAX_COST_DETAIL_CHARS

    service = make_service(tmp_path)
    write_script(
        tmp_path,
        "bigcomp",
        "def compute_cost(ctx):\n"
        "    parts = {('k%04d' % i): float(i) for i in range(2000)}\n"
        "    return {\"cost_cny\": 1.0, \"components\": parts, \"note\": \"x\" * 500}\n",
    )
    outcome = service.preview(script_name="bigcomp", ctx=context())
    assert outcome.source == "script:bigcomp"
    assert outcome.detail_json is not None
    assert len(outcome.detail_json) <= MAX_COST_DETAIL_CHARS
    import json as _json

    parsed = _json.loads(outcome.detail_json)
    assert parsed.get("truncated") is True


def test_script_can_override_source(tmp_path):
    """§4.2：返回值里的 source 覆盖默认脚本名。"""
    service = make_service(tmp_path)
    write_script(
        tmp_path,
        "named",
        "def compute_cost(ctx):\n    return {\"cost_cny\": 1.0, \"source\": \"my_policy\"}\n",
    )
    outcome = service.preview(script_name="named", ctx=context())
    assert outcome.source == "script:my_policy"


async def test_disabled_service_returns_builtin_without_running_script(tmp_path):
    """R4/§4.2：enabled=false 时 compute_cost 直接走内建，不加载、不执行脚本。"""
    service = make_service(tmp_path, enabled=False)
    write_script(tmp_path, "boom", "raise RuntimeError(\"should never run\")\n")
    outcome = await service.compute_cost(
        script_name="boom", ctx=context(), fallback_cost=12.5
    )
    assert outcome.source == "builtin"
    assert outcome.cost_cny == pytest.approx(12.5)
    assert not service.list_scripts() or "boom" in service.list_scripts()
