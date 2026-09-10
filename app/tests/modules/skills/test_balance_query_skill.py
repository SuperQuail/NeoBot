"""余额查询技能：http_request 工具的边界与正常路径。"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from neobot_app.skills.balance_query_skill import BalanceQuerySkill


class _Handler(BaseHTTPRequestHandler):
    received: dict = {}

    def do_GET(self) -> None:  # noqa: N802 - http.server 约定
        type(self).received = {"path": self.path, "headers": dict(self.headers)}
        body = json.dumps({"balance": 12.5, "currency": "CNY"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:  # 静默
        return


@pytest.fixture()
def local_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()


async def test_http_request_blocks_private_without_opt_in(local_server: str) -> None:
    skill = BalanceQuerySkill()

    result = json.loads(await skill.execute("http_request", {"url": local_server + "/balance"}))

    assert result["ok"] is False
    assert "公网" in result["error"]


async def test_http_request_allows_private_with_opt_in(local_server: str) -> None:
    skill = BalanceQuerySkill()

    result = json.loads(
        await skill.execute(
            "http_request",
            {
                "url": local_server + "/balance?key=1",
                "headers": {"Authorization": "Bearer sk-test"},
                "allow_private": True,
            },
        )
    )

    assert result["ok"] is True
    assert result["status"] == 200
    assert result["json"]["balance"] == 12.5
    assert _Handler.received["headers"]["Authorization"] == "Bearer sk-test"
    assert "key=1" in _Handler.received["path"]


async def test_http_request_rejects_bad_method() -> None:
    skill = BalanceQuerySkill()

    result = json.loads(
        await skill.execute("http_request", {"url": "https://example.com", "method": "TRACE"})
    )

    assert result["ok"] is False
    assert "方法" in result["error"]


async def test_http_request_rejects_empty_url() -> None:
    skill = BalanceQuerySkill()

    result = json.loads(await skill.execute("http_request", {}))

    assert result["ok"] is False
    assert "url" in result["error"]


async def test_http_request_unknown_tool() -> None:
    skill = BalanceQuerySkill()

    result = json.loads(await skill.execute("nope", {}))

    assert result["ok"] is False


def test_skill_has_no_prompt_instructions() -> None:
    """按需读取：说明文本不得常驻系统提示词。"""
    assert BalanceQuerySkill().instructions == ""
    assert BalanceQuerySkill().name == "balance_query"
    tools = BalanceQuerySkill().get_tools()
    assert [item["function"]["name"] for item in tools] == ["http_request"]
