"""搜索结果 URL 归一化（fix(12) 功能主线 / fix(9) D6）。

引擎出口与抓取入口共用这一层，解决四个问题：

1. **跳转壳**：Bing 的 `bing.com/ck/a?...&u=a1<base64url>`、`bing.com/aclick?...&u=`，
   Google 的 `/url?q=`，DuckDuckGo 的 `/l/?uddg=` —— 真实地址藏在查询参数里，
   引擎原样返回会让下游既读不到正文（读到 JS 跳转模板）也无法展示真实来源；
2. **跟踪参数**：`utm_*` / `gclid` / `fclid` / `spm` / `ref` / `from` 等
   只影响统计，不影响内容，留着会污染去重键与展示；
3. **去重键**：同一篇文章在 http/https、带不带 `www.`、带不带尾斜杠时是同一个页面；
4. **相对链接**：SERP 里出现 `/x/y` 或 `//a.b/c` 时要能还原成绝对地址。

约定（供引擎/会话层使用）：

* 解码失败**绝不丢结果**：`unwrap_tracking` 原样返回输入，`normalize_result_url`
  返回的原始 href 供留痕（raw）；
* 只接受 http/https 的最终结果，`javascript:` 之类的危险 scheme 一律视为解码失败；
* `normalize_for_dedup` 的返回值**不是 URL**，只能当 set/dict 的键，不能拿去请求。

调用示例（引擎出口）::

    from neobot_app.web_search.urls import normalize_result_url

    url, raw_href = normalize_result_url(self.base_url, href)
"""

from __future__ import annotations

import base64
import re
from urllib.parse import (
    parse_qs,
    unquote,
    urlencode,
    urljoin,
    urlparse,
    urlunparse,
)

__all__ = [
    "HTTP_SCHEMES",
    "absolutize",
    "host_of",
    "is_tracking_wrapper",
    "normalize_for_dedup",
    "normalize_result_url",
    "strip_tracking_params",
    "unwrap_tracking",
]

HTTP_SCHEMES = ("http", "https")

#: 已知跳转壳：(host 后缀, 承载真实地址的查询参数, base64 值的固定前缀)
#: 按 **host** 匹配，因此同 host 下的 ck/a 与 aclick 两种路径都覆盖。
_WRAPPERS: tuple[tuple[str, str, str], ...] = (
    ("bing.com", "u", "a1"),          # https://www.bing.com/ck/a?...&u=a1<base64url>
    ("bing.com", "u", "a1"),          # https://www.bing.com/aclick?...&u=a1<base64url>
    ("google.com", "q", ""),          # https://www.google.com/url?q=<urlencoded>
    ("google.com", "url", ""),        # https://www.google.com/url?url=<urlencoded>
    ("duckduckgo.com", "uddg", ""),   # https://duckduckgo.com/l/?uddg=<urlencoded>
)

#: 跟踪参数：前缀匹配
_TRACKING_PREFIXES = ("utm_", "pk_", "mtm_", "hsa_", "mc_")
#: 跟踪参数：精确匹配（保留 id / v / p / page 等语义参数）
_TRACKING_EXACT = frozenset({
    "gclid", "fbclid", "msclkid", "yclid", "dclid", "igshid", "spm", "scm",
    "fclid", "ref", "ref_src", "referer", "from", "from_source",
    "share_token", "share_source", "vd_source", "buvid", "seid", "sshare",
})

#: Bing 的 base64url 载荷（URL-safe 字母表，可带 padding）
_B64URL_RE = re.compile(r"^[A-Za-z0-9_\-]+={0,2}$")


def _b64url_decode(value: str) -> str | None:
    """解码 base64url 载荷；非法字符/非法 padding 一律返回 None。"""
    if not value or not _B64URL_RE.match(value):
        return None
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode(
            "utf-8", "replace"
        )
    except Exception:
        return None


def _host_matches(host: str, suffix: str) -> bool:
    host = (host or "").lower()
    return host == suffix or host.endswith("." + suffix)


