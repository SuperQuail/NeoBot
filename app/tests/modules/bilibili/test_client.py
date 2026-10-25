"""B 站 HTTP 客户端：认证、评论、私信、重试与 WBI 签名。"""

from __future__ import annotations

import threading
import time

import pytest
import requests

from neobot_app.bilibili.client import BilibiliClient, BilibiliMessage, BilibiliSession
from neobot_app.bilibili.errors import BilibiliApiError, BilibiliAuthError

from ._fakes import FakeResponse, FakeSession

_NAV_OK = {
    "code": 0,
    "data": {"isLogin": True, "mid": 7, "uname": "tester", "face": "face.png"},
}
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


def _client(session: FakeSession, uid: int = 7, **kwargs: object) -> BilibiliClient:
    return BilibiliClient("sessdata", "bili-jct", uid, session=session, **kwargs)


class _DownSession(FakeSession):
    """网络不可用：所有请求都抛 ConnectionError。"""

    def request(self, method: str, url: str, **kwargs: object) -> FakeResponse:
        raise requests.ConnectionError("boom")


def test_verify_auth_true_when_nav_logged_in() -> None:
    session = FakeSession([FakeResponse(_NAV_OK)])
    client = _client(session)
    assert client.verify_auth() is True
    assert session.calls[0]["url"].endswith("/x/web-interface/nav")
    assert client.my_uid == 7


def test_verify_auth_false_when_nav_not_logged_in() -> None:
    session = FakeSession([FakeResponse({"code": 0, "data": {"isLogin": False}})])
    assert _client(session, uid=0).verify_auth() is False


def test_verify_auth_false_on_auth_error() -> None:
    session = FakeSession([FakeResponse({"code": -101, "message": "账号未登录"})])
    assert _client(session).verify_auth() is False


def test_get_reply_feed_returns_items_and_respects_limit() -> None:
    items = [{"id": 1}, {"id": 2}, {"id": 3}]
    session = FakeSession([FakeResponse({"code": 0, "data": {"items": items}})])
    feed = _client(session).get_reply_feed(limit=2)
    assert feed == items[:2]
    assert session.calls[0]["params"]["platform"] == "web"


def test_get_reply_feed_returns_empty_on_api_error() -> None:
    session = FakeSession([FakeResponse({"code": -400, "message": "请求错误"})])
    assert _client(session).get_reply_feed() == []


def test_get_at_feed_returns_items_and_uses_message_center_context() -> None:
    items = [{"id": 1}, {"id": 2}]
    session = FakeSession([FakeResponse({"code": 0, "data": {"items": items}})])
    feed = _client(session).get_at_feed(limit=1)
    assert feed == items[:1]
    call = session.calls[0]
    assert call["url"].endswith("/x/msgfeed/at")
    assert call["params"] == {"platform": "web", "build": 0, "mobi_app": "web"}
    assert call["headers"]["Referer"] == "https://message.bilibili.com/"


def test_get_at_feed_returns_empty_on_api_error() -> None:
    session = FakeSession([FakeResponse({"code": -101, "message": "账号未登录"})])
    assert _client(session).get_at_feed() == []


def _comments_page(
    replies: list[dict], *, is_end: bool = True, next_offset: str = ""
) -> FakeResponse:
    return FakeResponse(
        {
            "code": 0,
            "data": {
                "replies": replies,
                "cursor": {
                    "is_end": is_end,
                    "pagination_reply": {"next_offset": next_offset},
                },
            },
        }
    )


def test_get_comments_signs_wbi_and_returns_cursor() -> None:
    replies = [{"rpid": 1}, {"rpid": 2}]
    session = FakeSession(
        [
            FakeResponse(_NAV_WBI),
            _comments_page(replies, is_end=False, next_offset="next-1"),
        ]
    )
    page = _client(session).get_comments(
        oid=170001, comment_type=17, mode="time", cursor="prev", page_size=5
    )
    assert [item["rpid"] for item in page["items"]] == [1, 2]
    assert page["cursor"] == "next-1"
    assert page["is_end"] is False
    assert page["raw"]["replies"] == replies
    call = session.calls[-1]
    assert call["url"].endswith("/x/v2/reply/wbi/main")
    params = call["params"]
    # WBI 签名会把参数值统一转成字符串再计算 w_rid。
    assert params["type"] == "17"
    assert params["oid"] == "170001"
    assert params["mode"] == "2"
    assert params["pagination_str"] == '{"offset":"prev"}'
    assert params["plat"] == "1"
    assert params["seek_rpid"] == ""
    assert params["web_location"] == "1315875"
    assert len(params["w_rid"]) == 32


