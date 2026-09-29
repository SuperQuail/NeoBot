"""URL 归一化回归（S2 Bing P0-A）：shell 解码 / 跟踪参数 / 去重键 / 相对转绝对。

数据来源：2026-09-14 真实 Bing 响应夹具（10 份 SERP HTML，见 fixtures/bing/）。
修复前 `BingSearchEngine._parse` 原样返回 `href`，结果 URL 100% 是
`bing.com/ck/a?...&u=a1<base64url>` 追踪壳（夹具实测：每份 10/10 条），下游 `read()`
抓到的是 JS 跳转模板 —— 本文件的夹具扫描用例在修复前必然失败（模块不存在 / 壳未解开）。
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from neobot_app.web_search.urls import (
    absolutize,
    is_tracking_wrapper,
    normalize_for_dedup,
    normalize_result_url,
    strip_tracking_params,
    unwrap_tracking,
)

#: 真实采集的 ck/a href → 期望域名（摘自 good_00_tsinghua.html，Bing 的 <cite> 交叉验证）
EMBEDDED = [
    ("https://www.bing.com/ck/a?!&&p=9429ce78f1ecd04c82a9a2bada288effd08ae1cf30216bc1915830856b1b1a4eJmltdHM9MTc4OTM0NDAwMA"
     "&ptn=3&ver=2&hsh=4&fclid=322ead11-fdbe-6611-1f60-bac5fc226745&u=a1aHR0cHM6Ly93d3cudHNpbmdodWEuZWR1LmNuLw&ntb=1",
     "www.tsinghua.edu.cn"),
    ("https://www.bing.com/ck/a?!&&p=ab49c1651719152eacdc1d6839d66facc89621e2df102c689da12aa7bdc1148dJmltdHM9MTc4OTM0NDAwMA"
     "&ptn=3&ver=2&hsh=4&fclid=322ead11-fdbe-6611-1f60-bac5fc226745&u=a1aHR0cHM6Ly96aC5tLndpa2lwZWRpYS5vcmcvd2lraS8lRTYlQjglODUlRTUlOEQlOEUlRTUlQTQlQTclRTUlQUQlQTY&ntb=1",
     "zh.m.wikipedia.org"),
    ("https://www.bing.com/ck/a?!&&p=758c861e62aa21883f9a662e794cb3c2b81b953b6b7ce1b70d6266ebe723f610JmltdHM9MTc4OTM0NDAwMA"
     "&ptn=3&ver=2&hsh=4&fclid=322ead11-fdbe-6611-1f60-bac5fc226745&u=a1aHR0cHM6Ly9iYWlrZS5iYWlkdS5jb20vaXRlbS8lRTYlQjglODUlRTUlOEQlOEUlRTUlQTQlQTclRTUlQUQlQTYvMTExNzY0&ntb=1",
     "baike.baidu.com"),
    ("https://www.bing.com/ck/a?!&&p=779cea85bd404d0bd15d308d6823967a8b6612d2302e3fb87a6b369605c27017JmltdHM9MTc4OTM0NDAwMA"
     "&ptn=3&ver=2&hsh=4&fclid=322ead11-fdbe-6611-1f60-bac5fc226745&u=a1aHR0cHM6Ly9tb3ZpZS5kb3ViYW4uY29tLw&ntb=1",
     "movie.douban.com"),
]

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "bing"


def _b64url(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def _manifest() -> list[dict]:
    return json.loads((FIXTURE_DIR / "MANIFEST.json").read_text(encoding="utf-8"))


def _serp_hrefs() -> list[tuple[str, str]]:
    """夹具里所有 li.b_algo 的 (fixture, href)。"""
    items: list[tuple[str, str]] = []
    for entry in _manifest():
        soup = BeautifulSoup((FIXTURE_DIR / entry["fixture"]).read_text(encoding="utf-8"), "lxml")
        for anchor in soup.select("li.b_algo h2 a"):
            items.append((entry["fixture"], anchor.get("href", "")))
    return items


class TestUnwrapTracking:
    @pytest.mark.parametrize("href,host", EMBEDDED)
    def test_embedded_real_bing_ck_urls(self, href: str, host: str) -> None:
        got = unwrap_tracking(href)
        assert got.startswith("http"), f"未还原为可用地址: {got[:80]}"
        assert host in got, f"{got[:80]} 不含期望域名 {host}"

    def test_real_bing_aclick_shell_is_unwrapped(self) -> None:
        """aclick 与 ck/a 同为追踪壳，真实地址同样在 u=a1<base64url>。"""
        url = f"https://www.bing.com/aclick?ld=e8&u=a1{_b64url('https://example.com/aclick-target')}&ntb=1"
        assert unwrap_tracking(url) == "https://example.com/aclick-target"

    def test_region_and_www_host_variants(self) -> None:
        for host in ("www.bing.com", "cn.bing.com", "bing.com"):
            url = f"https://{host}/ck/a?u=a1{_b64url('https://example.org/x')}"
            assert unwrap_tracking(url) == "https://example.org/x"

    def test_google_and_ddg_wrappers(self) -> None:
        assert unwrap_tracking("https://www.google.com/url?q=https%3A%2F%2Fexample.com%2Fa") == "https://example.com/a"
        assert unwrap_tracking("https://www.google.com/url?url=https%3A%2F%2Fexample.com%2Fc") == "https://example.com/c"
        assert unwrap_tracking("https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fb") == "https://example.com/b"

    def test_decoding_is_idempotent(self) -> None:
        for href, _ in EMBEDDED:
            once = unwrap_tracking(href)
            assert unwrap_tracking(once) == once

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.bing.com/ck/a",
            "https://www.bing.com/ck/a?u=a1!!!not-base64",
            "https://www.bing.com/ck/a?u=",
            "https://example.com/normal/page",
            "",
        ],
    )
    def test_malformed_input_is_returned_unchanged(self, url: str) -> None:
        """解码失败必须原样返回 —— 绝不因为解不开就丢结果。"""
        assert unwrap_tracking(url) == url

    def test_non_http_input_is_returned_unchanged(self) -> None:
        assert unwrap_tracking("ftp://www.bing.com/ck/a?u=a1aHR0cHM6Ly9leGFtcGxlLmNvbQ") == (
            "ftp://www.bing.com/ck/a?u=a1aHR0cHM6Ly9leGFtcGxlLmNvbQ"
        )

    def test_dangerous_scheme_is_rejected(self) -> None:
        payload = _b64url("javascript:alert(1)")
        url = f"https://www.bing.com/ck/a?u=a1{payload}"
        assert unwrap_tracking(url) == url
        assert is_tracking_wrapper(url) is True

    def test_shell_without_decodable_host_is_not_a_wrapper(self) -> None:
        assert is_tracking_wrapper("https://example.com/normal") is False
        assert is_tracking_wrapper("") is False

    def test_nested_shell_needs_explicit_second_level(self) -> None:
        """默认只解一层（fix(9) D6）；嵌套壳原样留在上层，由有效性判据兜底。"""
        inner = f"https://www.bing.com/ck/a?u=a1{_b64url('https://example.com/deep')}"
        outer = f"https://www.bing.com/ck/a?u=a1{_b64url(inner)}"
        one_level = unwrap_tracking(outer)
        assert one_level == inner
        assert is_tracking_wrapper(one_level) is True
        assert unwrap_tracking(outer, max_depth=2) == "https://example.com/deep"


class TestStripTrackingParams:
    def test_named_tracking_params_removed(self) -> None:
        """任务口径里点名的 6 类参数必须剥掉。"""
        url = (
            "https://example.com/p?a=1&utm_source=x&utm_medium=y&gclid=g&fclid=f"
            "&msclkid=m&spm=s&ref=r&from=home&id=7"
        )
        got = strip_tracking_params(url)
        for dropped in ("utm_source", "utm_medium", "gclid", "fclid", "msclkid", "spm", "ref=", "from="):
            assert dropped not in got, f"{dropped} 未被剥离: {got}"
        assert "a=1" in got and "id=7" in got

    def test_other_common_tracking_params_removed(self) -> None:
        url = "https://example.com/p?fbclid=x&yclid=y&ref_src=z&share_source=s&buvid=b&page=2"
        got = strip_tracking_params(url)
        for dropped in ("fbclid", "yclid", "ref_src", "share_source", "buvid"):
            assert dropped not in got
        assert "page=2" in got

    def test_semantic_params_kept(self) -> None:
        got = strip_tracking_params("https://example.com/p?id=7&v=2&p=3&page=4&q=hello")
        for token in ("id=7", "v=2", "p=3", "page=4", "q=hello"):
            assert token in got

    def test_no_op_leaves_url_untouched(self) -> None:
        """回归：没有参数被剥离时必须原样返回（重新编码会把 '!' 变成 '%21'）。"""
        original = "https://www.bing.com/ck/a?u=a1!!!not-base64"
        assert strip_tracking_params(original) == original
        assert strip_tracking_params("https://example.com/a") == "https://example.com/a"

    def test_fragment_is_preserved(self) -> None:
        got = strip_tracking_params("https://example.com/p?id=1&utm_source=x#section-2")
        assert got.endswith("#section-2")
        assert "utm_source" not in got


class TestAbsolutize:
    @pytest.mark.parametrize(
        "base,href,expect",
        [
            ("https://www.bing.com/search", "/x/y", "https://www.bing.com/x/y"),
            ("https://www.bing.com/search", "https://a.b/c", "https://a.b/c"),
            ("https://www.bing.com/search", "//a.b/c", "https://a.b/c"),
            ("http://www.bing.com/search", "//a.b/c", "http://a.b/c"),
            ("https://www.bing.com/search", "sub/page", "https://www.bing.com/sub/page"),
            ("https://www.bing.com/search", "", ""),
            ("https://www.bing.com/search", "   ", ""),
            ("https://www.bing.com/search", "#frag", "https://www.bing.com/search#frag"),
        ],
    )
    def test_absolutize(self, base: str, href: str, expect: str) -> None:
        assert absolutize(base, href) == expect

    def test_non_http_href_is_returned_as_is(self) -> None:
        got = absolutize("https://www.bing.com/search", "javascript:alert(1)")
        assert got.startswith("javascript:")
        assert is_tracking_wrapper(got) is False


class TestDedupKey:
    def test_www_and_scheme_are_normalised(self) -> None:
        assert normalize_for_dedup("https://www.example.com/a/") == normalize_for_dedup("http://example.com/a")

    def test_fragment_ignored(self) -> None:
        assert normalize_for_dedup("https://e.com/a#top") == normalize_for_dedup("https://e.com/a")

    def test_default_ports_ignored(self) -> None:
        assert normalize_for_dedup("https://e.com:443/a") == normalize_for_dedup("https://e.com/a")
        assert normalize_for_dedup("http://e.com:8080/a") != normalize_for_dedup("http://e.com/a")

    def test_tracking_params_ignored(self) -> None:
        """同一篇文章带不带 utm_* 必须去重成同一个键（否则排行榜/结果列表里会出现重复项）。"""
        assert normalize_for_dedup("https://e.com/a?utm_source=x") == normalize_for_dedup("https://e.com/a")

    def test_semantic_params_still_split(self) -> None:
        assert normalize_for_dedup("https://e.com/a?id=1") != normalize_for_dedup("https://e.com/a?id=2")

    def test_root_path_is_normalised(self) -> None:
        assert normalize_for_dedup("https://e.com") == normalize_for_dedup("https://e.com/")

    def test_result_is_not_a_url(self) -> None:
        """去重键故意不带 scheme：只能当 set/dict 的键，不能拿去请求。"""
        assert not normalize_for_dedup("https://e.com/a").startswith("http")


class TestNormalizeResultUrl:
    def test_wrapper_is_unwrapped_and_cleaned(self) -> None:
        target = "https://example.com/page?utm_source=bing&id=9"
        href = f"https://www.bing.com/ck/a?u=a1{_b64url(target)}"
        url, raw_href = normalize_result_url("https://www.bing.com/search", href)
        assert url == "https://example.com/page?id=9"
        assert raw_href == href, "原始 href 必须留痕（raw）"

    def test_relative_href_is_absolutized(self) -> None:
        url, _ = normalize_result_url("https://www.bing.com/search", "/x/y?utm_source=z")
        assert url == "https://www.bing.com/x/y"


class TestFixtureSweep:
    """A1 的离线部分：夹具里所有追踪壳都必须能还原成真实地址。"""

    def test_fixture_dir_present(self) -> None:
        assert FIXTURE_DIR.is_dir(), f"夹具目录缺失: {FIXTURE_DIR}"

    def test_all_shell_hrefs_decode_to_real_urls(self) -> None:
        hrefs = _serp_hrefs()
        assert len(hrefs) >= 100, f"夹具条目过少（{len(hrefs)}），夹具可能已损坏"
        wrapped = [item for item in hrefs if is_tracking_wrapper(item[1])]
        assert len(wrapped) >= 90, f"夹具里 ck/a 壳只有 {len(wrapped)} 条，夹具可能已损坏"
        for fixture, href in wrapped:
            got = unwrap_tracking(href)
            assert got.startswith("http"), f"{fixture}: 未还原 {href[:60]}"
            assert not is_tracking_wrapper(got), f"{fixture}: 还原后仍是壳 {got[:60]}"

    def test_result_urls_are_unique_after_normalization(self) -> None:
        """10 份夹具共 100 条结果，按去重键不应出现同页重复。"""
        keys = {normalize_for_dedup(unwrap_tracking(href)) for _, href in _serp_hrefs()}
        assert len(keys) >= 90
