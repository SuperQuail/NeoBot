"""B 站只读接口扩展：端点、参数、解析与降级（全部离线）。"""

from __future__ import annotations

import pytest
import requests

from neobot_app.bilibili.client import BilibiliClient
from neobot_app.bilibili.read_api import BilibiliReadApi

from ._fakes import FakeResponse, FakeSession

_NAV_WBI = {
    "code": 0,
    "data": {
        "isLogin": True,
        "mid": 7,
        "wbi_img": {
            "img_url": "https://i0.hdslb.com/bfs/wbi/" + "a" * 32 + ".png",
            "sub_url": "https://i0.hdslb.com/bfs/wbi/" + "b" * 32 + ".png",
        },
    },
}

_PLAYURL_DASH = {
    "code": 0,
    "data": {
        "quality": 80,
        "accept_quality": [80, 64],
        "dash": {
            "video": [
                {"id": 64, "base_url": "https://x/64.m4s", "bandwidth": 100},
                {
                    "id": 80,
                    "base_url": "https://x/80.m4s",
                    "bandwidth": 200,
                    "backup_url": ["https://x/80b.m4s"],
                    "codecs": "avc1",
                },
            ]
        },
    },
}

_DANMAKU_XML = (
    '<?xml version="1.0" encoding="UTF-8"?><i>'
    '<d p="1.50,1,25,16711680,1700000000,0,abc,1">第一条</d>'
    '<d p="2,5,25,255,1700000001,0,def,2">第二条</d>'
    '<d p="坏,1,25,0,1700000002,0,ghi,3">坏时间</d>'
    "</i>"
)


class _TextResponse(FakeResponse):
    """带 text/headers 的响应替身（弹幕 XML、短链跳转）。"""

    def __init__(
        self,
        text: str = "",
        *,
        location: str = "",
        status_code: int = 200,
    ) -> None:
        super().__init__(None, status_code=status_code)
        self.text = text
        self.headers = {"Location": location} if location else {}


def _redirect(location: str, status_code: int = 302) -> _TextResponse:
    return _TextResponse(location=location, status_code=status_code)


def _api(session: FakeSession) -> BilibiliReadApi:
    client = BilibiliClient("sessdata", "bili-jct", 7, session=session)
    return BilibiliReadApi(client)


def test_constructor_requires_client_with_fetch() -> None:
    with pytest.raises(ValueError):
        BilibiliReadApi(object())


def test_dynamic_detail_hits_detail_endpoint() -> None:
    session = FakeSession([FakeResponse({"code": 0, "data": {"item": {"id_str": "123", "type": "DYNAMIC_TYPE_WORD"}}})])

    result = _api(session).dynamic_detail("123")

    assert result["ok"] is True
    assert result["dynamic_id"] == "123"
    assert result["item"]["id_str"] == "123"
    call = session.calls[0]
    assert call["url"].endswith("/x/polymer/web-dynamic/v1/detail")
    assert call["params"]["id"] == "123"
    assert call["params"]["features"].startswith("itemOpusStyle")
    assert call["headers"]["Referer"] == "https://t.bilibili.com/"


def test_user_dynamics_signs_and_limits_items() -> None:
    items = [{"id_str": str(index)} for index in range(3)]
    session = FakeSession(
        [
            FakeResponse(_NAV_WBI),
            FakeResponse({"code": 0, "data": {"items": items, "has_more": True}}),
        ]
    )

    result = _api(session).user_dynamics(42, limit=2)

    assert result["ok"] is True
    assert [item["id_str"] for item in result["items"]] == ["0", "1"]
    assert result["count"] == 2
    assert result["has_more"] is True
    call = session.calls[-1]
    assert call["url"].endswith("/x/polymer/web-dynamic/v1/feed/space")
    params = call["params"]
    assert params["host_mid"] == "42"
    assert params["platform"] == "web"
    assert len(params["w_rid"]) == 32
    assert call["headers"]["Origin"] == "https://space.bilibili.com"
    assert call["headers"]["Referer"] == "https://space.bilibili.com/42/dynamic"