def test_get_comments_sends_page_size_and_keeps_whole_page() -> None:
    page_with_more = _comments_page([{"rpid": index} for index in range(1, 6)])
    session = FakeSession(
        [
            FakeResponse(_NAV_WBI),
            _comments_page([{"rpid": 1}, {"rpid": 2}, {"rpid": 1}, {"rpid": 3}]),
            page_with_more,
        ]
    )
    client = _client(session)
    page = client.get_comments(1, 1, page_size=3)
    assert [item["rpid"] for item in page["items"]] == [1, 2, 3]
    assert session.calls[-1]["params"]["ps"] == "3"
    assert page["is_end"] is True and page["cursor"] == ""

    # 接口返回条数多于 ps 时也全部保留：截断后用服务端游标翻页会丢中间的评论。
    full = client.get_comments(170001, 1, page_size=3)
    assert [item["rpid"] for item in full["items"]] == [1, 2, 3, 4, 5]


def test_get_comments_returns_empty_page_on_bad_args_or_api_error() -> None:
    session = FakeSession(
        [FakeResponse(_NAV_WBI), FakeResponse({"code": -404, "message": "啥都木有"})]
    )
    client = _client(session)
    empty = {"items": [], "cursor": "", "is_end": True, "raw": {}}
    assert client.get_comments(0, 1) == empty
    assert client.get_comments(1, 3) == empty  # 3 不是有效评论区类型
    assert client.get_comments(1, 99) == empty
    assert session.calls == []
    assert client.get_comments(1, 1) == empty
    assert len(session.calls) == 2  # nav + 评论接口


def test_get_video_comments_compat_walks_cursor_pages() -> None:
    session = FakeSession(
        [
            FakeResponse(_NAV_WBI),
            _comments_page([{"rpid": 1}], is_end=False, next_offset="cursor-1"),
            _comments_page([{"rpid": 2}]),
        ]
    )
    client = _client(session)
    assert client.get_video_comments(170001, page=2, order="time") == [{"rpid": 2}]
    assert session.calls[-2]["params"]["pagination_str"] == '{"offset":""}'
    assert session.calls[-1]["params"]["pagination_str"] == '{"offset":"cursor-1"}'
    assert session.calls[-1]["params"]["mode"] == "2"
    assert session.calls[-1]["params"]["type"] == "1"


def test_get_video_comments_compat_returns_empty_past_end() -> None:
    session = FakeSession([FakeResponse(_NAV_WBI), _comments_page([{"rpid": 1}])])
    assert _client(session).get_video_comments(170001, page=2, order="hot") == []
    assert session.calls[-1]["params"]["mode"] == "3"


def test_get_work_comments_resolves_bv_to_aid() -> None:
    session = FakeSession(
        [
            FakeResponse({"code": 0, "data": {"aid": 170001}}),
            FakeResponse(_NAV_WBI),
            _comments_page([{"rpid": 1}]),
        ]
    )
    page = _client(session).get_work_comments(
        "https://www.bilibili.com/video/BV1xx411c7mD", 1
    )
    assert [item["rpid"] for item in page["items"]] == [1]
    assert session.calls[0]["url"].endswith("/x/web-interface/view")
    assert session.calls[-1]["params"]["oid"] == "170001"
    assert session.calls[-1]["params"]["type"] == "1"


def test_get_work_comments_uses_dynamic_id_directly() -> None:
    session = FakeSession([FakeResponse(_NAV_WBI), _comments_page([])])
    page = _client(session).get_work_comments("987654321", 17)
    assert page["items"] == []
    assert len(session.calls) == 2
    assert session.calls[-1]["params"]["oid"] == "987654321"
    assert session.calls[-1]["params"]["type"] == "17"


def test_get_work_comments_unresolvable_returns_empty_without_request() -> None:
    session = FakeSession()
    assert _client(session).get_work_comments("没有作品号", 1) == {
        "items": [],
        "cursor": "",
        "is_end": True,
        "raw": {},
    }
    assert session.calls == []


def test_get_comment_replies_hits_reply_reply_and_signs() -> None:
    replies = [{"rpid": 11}, {"rpid": 12}]
    session = FakeSession(
        [
            FakeResponse(_NAV_WBI),
            FakeResponse({"code": 0, "data": {"replies": replies}}),
        ]
    )
    result = _client(session).get_comment_replies(
        oid=170001, root=9, page=2, page_size=10
    )
    assert result == replies
    call = session.calls[-1]
    assert call["url"].endswith("/x/v2/reply/reply")
    params = call["params"]
    # WBI 签名会把参数值统一转成字符串再计算 w_rid。
    assert params["type"] == "1"
    assert params["oid"] == "170001"
    assert params["root"] == "9"
    assert params["pn"] == "2"
    assert params["ps"] == "10"
    assert len(params["w_rid"]) == 32


