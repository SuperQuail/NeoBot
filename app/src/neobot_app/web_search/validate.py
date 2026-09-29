"""搜索结果有效性校验（fix(12) 功能主线 / fix(9) D2 判据 C1/C2/C3 + 硬信号）。

修复前的 Bing 通道「只要 HTTP 200 且解析出非空结果就算成功」，于是：
结果与查询无关（实测错配 21%）、正文是乱码、结果 URL 全是未解开的跳转壳 —— 全部被
判定为成功，重试与 DDG 兜底**从不触发**。本模块把「结果到底能不能用」变成可判定的
结构化结论，供引擎/会话层决定「采用 / 换通道 / 报错」。

判据（阈值来源见 fix(9) fix-plan.md D2 与 reference/threshold_calibration.json）：

============  ==========================================================  ==========
判据          口径                                                        误判代价
============  ==========================================================  ==========
C1 结构完整性  `li.b_algo` >= 1（给了 HTML 时）；可解真实 URL 比例 >= 0.8；  0（拦空/乱码）
              正文不是乱码
C2 跨通道一致  HTML 与 RSS 的域名 Jaccard >= 0.3 **或** URL 交集 >= 3        1 次请求
C3 查询相关性  查询 vs（标题+摘要）覆盖率：中文 2-gram / 英文词级，          0（纯计算）
              取 max 与 Top3 max，阈值见 COVERAGE_THRESHOLD
============  ==========================================================  ==========

硬信号（命中即判降级，独立于阈值）：无结果页（「没有与此相关的结果」/`li.b_no`）、
验证码 / 挑战页（`captcha` / `challenge` / `bm_sv`）、正文乱码、可解真实
URL 比例 < 0.8。

用法（引擎出口）::

    from neobot_app.web_search.validate import validate_results

    report = validate_results(query, results, html=html, channel="html", cross_channel=rss_rows)
    if not report.valid:
        # 换通道 / 上报 error（严格取向：宁可返回空也不用错结果）
        raise SearchDegraded(report.reason)

报告对象同时提供 `.valid` / `.reason` / `.signals`（对外契约）与
`.ok` / `.reasons` / `.cov_max` / `.confidence` 等只读别名（兼容 fix(9)
参考实现的判据字段）。
"""

from __future__ import annotations

from enum import Enum

import html as html_module
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from neobot_app.web_search.urls import (
    HTTP_SCHEMES,
    host_of,
    is_tracking_wrapper,
    normalize_for_dedup,
)

__all__ = [
    "COVERAGE_THRESHOLD",
    "EMPTY_BODY_MAX",
    "HIGH_CONFIDENCE",
    "MIN_CROSS_CHANNEL_INTERSECTION",
    "MIN_CROSS_CHANNEL_JACCARD",
    "SHELL_BODY_MAX",
    "URL_OK_RATIO",
    "ValidationReport",
    "coverage",
    "count_algo_results",
    "cross_channel_agreement",
    "is_js_redirect_shell",
    "judge_results",
    "looks_garbled",
    "looks_like_empty_body",
    "results_domains",
    "tokens",
    "url_is_real",
    "validate_results",
    "visible_text",
]

#: C3 主阈值：`reference/threshold_calibration.json` 的 `best.threshold`（393 条样本，
#: 放行错配 12 / 误杀正常 4）。BAD 样本最高 0.25，因此阈值必须严格大于 0.25；
#: 长跑样本 GOOD 最低 0.333，取 0.29 留出两侧余量。**不要照抄**，重标定后同步这里。
COVERAGE_THRESHOLD = 0.29
#: 高置信阈值：cov 达到此值直接采用；[COVERAGE_THRESHOLD, HIGH_CONFIDENCE) 为低置信带，
#: 引擎可再跑一条通道取更高者（不强制）。
HIGH_CONFIDENCE = 0.35
#: C1：可解出真实 http(s) URL 的最低比例
URL_OK_RATIO = 0.8
#: C2：域名 Jaccard 下限
MIN_CROSS_CHANNEL_JACCARD = 0.3
#: C2：URL 交集下限（满足其一即可）
MIN_CROSS_CHANNEL_INTERSECTION = 3