def test_article_info_content_and_cards() -> None:
    session = FakeSession(
        [
            FakeResponse({"code": 0, "data": {"title": "标题", "stats": {"view": 5}}}),
            FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "title": "标题",
                        "author_name": "作者",
                        "content": "<p>正文</p>",
                        "publish_time": 1_700_000_000,
                    },
                }
            ),
            FakeResponse({"code": 0, "data": {"cards": {"1": {"title": "卡片"}}}}),
        ]
    )
    api = _api(session)

    info = api.article_info("cv777")
    content = api.article_content("https://www.bilibili.com/read/cv777")
    cards = api.article_cards(["1", "2"])

    assert info["ok"] is True and info["cv_id"] == 777
    assert info["info"]["title"] == "标题"
    assert content["ok"] is True
    assert content["author"] == "作者" and content["content"] == "<p>正文</p>"
    assert cards["ok"] is True and cards["ids"] == ["1", "2"]
    assert cards["cards"]["cards"]["1"]["title"] == "卡片"
    assert session.calls[0]["url"].endswith("/x/article/viewinfo")
    assert session.calls[0]["params"] == {"id": 777}
    assert session.calls[1]["url"].endswith("/x/article/view")
    assert session.calls[1]["params"] == {"id": 777}
    assert session.calls[2]["url"].endswith("/x/article/cards")
    assert session.calls[2]["params"] == {"ids": "1,2"}


def test_bangumi_info_prefers_ep_and_accepts_season() -> None:
    session = FakeSession(
        [
            FakeResponse({"code": 0, "result": {"season_id": 33802, "title": "番剧"}}),
            FakeResponse({"code": 0, "result": {"season_id": 33802}}),
        ]
    )
    api = _api(session)

    info = api.bangumi_info(ep_id="ep330798")
    season = api.bangumi_info(season_id="ss33802")

    assert info["ok"] is True and info["ep_id"] == 330798
    assert info["info"]["title"] == "番剧"
    assert season["season_id"] == 33802
    assert session.calls[0]["url"].endswith("/pgc/view/web/season")
    assert session.calls[0]["params"] == {"ep_id": 330798}
    assert session.calls[1]["params"] == {"season_id": 33802}


def test_bangumi_stream_parses_dash() -> None:
    session = FakeSession([FakeResponse({"code": 0, "result": _PLAYURL_DASH["data"]})])

    result = _api(session).bangumi_stream("ep330798", 123, qn=80)

    assert result["ok"] is True
    assert result["ep_id"] == 330798 and result["cid"] == 123
    assert result["format"] == "dash"
    assert result["url"] == "https://x/80.m4s"
    call = session.calls[0]
    assert call["url"].endswith("/pgc/player/web/playurl")
    assert call["params"] == {"ep_id": 330798, "cid": 123, "qn": 80, "fnval": 4048, "fourk": 1}


def test_user_card_and_live_status() -> None:
    session = FakeSession(
        [
            FakeResponse({"code": 0, "data": {"card": {"mid": 42, "name": "UP"}, "follower": 99}}),
            FakeResponse({"code": 0, "data": {"roomid": 123, "live_status": 1}}),
        ]
    )
    api = _api(session)

    card = api.user_card(42)
    live = api.user_live_status(42)

    assert card["ok"] is True and card["info"]["card"]["name"] == "UP"
    assert live["ok"] is True and live["info"]["live_status"] == 1
    assert session.calls[0]["url"].endswith("/x/web-interface/card")
    assert session.calls[0]["params"] == {"mid": 42, "photo": "true"}
    assert session.calls[1]["url"] == "https://api.live.bilibili.com/room/v1/Room/getRoomInfoOld"
    assert session.calls[1]["params"] == {"mid": 42}


def test_user_card_detail_normalizes_card_stats() -> None:
    session = FakeSession(
        [
            FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "card": {
                            "mid": 42,
                            "name": "UP",
                            "sign": "签名",
                            "face": "https://i0.hdslb.com/bfs/face/42.jpg",
                            "fans": 100,
                            "attention": 3,
                            "level_info": {"current_level": 6},
                        },
                        "follower": 100,
                        "archive_count": 8,
                        "article_count": 2,
                        "like_num": 999,
                    },
                }
            )
        ]
    )

    result = _api(session).user_card_detail(42)

    assert result == {
        "ok": True,
        "uid": 42,
        "name": "UP",
        "sign": "签名",
        "level": 6,
        "fans": 100,
        "following": 3,
        "videos": 8,
        "articles": 2,
        "likes": 999,
        "face": "https://i0.hdslb.com/bfs/face/42.jpg",
        "url": "https://space.bilibili.com/42",
    }
    call = session.calls[0]
    assert call["url"].endswith("/x/web-interface/card")
    assert call["params"] == {"mid": 42, "photo": "true"}


