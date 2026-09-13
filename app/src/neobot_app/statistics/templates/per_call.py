# <DATA_DIR>/Billing/per_call.py
# 按次计费基础模板：每次调用固定金额，与 token 数无关。
# 用法：模型条目 billing_script = "per_call"
#       [models.registry.billing_config]
#       price_per_call = 0.01
#
# 同一个脚本可被任意多个模型复用，各自在 billing_config.price_per_call 填不同价格。


def compute_cost(ctx):
    price = float((ctx.get("billing_config") or {}).get("price_per_call") or 0.0)
    return {
        "cost_cny": price,
        "components": {"per_call": price},
        "note": "按次计费 " + str(price) + " CNY/次",
    }
