"""回给模型的工具错误详情必须先脱敏（异常文本里可能带密钥）。

这个分支此前没有任何测试：模型侧用的是 orchestrator 自己的一套正则，它只认
``key=value`` 与 ``Bearer``，异常里直接出现的 ``sk-...`` 会整条漏进 LLM 上下文。
"""

from __future__ import annotations

from neobot_app.reply.orchestrator import _scrub_secret_values


def test_bare_sk_key_is_scrubbed() -> None:
    text = _scrub_secret_values(
        "OpenAIError: Incorrect API key provided: sk-proj-ABCdef123456789"
    )

    assert "sk-proj-ABCdef123456789" not in text
    assert "<redacted>" in text


def test_prefixed_key_names_are_scrubbed() -> None:
    for name in ("client_secret", "DEEPSEEK_APIKEY", "csrf_token"):
        text = _scrub_secret_values(f"{name}=abcdef123456")

        assert "abcdef123456" not in text, name


def test_url_userinfo_is_scrubbed() -> None:
    text = _scrub_secret_values("GET https://admin:hunter2@example.com/x 失败")

    assert "hunter2" not in text


def test_bearer_prefix_is_kept() -> None:
    """``Bearer`` 形态保留前缀（Authorization: 形态由键名规则整条吃掉，同样安全）。"""
    text = _scrub_secret_values("unauthorized: Bearer abcDEF123.xyz")

    assert "abcDEF123.xyz" not in text
    assert "Bearer <redacted>" in text


def test_authorization_header_value_is_scrubbed() -> None:
    text = _scrub_secret_values("Authorization: Bearer abcDEF123.xyz")

    assert "abcDEF123.xyz" not in text
    assert "<redacted>" in text


def test_plain_text_is_untouched() -> None:
    text = "工具执行失败 [sandbox__read_file]: FileNotFoundError: no such file"

    assert _scrub_secret_values(text) == text
