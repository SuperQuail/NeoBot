"""B站只读 Skill：工具清单、参数转发、降级与只读说明。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from neobot_app.bilibili.client import BilibiliClient
from neobot_app.skills.base import SkillManager
from neobot_app.skills.bilibili_read import BilibiliReadSkill

_READ_ONLY_NOTE = "只读查询：不会发评论、私信、动态或点赞。"
_TOOL_NAMES = {
    "dynamic_detail",
    "user_dynamics",
    "article",
    "bangumi",
    "user_card",
    "user_live_status",
    "video_stream",
    "video_danmaku",
    "expand_b23",
}


class FakeReadApi:
    """只记录调用并返回预置结果的只读 API 替身。"""

    def __init__(self, results: dict[str, Any] | None = None) -> None:
        self.results = dict(results or {})
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)

        def call(*args: Any, **kwargs: Any) -> dict[str, Any]:
            self.calls.append((name, args, kwargs))
            return self.results.get(name, {"ok": True, "tool": name})

        return call


def _skill(api: FakeReadApi) -> BilibiliReadSkill:
    return BilibiliReadSkill(read_api=api)


def test_tool_list_and_read_only_descriptions() -> None:
    skill = BilibiliReadSkill(read_api=FakeReadApi())

    tools = {tool["function"]["name"]: tool["function"] for tool in skill.get_tools()}

    assert set(tools) == _TOOL_NAMES
    for function in tools.values():
        assert "只读" in function["description"]
    assert "只读" in skill.instructions
    assert "不会发评论" in skill.instructions


def test_no_dependency_means_no_tools() -> None:
    assert BilibiliReadSkill().get_tools() == []


def test_registers_with_skill_manager() -> None:
    manager = SkillManager()
    manager.register(BilibiliReadSkill(client=SimpleNamespace()))

    names = {tool["function"]["name"] for tool in manager.get_tools()}
    assert {f"bilibili_read__{name}" for name in _TOOL_NAMES} <= names


async def test_dynamic_detail_and_user_dynamics() -> None:
    api = FakeReadApi({"dynamic_detail": {"ok": True, "item": {"title": "动态"}}})
    skill = _skill(api)

    raw = await skill.execute("dynamic_detail", {"dynamic_id": "123"})
    result = json.loads(raw)
    dynamics = json.loads(await skill.execute("user_dynamics", {"mid": "42", "limit": 5}))

    assert result["ok"] is True
    assert result["item"]["title"] == "动态"
    assert result["note"] == _READ_ONLY_NOTE
    assert "动态" in raw  # ensure_ascii=False
    assert api.calls[0] == ("dynamic_detail", ("123",), {})
    assert dynamics["ok"] is True
    assert api.calls[1] == ("user_dynamics", (42,), {"limit": 5})


async def test_article_info_merges_content() -> None:
    api = FakeReadApi(
        {
            "article_info": {"ok": True, "cv_id": 777, "info": {"title": "标题"}},
            "article_content": {
                "ok": True,
                "cv_id": 777,
                "title": "标题",
                "author": "作者",
                "content": "<p>正文</p>",
                "publish_time": 1_700_000_000,
            },
        }
    )
    skill = _skill(api)

    result = json.loads(await skill.execute("article", {"cv_id": "cv777"}))

    assert result["ok"] is True
    assert result["author"] == "作者"
    # 正文去掉 HTML 标签再回给模型。
    assert result["content"] == "正文"
    assert api.calls[0] == ("article_info", ("cv777",), {})
    assert api.calls[1] == ("article_content", ("cv777",), {})


async def test_article_without_content_and_cards() -> None:
    api = FakeReadApi(
        {
            "article_info": {"ok": True, "cv_id": 777},
            "article_cards": {"ok": True, "ids": ["1", "2"], "cards": {}},
        }
    )
    skill = _skill(api)

    info = json.loads(await skill.execute("article", {"cv_id": 777, "include_content": False}))
    cards = json.loads(await skill.execute("article", {"ids": "1,2"}))

    assert info["ok"] is True and "content" not in info
    assert all(name != "article_content" for name, _, _ in api.calls)
    assert cards["ok"] is True
    assert api.calls[-1] == ("article_cards", (["1", "2"],), {})


async def test_article_content_failure_keeps_info() -> None:
    api = FakeReadApi(
        {
            "article_info": {"ok": True, "cv_id": 777},
            "article_content": {"ok": False, "error": "正文读取失败：风控"},
        }
    )

    result = json.loads(await _skill(api).execute("article", {"cv_id": 777}))

    assert result["ok"] is True
    assert result["content_error"] == "正文读取失败：风控"


async def test_bangumi_info_and_optional_stream() -> None:
    api = FakeReadApi(
        {
            "bangumi_info": {"ok": True, "ep_id": 330798, "info": {"title": "番剧"}},
            "bangumi_stream": {"ok": True, "format": "dash", "url": "https://x/ep.m4s"},
        }
    )
    skill = _skill(api)

    info = json.loads(await skill.execute("bangumi", {"ep_id": "ep330798"}))
    with_stream = json.loads(await skill.execute("bangumi", {"ep_id": "ep330798", "cid": 123, "qn": 64}))
    season_only = json.loads(await skill.execute("bangumi", {"season_id": "ss33802", "cid": 123}))

    assert info["ok"] is True and "stream" not in info
    assert all(name != "bangumi_stream" for name, _, _ in api.calls[:2])
    assert with_stream["stream"]["url"] == "https://x/ep.m4s"
    assert api.calls[-2] == (
        "bangumi_stream",
        ("ep330798", 123),
        {"qn": 64},
    )
    assert season_only["ok"] is True
    assert "ep_id" in season_only["stream_error"]


async def test_user_card_live_status_stream_danmaku_and_b23() -> None:
    api = FakeReadApi()
    skill = _skill(api)

    card = json.loads(await skill.execute("user_card", {"mid": "42"}))
    live = json.loads(await skill.execute("user_live_status", {"mid": 42}))
    stream = json.loads(await skill.execute("video_stream", {"bvid": "BV1xx411c7mD", "cid": "9"}))
    danmaku = json.loads(await skill.execute("video_danmaku", {"cid": 9, "limit": 30}))
    short = json.loads(await skill.execute("expand_b23", {"url": "b23.tv/abc"}))

    assert all(item["ok"] is True for item in (card, live, stream, danmaku, short))
    assert api.calls[0] == ("user_card", (42,), {})
    assert api.calls[1] == ("user_live_status", (42,), {})
    assert api.calls[2] == ("video_stream", ("BV1xx411c7mD", 9), {"qn": 80})
    assert api.calls[3] == ("video_danmaku", (9,), {"limit": 30})
    assert api.calls[4] == ("expand_b23", ("b23.tv/abc",), {})


async def test_invalid_arguments_and_unknown_tool() -> None:
    api = FakeReadApi()
    skill = _skill(api)

    results = [
        json.loads(await skill.execute("nope", {})),
        json.loads(await skill.execute("dynamic_detail", {})),
        json.loads(await skill.execute("user_dynamics", {"mid": 0})),
        json.loads(await skill.execute("article", {})),
        json.loads(await skill.execute("bangumi", {})),
        json.loads(await skill.execute("user_card", {})),
        json.loads(await skill.execute("user_live_status", {"mid": -1})),
        json.loads(await skill.execute("video_stream", {"bvid": "BV1", "cid": 0})),
        json.loads(await skill.execute("video_danmaku", {"cid": 0})),
        json.loads(await skill.execute("expand_b23", {})),
    ]

    assert all(result["ok"] is False for result in results)
    assert api.calls == []


async def test_dormant_service_returns_readable_error() -> None:
    skill = BilibiliReadSkill(service=SimpleNamespace(available=False, client=None))

    result = json.loads(await skill.execute("user_card", {"mid": 42}))

    assert result["ok"] is False
    assert "未登录" in result["error"]


async def test_live_client_wiring() -> None:
    # 真客户端 + 只替身 _fetch：断层在 HTTP 层，不依赖线程内 session 归属。
    calls: list[dict[str, Any]] = []

    class FetchClient(BilibiliClient):
        def _fetch(self, method, url, params=None, **kwargs):  # type: ignore[override]
            calls.append({"method": method, "url": url, "params": params})
            return {"code": 0, "data": {"roomid": 123, "live_status": 0}}

    result = json.loads(
        await BilibiliReadSkill(client=FetchClient("sessdata", "bili-jct", 7)).execute(
            "user_live_status", {"mid": 42}
        )
    )

    assert result["ok"] is True
    assert result["info"]["roomid"] == 123
    assert result["note"] == _READ_ONLY_NOTE
    assert calls[0]["params"] == {"mid": 42}


class _FetchClient:
    """只实现 _fetch 的客户端替身：BilibiliReadApi 只用到这一层。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def _fetch(self, method: str, url: str, params: Any = None, **kwargs: Any) -> dict:
        self.calls.append({"method": method, "url": url, "params": params})
        return {"code": 0, "data": {"card": {"mid": 42, "name": "UP"}, "fans": 1}}


