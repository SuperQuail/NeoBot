"""业务码判定（对照 amagi platforms/bilibili/judge.ts 与 contracts/error.ts）。"""

from __future__ import annotations

import pytest

from bilibili.judge import (
    ANTIBOT_PAGE,
    COOKIE_EXPIRED,
    NOT_FOUND,
    PLATFORM_ERROR,
    PLATFORM_UNAVAILABLE,
    RATE_LIMITED,
    RISK_CONTROL,
    judge,
)


class TestSuccess:
    def test_code_zero_is_ok(self):
        assert judge({"code": 0, "data": {"room_id": 1}}).ok

    def test_missing_code_is_ok(self):
        assert judge({"data": {}}).ok

    def test_empty_data_is_ok(self):
        assert judge({"code": 0, "data": None}).ok

    def test_live_time_zero_is_ok(self):
        assert judge({"code": 0, "data": {"live_time": 0}}).ok


class TestPlatformCodes:
    def test_risk_control_is_retryable(self):
        verdict = judge({"code": -412, "message": "请求被拦截"})
        assert (verdict.ok, verdict.kind, verdict.code, verdict.retryable) == (
            False,
            "risk",
            RISK_CONTROL,
            True,
        )
        assert verdict.platform_code == -412
        assert verdict.message == "请求被拦截"

    def test_not_logged_in_is_not_retryable(self):
        verdict = judge({"code": -101, "message": "账号未登录"})
        assert (verdict.kind, verdict.code, verdict.retryable) == ("auth", COOKIE_EXPIRED, False)

    def test_not_found(self):
        verdict = judge({"code": -404, "message": "啥都木有"})
        assert (verdict.kind, verdict.code) == ("not_found", NOT_FOUND)

    def test_feng_kong_verify_failure_is_retryable_improvement(self):
        """改进项：amagi 把 -352 归入 unknown 且不重试。"""
        verdict = judge({"code": -352, "message": "风控校验失败"})
        assert (verdict.kind, verdict.code, verdict.retryable) == ("risk", RISK_CONTROL, True)

    def test_too_many_requests_is_retryable_improvement(self):
        """改进项：amagi 把 -509 归入 unknown 且不重试。"""
        verdict = judge({"code": -509, "message": "请求过于频繁"})
        assert (verdict.kind, verdict.code, verdict.retryable) == (
            "rate_limit",
            RATE_LIMITED,
            True,
        )

    def test_unknown_business_code_is_not_retryable(self):
        verdict = judge({"code": 62002, "message": "稿件不可见"})
        assert (verdict.kind, verdict.code, verdict.retryable) == (
            "unknown",
            PLATFORM_ERROR,
            False,
        )
        assert verdict.platform_code == 62002


class TestNonJsonAndEmpty:
    """空响应体不是登录失效：一次网络抖动不该把用户引去重新扫码。"""

    @pytest.mark.parametrize("raw", [None, ""])
    def test_empty_body_is_retryable_unavailable(self, raw):
        verdict = judge(raw)
        assert (verdict.kind, verdict.code, verdict.retryable) == (
            "unavailable",
            PLATFORM_UNAVAILABLE,
            True,
        )
        assert verdict.kind != "auth"
        assert verdict.code != COOKIE_EXPIRED

    def test_empty_body_with_timeout_status_is_timeout(self):
        verdict = judge("", http_status=408)
        assert (verdict.kind, verdict.code, verdict.retryable) == ("timeout", "TIMEOUT", True)

    def test_empty_body_keeps_meaningful_http_status(self):
        # 有明确状态码时以状态码为准：429 仍是限流、404 仍是没找到
        assert judge("", http_status=429).code == RATE_LIMITED
        assert judge("", http_status=404).code == NOT_FOUND

    def test_html_page_is_antibot_and_retryable(self):
        verdict = judge("<html>403 forbidden</html>")
        assert (verdict.kind, verdict.code, verdict.retryable) == (
            "risk",
            ANTIBOT_PAGE,
            True,
        )


class TestMessageExtraction:
    @pytest.mark.parametrize(
        "payload,expected",
        [
            ({"code": -412, "message": "A"}, "A"),
            ({"code": -412, "status_msg": "B"}, "B"),
            ({"code": -412, "msg": "C"}, "C"),
            ({"code": -412, "error_msg": "D"}, "D"),
            ({"code": -412, "msg": "C", "message": "A"}, "A"),
        ],
    )
    def test_message_priority(self, payload, expected):
        assert judge(payload).message == expected

    @pytest.mark.parametrize(
        "payload",
        [{"status_code": -412}, {"statusCode": -412}, {"result": -412}],
    )
    def test_alternative_code_fields(self, payload):
        assert judge(payload).code == RISK_CONTROL


class TestHttpFallback:
    def test_2xx_is_ok(self):
        assert judge({"data": {}}, http_status=200).ok

    @pytest.mark.parametrize(
        "status,code,retryable",
        [
            (401, "LOGIN_REQUIRED", False),
            (403, RISK_CONTROL, True),
            (404, NOT_FOUND, False),
            (408, "TIMEOUT", True),
            (429, RATE_LIMITED, True),
            (503, "PLATFORM_UNAVAILABLE", True),
        ],
    )
    def test_http_status_mapping(self, status, code, retryable):
        verdict = judge({}, http_status=status)
        assert verdict.code == code
        assert verdict.retryable is retryable

    def test_business_code_wins_over_http_status(self):
        """amagi judge.test.ts:101-108：-412 优先于 HTTP 412。"""
        verdict = judge({"code": -412}, http_status=412)
        assert verdict.code == RISK_CONTROL