def test_user_card_detail_falls_back_to_follower_and_request_mid() -> None:
    session = FakeSession(
        [
            FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "card": {"name": "UP", "level_info": {"current_level": 3}},
                        "follower": 55,
                    },
                }
            )
        ]
    )

    result = _api(session).user_card_detail(42)

    assert result["ok"] is True
    assert result["uid"] == 42  # card.mid 缺失时回退到请求的 mid
    assert result["fans"] == 55
    assert result["following"] == 0 and result["videos"] == 0
    assert result["url"] == "https://space.bilibili.com/42"


def test_user_card_detail_passes_failure_through() -> None:
    session = FakeSession([FakeResponse({"code": -352, "message": "风控校验失败"})])

    result = _api(session).user_card_detail(42)

    assert result["ok"] is False
    assert set(result) == {"ok", "error"}
    assert "用户名片读取失败" in result["error"]
    assert "风控校验失败" in result["error"]


def test_video_stream_picks_requested_quality_and_signs() -> None:
    session = FakeSession([FakeResponse(_NAV_WBI), FakeResponse(_PLAYURL_DASH)])

    result = _api(session).video_stream("BV1xx411c7mD", 170001, qn=80)

    assert result["ok"] is True
    assert result["format"] == "dash"
    assert result["url"] == "https://x/80.m4s"
    assert result["backup"] == ["https://x/80b.m4s"]
    assert result["quality"] == 80
    assert result["accept_quality"] == [80, 64]
    call = session.calls[-1]
    assert call["url"].endswith("/x/player/wbi/playurl")
    params = call["params"]
    assert params["bvid"] == "BV1xx411c7mD"
    assert params["cid"] == "170001"
    assert params["qn"] == "80"
    assert params["fnval"] == "4048"
    assert len(params["w_rid"]) == 32
    assert call["headers"]["Referer"] == "https://www.bilibili.com/video/BV1xx411c7mD"


def test_video_stream_falls_back_to_best_bandwidth() -> None:
    session = FakeSession([FakeResponse(_NAV_WBI), FakeResponse(_PLAYURL_DASH)])

    result = _api(session).video_stream("BV1xx411c7mD", 1, qn=112)

    assert result["url"] == "https://x/80.m4s"
    assert result["quality"] == 80


def test_video_stream_parses_flv_durl() -> None:
    payload = {
        "code": 0,
        "data": {
            "quality": 32,
            "durl": [{"url": "https://x/v.flv", "backup_url": ["https://x/b.flv"]}],
        },
    }
    session = FakeSession([FakeResponse(_NAV_WBI), FakeResponse(payload)])

    result = _api(session).video_stream("BV1xx411c7mD", 1)

    assert result["format"] == "flv"
    assert result["url"] == "https://x/v.flv"
    assert result["backup"] == ["https://x/b.flv"]
    assert result["quality"] == 32


def test_video_danmaku_parses_xml_and_respects_limit() -> None:
    session = FakeSession([_TextResponse(_DANMAKU_XML)])

    result = _api(session).video_danmaku(170001, limit=1)

    assert result == {
        "ok": True,
        "cid": 170001,
        "count": 1,
        "danmakus": [{"text": "第一条", "time": 1.5, "mode": 1, "color": 16711680}],
    }
    assert session.calls[0]["url"].endswith("/x/v1/dm/list.so?oid=170001")


def test_video_danmaku_returns_all_entries_without_limit() -> None:
    session = FakeSession([_TextResponse(_DANMAKU_XML)])

    result = _api(session).video_danmaku(1, limit=100)

    assert result["count"] == 3
    assert result["danmakus"][1] == {"text": "第二条", "time": 2.0, "mode": 5, "color": 255}
    # 坏时间不抛异常，按 0 处理。
    assert result["danmakus"][2]["time"] == 0.0


def test_expand_b23_follows_redirect() -> None:
    final = "https://www.bilibili.com/video/BV1xx411c7mD?spm_id_from=333.999"
    session = FakeSession([_redirect(final)])

    result = _api(session).expand_b23("https://b23.tv/abc")

    assert result == {"ok": True, "url": final, "bvid": "BV1xx411c7mD", "aid": 0}
    call = session.calls[0]
    assert call["method"] == "GET"
    assert call["url"] == "https://b23.tv/abc"
    # 手动跟跳：不让 requests 自己跟随，才能在每一跳校验域名。
    assert call["allow_redirects"] is False