#: 壳页正文长度上限（Bing JS 跳转壳实测 1830 字节）
SHELL_BODY_MAX = 5000
#: 空响应阈值（字节）。真实站点即使前端渲染，HTML 也在 KB 级；
#: 实测失败样本是 0 / 47 / 95 / 141 字节。
#: 不要用「可见文本长度」当判据：实测腾讯视频 136KB HTML 只抽出 197 字可见文本，
#: 用可见文本判失败会把 SPA 正常页全部误杀。
EMPTY_BODY_MAX = 500

_CJK_SEGMENT_RE = re.compile(r"[\u4e00-\u9fff]+")
_ASCII_WORD_RE = re.compile(r"[a-z0-9][a-z0-9_.\-]{1,}")
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style|noscript|template)\b.*?</\1\s*>", re.IGNORECASE | re.DOTALL
)
_TAG_RE = re.compile(r"<[^>]+>")
_LI_B_ALGO_RE = re.compile(r"<li\b[^>]*\bb_algo\b", re.IGNORECASE)
_LI_B_NO_RE = re.compile(r"<li\b[^>]*\bb_no\b", re.IGNORECASE)

#: 无结果页文案（中英）
_NO_RESULT_PHRASES = (
    "没有与此相关的结果",
    "没有找到与此相关的结果",
    "没有找到相关结果",
    "未找到与此相关的结果",
    "there are no results for",
    "we didn't find any results",
    "no results found for",
)
#: 验证码标记（可见文本）
_CAPTCHA_PHRASES = (
    "验证码",
    "人机验证",
    "请输入验证码",
    "captcha",
    "recaptcha",
    "verify you are human",
    "unusual traffic",
)
#: 挑战页标记（可见文本 + DOM）
_CHALLENGE_PHRASES = (
    "just a moment",
    "checking your browser",
    "enable javascript and cookies to continue",
    "正在进行安全验证",
    "安全验证",
)
_CHALLENGE_DOM_MARKERS = (
    "challenge-form",
    "cf-challenge",
    "challenge-platform",
    "id=\"captcha\"",
    "name=\"captcha\"",
    "g-recaptcha",
    "h-captcha",
    "bm_sv",
)
#: JS 跳转壳标记（必须与「短正文」同时成立：302KB 正常页正文里也会出现 function l()）
_SHELL_MARKERS = ("function l()", "window.location.replace", "var s = false;")

#: 乱码判据：替换字符 / 控制字符 / 典型 mojibake 序列
_REPLACEMENT_CHAR = "\ufffd"
_MOJIBAKE_CHARS = ("\u00c3", "\u00c2", "\u00ef\u00bf\u00bd", "\u00e2\u20ac")
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


# ── 分词与覆盖率 ────────────────────────────────────────────────────


def tokens(text: str) -> set[str]:
    """CJK 2-gram + ASCII 单词。故意不引入 jieba：零依赖、可离线测试。"""
    low = (text or "").lower()
    out: set[str] = set(_ASCII_WORD_RE.findall(low))
    for segment in _CJK_SEGMENT_RE.findall(low):
        out.update(segment[i:i + 2] for i in range(len(segment) - 1))
    return out


def coverage(query: str, text: str) -> float:
    """查询 token 在文本中的覆盖率（0~1）。

    这是**保守**指标，不是相关性排序器：查询「清华大学 官网」与文本「清华大学官方网站」
    只有 0.75 —— 「官网」与「官方网站」的 2-gram 边界不同。因此它是「错配页拦网」，
    阈值必须留足余量（真实数据里 GOOD 最低 0.33 左右）。
    """
    q = tokens(query)
    return len(q & tokens(text)) / len(q) if q else 0.0


# ── 正文级判据 ──────────────────────────────────────────────────────


def visible_text(html: str, *, limit: int = 20000) -> str:
    """HTML 的可见文本：先剥 script/style/noscript/template，再去标签、解实体。

    **必须剥脚本**：真实 Bing 页的 JS 域名清单里含 `challenges.cloudflare.com`，
    直接对原始 HTML 搜 `challenge` 会把每一页都误判成挑战页（10 份真实夹具全部命中）。
    """
    raw = str(html or "")
    if not raw:
        return ""
    stripped = _SCRIPT_STYLE_RE.sub(" ", raw)
    text = _TAG_RE.sub(" ", stripped)
    text = html_module.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return text.strip()[: max(0, int(limit))]


