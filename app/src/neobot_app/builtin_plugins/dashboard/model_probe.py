"""模型连通性测试：检测网络、鉴权与模型是否可用。

面板「模型库」的「测试」按钮使用本模块：按模型条目的供应商 / 地址 / 密钥发一次
轻量请求，报告是否可达、鉴权是否通过、模型名是否在供应商返回的列表中。
代理行为跟随模型自身的 `use_system_proxy` 开关（默认直连）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass(slots=True)
class ModelProbeResult:
    """一次模型连通性测试的结果。"""

    ok: bool
    reachable: bool = False
    authorized: bool = False
    model_found: bool | None = None
    status: int | None = None
    latency_ms: int | None = None
    url: str = ""
    proxy: bool = False
    message: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reachable": self.reachable,
            "authorized": self.authorized,
            "model_found": self.model_found,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "url": self.url,
            "proxy": self.proxy,
            "message": self.message,
            "detail": self.detail,
        }


def _endpoint(base_url: str, path: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        return ""
    return f"{base}/{path.lstrip('/')}"


def _model_matches(target: str, candidate: str) -> bool:
    left = str(target or "").strip().casefold()
    right = str(candidate or "").strip().casefold()
    if not left or not right:
        return False
    return left == right or right.endswith("/" + left) or left.endswith("/" + right)


@dataclass(slots=True)
class ProviderModelList:
    """供应商可用模型列表。"""

    ok: bool
    models: list[str] = field(default_factory=list)
    status: int | None = None
    latency_ms: int | None = None
    url: str = ""
    message: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "models": list(self.models),
            "status": self.status,
            "latency_ms": self.latency_ms,
            "url": self.url,
            "message": self.message,
            "detail": self.detail,
        }


async def list_provider_models(
    *,
    base_url: str,
    api_key: str = "",
    use_system_proxy: bool = False,
    timeout: float = 20.0,
) -> ProviderModelList:
    """读取供应商的 /models 列表（部分供应商不支持时返回空列表与原因）。"""
    url = _endpoint(base_url, "models")
    if not url:
        return ProviderModelList(ok=False, message="供应商未配置 URL")
    headers = {"Authorization": f"Bearer {api_key}"} if str(api_key or "").strip() else {}
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(float(timeout), connect=min(float(timeout), 10.0)),
            trust_env=bool(use_system_proxy),
            follow_redirects=True,
        ) as client:
            response = await client.get(url, headers=headers)
    except httpx.ConnectError as exc:
        return ProviderModelList(
            ok=False, url=url, message="无法连接供应商（DNS/网络/代理问题）", detail=str(exc)[:300]
        )
    except httpx.TimeoutException:
        return ProviderModelList(ok=False, url=url, message=f"连接超时（{timeout:.0f}s）")
    except Exception as exc:  # noqa: BLE001
        return ProviderModelList(
            ok=False, url=url, message=f"拉取失败: {type(exc).__name__}", detail=str(exc)[:300]
        )
    latency = int((time.perf_counter() - started) * 1000)
    if response.status_code in (401, 403):
        return ProviderModelList(
            ok=False, status=response.status_code, latency_ms=latency, url=url,
            message="鉴权失败（请检查供应商 APIKey）", detail=response.text[:300],
        )
    if response.status_code >= 400:
        return ProviderModelList(
            ok=False, status=response.status_code, latency_ms=latency, url=url,
            message=f"供应商返回 HTTP {response.status_code}", detail=response.text[:300],
        )
    try:
        payload = response.json()
    except Exception:
        return ProviderModelList(
            ok=False, status=response.status_code, latency_ms=latency, url=url,
            message="响应不是 JSON，无法解析模型列表", detail=response.text[:300],
        )
    items = payload.get("data") if isinstance(payload, dict) else payload
    models: list[str] = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                name = str(item.get("id") or item.get("name") or "").strip()
            else:
                name = str(item or "").strip()
            if name and name not in models:
                models.append(name)
    models.sort(key=str.casefold)
    return ProviderModelList(
        ok=True, models=models, status=response.status_code, latency_ms=latency, url=url,
        message=f"读取到 {len(models)} 个模型" if models else "供应商未返回模型列表",
    )


async def probe_model(
    *,
    provider: str,
    model_name: str,
    base_url: str,
    api_key: str,
    use_system_proxy: bool = False,
    timeout: float = 20.0,
) -> ModelProbeResult:
    """测试模型是否可用；不抛出异常，全部结果通过返回值表达。"""
    url = _endpoint(base_url, "models")
    if not url:
        return ModelProbeResult(
            ok=False, proxy=use_system_proxy, message=f"供应商 {provider or '未填写'} 未配置 URL"
        )
    if not str(api_key or "").strip():
        return ModelProbeResult(
            ok=False, url=url, proxy=use_system_proxy, message=f"供应商 {provider} 未配置 APIKey"
        )

    headers = {"Authorization": f"Bearer {api_key}"}
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(float(timeout), connect=min(float(timeout), 10.0)),
            trust_env=bool(use_system_proxy),
            follow_redirects=True,
        ) as client:
            response = await client.get(url, headers=headers)
            latency = int((time.perf_counter() - started) * 1000)
            if response.status_code in (401, 403):
                return ModelProbeResult(
                    ok=False,
                    reachable=True,
                    authorized=False,
                    status=response.status_code,
                    latency_ms=latency,
                    url=url,
                    proxy=use_system_proxy,
                    message="网络可达，但鉴权失败（APIKey 无效或无权限）",
                    detail=response.text[:300],
                )
            if response.status_code in (404, 405):
                return await _probe_chat(
                    base_url=base_url,
                    api_key=api_key,
                    model_name=model_name,
                    use_system_proxy=use_system_proxy,
                    timeout=timeout,
                    note="供应商不支持 /models，改用最小对话请求探测",
                )
            if response.status_code >= 400:
                return ModelProbeResult(
                    ok=False,
                    reachable=True,
                    authorized=True,
                    status=response.status_code,
                    latency_ms=latency,
                    url=url,
                    proxy=use_system_proxy,
                    message=f"供应商返回 HTTP {response.status_code}",
                    detail=response.text[:300],
                )

            found: bool | None = None
            detail = ""
            try:
                payload = response.json()
                items = payload.get("data") if isinstance(payload, dict) else payload
                if isinstance(items, list):
                    ids = [
                        str(item.get("id") or item.get("name") or "")
                        for item in items
                        if isinstance(item, dict)
                    ]
                    found = any(_model_matches(model_name, candidate) for candidate in ids)
                    detail = f"供应商返回 {len(ids)} 个模型" + (
                        "，已匹配到目标模型" if found else "，未找到目标模型"
                    )
            except Exception:
                detail = "响应不是 JSON，仅确认网络与鉴权"

            return ModelProbeResult(
                ok=bool(found) if found is not None else True,
                reachable=True,
                authorized=True,
                model_found=found,
                status=response.status_code,
                latency_ms=latency,
                url=url,
                proxy=use_system_proxy,
                message=(
                    "连接正常，模型可用"
                    if found
                    else "连接与鉴权正常，但未在模型列表中看到该模型名"
                ),
                detail=detail,
            )
    except httpx.ConnectError as exc:
        return ModelProbeResult(
            ok=False, url=url, proxy=use_system_proxy,
            message="无法连接供应商（DNS/网络/代理问题）", detail=str(exc)[:300],
        )
    except httpx.TimeoutException:
        return ModelProbeResult(
            ok=False, url=url, proxy=use_system_proxy,
            message=f"连接超时（{timeout:.0f}s）",
        )
    except Exception as exc:  # noqa: BLE001 - 面板需要展示任何失败原因
        return ModelProbeResult(
            ok=False, url=url, proxy=use_system_proxy,
            message=f"测试失败: {type(exc).__name__}", detail=str(exc)[:300],
        )


async def _probe_chat(
    *,
    base_url: str,
    api_key: str,
    model_name: str,
    use_system_proxy: bool,
    timeout: float,
    note: str = "",
) -> ModelProbeResult:
    """用一次最小对话请求探测（部分供应商不提供 /models）。"""
    url = _endpoint(base_url, "chat/completions")
    if not url:
        return ModelProbeResult(ok=False, message="供应商未配置 URL")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
        "stream": False,
    }
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(float(timeout), connect=min(float(timeout), 10.0)),
            trust_env=bool(use_system_proxy),
            follow_redirects=True,
        ) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.ConnectError as exc:
        return ModelProbeResult(
            ok=False, url=url, proxy=use_system_proxy,
            message="无法连接供应商（DNS/网络/代理问题）", detail=str(exc)[:300],
        )
    except httpx.TimeoutException:
        return ModelProbeResult(ok=False, url=url, proxy=use_system_proxy, message=f"请求超时（{timeout:.0f}s）")
    except Exception as exc:  # noqa: BLE001
        return ModelProbeResult(
            ok=False, url=url, proxy=use_system_proxy,
            message=f"测试失败: {type(exc).__name__}", detail=str(exc)[:300],
        )
    latency = int((time.perf_counter() - started) * 1000)
    status = response.status_code
    if status in (401, 403):
        return ModelProbeResult(
            ok=False, reachable=True, authorized=False, status=status, latency_ms=latency,
            url=url, proxy=use_system_proxy,
            message="网络可达，但鉴权失败（APIKey 无效或无权限）", detail=response.text[:300],
        )
    if status >= 400:
        return ModelProbeResult(
            ok=False, reachable=True, authorized=True, status=status, latency_ms=latency,
            url=url, proxy=use_system_proxy,
            message=f"供应商返回 HTTP {status}", detail=response.text[:300],
        )
    return ModelProbeResult(
        ok=True, reachable=True, authorized=True, model_found=True, status=status,
        latency_ms=latency, url=url, proxy=use_system_proxy,
        message="连接、鉴权与模型调用均正常", detail=note,
    )