def host_of(url: str) -> str:
    """URL 的 host（小写、去尾点）；解析失败返回空串。"""
    try:
        return (urlparse(str(url or "")).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def _wrapper_hit(url: str) -> tuple[str, str] | None:
    """返回 (参数名, 值前缀)；不是已知跳转壳时返回 None。"""
    try:
        parsed = urlparse(str(url or ""))
    except ValueError:
        return None
    if parsed.scheme.lower() not in HTTP_SCHEMES:
        return None
    host = parsed.hostname or ""
    for suffix, param, prefix in _WRAPPERS:
        if _host_matches(host, suffix):
            values = parse_qs(parsed.query).get(param)
            if values and values[0]:
                return param, prefix
    return None


def is_tracking_wrapper(url: str) -> bool:
    """URL 是否是「未解开的已知跳转壳」（A1 的可观测口径）。"""
    return _wrapper_hit(url) is not None


def unwrap_tracking(url: str, *, max_depth: int = 1) -> str:
    """把已知跳转壳还原成真实 URL；无法还原时**原样返回**。

    * 只处理 http/https；解码结果必须也是 http/https 且带 host，否则视为失败；
    * `max_depth` 是最多解码层数（默认 1 层，见 fix(9) D6「最多递归解一层」）。
      真实夹具里壳只嵌套一层；若确实存在嵌套壳且希望一次解到底，传 `max_depth=2`。
      超过深度仍返回当前值（可能是壳），由调用方的 URL 有效性判据兜底。
    """
    original = url or ""
    current = original
    for _ in range(max(0, int(max_depth))):
        hit = _wrapper_hit(current)
        if hit is None:
            return current
        param, prefix = hit
        try:
            raw = (parse_qs(urlparse(current).query).get(param) or [""])[0]
        except ValueError:
            return original
        if not raw:
            return current
        if prefix:
            if not raw.startswith(prefix):
                return current
            candidate = _b64url_decode(raw[len(prefix):])
        else:
            candidate = unquote(raw)
        if not candidate:
            return current
        try:
            inner = urlparse(candidate)
        except ValueError:
            return current
        if inner.scheme.lower() not in HTTP_SCHEMES or not inner.hostname:
            return current
        current = candidate
    return current


def strip_tracking_params(url: str) -> str:
    """移除跟踪/来源参数，保留语义参数（`id` / `v` / `p` / `page` 等）。

    没有任何参数被剥离时**原样返回**：重新 urlencode 会把 `!` 变成 `%21` 这类
    无害但会破坏「幂等」断言的改写。
    """
    raw_url = str(url or "")
    try:
        parsed = urlparse(raw_url)
    except ValueError:
        return raw_url
    if not parsed.query:
        return raw_url
    kept: list[tuple[str, str]] = []
    dropped = 0
    for key, values in parse_qs(parsed.query, keep_blank_values=True).items():
        low = key.lower()
        if low in _TRACKING_EXACT or low.startswith(_TRACKING_PREFIXES):
            dropped += len(values) or 1
            continue
        for value in values:
            kept.append((key, value))
    if dropped == 0:
        return raw_url
    return urlunparse(parsed._replace(query=urlencode(kept, doseq=True)))


def absolutize(base: str, href: str) -> str:
    """相对链接转绝对；空 href 返回空串。非 http(s) 的 href 原样返回，由上层判据处理。"""
    if not href:
        return ""
    href = str(href).strip()
    if not href:
        return ""
    if href.lower().startswith(("http://", "https://")):
        return href
    if href.startswith("//"):
        try:
            base_scheme = urlparse(base).scheme.lower()
        except ValueError:
            base_scheme = ""
        return ("http:" if base_scheme == "http" else "https:") + href
    if not base:
        return href
    return urljoin(base, href)


def normalize_for_dedup(url: str) -> str:
    """生成去重键：小写 host、去 `www.` / scheme / 默认端口 / fragment / 尾斜杠，
    并剥离跟踪参数。

    **返回值不是 URL**（没有 scheme），只能用于 set/dict 去重；http 与 https 指向
    同一内容时视为重复。
    """
    raw_url = str(url or "")
    try:
        parsed = urlparse(raw_url)
    except ValueError:
        return raw_url
    host = (parsed.hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    try:
        port = parsed.port
    except ValueError:
        port = None
    netloc = host
    if port and not (
        (parsed.scheme.lower() == "http" and port == 80)
        or (parsed.scheme.lower() == "https" and port == 443)
    ):
        netloc = f"{host}:{port}"
    path = parsed.path.rstrip("/") or "/"
    query = ""
    if parsed.query:
        stripped = strip_tracking_params(f"https://{host}/?{parsed.query}")
        query = stripped.split("?", 1)[1] if "?" in stripped else ""
    return f"{netloc}{path}" + (f"?{query}" if query else "")


def normalize_result_url(base: str, href: str) -> tuple[str, str]:
    """引擎出口的统一入口：返回 `(可用于展示/抓取的 URL, 原始 href)`。

    展示 URL 的顺序是「相对转绝对 → 去壳 → 去跟踪参数」；去壳失败时保留绝对化后的
    原值（宁可给壳也不丢结果），原始 href 一并返回供留痕。
    """
    raw_href = str(href or "")
    absolute = absolutize(base, raw_href)
    real = unwrap_tracking(absolute)
    real = strip_tracking_params(real)
    return real, raw_href
