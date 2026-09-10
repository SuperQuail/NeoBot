"""BalanceQuerySkill — 按配置的查询方式发出简单网络请求查询供应商余额。

设计：
- 查询方式（各供应商差异极大）以文本形式保存在 config 的每个模型
  balance_query_hint 中，由生成的 balance-query SKILL.md 按需提供给 Agent，
  避免把说明常驻在系统提示词里浪费 token。
- 本 Skill 只提供一个通用 http_request 工具，负责把请求安全地发出去
  （限制方法、体积、超时与公网地址），具体地址与鉴权由 Agent 按 SKILL.md 组装。
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from neobot_app.skills.base import SkillModule
from neobot_app.utils.ssrf import validate_public_url_async

MAX_RESPONSE_BYTES = 256 * 1024
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_TIMEOUT_SECONDS = 60.0
ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"})
MAX_HEADER_COUNT = 32
MAX_HEADER_LENGTH = 4096


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class BalanceQuerySkill(SkillModule):
    """余额查询辅助：一个受限的通用 HTTP 请求工具。"""

    @property
    def name(self) -> str:
        return "balance_query"

    @property
    def description(self) -> str:
        return "按配置的查询方式发出简单网络请求查询模型供应商账户余额"

    @property
    def instructions(self) -> str:
        # 刻意留空：查询方式放在按需读取的 balance-query SKILL.md 中
        return ""

    def get_tools(self) -> list[dict]:
        return [
            self._tool_def(
                "http_request",
                "发出一次简单的 HTTP 请求并返回状态码与响应体，用于按技能说明查询供应商账户余额。"
                "默认只允许公网地址；查询自建平台（局域网地址）时需显式传 allow_private=true。",
                {
                    "properties": {
                        "url": {"type": "string", "description": "完整请求地址（http/https）"},
                        "method": {
                            "type": "string",
                            "enum": sorted(ALLOWED_METHODS),
                            "description": "可选，请求方法，默认 GET",
                        },
                        "headers": {
                            "type": "object",
                            "description": "可选，请求头键值对，如 {\"Authorization\": \"Bearer sk-xxx\"}",
                        },
                        "params": {
                            "type": "object",
                            "description": "可选，URL 查询参数键值对",
                        },
                        "body": {"type": "string", "description": "可选，原始请求体字符串"},
                        "json": {"type": "object", "description": "可选，JSON 请求体（与 body 二选一）"},
                        "timeout_seconds": {
                            "type": "number",
                            "description": f"可选，超时秒数，默认 {DEFAULT_TIMEOUT_SECONDS:g}，最大 {MAX_TIMEOUT_SECONDS:g}",
                        },
                        "allow_private": {
                            "type": "boolean",
                            "description": "可选，是否允许请求局域网/本机地址，默认 false",
                        },
                    },
                    "required": ["url"],
                },
            )
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        if tool_name != "http_request":
            return _json({"ok": False, "error": f"未知工具: {tool_name}"})
        return await self._execute_http_request(args)

    async def _execute_http_request(self, args: dict[str, Any]) -> str:
        url = str(args.get("url") or "").strip()
        if not url:
            return _json({"ok": False, "error": "url 不能为空"})
        method = str(args.get("method") or "GET").strip().upper()
        if method not in ALLOWED_METHODS:
            return _json({"ok": False, "error": f"不支持的请求方法: {method}"})
        allow_private = bool(args.get("allow_private"))
        if not allow_private and not await validate_public_url_async(url):
            return _json({
                "ok": False,
                "error": "目标地址不是公网地址，已拒绝。若查询自建平台请在参数中设置 allow_private=true",
            })

        headers: dict[str, str] = {}
        raw_headers = args.get("headers")
        if isinstance(raw_headers, dict):
            if len(raw_headers) > MAX_HEADER_COUNT:
                return _json({"ok": False, "error": f"请求头数量超过 {MAX_HEADER_COUNT} 个"})
            for key, value in raw_headers.items():
                text = str(value)
                if len(text) > MAX_HEADER_LENGTH:
                    return _json({"ok": False, "error": f"请求头 {key} 过长"})
                headers[str(key)] = text

        params = args.get("params") if isinstance(args.get("params"), dict) else None
        json_body = args.get("json") if isinstance(args.get("json"), dict) else None
        body = args.get("body")
        body_text = None if body is None else str(body)
        if json_body is not None and body_text is not None:
            return _json({"ok": False, "error": "json 与 body 不能同时提供"})

        try:
            timeout = float(args.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS)
        except (TypeError, ValueError):
            timeout = DEFAULT_TIMEOUT_SECONDS
        timeout = max(1.0, min(MAX_TIMEOUT_SECONDS, timeout))

        try:
            async with httpx.AsyncClient(follow_redirects=False, timeout=timeout) as client:
                response = await client.request(
                    method,
                    url,
                    headers=headers or None,
                    params=params,
                    content=body_text,
                    json=json_body,
                )
                raw = response.content
                truncated = len(raw) > MAX_RESPONSE_BYTES
                if truncated:
                    raw = raw[:MAX_RESPONSE_BYTES]
        except httpx.HTTPError as exc:
            return _json({"ok": False, "error": f"请求失败: {exc}"})
        except Exception as exc:
            return _json({"ok": False, "error": f"请求异常: {exc}"})

        text = raw.decode(response.encoding or "utf-8", errors="replace")
        payload: dict[str, Any] = {
            "ok": True,
            "status": response.status_code,
            "url": str(response.request.url),
            "content_type": response.headers.get("content-type", ""),
            "truncated": truncated,
            "body": text,
        }
        if response.headers.get("location"):
            payload["location"] = response.headers["location"]
            payload["note"] = "服务端返回重定向，未自动跟随"
        try:
            payload["json"] = json.loads(text)
        except Exception:
            payload["json"] = None
        return _json(payload)