def test_expand_b23_follows_multiple_bilibili_hops() -> None:
    session = FakeSession(
        [
            _redirect("https://www.bilibili.com/blackboard/activity.html"),
            _redirect("https://m.bilibili.com/video/BV1xx411c7mD"),
        ]
    )

    result = _api(session).expand_b23("b23.tv/abc")

    assert result["ok"] is True and result["bvid"] == "BV1xx411c7mD"
    # 拿到 BV 号就停，不再多请求一次落地页。
    assert [call["url"] for call in session.calls] == [
        "https://b23.tv/abc",
        "https://www.bilibili.com/blackboard/activity.html",
    ]


def test_expand_b23_rejects_foreign_host_without_request() -> None:
    session = FakeSession()
    api = _api(session)

    for url in (
        "https://evil.example.com/x",
        "http://127.0.0.1:8080/admin",
        "https://b23.tv.evil.com/x",
    ):
        result = api.expand_b23(url)
        assert result["ok"] is False
        assert "b23.tv / bilibili.com" in result["error"]
    assert session.calls == []


def test_expand_b23_rejects_redirect_to_foreign_host() -> None:
    session = FakeSession([_redirect("http://127.0.0.1:8080/admin")])

    result = _api(session).expand_b23("https://b23.tv/abc")

    assert result["ok"] is False
    assert "站外" in result["error"] and "127.0.0.1" in result["error"]
    assert len(session.calls) == 1  # 不跟随站外跳转


def test_expand_b23_stops_on_redirect_loop() -> None:
    session = FakeSession([_redirect("https://b23.tv/loop") for _ in range(6)])

    result = _api(session).expand_b23("https://b23.tv/loop")

    assert result["ok"] is False and "跳转次数过多" in result["error"]
    assert len(session.calls) == 6


def test_expand_b23_without_redirect_or_input() -> None:
    session = FakeSession([_TextResponse()])
    api = _api(session)

    stale = api.expand_b23("b23.tv/abc")
    missing = api.expand_b23("")

    assert stale["ok"] is False and "跳转" in stale["error"]
    assert missing["ok"] is False and "url" in missing["error"]
    assert len(session.calls) == 1  # 缺参数不发请求


def test_api_errors_degrade_to_chinese_error() -> None:
    session = FakeSession([FakeResponse({"code": -404, "message": "啥都木有"})])

    result = _api(session).article_info(777)

    assert result["ok"] is False
    assert "专栏信息读取失败" in result["error"]
    assert "啥都木有" in result["error"]


def test_network_error_degrades(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("neobot_app.bilibili.client.time.sleep", lambda _seconds: None)

    class _RaisingSession(FakeSession):
        def request(self, method: str, url: str, **kwargs: object) -> FakeResponse:
            raise requests.ConnectionError("boom")

    result = _api(_RaisingSession()).video_stream("BV1xx411c7mD", 1)

    assert result["ok"] is False
    assert "视频流地址读取失败" in result["error"]


def test_danmaku_transport_error_degrades() -> None:
    class _NoTextClient:
        def _fetch(self, *args: object, **kwargs: object) -> dict:
            raise AssertionError("不应调用 _fetch")

        def fetch_text(self, url: str) -> str:
            raise RuntimeError("boom")

    result = BilibiliReadApi(_NoTextClient()).video_danmaku(1)

    assert result["ok"] is False
    assert "弹幕读取失败" in result["error"]


def test_danmaku_parse_failure_and_empty_body() -> None:
    session = FakeSession([_TextResponse("not xml"), _TextResponse("")])
    api = _api(session)

    bad = api.video_danmaku(1)
    empty = api.video_danmaku(2)

    assert bad["ok"] is False and "弹幕解析失败" in bad["error"]
    assert empty["ok"] is False and "弹幕读取失败" in empty["error"]


def test_invalid_arguments_do_not_request() -> None:
    session = FakeSession()
    api = _api(session)

    results = [
        api.dynamic_detail(""),
        api.user_dynamics(0),
        api.article_info(0),
        api.article_cards([]),
        api.bangumi_info(),
        api.bangumi_stream("", 1),
        api.bangumi_stream("ep1", 0),
        api.user_card(0),
        api.user_card_detail(0),
        api.user_live_status(-1),
        api.video_stream("", 1),
        api.video_stream("BV1xx411c7mD", 0),
        api.video_danmaku(0),
    ]

    assert all(result["ok"] is False for result in results)
    assert session.calls == []
