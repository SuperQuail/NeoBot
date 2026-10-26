"""计费脚本的常量：来源闭集、超时/并发上限与内置脚本口径。"""

from __future__ import annotations

from datetime import time as dtime
from pathlib import Path

#: 来源闭集（见 §4.4「新增列」表）
SOURCE_BUILTIN = "builtin"

SOURCE_MISSING = "fallback:missing"

SOURCE_ERROR = "fallback:error"

SOURCE_TIMEOUT = "fallback:timeout"

#: ``cost_detail`` 序列化后的字符上限；超过即截断（永不因分项过大导致落库失败）
MAX_COST_DETAIL_CHARS = 8192

#: 默认超时（毫秒）；与 ``[billing].timeout_ms`` 默认值一致
DEFAULT_TIMEOUT_MS = 200

#: 常驻线程池大小 / 允许同时在跑（或排队）的求值上限
BILLING_MAX_WORKERS = 2

BILLING_MAX_INFLIGHT = 2

#: 脚本可读取的 usage 原始量（其余键不透传，保持 ctx 边界清晰）
_USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_hit_tokens",
    "cache_miss_tokens",
    "completion_tokens_details",
)

#: 记录「本程序上次写入各模板的内容哈希」，用于判定用户是否改过模板文件
_TEMPLATE_MANIFEST = ".templates.json"

#: 内置计价脚本的哨兵路径：面板据此显示「随代码分发，不是用户脚本文件」
_BUILTIN_PATH = Path("<内置>")

#: DeepSeek 峰谷口径（北京时间；官方：周一至周五 09:00-12:00、14:00-18:00 为高峰）
_DEEPSEEK_PEAK_WINDOWS = ((dtime(9, 0), dtime(12, 0)), (dtime(14, 0), dtime(18, 0)))

_DEEPSEEK_OFF_PEAK_RATIO = 0.5

#: 模板脚本目录（随仓库分发，启动时同步到 <DATA_DIR>/Billing/）
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
