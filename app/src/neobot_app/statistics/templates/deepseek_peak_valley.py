# <DATA_DIR>/Billing/deepseek_peak_valley.py
# DeepSeek 峰谷定价（口径来源：https://api-docs.deepseek.com/zh-cn/quick_start/pricing/）
# 高峰 = 北京时间 周一至周五 09:00-12:00、14:00-18:00；其余为空闲；空闲价 = 高峰价 × 0.5
#
# 重要：模型条目的 pricing 请填**高峰价**（默认价目表就是高峰价）。
# 本脚本在空闲时段按 0.5 折算；若把 pricing 填成均价，金额会系统性偏小。
#
# 用法：模型条目 billing_script = "deepseek_peak_valley"，无需 billing_config。
from datetime import datetime, timedelta, timezone, time as dtime

PEAK_WINDOWS = ((dtime(9, 0), dtime(12, 0)), (dtime(14, 0), dtime(18, 0)))
OFF_PEAK_RATIO = 0.5


def _beijing(occurred_at_iso: str) -> datetime:
    return datetime.fromisoformat(occurred_at_iso).astimezone(timezone(timedelta(hours=8)))


def compute_cost(ctx):
    now = _beijing(ctx["occurred_at"])
    is_peak = now.weekday() < 5 and any(s <= now.time() < e for s, e in PEAK_WINDOWS)
    ratio = 1.0 if is_peak else OFF_PEAK_RATIO

    u, p = ctx["usage"], ctx["pricing"]
    hit = u.get("cache_hit_tokens") or 0
    miss = u.get("cache_miss_tokens") or u.get("input_tokens") or 0
    out = u.get("output_tokens") or 0
    parts = {
        "cache_hit": hit * (p.get("cache_hit_price_per_mtokens") or 0.0) / 1e6,
        "cache_miss": miss * (p.get("input_price_per_mtokens") or 0.0) / 1e6,
        "output": out * (p.get("output_price_per_mtokens") or 0.0) / 1e6,
    }
    window = "高峰" if is_peak else "空闲 ×0.5"
    return {
        "cost_cny": sum(parts.values()) * ratio,
        "components": {k: round(v * ratio, 8) for k, v in parts.items()},
        "note": window + " @ " + now.strftime("%Y-%m-%d %H:%M") + " CST",
    }