def count_algo_results(html: str) -> int:
    """HTML 里 `li.b_algo` 结果条目数（C1 结构判据）。"""
    return len(_LI_B_ALGO_RE.findall(str(html or "")))


def looks_garbled(text: str) -> bool:
    """正文是否像「非文本 / 乱码」（压缩内容被当文本解码、mojibake）。

    刻意保守：只在替换字符 / 控制字符 / mojibake 标记**成规模出现**时才判乱码，
    避免把正常的中英混排正文误杀（误杀会白白多跑一次兜底）。
    """
    value = str(text or "")
    total = len(value)
    if total < 40:
        return False
    replacement = value.count(_REPLACEMENT_CHAR)
    if replacement >= 3 and replacement / total >= 0.005:
        return True
    control = len(_CONTROL_CHAR_RE.findall(value))
    if control >= 3 and control / total >= 0.01:
        return True
    mojibake = sum(value.count(marker) for marker in _MOJIBAKE_CHARS)
    return mojibake >= 5 and mojibake / total >= 0.01


def is_js_redirect_shell(body: str) -> bool:
    """识别 `read()` 抓到的 JS 跳转壳（Bing `ck/a` 直连返回的就是它）。

    必须同时满足「短」和「含跳转脚本标记」：实测 302KB 的正常页面正文里也出现
    `function l()` 字样，只看标记会误判。
    """
    return bool(body) and len(body) < SHELL_BODY_MAX and any(
        marker in body for marker in _SHELL_MARKERS
    )


def looks_like_empty_body(body: str) -> bool:
    """识别空响应（含 0 字节与只有几行报错模板的情况）；理由见 EMPTY_BODY_MAX。"""
    return len(body or "") < EMPTY_BODY_MAX


# ── 结果行适配（dict 与 SearchResult 都支持）──────────────────────────


def _field(row: Any, *names: str) -> Any:
    for name in names:
        if isinstance(row, Mapping):
            if name in row and row[name] is not None:
                return row[name]
        else:
            value = getattr(row, name, None)
            if value is not None:
                return value
    return None


def _row_url(row: Any) -> str:
    return str(_field(row, "url", "href") or "").strip()


def _row_text(row: Any) -> str:
    """参与 C3 的文本 = 标题 + 摘要。

    - 摘要取 `text` / `snippet` / `content` 里第一个非空的（SearchResult 只有
      `snippet`；会话层补过正文时用 `text`）；
    - **不含域名**：英文查询下 host（如 `hub.docker.com`）会平白贡献 token，把错配页
      推过阈值（假放行）。宁可少一个信号，也不要假放行。
    """
    title = str(_field(row, "title") or "").strip()
    body = ""
    for name in ("text", "snippet", "content"):
        value = _field(row, name)
        if value is None:
            continue
        candidate = str(value).strip()
        if candidate:
            body = candidate
            break
    return f"{title} {body}".strip()


def url_is_real(url: str) -> bool:
    """URL 是否「可解出的真实 http(s) 地址」（未解开的跳转壳不算）。"""
    raw = str(url or "").strip()
    if not raw:
        return False
    try:
        parsed = urlparse(raw)
    except ValueError:
        return False
    if parsed.scheme.lower() not in HTTP_SCHEMES or not parsed.hostname:
        return False
    return not is_tracking_wrapper(raw)


def results_domains(results: Sequence[Any]) -> set[str]:
    """结果的域名集合（小写、去 `www.`），用于 C2 的 Jaccard。"""
    domains: set[str] = set()
    for row in results or ():
        host = host_of(_row_url(row))
        if host.startswith("www."):
            host = host[4:]
        if host:
            domains.add(host)
    return domains


def cross_channel_agreement(
    primary: Sequence[Any],
    other: Sequence[Any],
    *,
    min_jaccard: float = MIN_CROSS_CHANNEL_JACCARD,
    min_intersection: int = MIN_CROSS_CHANNEL_INTERSECTION,
) -> dict[str, Any]:
    """C2：两个通道的域名 Jaccard 与 URL 交集（满足其一即视为一致）。"""
    a_domains = results_domains(primary)
    b_domains = results_domains(other)
    union = a_domains | b_domains
    intersection_domains = a_domains & b_domains
    jaccard = len(intersection_domains) / len(union) if union else 0.0

    def _keys(rows: Sequence[Any]) -> set[str]:
        return {
            key
            for key in (normalize_for_dedup(_row_url(row)) for row in rows or ())
            if key
        }

    intersection = len(_keys(primary) & _keys(other))
    return {
        "checked": True,
        "jaccard": round(jaccard, 3),
        "domains_a": len(a_domains),
        "domains_b": len(b_domains),
        "intersection": intersection,
        "min_jaccard": min_jaccard,
        "min_intersection": min_intersection,
        "consistent": jaccard >= min_jaccard or intersection >= min_intersection,
    }


