"""结果有效性校验回归（S2 Bing P0-A）：C1 结构 / C2 跨通道 / C3 相关性 + 硬信号。

核心回归（修复前必失败）：修复前 Bing 通道「解析出非空结果即成功」，于是 10 份真实夹具里
7 份错配页被判成功（实测错配 21%）且 URL 100% 是未解开的追踪壳。本文件用同一批夹具断言：

* 7 份错配页必须全部被 C3 拦下（DOM 与正常页同构，只有相关性判据能区分）；
* 3 份正常页不许被误杀（误杀会白白多跑一次兜底）；
* 未去壳的原始 href 必须触发 C1 的 url_ok_ratio 判据（修复前的结果集形态）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from bs4 import BeautifulSoup

from neobot_app.web_search.models import SearchResult
from neobot_app.web_search.urls import unwrap_tracking
from neobot_app.web_search.validate import (
    COVERAGE_THRESHOLD,
    HIGH_CONFIDENCE,
    MIN_CROSS_CHANNEL_INTERSECTION,
    MIN_CROSS_CHANNEL_JACCARD,
    URL_OK_RATIO,
    count_algo_results,
    coverage,
    cross_channel_agreement,
    is_js_redirect_shell,
    looks_garbled,
    looks_like_empty_body,
    tokens,
    url_is_real,
    validate_results,
    visible_text,
)

REAL = "https://www.tsinghua.edu.cn/"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "bing"


def rows(*items: tuple[str, str, str]) -> list[dict[str, str]]:
    """items: (title, url, text)"""
    return [{"title": title, "url": url, "text": text} for title, url, text in items]


def fixture_html(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def manifest() -> list[dict[str, Any]]:
    return json.loads((FIXTURE_DIR / "MANIFEST.json").read_text(encoding="utf-8"))


def parse_fixture(name: str, *, unwrap: bool = True) -> list[dict[str, str]]:
    soup = BeautifulSoup(fixture_html(name), "lxml")
    parsed: list[dict[str, str]] = []
    for li in soup.select("li.b_algo"):
        anchor = li.select_one("h2 a")
        if not anchor:
            continue
        href = anchor.get("href", "")
        parsed.append(
            {
                "title": anchor.get_text(strip=True),
                "url": unwrap_tracking(href) if unwrap else href,
                "text": li.get_text(" ", strip=True)[:500],
            }
        )
    return parsed


def calibration_path() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        candidate = (
            parent / "bugfixes" / "fix(9)-bing-search-rebuild" / "reference" / "threshold_calibration.json"
        )
        if candidate.exists():
            return candidate
    return None


def ascii_query(count: int) -> str:
    """count 个互不相同的 ASCII 词，每个正好 1 个 token（便于精确构造覆盖率）。"""
    return " ".join(f"w{index:03d}" for index in range(count))


class TestTokenizer:
    def test_cjk_bigrams_within_segment(self) -> None:
        assert tokens("清华大学") == {"清华", "华大", "大学"}

    def test_ascii_words(self) -> None:
        assert {"python", "asyncio"} <= tokens("Python asyncio tutorial")

    def test_no_cross_space_bigrams(self) -> None:
        """中文按空格切段，不生成跨空格的 2-gram（阈值稳定性依赖这一点）。"""
        assert tokens("清华 大学") == {"清华", "大学"}


class TestCoverage:
    def test_high_match(self) -> None:
        """保守指标：「官网」与「官方网站」的 bigram 边界不同，只能拿到 0.75。"""
        assert coverage("清华大学 官网", "清华大学官方网站") >= 0.7

    def test_exact_match(self) -> None:
        assert coverage("清华大学", "清华大学") == pytest.approx(1.0)

    def test_no_match(self) -> None:
        assert coverage("清华大学 官网", "芒果TV 在线视频") < 0.2

    def test_empty_query(self) -> None:
        assert coverage("", "任何内容") == 0.0


class TestHardSignals:
    def test_no_results_phrase_page_is_rejected(self) -> None:
        html = "<html><body><div class='b_no'>没有与此相关的结果</div></body></html>"
        report = validate_results("清华大学", rows(("清华大学", REAL, "清华大学")), html=html, channel="html")
        assert report.valid is False
        assert "no_results" in report.signals["hard_signals"]
        assert report.reason.startswith("no_results")

    def test_li_b_no_dom_marker_is_rejected(self) -> None:
        html = "<html><body><ul><li class='b_no'>没有结果</li></ul></body></html>"
        report = validate_results("清华大学", rows(("清华大学", REAL, "清华大学")), html=html)
        assert report.valid is False
        assert "no_results" in report.signals["hard_signals"]

    def test_captcha_page_is_rejected(self) -> None:
        html = "<html><body><p>请输入验证码以继续访问</p></body></html>"
        report = validate_results("清华大学", rows(("清华大学", REAL, "清华大学")), html=html)
        assert report.valid is False
        assert "captcha" in report.signals["hard_signals"]

    def test_challenge_page_is_rejected(self) -> None:
        html = "<html><body><h1>Just a moment...</h1><p>Checking your browser before accessing</p></body></html>"
        report = validate_results("清华大学", rows(("清华大学", REAL, "清华大学")), html=html)
        assert report.valid is False
        assert "challenge" in report.signals["hard_signals"]

    def test_bm_sv_blocked_page_is_rejected(self) -> None:
        html = "<html><body><form id=\"bm_sv\"></form><p>请完成安全验证</p></body></html>"
        report = validate_results("清华大学", rows(("清华大学", REAL, "清华大学")), html=html)
        assert report.valid is False
        assert "challenge" in report.signals["hard_signals"]

    def test_script_only_challenge_domain_is_not_a_signal(self) -> None:
        """真实 Bing 页的 JS 域名清单里含 challenges.cloudflare.com / #b_notificationContainer；
        直接对原始 HTML 搜 challenge / b_no 会把每一页都误判（10 份夹具实测全部命中）。"""
        html = (
            "<html><body><ul><li class='b_algo'>正常结果</li></ul>"
            "<script>var hosts=[\"challenges.cloudflare.com\",\"akchal.bing.com\"];"
            "var sel={\"#b_notificationContainer\":[-1,-1,0]};</script>"
            "</body></html>"
        )
        report = validate_results("清华大学", rows(("清华大学", REAL, "清华大学")), html=html)
        assert report.signals["hard_signals"] == []

    def test_real_fixture_pages_never_trigger_hard_signals(self) -> None:
        for entry in manifest():
            report = validate_results(
                entry["query"], parse_fixture(entry["fixture"]), html=fixture_html(entry["fixture"]), channel="html"
            )
            assert report.signals["hard_signals"] == [], f"{entry['fixture']} 误报硬信号"


class TestStructureCriteria:
    def test_empty_results_are_rejected(self) -> None:
        report = validate_results("清华大学", [])
        assert report.valid is False and "no_results" in report.signals["codes"]

    def test_relative_or_broken_urls_fail_structure_check(self) -> None:
        report = validate_results("测试", rows(("测试标题", "/relative/path", "测试"), ("测试标题2", "", "测试")))
        assert report.valid is False
        assert "url_ok_ratio" in report.signals["codes"]
        assert report.signals["url_ok_ratio"] < URL_OK_RATIO

    def test_unwrapped_tracking_shells_fail_structure_check(self) -> None:
        """修复前的真实结果形态：href 原样返回（全是 ck/a 壳）→ 必须判失败。"""
        parsed = parse_fixture("good_00_tsinghua.html", unwrap=False)
        assert parsed and all(not url_is_real(row["url"]) for row in parsed)
        report = validate_results("清华大学 官网", parsed)
        assert report.valid is False
        assert "url_ok_ratio" in report.signals["codes"]
        assert report.signals["url_ok_ratio"] == 0.0

    def test_html_without_algo_results_fails_structure_check(self) -> None:
        html = "<html><body><div>解析不到结果</div></body></html>"
        report = validate_results("清华大学", rows(("清华大学", REAL, "清华大学")), html=html, channel="html")
        assert report.valid is False
        assert "structure" in report.signals["codes"]
        assert report.signals["n_algo"] == 0

    def test_rss_channel_does_not_require_algo_items(self) -> None:
        xml = "<rss><channel><item><title>豆瓣电影</title></item></channel></rss>"
        report = validate_results(
            "豆瓣电影", rows(("豆瓣电影", "https://movie.douban.com/", "豆瓣电影")), html=xml, channel="rss"
        )
        assert report.signals["n_algo"] is None
        assert "structure" not in report.signals["codes"]
        assert report.valid is True

    def test_garbled_body_is_rejected(self) -> None:
        html = "<html><body>" + ("\ufffd" * 400) + "</body></html>"
        report = validate_results("清华大学", rows(("清华大学", REAL, "清华大学")), html=html)
        assert report.valid is False
        assert "garbled" in report.signals["hard_signals"]

    def test_mojibake_text_is_detected_but_normal_text_is_not(self) -> None:
        assert looks_garbled("Ã¤Â¸ÂÃ¦Â–Â‡" * 20) is True
        assert looks_garbled("正常的中文正文，含 English words 与数字 123。") is False
        assert looks_garbled("") is False

    def test_count_algo_results_counts_real_fixtures(self) -> None:
        for entry in manifest():
            assert count_algo_results(fixture_html(entry["fixture"])) >= 1


class TestRelevanceCriteria:
    def test_relevant_page_passes(self) -> None:
        report = validate_results(
            "清华大学 官网",
            rows(
                ("清华大学", REAL, "清华大学官方网站"),
                ("清华大学 - 维基百科", "https://zh.wikipedia.org/wiki/x", "清华大学百科"),
            ),
        )
        assert report.valid is True, report.reasons
        assert report.cov_max >= COVERAGE_THRESHOLD

    def test_unrelated_page_is_rejected(self) -> None:
        """核心回归：错配页必须被拦下（真实样本：查京东返回 Microsoft 支持页）。"""
        report = validate_results(
            "京东 购物",
            rows(
                ("Contact Us - Microsoft Support", "https://support.microsoft.com/x", "Get help for Windows"),
                ("Anmelden bei Hotmail", "https://support.microsoft.com/y", "Microsoft account"),
            ),
        )
        assert report.valid is False
        assert "cov_max" in report.signals["codes"]
        assert report.confidence == "rejected"

    def test_threshold_boundary_exactly_at_threshold_passes(self) -> None:
        """恰好等于阈值视为通过（>=，不是 >）；100 词里命中 29 词 = 0.29。"""
        query = ascii_query(100)
        title = " ".join(f"w{index:03d}" for index in range(29))
        report = validate_results(query, rows((title, "https://example.com/x", "")))
        assert report.cov_max == pytest.approx(COVERAGE_THRESHOLD)
        assert report.valid is True, report.reasons

    def test_threshold_boundary_just_below_fails(self) -> None:
        query = ascii_query(100)
        title = " ".join(f"w{index:03d}" for index in range(28))
        report = validate_results(query, rows((title, "https://example.com/x", "")))
        assert report.valid is False
        assert "cov_max" in report.signals["codes"]

    def test_top3_gate_rejects_when_only_late_results_match(self) -> None:
        """D2：Top3 至少 1 条命中。第 4 条才相关 → 判失败（cov_max 够但 cov_top3 不够）。"""
        report = validate_results(
            "alpha beta gamma",
            rows(
                ("zzz zzz", "https://example.com/1", "zzz"),
                ("zzz zzz", "https://example.com/2", "zzz"),
                ("zzz zzz", "https://example.com/3", "zzz"),
                ("alpha", "https://example.com/4", "alpha"),
            ),
        )
        assert report.valid is False
        assert "cov_top3" in report.signals["codes"]
        assert report.signals["cov_max"] >= COVERAGE_THRESHOLD

    def test_confidence_band_is_low_between_threshold_and_high(self) -> None:
        report = validate_results(
            "docker compose tutorial",
            rows(("Docker Hub", "https://hub.docker.com/", "container registry")),
        )
        assert report.valid is True
        assert report.cov_max < HIGH_CONFIDENCE
        assert report.confidence == "low"

    def test_confidence_is_high_above_high_threshold(self) -> None:
        report = validate_results("豆瓣电影", rows(("豆瓣电影", "https://movie.douban.com/", "豆瓣电影")))
        assert report.valid is True and report.confidence == "high"

    def test_threshold_is_above_calibrated_bad_max(self) -> None:
        """夹具上 BAD 最高 0.25，阈值必须严格高于它。"""
        assert COVERAGE_THRESHOLD > 0.25

    def test_threshold_matches_calibration_file(self) -> None:
        path = calibration_path()
        if path is None:
            pytest.skip("threshold_calibration.json 不在本工作区（bugfixes/ 未随仓库分发）")
        best = json.loads(path.read_text(encoding="utf-8"))["best"]["threshold"]
        assert COVERAGE_THRESHOLD == pytest.approx(best)


class TestCrossChannelCriteria:
    def _consistent_rows(self) -> list[dict[str, str]]:
        return rows(*[(f"标题{i}", f"https://site{i}.example.com/page", "正文") for i in range(10)])

    def test_c2_skipped_without_second_channel(self) -> None:
        report = validate_results(
            "标题0", rows(("标题0", "https://site0.example.com/page", "正文")), cross_channel=None
        )
        assert report.signals["cross_channel"] is None
        assert "cross_channel" not in report.signals["codes"]

    def test_same_domains_are_consistent(self) -> None:
        primary = self._consistent_rows()
        other = rows(*[(f"标题{i}", f"https://www.site{i}.example.com/other", "正文") for i in range(10)])
        report = validate_results("标题0", primary, cross_channel=other)
        assert report.valid is True, report.reasons
        assert report.signals["cross_channel"]["jaccard"] >= MIN_CROSS_CHANNEL_JACCARD
        assert "cross_channel" not in report.signals["codes"]

    def test_url_intersection_can_rescue_low_jaccard(self) -> None:
        """Jaccard < 0.3 但 URL 交集 >= 3 时仍视为一致（满足其一即可）。"""
        primary = self._consistent_rows()
        other = rows(
            *[(f"标题{i}", f"https://site{i}.example.com/page", "正文") for i in range(3)],
            *[(f"其他{i}", f"https://other{i}.example.org/page", "正文") for i in range(7)],
        )
        agreement = cross_channel_agreement(primary, other)
        assert agreement["jaccard"] < MIN_CROSS_CHANNEL_JACCARD
        assert agreement["intersection"] >= MIN_CROSS_CHANNEL_INTERSECTION
        assert agreement["consistent"] is True
        assert validate_results("标题0", primary, cross_channel=other).valid is True

    def test_disjoint_channels_are_rejected(self) -> None:
        primary = self._consistent_rows()
        other = rows(*[(f"其它{i}", f"https://unrelated{i}.example.org/page", "正文") for i in range(10)])
        report = validate_results("标题0", primary, cross_channel=other)
        assert report.valid is False
        assert "cross_channel" in report.signals["codes"]
        assert "cov_max" not in report.signals["codes"], "本用例只应由 C2 决定，C3 必须通过"
        assert report.signals["cross_channel"]["consistent"] is False


class TestRowAdapters:
    def test_search_result_objects_are_supported(self) -> None:
        """S3 会直接把 SearchResult 传进来（而不是 dict）。"""
        result = SearchResult(
            index=0, title="豆瓣电影", url="https://movie.douban.com/", snippet="豆瓣电影", engine="bing"
        )
        report = validate_results("豆瓣电影", [result])
        assert report.valid is True
        assert report.n == 1
        assert report.cov_max == pytest.approx(1.0)

    def test_rows_without_url_or_title_are_rejected(self) -> None:
        report = validate_results("测试", [{}])
        assert report.valid is False
        assert "url_ok_ratio" in report.signals["codes"]


class TestFixtureVerdicts:
    @pytest.mark.parametrize("entry", manifest(), ids=[entry["fixture"] for entry in manifest()])
    def test_fixture_verdict_matches_expectation(self, entry: dict[str, Any]) -> None:
        report = validate_results(entry["query"], parse_fixture(entry["fixture"]))
        assert report.valid is entry["expected_ok"], (
            f"{entry['fixture']}（query={entry['query']}）判定不符："
            f"valid={report.valid} reasons={report.reasons} n={report.n}"
        )

    @pytest.mark.parametrize(
        "entry", [item for item in manifest() if item["kind"] == "degraded"],
        ids=[item["fixture"] for item in manifest() if item["kind"] == "degraded"],
    )
    def test_degraded_fixtures_are_rejected(self, entry: dict[str, Any]) -> None:
        """错配页样本必须全部被拦下，一个都不许放行。"""
        assert validate_results(entry["query"], parse_fixture(entry["fixture"])).valid is False

    @pytest.mark.parametrize(
        "entry", [item for item in manifest() if item["kind"] == "good"],
        ids=[item["fixture"] for item in manifest() if item["kind"] == "good"],
    )
    def test_good_fixtures_are_accepted(self, entry: dict[str, Any]) -> None:
        """正常页不许被误杀（误杀会白白多花一次兜底请求）。"""
        assert validate_results(entry["query"], parse_fixture(entry["fixture"])).valid is True

    def test_degraded_pages_are_structurally_normal(self) -> None:
        """反直觉但重要：错配页的 DOM 与正常页同构 —— 结构判据拦不住它们，只有 C3 能。"""
        for entry in [item for item in manifest() if item["kind"] == "degraded"]:
            parsed = parse_fixture(entry["fixture"])
            assert len(parsed) >= 7, f"{entry['fixture']} 结果数过少，夹具可能已损坏"
            assert all(url_is_real(row["url"]) for row in parsed), "去壳后应全部是真实地址"
            assert count_algo_results(fixture_html(entry["fixture"])) >= 1


class TestReadGuards:
    def test_bing_ck_redirect_shell(self) -> None:
        body = (
            "<!DOCTYPE html><html><head><script>//<![CDATA[\n var s = false;\n "
            "function l() { setTimeout(f, 10000); }\n</script></head></html>"
        )
        assert is_js_redirect_shell(body) is True

    def test_normal_page_is_not_shell(self) -> None:
        assert is_js_redirect_shell("<html><body>" + "真实正文" * 3000 + "</body></html>") is False
        assert is_js_redirect_shell("") is False

    def test_empty_body_detection(self) -> None:
        assert looks_like_empty_body("") is True
        assert looks_like_empty_body("<html></html>") is True
        assert looks_like_empty_body("<html><body>" + "正文" * 500 + "</body></html>") is False

    def test_visible_text_strips_scripts(self) -> None:
        html = "<html><head><script>var x='challenges.cloudflare.com';</script></head><body>可见正文</body></html>"
        text = visible_text(html)
        assert "可见正文" in text
        assert "cloudflare" not in text
