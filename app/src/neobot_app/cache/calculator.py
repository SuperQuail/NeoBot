"""字符级缓存命中计算器(内建,无需 tokenizer/transformer 依赖)。

按 DeepSeek 上下文硬盘缓存机制模拟(前缀缓存单元模型),以字符代替 token:

落盘时机:
1. 请求结束位置落盘:每次请求的用户输入结束位置与模型输出结束位置,
   各产生一个缓存前缀单元。
2. 公共前缀检测落盘:检测到多次请求之间存在公共前缀时,将该公共前缀
   作为一个独立单元落盘。
3. 固定字符间隔落盘:长输入/长输出按固定字符间隔截取前缀单元,
   避免长前缀迟迟未到结束位置而完全无法缓存。

命中规则:
- 每条缓存前缀是一个独立完整单元;
- 后续请求只有在完整匹配某个已落盘单元时才能命中该单元;
- 一次请求最多命中一个最长匹配单元(取其字符数)。

其他特性:
- 全局共享:按供应商(provider_key)分组,同一供应商的请求一并处理;
- 缓存单元有过期时间(默认 30 分钟,config 可配置),过期后自动失效;
- 提供成本估算:缓存命中部分按 1/价格差价 计费,用于聊天管线的
  成本续用决策(仅聊天管线使用;记忆总结/子Agent/非聊天模型不接入)。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

# 公共前缀落盘的最小字符数(对应 token 版约 16 tokens,中文约 1.5 字符/token)
COMMON_PREFIX_MIN_CHARS = 32
# 固定间隔落盘步长(字符)
INTERVAL_CHARS = 512
# 单个供应商的缓存单元数量上限(防内存膨胀,按最近使用时间淘汰)
MAX_UNITS_PER_PROVIDER = 200


@dataclass
class CacheUnit:
    """一个已落盘的缓存前缀单元。"""

    prefix: str
    source: str  # request_end_user / request_end_output / common_prefix / interval
    created_at: float
    expires_at: float


@dataclass
class RequestRecord:
    """一次请求的缓存模拟结果。"""

    index: int
    input_chars: int
    output_chars: int
    hit_chars: int = 0
    hit_unit: str = ""
    miss_chars: int = 0
    cached_units_created: int = 0

    @property
    def hit_ratio(self) -> float:
        return self.hit_chars / self.input_chars if self.input_chars else 0.0


@dataclass
class CostEstimate:
    """一次请求(或续用决策)的成本估算。

    cost = miss_chars * 1 + hit_chars / price_difference
    """

    total_chars: int
    hit_chars: int
    miss_chars: int
    cost: float
    hit_unit: str = ""

    def cheaper_than_full_miss(self) -> bool:
        """命中后的成本是否低于全量未命中成本(即存在有效命中)。"""
        return self.hit_chars > 0 and self.cost < self.total_chars


# 内容中的角色边界转义:防止内容里的 "<user>" 等文本伪装成角色标签造成假命中;
# 同时转义 "|()" 等 calls 标记的结构字符与转义目标控制符自身,保证映射单射
# (内容含字面控制符时不会与转义结果混淆)。
# 所有目标均以 \x1c 为前缀,单遍 translate 替换,不重扫,可逆。
_ESCAPE_MAP = str.maketrans(
    {
        "<": "\x1c<",
        "|": "\x1c|",
        "(": "\x1c(",
        ")": "\x1c)",
        "\x1c": "\x1c\x1c",
        "\x1d": "\x1c\x1d",
        "\x1e": "\x1c\x1e",
        "\x1f": "\x1c\x1f",
    }
)


def _escape_content(text: str) -> str:
    if not any(ch in text for ch in "<|()\x1c\x1d\x1e\x1f"):
        return text
    return text.translate(_ESCAPE_MAP)


def serialize_messages(messages: list[dict]) -> str:
    """把发给 LLM 的 messages 序列化为确定性的字符前缀序列。

    角色以 <role> 标签区分,内容中的 "<" 被转义,避免内容伪装角色边界;
    tool_calls 与普通内容按各自文本序列化。同一会话内序列化方式必须保持一致。
    """
    parts: list[str] = []
    for message in messages:
        role = str(message.get("role") or "")
        content = message.get("content")
        if content is None:
            tool_calls = message.get("tool_calls")
            if tool_calls:
                call_parts: list[str] = []
                for tc in tool_calls:
                    fn = tc.get("function", {}) if isinstance(tc, dict) else {}
                    call_parts.append(
                        _escape_content(str(fn.get("name", "")))
                        + "("
                        + _escape_content(str(fn.get("arguments", "")))
                        + ")"
                    )
                # calls 字符串的片段已逐段转义,结构括号/分隔符保持原样,
                # 不再整体二次转义(与 serialize_response_text 格式一致)
                content = "calls:" + "|".join(call_parts)
            else:
                content = ""
        elif not isinstance(content, str):
            # 多模态等非文本内容:固定占位符(避免 repr 的键序敏感与长度失真)
            content = "[非文本]"
        else:
            content = _escape_content(content)
        parts.append(f"<{role}>{content}")
    return "".join(parts)


def serialize_response_text(response: dict) -> str:
    """把模型响应序列化为输出文本,格式与 serialize_messages 中的 assistant 消息一致。

    - 有文本内容:与下一轮历史中该 assistant 消息的序列化完全相同
    - 仅有 tool_calls:与历史中 assistant tool_calls 消息的序列化相同
    角色键缺失时与 serialize_messages 用同一规则(缺省为无标签),保证
    request_end_output 单元是下一轮输入的字面前缀。
    """
    role = str(response.get("role") or "")
    content = response.get("content")
    if content is None:
        parts: list[str] = []
        for tc in response.get("tool_calls") or []:
            fn = tc.get("function", {}) if isinstance(tc, dict) else {}
            parts.append(
                _escape_content(str(fn.get("name", "")))
                + "("
                + _escape_content(str(fn.get("arguments", "")))
                + ")"
            )
        if parts:
            return f"<{role}>calls:{'|'.join(parts)}"
        return f"<{role}>"
    if isinstance(content, str):
        return f"<{role}>{_escape_content(content)}"
    return f"<{role}>[非文本]"


class CacheCalculator:
    """全局聊天管线缓存命中计算器(字符级)。"""

    def __init__(
        self,
        *,
        retention_seconds: float = 1800.0,
        price_difference: float = 120.0,
        logger: Any = None,
        now_fn: Callable[[], float] = time.time,
    ) -> None:
        self.retention_seconds = float(retention_seconds)
        self.price_difference = max(1.0, float(price_difference))
        self._logger = logger
        self._now = now_fn
        self._units: dict[str, list[CacheUnit]] = {}
        self._previous_input: dict[str, str] = {}
        self._record_count: dict[str, int] = {}

    # ── 对外接口 ──

    def record(
        self,
        provider_key: str,
        input_text: str,
        output_text: str = "",
    ) -> RequestRecord:
        """记录一次请求(聊天管线每次模型调用),执行命中检测与落盘。"""
        now = self._now()
        self._prune_expired(provider_key, now)
        units = self._units.setdefault(provider_key, [])
        index = self._record_count.get(provider_key, 0)
        self._record_count[provider_key] = index + 1

        record = RequestRecord(
            index=index,
            input_chars=len(input_text),
            output_chars=len(output_text),
        )

        # 1. 命中检测:找最长完整匹配的已落盘单元
        hit_chars, hit_unit = self._longest_match(units, input_text)
        record.hit_chars = hit_chars
        record.hit_unit = hit_unit
        record.miss_chars = max(0, len(input_text) - hit_chars)

        created = 0
        # 2a. 请求结束位置落盘(用户输入结束位置)
        if input_text:
            if self._add_unit(units, input_text, "request_end_user", now):
                created += 1
        # 2b. 请求结束位置落盘(模型输出结束位置)
        if output_text:
            if self._add_unit(units, input_text + output_text, "request_end_output", now):
                created += 1

        # 2c. 公共前缀检测落盘
        previous_input = self._previous_input.get(provider_key)
        if previous_input:
            common = self._common_prefix(previous_input, input_text)
            if len(common) >= COMMON_PREFIX_MIN_CHARS and len(common) < len(input_text):
                if self._add_unit(units, common, "common_prefix", now):
                    created += 1

        # 2d/2e. 固定字符间隔落盘(长输入/长输出)。
        # 单侧 interval 单元数设上限(输入/输出各 24),过长输入会产生数百个
        # 前缀副本,既浪费内存,又会淹没单元预算;完整单元覆盖其字面前缀,
        # 间隔单元仅在"请求未完成时也能部分命中"上有边际价值。
        max_interval_per_side = 24
        max_interval_unit_chars = 60_000

        def _add_interval_units(
            prefix_of: str, total: int, created_count: list[int]
        ) -> None:
            for cut in range(INTERVAL_CHARS, total, INTERVAL_CHARS):
                if created_count[0] >= max_interval_per_side:
                    break
                if cut > max_interval_unit_chars:
                    break
                if self._add_unit(units, prefix_of[:cut], "interval", now):
                    created_count[0] += 1

        _input_interval_created = [0]
        _add_interval_units(input_text, len(input_text), _input_interval_created)
        created += _input_interval_created[0]
        if output_text:
            _output_interval_created = [0]
            # 输出侧间隔单元 = 输入 + 输出前缀(切点在输出段内)
            for cut in range(INTERVAL_CHARS, len(output_text), INTERVAL_CHARS):
                if _output_interval_created[0] >= max_interval_per_side:
                    break
                if len(input_text) + cut > max_interval_unit_chars:
                    break
                if self._add_unit(
                    units, input_text + output_text[:cut], "interval", now
                ):
                    _output_interval_created[0] += 1
            created += _output_interval_created[0]

        record.cached_units_created = created

        # 仅在新建过单元时才触发 trim(上限未满或本次无新增时无需排序)
        if created > 0:
            self._trim_units(units)
        self._previous_input[provider_key] = input_text + output_text
        return record

    def estimate_cost(self, provider_key: str, text: str) -> CostEstimate:
        """按当前缓存状态估算一次请求的成本(不落盘、不修改状态)。"""
        now = self._now()
        self._prune_expired(provider_key, now)
        units = self._units.get(provider_key) or []
        hit_chars, hit_unit = self._longest_match(units, text)
        total = len(text)
        miss = max(0, total - hit_chars)
        cost = miss + hit_chars / self.price_difference
        return CostEstimate(
            total_chars=total,
            hit_chars=hit_chars,
            miss_chars=miss,
            cost=cost,
            hit_unit=hit_unit,
        )

    def hit_chars_for(self, provider_key: str, text: str) -> int:
        return self.estimate_cost(provider_key, text).hit_chars

    def reset(self) -> None:
        """清空全部缓存状态(测试/热重载用)。"""
        self._units.clear()
        self._previous_input.clear()
        self._record_count.clear()

    def summary(self, provider_key: str) -> dict[str, Any]:
        """单个供应商的缓存状态摘要。"""
        units = self._units.get(provider_key) or []
        counts: dict[str, int] = {}
        for unit in units:
            counts[unit.source] = counts.get(unit.source, 0) + 1
        return {
            "provider_key": provider_key,
            "units": len(units),
            "units_by_source": counts,
            "records": self._record_count.get(provider_key, 0),
            "retention_seconds": self.retention_seconds,
            "price_difference": self.price_difference,
        }

    # ── 内部实现 ──

    def _add_unit(
        self, units: list[CacheUnit], prefix: str, source: str, now: float
    ) -> bool:
        if not prefix:
            return False
        for unit in units:
            if unit.prefix == prefix:
                return False
        units.append(
            CacheUnit(
                prefix=prefix,
                source=source,
                created_at=now,
                expires_at=now + self.retention_seconds,
            )
        )
        return True

    def _longest_match(self, units: list[CacheUnit], text: str) -> tuple[int, str]:
        best_length = 0
        best_source = ""
        for unit in units:
            unit_len = len(unit.prefix)
            if unit_len <= best_length or unit_len > len(text):
                continue
            if text.startswith(unit.prefix):
                best_length = unit_len
                best_source = unit.source
        return best_length, best_source

    @staticmethod
    def _common_prefix(a: str, b: str) -> str:
        # C 级短路:上一轮输入通常是本轮输入的前缀(管线内 append-only)
        if b.startswith(a):
            return a
        limit = min(len(a), len(b))
        for i in range(limit):
            if a[i] != b[i]:
                return a[:i]
        return a[:limit]

    def _prune_expired(self, provider_key: str, now: float) -> None:
        units = self._units.get(provider_key)
        if not units:
            return
        kept = [u for u in units if u.expires_at > now]
        if len(kept) != len(units):
            self._units[provider_key] = kept

    def _trim_units(self, units: list[CacheUnit]) -> None:
        """超过上限时淘汰:按来源优先级(request_end > common_prefix > interval),
        同优先级按落盘时间保留最新的。保证完整单元不被间隔单元挤掉。"""
        if len(units) <= MAX_UNITS_PER_PROVIDER:
            return
        priority = {"request_end_user": 0, "request_end_output": 0, "common_prefix": 1}
        units.sort(
            key=lambda u: (priority.get(u.source, 2), -u.created_at),
        )
        del units[MAX_UNITS_PER_PROVIDER:]