def test_get_comment_replies_supports_cursor_type_pn_ps_aliases() -> None:
    session = FakeSession(
        [
            FakeResponse(_NAV_WBI),
            FakeResponse({"code": 0, "data": {"replies": [{"rpid": 11}]}}),
            FakeResponse({"code": 0, "data": {"replies": [{"rpid": 12}]}}),
        ]
    )
    client = _client(session)
    assert client.get_comment_replies(
        987654321, 9, type_=17, cursor="3", ps=5
    ) == [{"rpid": 11}]
    assert client.get_comment_replies(987654321, 9, pn=4, page_size=6) == [{"rpid": 12}]
    cursor_params = session.calls[1]["params"]
    assert cursor_params["type"] == "17"
    assert cursor_params["pn"] == "3"
    assert cursor_params["ps"] == "5"
    alias_params = session.calls[2]["params"]
    assert alias_params["type"] == "1"
    assert alias_params["pn"] == "4"
    assert alias_params["ps"] == "6"


def test_get_comment_replies_returns_empty_on_error_or_bad_args() -> None:
    session = FakeSession(
        [FakeResponse(_NAV_WBI), FakeResponse({"code": -400, "message": "请求错误"})]
    )
    client = _client(session)
    assert client.get_comment_replies(oid=170001, root=9) == []
    assert client.get_comment_replies(oid=0, root=9) == []
    assert client.get_comment_replies(oid=170001, root=0) == []
    assert len(session.calls) == 2


def test_send_comment_reply_posts_expected_form() -> None:
    session = FakeSession([FakeResponse({"code": 0, "data": {"rpid": 5566}})])
    assert _client(session).send_comment_reply(oid=1, root=2, parent=3, text="  hi  ")
    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"].endswith("/x/v2/reply/add")
    assert call["data"] == {
        "oid": 1,
        "type": 1,
        "message": "hi",
        "plat": 1,
        "csrf": "bili-jct",
        "root": 2,
        "parent": 3,
    }


def test_send_comment_reply_returns_false_on_api_error() -> None:
    session = FakeSession([FakeResponse({"code": 12002, "message": "评论区已关闭"})])
    assert _client(session).send_comment_reply(oid=1, root=2, parent=2, text="hi") is False


def test_send_message_posts_expected_form() -> None:
    session = FakeSession([FakeResponse({"code": 0, "data": {}})])
    assert _client(session).send_message(8, "hello") is True
    form = session.calls[0]["data"]
    assert form["msg[sender_uid]"] == 7
    assert form["msg[receiver_id]"] == 8
    assert form["csrf"] == "bili-jct"
    assert "hello" in form["msg[content]"]


def test_send_message_without_uid_returns_false() -> None:
    session = FakeSession([FakeResponse({"code": -101, "message": "未登录"})])
    client = _client(session, uid=0)
    assert client.send_message(8, "hello") is False


def test_get_sessions_parses_and_sorts_by_last_message() -> None:
    session = FakeSession(
        [
            FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "session_list": [
                            {
                                "talker_id": 1,
                                "last_msg": {
                                    "sender_uid": 1,
                                    "msg_type": 1,
                                    "content": '{"content": "old"}',
                                    "timestamp": 100,
                                },
                            },
                            {
                                "talker_id": 2,
                                "last_msg": {
                                    "sender_uid": 7,
                                    "msg_type": 1,
                                    "content": '{"content": "new"}',
                                    "timestamp": 200,
                                },
                            },
                        ]
                    },
                }
            )
        ]
    )
    sessions = _client(session).get_sessions(count=10)
    assert [item.talker_id for item in sessions] == [2, 1]
    assert isinstance(sessions[0], BilibiliSession)
    assert sessions[0].last_msg is not None
    assert sessions[0].last_msg.text == "new"


def test_get_messages_parses_messages() -> None:
    session = FakeSession(
        [
            FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "messages": [
                            {
                                "receiver_id": 7,
                                "sender_uid": 7,
                                "msg_type": 1,
                                "content": '{"content": "mine"}',
                                "timestamp": 300,
                            },
                            {
                                "receiver_id": 7,
                                "sender_uid": 9,
                                "msg_type": 2,
                                "content": '{"url": "https://x/y.png"}',
                                "timestamp": 301,
                            },
                        ]
                    },
                }
            )
        ]
    )
    messages = _client(session).get_messages(7, size=5)
    assert [item.text for item in messages] == ["mine", ""]
    assert isinstance(messages[0], BilibiliMessage)
    assert messages[0].is_self is True
    assert messages[1].is_self is False