class _Service:
    """按 refresh() 结果切换可用性的 service 替身。"""

    def __init__(self, client: _FetchClient, *, refresh_result: bool, error: str = "") -> None:
        self.client = client
        self.available = False
        self.refresh_result = refresh_result
        self.error = error
        self.refresh_calls = 0

    async def refresh(self) -> bool:
        self.refresh_calls += 1
        self.available = self.refresh_result
        return self.available

    def status(self) -> dict[str, Any]:
        return {"available": self.available, "error": self.error}


async def test_login_gate_refreshes_service_before_reporting() -> None:
    client = _FetchClient()
    service = _Service(client, refresh_result=True)

    result = json.loads(
        await BilibiliReadSkill(service=service).execute("user_card", {"mid": 42})
    )

    assert result["ok"] is True
    assert service.refresh_calls == 1
    assert client.calls  # refresh 之后才真的发请求


async def test_login_gate_keeps_service_reason_when_dormant() -> None:
    service = _Service(
        _FetchClient(),
        refresh_result=False,
        error="B站登录态校验失败（网络异常）：Timeout",
    )

    result = json.loads(
        await BilibiliReadSkill(service=service).execute("user_card", {"mid": 42})
    )

    assert result["ok"] is False
    assert "未登录" in result["error"]
    assert "网络异常" in result["error"]
    assert service.refresh_calls == 1


async def test_article_body_is_stripped_and_truncated() -> None:
    body = "<p>" + "字" * 6000 + "</p>"
    api = FakeReadApi(
        {
            "article_info": {"ok": True, "cv_id": 777},
            "article_content": {"ok": True, "content": body, "author": "作者"},
        }
    )

    result = json.loads(await _skill(api).execute("article", {"cv_id": 777}))

    assert result["content_truncated"] is True
    assert result["content_chars"] == 6000
    assert len(result["content"]) < 6000
    assert "<p>" not in result["content"]
