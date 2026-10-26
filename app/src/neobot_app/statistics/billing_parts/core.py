"""计费脚本的纯数据模型与上下文构造（内置脚本 / 设置 / 结果 / ctx）。"""

from __future__ import annotations

import copy
import json
import math
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping

from .constants import (
    SOURCE_BUILTIN,
    MAX_COST_DETAIL_CHARS,
    DEFAULT_TIMEOUT_MS,
    _USAGE_KEYS,
    _DEEPSEEK_PEAK_WINDOWS,
    _DEEPSEEK_OFF_PEAK_RATIO,
)

def builtin_deepseek_peak_valley(ctx: Mapping[str, Any]) -> dict[str, Any]:
    """DeepSeek 峰谷计价（**内置**脚本）。

    口径来源：https://api-docs.deepseek.com/zh-cn/quick_start/pricing/
    高峰 = 北京时间周一至周五 09:00-12:00、14:00-18:00；其余为空闲；空闲价 = 高峰价 ×0.5。

    **模型条目的 pricing 要填高峰价**（默认模型库就是这么填的）；填均价会让金额系统性偏小。

    为什么不放在 <DATA_DIR>/Billing/ 里当模板：默认模型库本来就要求按峰谷折算，
    而模板文件可能没同步、被误删或改坏 —— 放代码里就没有这些失败面。
    用户若在 <DATA_DIR>/Billing/ 放了同名脚本，**用户脚本优先**（见 `_load_policy`）。

    节假日不特殊处理：官方口径里法定节假日全天算空闲，而节假日表无法离线维护；
    真要精确到节假日，写个同名用户脚本覆盖即可。
    """
    occurred_at = datetime.fromisoformat(str(ctx["occurred_at"]))
    now = occurred_at.astimezone(timezone(timedelta(hours=8)))
    is_peak = now.weekday() < 5 and any(
        start <= now.time() < end for start, end in _DEEPSEEK_PEAK_WINDOWS
    )
    ratio = 1.0 if is_peak else _DEEPSEEK_OFF_PEAK_RATIO

    usage = ctx.get("usage") or {}
    pricing = ctx.get("pricing") or {}
    hit = usage.get("cache_hit_tokens") or 0
    miss = usage.get("cache_miss_tokens") or usage.get("input_tokens") or 0
    out = usage.get("output_tokens") or 0
    parts = {
        "cache_hit": hit * float(pricing.get("cache_hit_price_per_mtokens") or 0.0) / 1e6,
        "cache_miss": miss * float(pricing.get("input_price_per_mtokens") or 0.0) / 1e6,
        "output": out * float(pricing.get("output_price_per_mtokens") or 0.0) / 1e6,
    }
    window = "高峰" if is_peak else "空闲 ×0.5"
    return {
        "cost_cny": sum(parts.values()) * ratio,
        "components": {key: round(value * ratio, 8) for key, value in parts.items()},
        "note": window + " @ " + now.strftime("%Y-%m-%d %H:%M") + " CST",
    }


#: 内置计价脚本表：名字 -> compute(ctx)。`billing_script` 命中且**没有**同名用户脚本时生效。
BUILTIN_SCRIPTS: Mapping[str, Callable[[Mapping[str, Any]], Any]] = {
    "deepseek_peak_valley": builtin_deepseek_peak_valley,
}


def builtin_cost(
    *,
    input_tokens: int,
    output_tokens: int,
    cache_hit_tokens: int,
    cache_miss_tokens: int,
    pricing: Any,
) -> float:
    """内建线性计费公式（**逐字**保留改造前 tracker.py 的实现）。"""
    effective_cache_miss = cache_miss_tokens if cache_miss_tokens > 0 else input_tokens
    return (
        cache_hit_tokens * float(getattr(pricing, "cache_hit_price_per_mtokens", 0.0) or 0.0)
        + effective_cache_miss * float(getattr(pricing, "input_price_per_mtokens", 0.0) or 0.0)
        + output_tokens * float(getattr(pricing, "output_price_per_mtokens", 0.0) or 0.0)
    ) / 1_000_000.0


