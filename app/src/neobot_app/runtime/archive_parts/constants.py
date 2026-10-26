"""档案自动总结的阈值与常量（spec(1) 容量治理 / spec(4) 手动压缩）。"""

from __future__ import annotations

COUNTER_TABLE = "memory_counter"
ITEM_ARCHIVE_TABLE = "item_archive"
MAX_STORED_MESSAGE_CHARS = 800
DEFAULT_PROMPT_SNIPPET_CHARS = 120
DEFAULT_MAX_TOOL_ROUNDS = 20
# 工具执行失败(未知工具/执行异常)累计达到该次数即中止本次总结，避免模型反复重试烧 token。
MAX_TOOL_FAILURES = 3
_TOOL_FAILURE_MARKERS = ("未知工具", "工具执行失败", "Tool error")
#: 计数器解析缓存的存活时间：缓存把「每条消息一次 DB 读 + json.loads」降到
#: 「每 30 秒一次」，同时保证外部对该行的修改（模型经 archive_crud 写
#: memory_counter、另一进程、人工改库）在有限时间内重新可见。
_COUNTER_CACHE_TTL_SECONDS = 30.0

# 总结失败后的冷却窗口：失败一次至少要等这么久才会再次尝试。
# 没有它时，计数器一旦越过间隔且总结持续失败，每条新消息都会重跑一整轮工具循环，
# 形成「每条消息 = 一次模型超时」的 token 风暴。
RETRY_BACKOFF_BASE_SECONDS = 60.0
# 连续失败时的退避上限，避免长时间完全不总结。
RETRY_BACKOFF_MAX_SECONDS = 900.0
# 退避翻倍的最大次数(1→2→4→8→16 倍)。
RETRY_BACKOFF_MAX_DOUBLINGS = 4
# 单次总结的总时长预算(秒)：超过即中止本轮并进入冷却，
# 避免多轮工具调用把一次总结拖成数十分钟。
# 取值要能装下至少两轮完整调用（第一轮工具调用 + 第二轮收尾）：单次调用超时
# 默认跟随模型的请求超时(常见 120 秒)再留余量，180 秒会让第二轮必然被腰斩。
DEFAULT_SUMMARY_BUDGET_SECONDS = 300.0
# 单次总结内层模型调用的超时(秒)，同时也是单轮上限。
# 仅作为兜底：配置 agent.memory.trigger.model_call_timeout_seconds 为 0（默认）时
# 跟随总结模型自身的请求超时，provider 不暴露超时时才用它。
DEFAULT_SUMMARY_CALL_TIMEOUT_SECONDS = 60.0
#: 自动模式(配置为 0)下给 provider 自身超时留的余量：让 httpx 先超时并返回可读错误，
#: 而不是被外层 wait_for 在模型仍在正常推理时掐断。
PROVIDER_TIMEOUT_MARGIN_SECONDS = 15.0
# 单条工具返回写入上下文的最大字符数。read_pending_messages 会返回 500 条消息全文，
# list_archive 会返回整条档案 value，原样追加会让之后每一轮都把这几百 KB 重发一遍。
MAX_TOOL_RESULT_CHARS = 4000
# 整个总结过程中保留的工具返回总量上限；超出后丢弃最早的工具返回。
MAX_TOOL_RESULT_TOTAL_CHARS = 60_000

# ── 档案长度硬上限（spec(1)）──
#: 「档案超限压缩」单次注入提示词的档案内容上限（字符）：超限档案在冷却/失败期间可能
#: 继续变大，全量塞进提示词会顶爆上下文；超过时保留首尾（头通常是总体概述、尾是最新
#: 内容），中间部分省略。
MAX_OVERFLOW_PROMPT_CHARS = 60_000
_ARCHIVE_PROMPT_OMITTED = "\n...[档案中间部分已省略，仅保留首尾用于压缩]...\n"
#: 失败退避表最多保留的条目数（防止长时间运行后无界增长）。
MAX_OVERFLOW_BACKOFF_ENTRIES = 512
#: 自动「档案超限压缩」的目标字符数：压缩到该值而非存储上限本身，给下一次写入
#: 留出余量；否则 agent 严格按上限压缩后会立刻再次超限。上限低于该值时以实际上限为准。
AUTO_COMPRESSION_TARGET_CHARS = 10_000

# ── 面板触发的手动 / 批量压缩（spec(4) Part C）──
#: 手动压缩目标字符数下限：低于它必然丢关键事实（R15 / §4.10.2）。
MIN_MANUAL_TARGET_CHARS = 200
#: max_total_chars=0（容量治理关闭）时手动压缩目标的兜底上限。
MANUAL_TARGET_FALLBACK_MAX_CHARS = 100_000
#: 一次批量压缩请求最多处理多少条超限档案（R20；逐条串行）。
MAX_BATCH_COMPRESS_ITEMS = 20
#: 手动压缩状态表的 FIFO 上限（进程内，重启即清空）。
MAX_MANUAL_TASKS = 50
#: 已结束的手动压缩记录保留多久（秒）：超过后下次访问时清理。
MANUAL_TASK_TTL_SECONDS = 1800.0
#: 用量统计里手动压缩的 conversation_kind（与自动的 archive_overflow 单列区分）。
MANUAL_COMPRESSION_USAGE_KIND = "archive_manual"
AUTO_COMPRESSION_USAGE_KIND = "archive_overflow"
#: 配置缺省时使用的超限压缩冷却秒数（与 AgentMemoryArchive 默认值一致）。
DEFAULT_OVERFLOW_COOLDOWN_SECONDS = 600.0
_TOOL_TRUNCATED_MARKER = "\n...[工具返回已截断，需要更多内容请缩小查询范围后重试]"
_TOOL_DROPPED_MARKER = "[已省略：更早的工具返回，避免上下文膨胀]"