# ── 硬信号 ──────────────────────────────────────────────────────────


def _hard_signals(html: str | None, scan_text: str) -> list[str]:
    """命中即降级的硬信号（D2）。返回去重后的信号码列表。"""
    codes: list[str] = []
    body = str(html or "")
    text = (scan_text or "").lower()

    if _LI_B_NO_RE.search(body) or any(phrase in text for phrase in _NO_RESULT_PHRASES):
        codes.append("no_results")
    if any(phrase in text for phrase in _CAPTCHA_PHRASES) or any(
        marker in body.lower() for marker in ("id=\"captcha\"", "name=\"captcha\"", "g-recaptcha", "h-captcha")
    ):
        codes.append("captcha")
    if any(phrase in text for phrase in _CHALLENGE_PHRASES) or any(
        marker in body.lower() for marker in _CHALLENGE_DOM_MARKERS
    ):
        codes.append("challenge")
    if looks_garbled(scan_text):
        codes.append("garbled")
    return codes


# ── 报告对象 ────────────────────────────────────────────────────────


@dataclass
class ValidationReport:
    """一次结果集的有效性结论。

    对外契约：`.valid` / `.reason` / `.signals`。
    其余属性是兼容 fix(9) 参考实现判据字段的只读别名。
    """

    valid: bool
    reason: str
    signals: dict[str, Any] = field(default_factory=dict)

    # -- 契约字段之外的只读别名（兼容旧判据字段名）--
    @property
    def ok(self) -> bool:
        return self.valid

    @property
    def codes(self) -> list[str]:
        return list(self.signals.get("codes") or ())

    @property
    def reasons(self) -> list[str]:
        return list(self.signals.get("reasons") or ())

    @property
    def n(self) -> int:
        return int(self.signals.get("n") or 0)

    @property
    def url_ok_ratio(self) -> float:
        return float(self.signals.get("url_ok_ratio") or 0.0)

    @property
    def cov_max(self) -> float:
        return float(self.signals.get("cov_max") or 0.0)

    @property
    def cov_top3(self) -> float:
        return float(self.signals.get("cov_top3") or 0.0)

    @property
    def cov_title_max(self) -> float:
        return float(self.signals.get("cov_title_max") or 0.0)

    @property
    def confidence(self) -> str:
        return str(self.signals.get("confidence") or "rejected")

    def as_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "reason": self.reason, **self.signals}


# ── 主入口 ──────────────────────────────────────────────────────────


