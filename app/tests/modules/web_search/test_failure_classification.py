"""失败分级（fix(9) 附录 B v2 §1）的回归测试。

分级决定"该换什么"：结构类值得同通道重试，内容/网络类必须换来源，
空结果不算失败。用例同时钉住夹具的真实行为（degraded_* / good_*）。
"""

from __future__ import annotations

from pathlib import Path

from neobot_app.web_search.urls import normalize_result_url
from neobot_app.web_search.validate import (
    FailureKind,
    classify_failure,
)

FIXTURES = Path(__file__).parent / "fixtures" / "bing"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8", errors="replace")


def _rows_from_html(html: str) -> list[dict]:
    """用真实页面里的 li.b_algo 组装结果行。

    **必须模拟引擎出口**：真实链路里引擎会先调 urls.normalize_result_url 解壳，
    校验拿到的是已归一化的 URL。夹具页面里的 href 全是 bing.com/ck/a 壳，
    若直接送校验会被判 url_ok_ratio（那是"结构类"，不代表真实语义）。
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    for li in soup.select("li.b_algo"):
        a = li.select_one("h2 a") or li.select_one("a")
        if a is None:
            continue
        url, raw = normalize_result_url("https://www.bing.com/", a.get("href") or "")
        rows.append(
            {
                "title": a.get_text(" ", strip=True),
                "url": url,
                "raw_url": raw,
                "snippet": li.get_text(" ", strip=True)[:200],
            }
        )
    return rows


def test_good_fixture_is_not_a_failure() -> None:
    html = _fixture("good_00_tsinghua.html")
    report = classify_failure("清华大学 官网", _rows_from_html(html), html=html, channel="html")
    assert report.kind is FailureKind.NONE
    assert report.ok is True
    assert report.retry_same_channel is False
    assert report.switch_engine is False


def test_fetch_error_is_network_class() -> None:
    report = classify_failure("任意查询", [], error="httpx.TimeoutException: timed out")
    assert report.kind is FailureKind.NETWORK
    assert report.retry_same_channel is False
    assert report.switch_engine is True
    assert "抓取失败" in report.reason


def test_degraded_fixture_is_content_class() -> None:
    """错配页：结构齐全但与查询无关 → 内容类（换引擎，不重试同通道）。"""
    html = _fixture("degraded_05_zhihu-zhinan.html")
    rows = _rows_from_html(html)
    report = classify_failure("京东 购物", rows, html=html, channel="html")
    assert report.kind is FailureKind.CONTENT
    assert report.retry_same_channel is False
    assert report.switch_engine is True


def test_empty_page_is_empty_class_not_failure_to_switch() -> None:
    """页面明说"没有结果" → EMPTY：不重试、不换引擎（返回 degraded 空结果）。"""
    html = "<html><body><ol id='b_results'><li>没有与此相关的结果</li></ol></body></html>"
    report = classify_failure("不存在的查询 xyzzy", [], html=html, channel="html")
    assert report.kind is FailureKind.EMPTY
    assert report.retry_same_channel is False
    assert report.switch_engine is False


def test_structure_failure_allows_same_channel_retry() -> None:
    """拿到页面、也解析出结果，但结构判据不过 → 结构类，允许同通道重试一次。

    注意不能传空结果：空结果会先命中 no_results（页面上没有结果），那是 EMPTY 语义。
    这里模拟"抽到了行但机器可读结构不合格"（例如半包 HTML）。
    """
    html = "<html><body><ol id='b_results'></ol><main>无关内容</main></body></html>"
    rows = [{"title": "some title", "url": "https://example.com/a", "snippet": "some snippet"}]
    report = classify_failure("任意查询", rows, html=html, channel="html")
    assert report.kind is FailureKind.STRUCTURE
    assert report.retry_same_channel is True
    assert report.switch_engine is True


def test_captcha_hard_signal_is_network_class() -> None:
    html = (
        '<html><body><form id="captcha">请输入验证码</form>'
        "<ol id='b_results'><li class='b_algo'><h2><a href='https://example.com/a'>t</a></h2></li></ol>"
        "</body></html>"
    )
    rows = [{"title": "example", "url": "https://example.com/a", "snippet": "example"}]
    report = classify_failure("example", rows, html=html, channel="html")
    assert report.kind is FailureKind.NETWORK
    assert report.retry_same_channel is False


def test_describe_is_human_readable() -> None:
    report = classify_failure("q", [], error="boom")
    assert report.describe().startswith("network: ")
    assert "boom" in report.describe()
