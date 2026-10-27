"""可脚本化的消耗计费（spec(4) Part A）。

设计要点（见 ``features/spec(4)-scripted-billing-and-model-params/description.md`` §4.1-§4.4）：

- 计价脚本放在 ``<DATA_DIR>/Billing/``，按名加载（``<name>.py`` 或 ``<name>/__init__.py``），
  加载写法照抄 ``neobot_app.willing.service``，另补三处 willing 没有的能力：
  ``st_mtime_ns + st_size`` 变更自动重载、执行超时、异常/非法值兜底；
- 脚本只做**纯计算**：框架只注入纯数据 ``ctx``（``MappingProxyType`` + 顶层深拷贝），
  不注入 provider / DB session / 服务对象（R7）；
- 默认关闭（``[billing].enabled=false``）：此时不加载任何脚本、不建线程池，
  全部模型走内建线性公式（``builtin_cost``，与改造前逐字相同）；
- 任何失败都**不抛异常、不中断落库**：脚本缺失/加载失败/抛异常/超时/返回值非法
  一律回落内建公式，并把来源写成 ``builtin`` / ``fallback:*``（R3/R6）。

实现按职责拆在 billing_parts（常量、纯数据模型与上下文、状态与面板投影、模板/脚本加载、求值与节流）；本模块保留 BillingService 聚合类、线程池门面与原有模块级名称的 re-export。
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from .billing_parts.base import BillingServiceBase
from .billing_parts.constants import (
    SOURCE_BUILTIN,
    SOURCE_MISSING,
    SOURCE_ERROR,
    SOURCE_TIMEOUT,
    MAX_COST_DETAIL_CHARS,
    DEFAULT_TIMEOUT_MS,
    BILLING_MAX_WORKERS,
    BILLING_MAX_INFLIGHT,
    _USAGE_KEYS,
    _TEMPLATE_MANIFEST,
    _BUILTIN_PATH,
    _DEEPSEEK_PEAK_WINDOWS,
    _DEEPSEEK_OFF_PEAK_RATIO,
    _TEMPLATES_DIR,
)
from .billing_parts.core import (
    builtin_deepseek_peak_valley,
    BUILTIN_SCRIPTS,
    builtin_cost,
    BillingSettings,
    _coerce_int,
    BillingOutcome,
    _LoadedPolicy,
    _ScriptStat,
    freeze_context,
    _plain,
    build_billing_context,
    _serialize_detail,
    _to_finite_float,
)
from .billing_parts.evaluate import EvaluateMixin
from .billing_parts.loader import LoaderMixin


#: 进程内共享的计价脚本线程池：脚本是同步函数，UsageTracker.record 走
#: loop.run_in_executor；[billing].enabled=false 时不创建（零开销）。
#: 放在门面便于测试替换（fixture 直接给模块的 _EXECUTOR 换一个新池）。
_EXECUTOR: ThreadPoolExecutor | None = None
_EXECUTOR_LOCK = threading.Lock()


def get_billing_executor() -> ThreadPoolExecutor:
    """惰性创建进程内专用计价线程池（默认 2 线程）。"""
    global _EXECUTOR
    with _EXECUTOR_LOCK:
        if _EXECUTOR is None:
            _EXECUTOR = ThreadPoolExecutor(
                max_workers=BILLING_MAX_WORKERS,
                thread_name_prefix="billing",
            )
        return _EXECUTOR


class BillingService(LoaderMixin, EvaluateMixin, BillingServiceBase):
    """<DATA_DIR>/Billing/ 脚本加载器 + 策略求值。"""


__all__ = [
    "SOURCE_BUILTIN",
    "SOURCE_MISSING",
    "SOURCE_ERROR",
    "SOURCE_TIMEOUT",
    "MAX_COST_DETAIL_CHARS",
    "DEFAULT_TIMEOUT_MS",
    "BILLING_MAX_WORKERS",
    "BILLING_MAX_INFLIGHT",
    "_USAGE_KEYS",
    "_TEMPLATES_DIR",
    "_TEMPLATE_MANIFEST",
    "_EXECUTOR",
    "_EXECUTOR_LOCK",
    "get_billing_executor",
    "_BUILTIN_PATH",
    "_DEEPSEEK_PEAK_WINDOWS",
    "_DEEPSEEK_OFF_PEAK_RATIO",
    "builtin_deepseek_peak_valley",
    "BUILTIN_SCRIPTS",
    "builtin_cost",
    "BillingSettings",
    "_coerce_int",
    "BillingOutcome",
    "_LoadedPolicy",
    "_ScriptStat",
    "freeze_context",
    "_plain",
    "build_billing_context",
    "_serialize_detail",
    "_to_finite_float",
    "BillingService",
]
