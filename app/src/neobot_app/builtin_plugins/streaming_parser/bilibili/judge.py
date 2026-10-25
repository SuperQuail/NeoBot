"""业务码判定。

对照参考：amagi packages/core/src/platforms/bilibili/judge.ts:21-60 与
packages/core/src/contracts/error.ts:271-306。

判定顺序与 amagi 一致：空响应体 → 非 JSON 文本 → 业务码 → HTTP 状态码。
有意保留的差异（改进项，见 docs/roadmap.md）：
- amagi 只对 -412 归入可重试风控；这里把 -352 / -509 也归入可重试，
  因为它们分别是「风控校验失败」和「请求过于频繁」（见 amagi packages/typegen/src/corpus.ts:232-243）。
- 空响应体不再判 COOKIE_EXPIRED（amagi judge.ts:23 的写法）：一次网络抖动就会
  把用户引去重新扫码，而空体更常见的原因是 WAF 拦断或连接被截断。这里按
  「平台暂时不可用 / 超时」处理并标为可重试（有状态码时以状态码为准）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: 错误大类，与 amagi 的 ErrorKind 对齐
KIND_AUTH = "auth"
KIND_RISK = "risk"
KIND_NOT_FOUND = "not_found"
KIND_RATE_LIMIT = "rate_limit"
KIND_TIMEOUT = "timeout"
KIND_UNAVAILABLE = "unavailable"
KIND_UNKNOWN = "unknown"

COOKIE_EXPIRED = "COOKIE_EXPIRED"
RISK_CONTROL = "RISK_CONTROL"
NOT_FOUND = "NOT_FOUND"
ANTIBOT_PAGE = "ANTIBOT_PAGE"
RATE_LIMITED = "RATE_LIMITED"
PLATFORM_UNAVAILABLE = "PLATFORM_UNAVAILABLE"
PLATFORM_ERROR = "PLATFORM_ERROR"

#: 平台返回码 → 判定
_PLATFORM_CODE_TABLE: dict[int, tuple[str, str, bool]] = {
    -412: (KIND_RISK, RISK_CONTROL, True),
    -101: (KIND_AUTH, COOKIE_EXPIRED, False),
    -404: (KIND_NOT_FOUND, NOT_FOUND, False),
    # 改进项：amagi 未特殊处理这两码（落到 unknown/PLATFORM_ERROR 且不重试）
    -352: (KIND_RISK, RISK_CONTROL, True),
    -509: (KIND_RATE_LIMIT, RATE_LIMITED, True),
}

#: 消息字段的提取顺序，与 amagi execute.ts:123-131 一致
_MESSAGE_KEYS = ("message", "status_msg", "msg", "error_msg")
#: 业务码字段的提取顺序，与 amagi execute.ts:144-152 一致
_CODE_KEYS = ("code", "status_code", "statusCode", "result")


@dataclass(frozen=True)
class Verdict:
    """一次响应的判定结果。ok 为真时其余字段无意义。"""

    ok: bool
    kind: str = ""
    code: str = ""
    message: str = ""
    retryable: bool = False
    platform_code: Any = None
    platform_message: str = ""
    http_status: int | None = None
    raw: Any = field(default=None, repr=False)


def _first_value(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return None


def _verdict_from_http_status(status: int | None) -> Verdict | None:
    """2xx 返回 None（表示「业务码说了算，没有 HTTP 层面的错误」）。"""
    if status is None or 200 <= status < 300:
        return None
    if status == 401:
        return Verdict(ok=False, kind=KIND_AUTH, code="LOGIN_REQUIRED", http_status=status)
    if status == 403:
        return Verdict(ok=False, kind=KIND_RISK, code=RISK_CONTROL, retryable=True, http_status=status)
    if status == 404:
        return Verdict(ok=False, kind=KIND_NOT_FOUND, code=NOT_FOUND, http_status=status)
    if status == 408:
        return Verdict(ok=False, kind=KIND_TIMEOUT, code="TIMEOUT", retryable=True, http_status=status)
    if status == 429:
        return Verdict(ok=False, kind=KIND_RATE_LIMIT, code=RATE_LIMITED, retryable=True, http_status=status)
    if 500 <= status < 600:
        return Verdict(ok=False, kind=KIND_UNAVAILABLE, code=PLATFORM_UNAVAILABLE, retryable=True, http_status=status)
    return Verdict(ok=False, kind=KIND_UNKNOWN, code=PLATFORM_ERROR, http_status=status)


def _verdict_from_empty_body(http_status: int | None) -> Verdict:
    """空响应体：WAF 拦断或连接被截断，不是登录失效。

    有明确 HTTP 状态码时按状态码判定（408 归超时、429 限流、5xx 不可用）；
    2xx 空体按「平台暂时不可用且可重试」处理——绝不能判成 COOKIE_EXPIRED，
    否则一次抖动就会让插件以为 cookie 失效、把用户引去重新扫码。
    """
    fallback = _verdict_from_http_status(http_status)
    if fallback is not None:
        return fallback
    return Verdict(
        ok=False,
        kind=KIND_UNAVAILABLE,
        code=PLATFORM_UNAVAILABLE,
        message="空响应体（WAF 拦截或连接被截断）",
        retryable=True,
        http_status=http_status,
    )


def judge(raw: Any, *, http_status: int | None = 200) -> Verdict:
    """对平台响应做判定。raw 可以是解析后的对象，也可以是原始文本。"""
    if raw is None or raw == "":
        return _verdict_from_empty_body(http_status)

    if isinstance(raw, str):
        # 非空字符串 = WAF / 反爬页，amagi 判为 risk 且可重试
        return Verdict(
            ok=False,
            kind=KIND_RISK,
            code=ANTIBOT_PAGE,
            retryable=True,
            message=raw[:200],
            http_status=http_status,
            raw=raw,
        )

    if not isinstance(raw, dict):
        fallback = _verdict_from_http_status(http_status)
        return fallback if fallback else Verdict(ok=True, raw=raw)

    platform_code = _first_value(raw, _CODE_KEYS)
    if platform_code is None or int(platform_code) == 0:
        fallback = _verdict_from_http_status(http_status)
        return fallback if fallback else Verdict(ok=True, raw=raw)

    message = str(_first_value(raw, _MESSAGE_KEYS) or "")
    mapped = _PLATFORM_CODE_TABLE.get(int(platform_code))
    if mapped is None:
        return Verdict(
            ok=False,
            kind=KIND_UNKNOWN,
            code=PLATFORM_ERROR,
            message=message,
            platform_code=platform_code,
            platform_message=message,
            http_status=http_status,
            raw=raw,
        )
    kind, code, retryable = mapped
    return Verdict(
        ok=False,
        kind=kind,
        code=code,
        message=message,
        retryable=retryable,
        platform_code=platform_code,
        platform_message=message,
        http_status=http_status,
        raw=raw,
    )

