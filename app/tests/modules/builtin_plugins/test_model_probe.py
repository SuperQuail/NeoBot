"""模型连通性测试（面板「测试」按钮）。"""

from __future__ import annotations

import httpx
import pytest

from neobot_app.builtin_plugins.dashboard import model_probe


def _patch_transport(monkeypatch, handler) -> list[dict]:
    """把 AsyncClient 换成 MockTransport，并记录 trust_env 参数。"""
    captured: list[dict] = []
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)

    def factory(**kwargs):
        captured.append(dict(kwargs))
        kwargs.pop("trust_env", None)
        kwargs.pop("follow_redirects", None)
        return real_client(transport=transport, **kwargs)

    monkeypatch.setattr(model_probe.httpx, "AsyncClient", factory)
    return captured


def _ok_models(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200, json={"data": [{"id": "deepseek-v4-pro"}, {"id": "deepseek-chat"}]}
    )


@pytest.mark.asyncio
async def test_probe_reports_model_found_and_direct_by_default(monkeypatch) -> None:
    captured = _patch_transport(monkeypatch, _ok_models)

    result = await model_probe.probe_model(
        provider="DeepSeek",
        model_name="deepseek-v4-pro",
        base_url="https://api.deepseek.com",
        api_key="sk-test",
    )

    assert result.ok is True
    assert result.reachable and result.authorized
    assert result.model_found is True
    assert result.status == 200
    assert result.latency_ms is not None
    assert result.url == "https://api.deepseek.com/models"
    assert result.proxy is False
    # 默认直连：不跟随系统代理
    assert captured[-1]["trust_env"] is False


@pytest.mark.asyncio
async def test_probe_uses_system_proxy_when_enabled(monkeypatch) -> None:
    captured = _patch_transport(monkeypatch, _ok_models)

    result = await model_probe.probe_model(
        provider="DeepSeek",
        model_name="deepseek-v4-pro",
        base_url="https://api.deepseek.com/",
        api_key="sk-test",
        use_system_proxy=True,
    )

    assert result.proxy is True
    assert captured[-1]["trust_env"] is True


@pytest.mark.asyncio
async def test_probe_reports_missing_model(monkeypatch) -> None:
    _patch_transport(monkeypatch, _ok_models)

    result = await model_probe.probe_model(
        provider="DeepSeek",
        model_name="not-a-model",
        base_url="https://api.deepseek.com",
        api_key="sk-test",
    )

    assert result.ok is False
    assert result.reachable and result.authorized
    assert result.model_found is False
    assert "未在模型列表" in result.message


@pytest.mark.asyncio
async def test_probe_reports_auth_failure(monkeypatch) -> None:
    _patch_transport(monkeypatch, lambda request: httpx.Response(401, text="unauthorized"))

    result = await model_probe.probe_model(
        provider="DeepSeek",
        model_name="deepseek-v4-pro",
        base_url="https://api.deepseek.com",
        api_key="sk-bad",
    )

    assert result.ok is False
    assert result.reachable is True
    assert result.authorized is False
    assert "鉴权失败" in result.message


@pytest.mark.asyncio
async def test_probe_falls_back_to_chat_when_models_missing(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(404, text="not found")
        return httpx.Response(200, json={"choices": [{"message": {"content": ""}}]})

    _patch_transport(monkeypatch, handler)

    result = await model_probe.probe_model(
        provider="DeepSeek",
        model_name="deepseek-v4-pro",
        base_url="https://api.deepseek.com",
        api_key="sk-test",
    )

    assert result.ok is True
    assert result.url.endswith("/chat/completions")
    assert result.message == "连接、鉴权与模型调用均正常"


@pytest.mark.asyncio
async def test_probe_reports_network_error(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns failure")

    _patch_transport(monkeypatch, handler)

    result = await model_probe.probe_model(
        provider="DeepSeek",
        model_name="deepseek-v4-pro",
        base_url="https://api.deepseek.com",
        api_key="sk-test",
    )

    assert result.ok is False
    assert result.reachable is False
    assert "无法连接供应商" in result.message


@pytest.mark.asyncio
async def test_probe_requires_url_and_key() -> None:
    missing_url = await model_probe.probe_model(
        provider="MyProvider", model_name="x", base_url="", api_key="sk-test"
    )
    missing_key = await model_probe.probe_model(
        provider="MyProvider", model_name="x", base_url="https://x.example.com", api_key=""
    )

    assert missing_url.ok is False and "未配置 URL" in missing_url.message
    assert missing_key.ok is False and "未配置 APIKey" in missing_key.message