def test_get_new_messages_deduplicates_and_skips_self() -> None:
    payload = {
        "code": 0,
        "data": {
            "messages": [
                {"sender_uid": 9, "msg_type": 1, "content": '{"content": "a"}', "timestamp": 10},
                {"sender_uid": 7, "msg_type": 1, "content": '{"content": "self"}', "timestamp": 11},
            ]
        },
    }
    session = FakeSession([FakeResponse(payload)])
    client = _client(session)
    session_obj = BilibiliSession(talker_id=7)
    first = client.get_new_messages(session_obj)
    assert [item.text for item in first] == ["a"]
    session.queue(FakeResponse(payload))
    assert client.get_new_messages(session_obj) == []


def test_retries_on_http_5xx(monkeypatch) -> None:
    monkeypatch.setattr("neobot_app.bilibili.client.time.sleep", lambda _seconds: None)
    session = FakeSession([FakeResponse(None, status_code=503), FakeResponse(_NAV_OK)])
    assert _client(session).verify_auth() is True
    assert len(session.calls) == 2


def test_network_error_returns_empty(monkeypatch) -> None:
    monkeypatch.setattr("neobot_app.bilibili.client.time.sleep", lambda _seconds: None)

    class _RaisingSession(FakeSession):
        def request(self, method: str, url: str, **kwargs: object) -> FakeResponse:
            raise requests.ConnectionError("boom")

    assert _client(_RaisingSession()).get_reply_feed() == []