def validate_results(
    query: str,
    results: Sequence[Any] | Iterable[Any] | None,
    *,
    cross_channel: Sequence[Any] | Iterable[Any] | None = None,
    html: str | None = None,
    channel: str = "",
    coverage_threshold: float | None = None,
) -> ValidationReport:
    """校验一次搜索的结果集，返回结构化报告。

    Parameters
    ----------
    query : 原始查询（C3 覆盖率的基准）。
    results : 结果行；每项可以是 dict（`title` / `url` / `text`|`snippet`）或
        `SearchResult`（`title` / `url` / `snippet` 会被自动读取）。
    cross_channel : 另一通道的结果行（HTML vs RSS）。给了就做 C2；没给则跳过 C2。
    html : 原始 HTML（可选）。给了才能做 `li.b_algo` 结构判据与页面级硬信号。
    channel : 通道名（`"html"` / `"rss"` / ...）。RSS/XML 不做 `li.b_algo` 判据。
    coverage_threshold : 覆盖 C3 阈值（默认 COVERAGE_THRESHOLD）。

    判定顺序（reason 取第一个命中的原因）：无结果 → 硬信号（无结果页/验证码/挑战/乱码）
    → C1 结构（`li.b_algo`、可解 URL 比例）→ C3 相关性 → C2 跨通道一致性。
    """
    rows = list(results or ())
    other = list(cross_channel) if cross_channel is not None else None
    threshold = COVERAGE_THRESHOLD if coverage_threshold is None else float(coverage_threshold)
    n = len(rows)

    texts = [_row_text(row) for row in rows]
    urls = [_row_url(row) for row in rows]
    covs = [coverage(query, text) for text in texts]
    title_covs = [coverage(query, str(_field(row, "title") or "")) for row in rows]
    cov_max = max(covs) if covs else 0.0
    cov_top3 = max(covs[:3]) if covs else 0.0
    cov_title_max = max(title_covs) if title_covs else 0.0
    url_ok = sum(1 for url in urls if url_is_real(url))
    url_ok_ratio = (url_ok / n) if n else 0.0
    check_algo = bool(html) and str(channel or "").lower() not in {"rss", "xml", "feed"}
    n_algo = count_algo_results(html) if check_algo else None

    scan_parts = [visible_text(html)] if html else []
    scan_parts.extend(text for text in texts if text)
    scan_text = "\n".join(part for part in scan_parts if part)

    hard = _hard_signals(html, scan_text)
    if n and url_ok_ratio < URL_OK_RATIO and "url_ok_ratio" not in hard:
        hard.append("url_ok_ratio")

    codes: list[str] = []
    reasons: list[str] = []

    def _fail(code: str, detail: str) -> None:
        if code not in codes:
            codes.append(code)
        reasons.append(f"{code}: {detail}")

    if n == 0:
        _fail("no_results", "结果列表为空")
    for signal in hard:
        if signal == "no_results":
            _fail("no_results", "页面含无结果标记（li.b_no / 「没有与此相关的结果」）")
        elif signal == "captcha":
            _fail("captcha", "命中验证码标记")
        elif signal == "challenge":
            _fail("challenge", "命中挑战页标记（challenge / bm_sv）")
        elif signal == "garbled":
            _fail("garbled", "正文乱码（非文本）")
        elif signal == "url_ok_ratio":
            _fail(
                "url_ok_ratio",
                f"可解真实 URL 比例 {url_ok_ratio:.2f} < {URL_OK_RATIO}",
            )
    if n_algo is not None and n_algo < 1:
        _fail("structure", "结构判据不通过：li.b_algo=0")
    if n and cov_max < threshold:
        _fail("cov_max", f"相关性不足：cov_max={cov_max:.2f} < {threshold}")
    elif n and cov_top3 < threshold:
        _fail("cov_top3", f"Top3 无相关结果：cov_top3={cov_top3:.2f} < {threshold}")

    agreement: dict[str, Any] | None = None
    if other is not None:
        agreement = cross_channel_agreement(rows, other)
        if not agreement["consistent"]:
            _fail(
                "cross_channel",
                f"跨通道不一致：jaccard={agreement['jaccard']} < {MIN_CROSS_CHANNEL_JACCARD} "
                f"且 URL 交集={agreement['intersection']} < {MIN_CROSS_CHANNEL_INTERSECTION}",
            )

    valid = not codes
    if valid:
        confidence = "high" if cov_max >= HIGH_CONFIDENCE else "low"
    else:
        confidence = "rejected"

    signals: dict[str, Any] = {
        "channel": str(channel or ""),
        "query": str(query or ""),
        "n": n,
        "n_algo": n_algo,
        "url_real": url_ok,
        "url_ok_ratio": round(url_ok_ratio, 3),
        "cov_max": round(cov_max, 3),
        "cov_top3": round(cov_top3, 3),
        "cov_title_max": round(cov_title_max, 3),
        "threshold": threshold,
        "confidence": confidence,
        "garbled": "garbled" in hard,
        "hard_signals": hard,
        "codes": codes,
        "reasons": reasons,
        "cross_channel": agreement,
    }
    return ValidationReport(valid=valid, reason="ok" if valid else reasons[0], signals=signals)


def judge_results(
    query: str,
    results: Sequence[Any] | Iterable[Any] | None,
) -> ValidationReport:
    """`validate_results` 的两参兼容入口（fix(9) 参考实现的判据字段名）。"""
    return validate_results(query, results)


# ── 失败分级（fix(9) 附录 B v2 §1）────────────────────────────────────