@dataclass(frozen=True, slots=True)
class BillingSettings:
    """[billing] 段的运行时视图。"""

    enabled: bool = False
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    reload_on_change: bool = True
    record_detail: bool = True

    @property
    def timeout_seconds(self) -> float:
        return max(1, int(self.timeout_ms)) / 1000.0

    @classmethod
    def from_config(cls, config: Any) -> "BillingSettings":
        section = getattr(config, "billing", None) if config is not None else None
        if section is None:
            return cls()
        return cls(
            enabled=bool(getattr(section, "enabled", False)),
            timeout_ms=_coerce_int(
                getattr(section, "timeout_ms", DEFAULT_TIMEOUT_MS), DEFAULT_TIMEOUT_MS
            ),
            reload_on_change=bool(getattr(section, "reload_on_change", True)),
            record_detail=bool(getattr(section, "record_detail", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "timeout_ms": self.timeout_ms,
            "reload_on_change": self.reload_on_change,
            "record_detail": self.record_detail,
        }


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True, slots=True)
class BillingOutcome:
    """一次计费求值的结果（含来源与分项）。"""

    cost_cny: float
    source: str = SOURCE_BUILTIN
    components: Mapping[str, float] | None = None
    note: str = ""
    detail_json: str | None = None
    elapsed_ms: float = 0.0
    error: str = ""

    @property
    def is_script(self) -> bool:
        return self.source.startswith("script:")

    def to_payload(self) -> dict[str, Any]:
        """面板 preview 用的载荷（分项为已解析的 dict）。"""
        return {
            "cost_cny": self.cost_cny,
            "source": self.source,
            "components": dict(self.components) if self.components else {},
            "note": self.note,
            "elapsed_ms": round(self.elapsed_ms, 4),
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class _LoadedPolicy:
    name: str
    path: Path
    mtime_ns: int
    size: int
    compute: Callable[[Mapping[str, Any]], Any]


@dataclass
class _ScriptStat:
    """面板展示用的加载 / 求值状态。"""

    name: str
    path: str = ""
    ok: bool = False
    error: str = ""
    loaded_at: str = ""
    elapsed_ms: float = 0.0
    reload_count: int = 0
    #: 最近一次求值（含兜底）耗时与来源，供 GET /api/config/billing 展示
    last_eval_ms: float = 0.0
    last_source: str = ""
    eval_count: int = 0
    fallback_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "ok": self.ok,
            "error": self.error,
            "loaded_at": self.loaded_at,
            "elapsed_ms": round(self.elapsed_ms, 4),
            "reload_count": self.reload_count,
            "last_eval_ms": round(self.last_eval_ms, 4),
            "last_source": self.last_source,
            "eval_count": self.eval_count,
            "fallback_count": self.fallback_count,
        }


def freeze_context(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """把脚本输入冻结成只读映射（顶层 MappingProxyType + 深拷贝）。

    传副本而非引用，脚本即使改写嵌套结构也不会污染调用方状态。
    """
    return MappingProxyType({str(key): copy.deepcopy(value) for key, value in payload.items()})


def _plain(value: Any) -> Any:
    """把 dataclass / 映射转成脚本可直接读取的纯数据。"""
    if is_dataclass(value) and not isinstance(value, type):
        try:
            return asdict(value)
        except Exception:  # pragma: no cover - asdict 对常规 dataclass 不会失败
            return {}
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    return value


def build_billing_context(
    *,
    model_key: str,
    model_name: str,
    provider: str,
    model_type: str,
    module: str,
    usage: Mapping[str, Any],
    pricing: Any,
    settings: Any,
    billing_config: Mapping[str, Any] | None = None,
    conversation_kind: str = "",
    conversation_id: str = "",
    occurred_at: datetime | None = None,
) -> Mapping[str, Any]:
    """组装脚本 ctx（字段清单见 spec §4.2）。"""
    moment = occurred_at or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    local = moment.astimezone()
    usage_payload = {
        key: usage.get(key) for key in _USAGE_KEYS if isinstance(usage, Mapping) and key in usage
    }
    payload: dict[str, Any] = {
        "model_key": str(model_key or ""),
        "model_name": str(model_name or ""),
        "provider": str(provider or ""),
        "model_type": str(model_type or "chat"),
        "module": str(module or ""),
        "usage": usage_payload,
        "pricing": _plain(pricing),
        "settings": _plain(settings),
        "billing_config": dict(billing_config or {}),
        "conversation": {"kind": str(conversation_kind or ""), "id": str(conversation_id or "")},
        "occurred_at": moment.isoformat(),
        "local_time": local.isoformat(),
        "tzname": local.tzname() or "",
    }
    return freeze_context(payload)


def _serialize_detail(payload: Mapping[str, Any]) -> str:
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(text) <= MAX_COST_DETAIL_CHARS:
        return text
    head = json.dumps(
        {"truncated": True, "components": payload.get("components", {})},
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    if len(head) > MAX_COST_DETAIL_CHARS:
        head = json.dumps({"truncated": True}, separators=(",", ":"))
    return head[:MAX_COST_DETAIL_CHARS]


def _to_finite_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except (TypeError, ValueError):
            return None
    else:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number