def test_rate_limiter_sleeps_between_writes(monkeypatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("neobot_app.bilibili.client.time.sleep", sleeps.append)
    session = FakeSession([FakeResponse({"code": 0, "data": {}})])
    client = _client(session)
    client._last_write_at = time.monotonic()  # type: ignore[attr-defined]
    assert client.send_message(8, "hello") is True
    assert sleeps and sleeps[0] > 0


def test_write_limiter_error_codes_raise_interval() -> None:
    client = _client(FakeSession())
    initial = client._write_interval  # type: ignore[attr-defined]
    client._on_write_error("评论回复", BilibiliApiError(-412, "风控"))  # type: ignore[attr-defined]
    assert client._write_interval > initial  # type: ignore[attr-defined]


def test_auth_error_from_write_is_not_raised() -> None:
    session = FakeSession([FakeResponse({"code": -101, "message": "未登录"})])
    assert _client(session).send_comment_reply(oid=1, root=2, parent=2, text="hi") is False
    with pytest.raises(BilibiliAuthError):
        _client(FakeSession([FakeResponse({"code": -101})])).publish_dynamic("hi")


# ── nav 三种返回：成功 data / 登录失效 / 接口失败 ──


def test_get_my_info_returns_data_and_caches_uid() -> None:
    client = _client(FakeSession([FakeResponse(_NAV_WBI)]))
    info = client.get_my_info()
    assert info["mid"] == 7 and info["isLogin"] is True
    assert client.my_uid == 7


def test_get_my_info_raises_auth_error_when_logged_out() -> None:
    # -101 与 isLogin=False 都是「未登录」，不能返回空 dict 让调用方当成功。
    for payload in (
        {"code": -101, "message": "账号未登录"},
        {"code": 0, "data": {"isLogin": False}},
        {"code": 0, "data": {"isLogin": True, "mid": 0}},
    ):
        client = _client(FakeSession([FakeResponse(payload)]), uid=0)
        with pytest.raises(BilibiliAuthError):
            client.get_my_info()


def test_get_my_info_raises_api_error_on_network_or_bad_payload(monkeypatch) -> None:
    monkeypatch.setattr("neobot_app.bilibili.client.time.sleep", lambda _seconds: None)
    with pytest.raises(BilibiliApiError):
        _client(_DownSession()).get_my_info()
    with pytest.raises(BilibiliApiError):
        _client(FakeSession([FakeResponse(None)])).get_my_info()  # 非法 JSON
    with pytest.raises(BilibiliApiError):
        _client(FakeSession([FakeResponse({"code": 0, "data": []})])).get_my_info()


def test_my_uid_returns_zero_when_nav_unavailable(monkeypatch) -> None:
    monkeypatch.setattr("neobot_app.bilibili.client.time.sleep", lambda _seconds: None)
    assert _client(_DownSession(), uid=0).my_uid == 0
    assert _client(FakeSession([FakeResponse({"code": -101})]), uid=0).my_uid == 0


# ── 重试：只对幂等的 GET/HEAD ──


def test_post_is_not_retried_on_5xx(monkeypatch) -> None:
    monkeypatch.setattr("neobot_app.bilibili.client.time.sleep", lambda _seconds: None)
    session = FakeSession([FakeResponse(None, status_code=503)])
    assert _client(session).send_comment_reply(oid=1, root=2, parent=2, text="hi") is False
    assert len(session.calls) == 1  # 写请求绝不重发，避免重复发评论


# ── 风控：HTTP 412/429 ──


def test_http_412_and_429_raise_risk_control_error() -> None:
    for status in (412, 429):
        session = FakeSession([FakeResponse(None, status_code=status)])
        client = _client(session)
        initial = client._write_interval  # type: ignore[attr-defined]
        with pytest.raises(BilibiliApiError) as info:
            client._fetch("GET", "https://api.bilibili.com/x/test")  # type: ignore[attr-defined]
        assert info.value.code == -status
        assert "风控" in str(info.value)
        assert client._write_interval > initial  # type: ignore[attr-defined]
        assert len(session.calls) == 1  # 风控拦截不重试


# ── WBI：TTL 与 -352 重取 ──


def test_wbi_keys_are_refetched_after_ttl(monkeypatch) -> None:
    clock = {"now": 1000.0}
    monkeypatch.setattr("neobot_app.bilibili.client.time.monotonic", lambda: clock["now"])
    session = FakeSession(
        [
            FakeResponse(_NAV_WBI),
            _comments_page([{"rpid": 1}]),
            FakeResponse(_NAV_WBI),
            _comments_page([{"rpid": 2}]),
        ]
    )
    client = _client(session)
    assert [item["rpid"] for item in client.get_comments(1, 1)["items"]] == [1]
    clock["now"] += client._WBI_KEY_TTL_SECONDS + 1  # type: ignore[attr-defined]
    assert [item["rpid"] for item in client.get_comments(1, 1)["items"]] == [2]
    nav_calls = [call for call in session.calls if call["url"].endswith("/x/web-interface/nav")]
    assert len(nav_calls) == 2


def test_wbi_352_clears_keys_and_retries_once() -> None:
    session = FakeSession(
        [
            FakeResponse(_NAV_WBI),
            FakeResponse({"code": -352, "message": "风控校验失败"}),
            FakeResponse(_NAV_WBI),
            _comments_page([{"rpid": 1}]),
        ]
    )
    page = _client(session).get_comments(170001, 1)
    assert [item["rpid"] for item in page["items"]] == [1]
    nav_calls = [call for call in session.calls if call["url"].endswith("/x/web-interface/nav")]
    assert len(nav_calls) == 2  # 清空重取一次
    # 重试请求重新签名（不是把失效的 w_rid 原样重发）。
    assert session.calls[-1]["url"].endswith("/x/v2/reply/wbi/main")
    assert len(session.calls[-1]["params"]["w_rid"]) == 32


def test_wbi_352_is_retried_only_once() -> None:
    session = FakeSession(
        [
            FakeResponse(_NAV_WBI),
            FakeResponse({"code": -352}),
            FakeResponse(_NAV_WBI),
            FakeResponse({"code": -352}),
        ]
    )
    assert _client(session).get_comments(170001, 1)["items"] == []
    assert len(session.calls) == 4


# ── 并发：Session 按线程隔离、close 只关自建 Session ──


def test_http_session_is_per_thread_and_copies_cookies() -> None:
    session = FakeSession()
    client = _client(session)
    seen: dict[str, object] = {}

    def worker() -> None:
        other = client._http  # type: ignore[attr-defined]
        seen["session"] = other
        seen["cookies"] = {cookie.name: cookie.value for cookie in other.cookies}
        seen["domains"] = {cookie.name: cookie.domain for cookie in other.cookies}

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    assert seen["session"] is not session
    assert seen["cookies"] == {
        "SESSDATA": "sessdata",
        "bili_jct": "bili-jct",
        "DedeUserID": "7",
    }
    # 复制 Cookie 时要保留 domain，否则会被当成全局 cookie。
    assert set(seen["domains"].values()) == {".bilibili.com"}
    assert client._http is session  # type: ignore[attr-defined]  # 创建线程仍用注入的 session


def test_close_does_not_close_injected_session(monkeypatch) -> None:
    injected = FakeSession()
    _client(injected).close()
    assert injected.closed is False

    created: list[FakeSession] = []

    def _new_session() -> FakeSession:
        session = FakeSession()
        created.append(session)
        return session

    monkeypatch.setattr("neobot_app.bilibili.client.requests.Session", _new_session)
    client = BilibiliClient("sessdata", "bili-jct", 7)
    client.close()
    assert created and created[0].closed is True