class FailureKind(str, Enum):
    """一次检索的失败类型 —— 决定"该换什么"，而不是盲目重试。

    设计依据（实测）：
    - 内容类失败是同一份缓存/身份问题，同通道重试 3 次自愈 0/21；
    - 结构类失败（半包、未解码压缩）重试一次往往能恢复；
    - 网络类失败（挑战页/超时）重试只会加深风控。
    """

    NONE = "none"          # 通过校验
    NETWORK = "network"    # 超时 / 5xx / 挑战页 / 验证码
    STRUCTURE = "structure"  # 解析不到结构 / 可解 URL 比例过低 / 正文乱码
    CONTENT = "content"    # 能解析但与查询不相关（错配页）
    EMPTY = "empty"        # 页面明确表示"没有结果"


#: 命中这些 code 说明"没拿到合格页面"，属于网络/风控层面。
_NETWORK_CODES = frozenset({"captcha", "challenge"})
#: 命中这些 code 说明页面拿到了但结构不可用，值得同通道重试一次。
_STRUCTURE_CODES = frozenset({"structure", "garbled", "url_ok_ratio"})
#: 命中这些 code 说明是"页面内容与查询无关"，换通道无用、必须换身份/换引擎。
_CONTENT_CODES = frozenset({"cov_max", "cov_top3", "cross_channel"})


@dataclass
class FailureClass:
    """失败分级结论。

    对外契约：`kind` / `retry_same_channel` / `switch_engine` / `describe()`。
    其中 `retry_same_channel` 只是"允许"，是否真的重试由调用方按预算决定。
    """

    kind: FailureKind
    reason: str
    signals: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.kind is FailureKind.NONE

    @property
    def retry_same_channel(self) -> bool:
        return self.kind is FailureKind.STRUCTURE

    @property
    def switch_engine(self) -> bool:
        """是否需要换一个来源（换引擎/换身份）。EMPTY 与 NONE 都不需要。"""
        return self.kind in (FailureKind.NETWORK, FailureKind.CONTENT, FailureKind.STRUCTURE)

    def describe(self) -> str:
        return f"{self.kind.value}: {self.reason}" if self.reason else self.kind.value


def classify_failure(
    query: str,
    results: Sequence[Any] | Iterable[Any] | None = None,
    *,
    html: str | None = None,
    error: str | None = None,
    cross_channel: Sequence[Any] | Iterable[Any] | None = None,
    channel: str = "",
    coverage_threshold: float | None = None,
) -> FailureClass:
    """把一次检索的结局分成 通过 / 网络 / 结构 / 内容 / 空结果 五类。

    `error` 表示"连页面都没拿到"（超时、5xx、连接失败），此时必然归为网络类；
    已拿到页面则按校验信号的 code 归类。`EMPTY`（页面明说没有结果）**不算失败**，
    调用方应返回 degraded + 空结果，而不是继续回退。
    """
    report = validate_results(
        query,
        results,
        html=html,
        cross_channel=cross_channel,
        channel=channel,
        coverage_threshold=coverage_threshold,
    )
    if report.valid:
        return FailureClass(FailureKind.NONE, "ok", report.signals)

    codes = set(report.codes)
    # "空结果"必须是**页面明说没有结果**（li.b_no 或「没有与此相关的结果」文案）。
    # 所有校验失败都会带 no_results code（n=0 时），所以只凭 code 无法区分
    # "页面说没结果"与"我们什么都没解析到" —— 后者是结构类问题，值得重试一次。
    page_says_empty = report.valid or (
        "no_results" in set(report.signals.get("hard_signals") or ())
    )
    if error:
        # 抓取层失败：页面都没拿到，重试同通道通常无意义（风控/网络）。
        kind, reason = FailureKind.NETWORK, f"抓取失败: {error}"
    elif codes & _NETWORK_CODES:
        kind, reason = FailureKind.NETWORK, report.reason
    elif page_says_empty:
        # 空结果页通常也会伴随 structure（li.b_algo=0）：本来就该没有结果块，
        # 不能因此判成结构类去重试/回退。
        kind, reason = FailureKind.EMPTY, report.reason
    elif codes & _STRUCTURE_CODES:
        kind, reason = FailureKind.STRUCTURE, report.reason
    elif codes & _CONTENT_CODES:
        kind, reason = FailureKind.CONTENT, report.reason
    else:
        kind, reason = FailureKind.CONTENT, report.reason or "未知校验失败"
    return FailureClass(kind, reason, report.signals)
