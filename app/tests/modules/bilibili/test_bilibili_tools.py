"""B站工具 Skill 测试：搜索映射、视频信息/看视频/评论、用户与关联QQ主页。"""

from __future__ import annotations

import json
from types import SimpleNamespace

from neobot_app.skills.base import SkillManager
from neobot_app.skills.bilibili_tools import (
    BilibiliSearchSkill,
    BilibiliUserSkill,
    BilibiliVideoSkill,
)

_VIDEO_URL = "https://www.bilibili.com/video/BV1xx411c7mD"


class FakeClient:
    def __init__(self) -> None:
        self.search_calls: list[tuple] = []
        self.info_calls: list[str] = []
        self.comment_calls: list[tuple] = []
        self.my_uid = 7
        self.comment_cursor = ""
        self.comment_is_end = True

    async def search(self, keyword, *, search_type="video", page=1):
        # 与真实 BilibiliClient 一致：当前不支持 order。
        self.search_calls.append((keyword, search_type, page))
        if search_type == "video":
            return {
                "result": [
                    {
                        "type": "video",
                        "title": '<em class="keyword">猫</em>片 &amp; 日常',
                        "bvid": "BV1xx411c7mD",
                        "author": "UP主",
                        "play": 12345,
                        "arcurl": _VIDEO_URL,
                        "description": "视频简介",
                    }
                ],
                "numResults": 1,
            }
        if search_type == "bili_user":
            return {
                "result": [
                    {
                        "type": "bili_user",
                        "mid": 42,
                        "uname": "阿猫",
                        "usign": "签名",
                        "fans": 99,
                        "videos": 8,
                        "level": 6,
                    }
                ]
            }
        return {
            "result": [
                {
                    "type": "article",
                    "id": 777,
                    "title": "专栏标题",
                    "desc": "专栏摘要",
                    "view": 321,
                    "author": "作者",
                }
            ]
        }

    async def get_video_info(self, identifier):
        self.info_calls.append(identifier)
        return {
            "bvid": "BV1xx411c7mD",
            "aid": 170001,
            "title": "视频标题",
            "owner": {"name": "UP主", "mid": 5},
            "stat": {"view": 1000, "like": 20},
            "duration": 61,
            "desc": "视频简介",
            "url": _VIDEO_URL,
        }

    async def get_comments(
        self, oid, comment_type=1, *, mode="hot", cursor=None, page_size=20
    ):
        self.comment_calls.append((oid, comment_type, mode, cursor, page_size))
        return {
            "items": [
                {
                    "rpid": 9,
                    "member": {"uname": "甲", "mid": 2},
                    "content": {"message": "好看"},
                    "like": 3,
                    "ctime": 1_700_000_000,
                    "rcount": 2,
                }
            ],
            "cursor": self.comment_cursor,
            "is_end": self.comment_is_end,
            "raw": {},
        }

    async def get_user_videos(self, mid, page=1):
        return {
            "result": [
                {"bvid": "BV1xx411c7mD", "title": "投稿", "author": "UP主", "play": 5}
            ]
        }

    async def follow_user(self, uid, *, follow=True):
        self.follow_calls = getattr(self, "follow_calls", [])
        self.follow_calls.append((uid, follow))
        return True


class LegacyCommentsClient(FakeClient):
    """旧客户端：评论只有列表形式的 get_video_comments。"""

    get_comments = None

    async def get_video_comments(self, oid, page=1, order="hot"):
        self.comment_calls.append((oid, page, order))
        return [{"rpid": 9, "member": {"uname": "甲", "mid": 2}, "content": {"message": "好看"}}]


class OrderedSearchClient(FakeClient):
    """未来签名：search 支持 order 时应该原样转发。"""

    async def search(self, keyword, *, search_type="video", page=1, order=None):
        self.search_calls.append((keyword, search_type, page, order))
        return {"result": []}


class LegacyClient(FakeClient):
    """并行实现的旧签名：get_user_videos 只接受 mid。"""

    async def get_user_videos(self, mid):
        return [{"bvid": "BV1xx411c7mD", "title": "投稿", "author": "UP主", "play": 5}]


class FakeVideoService:
    def __init__(self, result=None) -> None:
        self.result = result or {}
        self.calls: list[tuple] = []

    async def watch(self, identifier, max_chars=6000, include_comments=0):
        self.calls.append((identifier, max_chars, include_comments))
        return self.result


class FakeArchive:
    def __init__(self, entries=None) -> None:
        self.entries = dict(entries or {})

    async def get(self, table, key):
        value = self.entries.get((table, key))
        return SimpleNamespace(value=value) if value is not None else None


class FakeLinks:
    def __init__(self, links=None) -> None:
        self.links = list(links or [])

    async def find_by_uid(self, uid):
        return [link for link in self.links if link.bilibili_uid == uid]


class FakeProfiles:
    def __init__(self, users=None) -> None:
        self.users = dict(users or {})

    async def get_user(self, user_id):
        return self.users.get(str(user_id))


class FakeUow:
    def __init__(self, links=None, profiles=None) -> None:
        self.bilibili_links = links or FakeLinks()
        self.profiles = profiles or FakeProfiles()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _uow_factory(links=None, profiles=None):
    def make():
        return FakeUow(links=links, profiles=profiles)

    return make


def _service(client, uid: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        available=True,
        client=client,
        status=lambda: {"uid": uid or client.my_uid},
    )


def _card(mid: int, name: str = "UP主", **extra: object) -> dict:
    return {
        "ok": True,
        "uid": mid,
        "name": name,
        "sign": "签名",
        "level": 6,
        "fans": 100,
        "following": 3,
        "videos": 8,
        "articles": 2,
        "likes": 999,
        "face": "",
        "url": f"https://space.bilibili.com/{mid}",
        **extra,
    }


_DYNAMIC_AV = {
    "id_str": "1001",
    "type": "DYNAMIC_TYPE_AV",
    "module_author": {"pub_ts": 1_700_000_000, "pub_time": "2023-11-14 22:13"},
    "module_dynamic": {
        "desc": {"text": "视频简介" * 100},
        "major": {"archive": {"bvid": "BV1xx411c7mD", "title": "投稿标题"}},
    },
    "module_stat": {"like": {"count": 5}, "comment": {"count": 2}, "forward": {"count": 1}},
}

_DYNAMIC_FORWARD = {
    "id_str": "1002",
    "type": "DYNAMIC_TYPE_FORWARD",
    "module_author": {"pub_ts": 1_700_000_100, "pub_time": "昨天 12:00"},
    "module_dynamic": {"desc": {"text": "转发说点什么"}},
    "module_stat": {"like": 3, "comment": 0, "forward": 4},
}

_DYNAMIC_FORWARD_EMPTY = {
    "id_str": "1003",
    "type": "DYNAMIC_TYPE_FORWARD",
    "module_author": {},
    "module_dynamic": {"desc": None},
    "module_stat": {},
    "orig": {"module_dynamic": {"desc": {"text": "原动态正文"}}},
}

_DYNAMIC_ARTICLE = {
    "id_str": "2001",
    "type": "DYNAMIC_TYPE_ARTICLE",
    "module_author": {"pub_ts": 1_700_000_200, "pub_time": "前天"},
    "module_dynamic": {"major": {"article": {"id": 777, "title": "专栏标题"}}},
    "module_stat": {},
}


class FakeReadApi:
    """只读扩展替身：名片按 mid 预置，动态按列表返回。"""

    def __init__(
        self,
        cards: dict[int, dict] | None = None,
        dynamics: list[dict] | None = None,
        card_error: str = "",
        dynamics_error: str = "",
    ) -> None:
        self.cards = dict(cards or {})
        self.dynamics = dynamics
        self.card_error = card_error
        self.dynamics_error = dynamics_error
        self.card_calls: list[int] = []
        self.dynamics_calls: list[tuple[int, int]] = []

    async def user_card_detail(self, mid):
        self.card_calls.append(int(mid))
        if self.card_error:
            return {"ok": False, "error": self.card_error}
        return self.cards.get(int(mid)) or _card(int(mid))

    async def user_dynamics(self, mid, limit=20):
        self.dynamics_calls.append((int(mid), limit))
        if self.dynamics_error:
            return {"ok": False, "error": self.dynamics_error}
        items = self.dynamics if self.dynamics is not None else [_DYNAMIC_AV]
        return {"ok": True, "mid": int(mid), "count": len(items), "items": list(items), "has_more": True}


# ── 搜索 ──


async def test_search_video_maps_and_cleans_fields() -> None:
    client = FakeClient()
    skill = BilibiliSearchSkill(service=_service(client))

    raw = await skill.execute("search_video", {"keyword": "猫", "order": "click"})
    result = json.loads(raw)

    assert result["ok"] is True
    assert result["total"] == 1
    item = result["items"][0]
    assert item["title"] == "猫片 & 日常"
    assert item["bvid"] == "BV1xx411c7mD"
    assert item["up"] == "UP主"
    assert item["play"] == 12345
    assert item["url"] == _VIDEO_URL
    assert item["desc"] == "视频简介"
    # order 当前不在真实 client.search 签名里：过滤掉而不是 TypeError。
    assert client.search_calls == [("猫", "video", 1)]
    assert "猫片" in raw  # ensure_ascii=False


async def test_search_video_forwards_order_when_client_supports_it() -> None:
    client = OrderedSearchClient()
    skill = BilibiliSearchSkill(client=client)

    await skill.execute("search_video", {"keyword": "猫", "order": "click"})

    assert client.search_calls == [("猫", "video", 1, "click")]


async def test_search_user_and_article() -> None:
    skill = BilibiliSearchSkill(client=FakeClient())

    user = json.loads(await skill.execute("search_user", {"keyword": "猫"}))["items"][0]
    article = json.loads(
        await skill.execute("search_article", {"keyword": "猫"})
    )["items"][0]

    assert user["uid"] == 42
    assert user["name"] == "阿猫"
    assert user["fans"] == 99
    assert user["url"] == "https://space.bilibili.com/42"
    assert article["cv_id"] == 777
    assert article["url"] == "https://www.bilibili.com/read/cv777"


async def test_search_requires_keyword_and_valid_order() -> None:
    skill = BilibiliSearchSkill(client=FakeClient())

    missing = json.loads(await skill.execute("search_video", {}))
    bad_order = json.loads(
        await skill.execute("search_video", {"keyword": "猫", "order": "nope"})
    )

    assert missing["ok"] is False and "keyword" in missing["error"]
    assert bad_order["ok"] is False and "totalrank" in bad_order["error"]


async def test_dormant_service_returns_readable_error() -> None:
    skill = BilibiliSearchSkill(service=SimpleNamespace(available=False, client=None))

    result = json.loads(await skill.execute("search_video", {"keyword": "猫"}))

    assert result["ok"] is False
    assert "未登录" in result["error"]


def test_no_dependency_means_no_tools() -> None:
    assert BilibiliSearchSkill().get_tools() == []
    assert BilibiliVideoSkill().get_tools() == []
    assert BilibiliUserSkill().get_tools() == []


# ── 视频 ──


async def test_video_info_accepts_url() -> None:
    client = FakeClient()
    skill = BilibiliVideoSkill(client=client)

    result = json.loads(await skill.execute("video_info", {"identifier": _VIDEO_URL}))

    assert result["ok"] is True
    assert result["bvid"] == "BV1xx411c7mD"
    assert result["aid"] == 170001
    assert result["up"] == "UP主"
    assert result["duration"] == 61
    assert result["view"] == 1000
    assert client.info_calls == ["BV1xx411c7mD"]


async def test_watch_video_returns_transcript_and_source() -> None:
    video = FakeVideoService(
        {
            "ok": True,
            "bvid": "BV1xx411c7mD",
            "title": "视频标题",
            "owner": "UP主",
            "duration": 61,
            "desc": "简介",
            "url": _VIDEO_URL,
            "source": "asr",
            "transcript": "这是语音识别转写",
            "comments": [],
        }
    )
    skill = BilibiliVideoSkill(video_service=video)

    result = json.loads(
        await skill.execute(
            "watch_video", {"identifier": "BV1xx411c7mD", "max_chars": 1500}
        )
    )

    assert result["ok"] is True
    assert result["source"] == "asr"
    assert result["transcript"] == "这是语音识别转写"
    assert result["title"] == "视频标题"
    assert video.calls == [("BV1xx411c7mD", 1500, 0)]


async def test_watch_video_without_service_and_with_error() -> None:
    no_service = BilibiliVideoSkill(client=FakeClient())
    missing = json.loads(
        await no_service.execute("watch_video", {"identifier": "BV1xx411c7mD"})
    )
    assert missing["ok"] is False and "视频解析服务未配置" in missing["error"]

    failing = BilibiliVideoSkill(
        video_service=FakeVideoService({"ok": False, "error": "没有字幕"})
    )
    failed = json.loads(
        await failing.execute("watch_video", {"identifier": "BV1xx411c7mD"})
    )
    assert failed["ok"] is False and "没有字幕" in failed["error"]


async def test_video_comments_resolves_bv_to_aid() -> None:
    client = FakeClient()
    skill = BilibiliVideoSkill(client=client)

    result = json.loads(
        await skill.execute("video_comments", {"identifier": _VIDEO_URL})
    )

    assert result["ok"] is True
    assert result["oid"] == 170001
    assert result["comment_type"] == "video"
    assert result["cursor"] == "" and result["is_end"] is True
    assert result["count"] == 1
    assert result["comments"][0]["uname"] == "甲"
    assert result["comments"][0]["content"] == "好看"
    assert client.comment_calls == [(170001, 1, "hot", "", 20)]


async def test_video_comments_accepts_av_number_without_extra_lookup() -> None:
    client = FakeClient()
    skill = BilibiliVideoSkill(client=client)

    result = json.loads(
        await skill.execute("video_comments", {"identifier": "av170001", "order": "time"})
    )

    assert result["oid"] == 170001
    assert client.info_calls == []
    assert client.comment_calls == [(170001, 1, "time", "", 20)]


async def test_video_comments_passes_comment_type_limit_and_cursor() -> None:
    client = FakeClient()
    client.comment_cursor = "next-page"
    client.comment_is_end = False
    skill = BilibiliVideoSkill(client=client)

    result = json.loads(
        await skill.execute(
            "video_comments",
            {
                "identifier": "987654321",
                "comment_type": "dynamic",
                "order": "time",
                "cursor": "c1",
                "limit": 5,
            },
        )
    )

    assert result["ok"] is True
    assert result["oid"] == 987654321
    assert result["comment_type"] == "dynamic"
    assert result["cursor"] == "next-page"
    assert result["is_end"] is False
    assert result["count"] == 1
    assert client.comment_calls == [(987654321, 17, "time", "c1", 5)]
    assert client.info_calls == []


async def test_video_comments_rejects_unknown_type_and_falls_back_for_legacy_client() -> None:
    invalid = json.loads(
        await BilibiliVideoSkill(client=FakeClient()).execute(
            "video_comments", {"identifier": "av170001", "comment_type": "弹幕"}
        )
    )
    assert invalid["ok"] is False and "comment_type" in invalid["error"]

    legacy_client = LegacyCommentsClient()
    legacy = BilibiliVideoSkill(client=legacy_client)
    video = json.loads(
        await legacy.execute("video_comments", {"identifier": "av170001"})
    )
    assert video["ok"] is True
    assert video["cursor"] == "" and video["is_end"] is True
    assert legacy_client.comment_calls == [(170001, 1, "hot")]

    dynamic = json.loads(
        await legacy.execute(
            "video_comments", {"identifier": "123456", "comment_type": "dynamic"}
        )
    )
    assert dynamic["ok"] is False and "get_comments" in dynamic["error"]


# ── 用户 ──


async def test_user_info_and_legacy_user_videos() -> None:
    skill = BilibiliUserSkill(client=LegacyClient(), read_api=FakeReadApi())

    info = json.loads(
        await skill.execute("user_info", {"uid": "https://space.bilibili.com/42"})
    )
    videos = json.loads(
        await skill.execute("user_videos", {"uid": "42", "page": 2})
    )

    assert info["ok"] is True
    assert info["uid"] == 42
    assert info["name"] == "UP主"
    assert info["fans"] == 100 and info["following"] == 3
    assert videos["ok"] is True
    assert videos["videos"][0]["title"] == "投稿"
    assert videos["page"] == 2


async def test_user_info_lazily_builds_read_api_from_client() -> None:
    class FetchClient(FakeClient):
        def _fetch(self, method, url, params=None, headers=None):
            return {"code": 0, "data": {"card": {"mid": 42, "name": "UP", "fans": 7}}}

    result = json.loads(
        await BilibiliUserSkill(client=FetchClient()).execute("user_info", {"uid": 42})
    )

    assert result["ok"] is True
    assert result["uid"] == 42 and result["fans"] == 7


async def test_user_info_accepts_nickname_and_blank_for_self() -> None:
    client = FakeClient()
    api = FakeReadApi(cards={7: _card(7, "我自己")})
    skill = BilibiliUserSkill(service=_service(client), read_api=api)

    by_name = json.loads(await skill.execute("user_info", {"uid": "阿猫"}))
    by_self = json.loads(await skill.execute("user_info", {}))
    by_me = json.loads(await skill.execute("user_info", {"uid": "我"}))

    assert by_name["ok"] is True and by_name["uid"] == 42
    assert by_name["matched_by"] == "name" and by_name["keyword"] == "阿猫"
    assert by_name["fans"] == 100
    assert by_self["ok"] is True and by_self["uid"] == 7
    assert by_self["matched_by"] == "self" and by_self["name"] == "我自己"
    assert by_me["ok"] is True and by_me["uid"] == 7
    assert client.search_calls == [("阿猫", "bili_user", 1)]
    assert api.card_calls == [42, 7, 7]


async def test_user_info_falls_back_to_client_my_uid() -> None:
    client = FakeClient()
    skill = BilibiliUserSkill(
        service=SimpleNamespace(available=True, client=client),
        read_api=FakeReadApi(),
    )

    result = json.loads(await skill.execute("user_info", {"uid": ""}))

    assert result["ok"] is True and result["uid"] == 7
    assert result["matched_by"] == "self"


async def test_user_info_without_login_uid_reports_error() -> None:
    client = FakeClient()
    client.my_uid = 0
    skill = BilibiliUserSkill(
        service=SimpleNamespace(available=True, client=client, status=lambda: {"uid": 0}),
        read_api=FakeReadApi(),
    )

    result = json.loads(await skill.execute("user_info", {}))

    assert result["ok"] is False
    assert "无法确定当前登录账号的UID" in result["error"]


async def test_user_info_unknown_nickname_and_card_failure() -> None:
    class EmptySearchClient(FakeClient):
        async def search(self, keyword, *, search_type="video", page=1):
            return {"result": []}

    missing = json.loads(
        await BilibiliUserSkill(
            client=EmptySearchClient(), read_api=FakeReadApi()
        ).execute("user_info", {"uid": "查无此人"})
    )
    failed = json.loads(
        await BilibiliUserSkill(
            client=FakeClient(),
            read_api=FakeReadApi(card_error="用户名片读取失败：-352 风控校验失败"),
        ).execute("user_info", {"uid": 42})
    )

    assert missing["ok"] is False
    assert "没有搜到昵称「查无此人」" in missing["error"]
    assert failed["ok"] is False
    assert "风控" in failed["error"] and "fans" not in failed


async def test_search_user_by_uid_returns_full_card() -> None:
    api = FakeReadApi()
    skill = BilibiliSearchSkill(client=FakeClient(), read_api=api)

    result = json.loads(
        await skill.execute("search_user", {"keyword": "https://space.bilibili.com/42"})
    )

    item = result["items"][0]
    assert result["ok"] is True
    assert (result["page"], result["total"], result["count"]) == (1, 1, 1)
    assert result["keyword"] == "https://space.bilibili.com/42"
    assert item["uid"] == 42 and item["name"] == "UP主"
    assert item["fans"] == 100 and item["following"] == 3
    assert item["level"] == 6 and item["videos"] == 8 and item["likes"] == 999
    assert api.card_calls == [42]


async def test_search_user_by_nickname_keeps_keyword_search() -> None:
    client = FakeClient()
    api = FakeReadApi()

    result = json.loads(
        await BilibiliSearchSkill(client=client, read_api=api).execute(
            "search_user", {"keyword": "阿猫"}
        )
    )

    assert result["ok"] is True and result["items"][0]["uid"] == 42
    assert client.search_calls == [("阿猫", "bili_user", 1)]
    assert api.card_calls == []


async def test_search_user_uid_card_failure_returns_error() -> None:
    api = FakeReadApi(card_error="用户名片读取失败：-352 风控校验失败")

    result = json.loads(
        await BilibiliSearchSkill(client=FakeClient(), read_api=api).execute(
            "search_user", {"keyword": "42"}
        )
    )

    assert result["ok"] is False and "风控" in result["error"]


async def test_user_home_self_and_others_share_one_shape() -> None:
    client = FakeClient()
    api = FakeReadApi(dynamics=[_DYNAMIC_AV, _DYNAMIC_FORWARD])
    skill = BilibiliUserSkill(service=_service(client), read_api=api)

    mine = json.loads(await skill.execute("user_home", {}))
    theirs = json.loads(await skill.execute("user_home", {"uid": "阿猫"}))

    assert mine["ok"] is True and mine["uid"] == 7
    assert theirs["ok"] is True and theirs["uid"] == 42
    assert set(mine) == set(theirs)
    for home in (mine, theirs):
        assert home["fans"] == 100 and home["following"] == 3
        assert home["videos_count"] == 8
        assert [item["type"] for item in home["dynamics"]] == ["视频", "转发"]
        assert home["dynamics_has_more"] is True
        assert home["videos"][0]["title"] == "投稿"
    assert api.dynamics_calls == [(7, 5), (42, 5)]


async def test_user_home_maps_dynamics_and_clamps_limit() -> None:
    api = FakeReadApi(
        dynamics=[
            _DYNAMIC_AV,
            _DYNAMIC_FORWARD,
            _DYNAMIC_FORWARD_EMPTY,
            _DYNAMIC_ARTICLE,
            {"id_str": "3001", "type": "DYNAMIC_TYPE_NEW"},
        ]
    )
    skill = BilibiliUserSkill(client=FakeClient(), read_api=api)

    home = json.loads(await skill.execute("user_home", {"uid": 42, "limit": 99}))
    video, forward, forward_empty, article, unknown = home["dynamics"]

    assert api.dynamics_calls == [(42, 20)]
    assert video["type"] == "视频"
    assert video["url"] == "https://www.bilibili.com/video/BV1xx411c7mD"
    assert len(video["text"]) == 200  # 正文摘要截断到 200 字
    assert video["time"] == 1_700_000_000 and video["time_text"] == "2023-11-14 22:13"
    assert (video["likes"], video["comments"], video["reposts"]) == (5, 2, 1)
    assert forward["type"] == "转发" and forward["text"] == "转发说点什么"
    assert (forward["likes"], forward["comments"], forward["reposts"]) == (3, 0, 4)
    assert forward["url"] == "https://t.bilibili.com/1002"
    assert forward_empty["text"] == "原动态正文"
    assert article["type"] == "专栏"
    assert article["url"] == "https://www.bilibili.com/read/cv777"
    assert unknown["type"] == "DYNAMIC_TYPE_NEW"
    assert unknown["url"] == "https://t.bilibili.com/3001"


async def test_user_home_degrades_dynamics_and_videos_separately() -> None:
    class BrokenVideosClient(FakeClient):
        async def get_user_videos(self, mid, page=1):
            raise RuntimeError("投稿接口炸了")

    skill = BilibiliUserSkill(
        client=BrokenVideosClient(),
        read_api=FakeReadApi(dynamics_error="动态接口失败：-412 风控"),
    )

    home = json.loads(await skill.execute("user_home", {"uid": 42}))

    assert home["ok"] is True
    assert home["name"] == "UP主" and home["fans"] == 100
    assert home["videos_count"] == 8
    assert "dynamics" not in home and "dynamics_has_more" not in home
    assert "动态接口失败" in home["dynamics_error"]
    assert "videos" not in home and "投稿接口炸了" in home["videos_error"]


async def test_user_home_requires_resolvable_user_and_card() -> None:
    class EmptySearchClient(FakeClient):
        async def search(self, keyword, *, search_type="video", page=1):
            return {"result": []}

    missing = json.loads(
        await BilibiliUserSkill(
            client=EmptySearchClient(), read_api=FakeReadApi()
        ).execute("user_home", {"uid": "查无此人"})
    )
    failed = json.loads(
        await BilibiliUserSkill(
            client=FakeClient(), read_api=FakeReadApi(card_error="名片读取失败")
        ).execute("user_home", {})
    )

    assert missing["ok"] is False and "没有搜到昵称「查无此人」" in missing["error"]
    assert failed["ok"] is False and "名片读取失败" in failed["error"]
    assert "dynamics" not in failed


async def test_user_home_with_legacy_video_client() -> None:
    skill = BilibiliUserSkill(client=LegacyClient(), read_api=FakeReadApi())

    home = json.loads(await skill.execute("user_home", {"uid": "42"}))

    assert home["ok"] is True
    assert home["videos"][0]["title"] == "投稿"
    assert home["dynamics"][0]["type"] == "视频"


def test_user_tools_document_uid_search_and_home() -> None:
    search_tools = {
        tool["function"]["name"]: tool["function"]
        for tool in BilibiliSearchSkill(client=FakeClient()).get_tools()
    }
    user_tools = {
        tool["function"]["name"]: tool["function"]
        for tool in BilibiliUserSkill(client=FakeClient()).get_tools()
    }

    assert "UID" in search_tools["search_user"]["description"]
    info = user_tools["user_info"]
    assert info["parameters"]["required"] == []
    assert "UID" in info["description"] and "留空" in info["description"]
    home = user_tools["user_home"]
    assert home["parameters"]["required"] == []
    assert home["parameters"]["properties"]["limit"]["default"] == 5
    assert "动态" in home["description"] and "投稿" in home["description"]


async def test_linked_qq_profile_returns_qq_data() -> None:
    links = FakeLinks([SimpleNamespace(bilibili_uid=42, qq_number="10001")])
    profiles = FakeProfiles(
        {"10001": SimpleNamespace(nick_name="小王", remark="老友", profile="常聊天", known_gender="男")}
    )
    archive = FakeArchive(
        {("user_summary", "10001"): "QQ摘要", ("user_profile", "10001"): "完整档案"}
    )
    skill = BilibiliUserSkill(
        client=FakeClient(),
        archive_service=archive,
        uow_factory=_uow_factory(links, profiles),
    )

    result = json.loads(await skill.execute("linked_qq_profile", {"uid": 42}))

    assert result["ok"] is True
    assert result["linked"] is True
    assert result["qq_numbers"] == ["10001"]
    profile = result["profiles"][0]
    assert profile["remark"] == "老友"
    assert profile["nick_name"] == "小王"
    assert profile["user_summary"] == "QQ摘要"
    assert profile["user_profile"] == "完整档案"


async def test_linked_qq_profile_not_linked() -> None:
    skill = BilibiliUserSkill(
        client=FakeClient(),
        uow_factory=_uow_factory(FakeLinks(), FakeProfiles()),
    )

    result = json.loads(await skill.execute("linked_qq_profile", {"uid": 42}))

    assert result["ok"] is True
    assert result["linked"] is False
    assert "还没有关联" in result["message"]


async def test_linked_qq_profile_requires_store() -> None:
    skill = BilibiliUserSkill(client=FakeClient())

    result = json.loads(await skill.execute("linked_qq_profile", {"uid": 42}))

    assert result["ok"] is False
    assert "未配置" in result["error"]


async def test_unknown_tool() -> None:
    result = json.loads(await BilibiliSearchSkill(client=FakeClient()).execute("nope", {}))

    assert result["ok"] is False


async def test_three_skills_register_and_route_together() -> None:
    manager = SkillManager()
    client = FakeClient()
    manager.register(BilibiliSearchSkill(client=client))
    manager.register(BilibiliVideoSkill(client=client))
    manager.register(BilibiliUserSkill(client=client, read_api=FakeReadApi()))

    names = {tool["function"]["name"] for tool in manager.get_tools()}
    assert {
        "bilibili_search__search_video",
        "bilibili_video__watch_video",
        "bilibili_user__linked_qq_profile",
        "bilibili_user__user_home",
    } <= names

    result = json.loads(
        await manager.execute("bilibili_user__user_info", {"uid": "42"})
    )
    assert result["ok"] is True
    assert result["uid"] == 42


async def test_read_video_transcript_from_archive() -> None:
    archive = FakeArchive(
        {("bilibili_video", "BV1xx411c7mD"): "完整转写" * 1000}
    )
    skill = BilibiliVideoSkill(client=FakeClient(), archive_service=archive)
    tools = {tool["function"]["name"] for tool in skill.get_tools()}
    assert "read_video_transcript" in tools

    result = json.loads(
        await skill.execute("read_video_transcript", {"identifier": "BV1xx411c7mD"})
    )
    assert result["ok"] is True
    assert result["found"] is True
    assert result["transcript"] == "完整转写" * 1000


async def test_read_video_transcript_not_found() -> None:
    skill = BilibiliVideoSkill(client=FakeClient(), archive_service=FakeArchive())
    result = json.loads(
        await skill.execute("read_video_transcript", {"identifier": "BV1xx411c7mD"})
    )
    assert result["ok"] is True
    assert result["found"] is False
    assert "没有找到" in result["message"]


# ── 写操作（评论 / 点赞）──


class WriteClient(FakeClient):
    """模拟并行实现的写接口；result=False 表示失败，error 模拟抛异常。"""

    def __init__(self, result: bool = True, error: Exception | None = None) -> None:
        super().__init__()
        self.result = result
        self.error = error
        self.comment_calls: list[tuple] = []
        self.like_calls: list[str] = []
        self.like_comment_calls: list[tuple] = []
        self.coin_calls: list[tuple] = []
        self.share_calls: list[str] = []
        self.favorite_calls: list[tuple] = []
        self.folder_calls: list[bool] = []
        self.folders: list[dict] = [
            {"id": 101, "title": "默认收藏夹", "media_count": 3},
            {"id": 202, "fid": 202, "title": "学习", "media_count": 1},
        ]

    async def post_video_comment(self, identifier, text, *, root=0, parent=0):
        self.comment_calls.append((identifier, text, root, parent))
        if self.error is not None:
            raise self.error
        return self.result

    async def like_video(self, identifier):
        self.like_calls.append(identifier)
        if self.error is not None:
            raise self.error
        return self.result

    async def like_comment(self, oid, rpid, type_=1):
        self.like_comment_calls.append((oid, rpid, type_))
        if self.error is not None:
            raise self.error
        return self.result

    async def coin_video(self, identifier, multiply=1):
        self.coin_calls.append((identifier, multiply))
        if self.error is not None:
            raise self.error
        return self.result

    async def share_video(self, identifier):
        self.share_calls.append(identifier)
        if self.error is not None:
            raise self.error
        return self.result

    async def favorite_video(self, identifier, folder_id):
        self.favorite_calls.append((identifier, folder_id))
        if self.error is not None:
            raise self.error
        return self.result

    async def get_favorite_folders(self):
        self.folder_calls.append(True)
        if self.error is not None:
            raise self.error
        return list(self.folders)


def test_video_skill_exposes_write_tools_with_public_action_warning() -> None:
    tools = {
        tool["function"]["name"]: tool["function"]
        for tool in BilibiliVideoSkill(client=FakeClient()).get_tools()
    }

    assert {"comment_video", "like_video", "like_comment"} <= set(tools)
    assert "确认用户意图后再调用" in tools["comment_video"]["description"]
    assert "确认用户意图后再调用" in tools["like_video"]["description"]
    assert "确认用户意图后再调用" in tools["like_comment"]["description"]


async def test_comment_video_posts_top_level_and_reply() -> None:
    client = WriteClient()
    skill = BilibiliVideoSkill(client=client)

    top = json.loads(
        await skill.execute(
            "comment_video", {"identifier": _VIDEO_URL, "text": "好看", "confirm": True}
        )
    )
    reply = json.loads(
        await skill.execute(
            "comment_video",
            {
                "identifier": "av170001",
                "text": "同意",
                "root": 9,
                "parent": 10,
                "confirm": True,
            },
        )
    )

    assert top["ok"] is True
    assert top["comment"] == "好看"
    assert top["root"] == 0 and top["parent"] == 0
    assert reply["ok"] is True
    assert reply["root"] == 9 and reply["parent"] == 10
    assert client.comment_calls == [
        ("BV1xx411c7mD", "好看", 0, 0),
        ("av170001", "同意", 9, 10),
    ]
    assert "好看" in json.dumps(top, ensure_ascii=False)


async def test_comment_video_failure_and_missing_capability() -> None:
    failing = BilibiliVideoSkill(client=WriteClient(result=False))
    failed = json.loads(
        await failing.execute(
            "comment_video", {"identifier": "av170001", "text": "好", "confirm": True}
        )
    )
    assert failed["ok"] is False
    assert "风控" in failed["error"]

    missing_text = json.loads(
        await failing.execute("comment_video", {"identifier": "av170001", "confirm": True})
    )
    assert missing_text["ok"] is False and "text" in missing_text["error"]

    legacy = BilibiliVideoSkill(client=FakeClient())
    missing = json.loads(
        await legacy.execute(
            "comment_video", {"identifier": "av170001", "text": "好", "confirm": True}
        )
    )
    assert missing["ok"] is False
    assert "post_video_comment" in missing["error"]


async def test_like_video_and_like_comment() -> None:
    client = WriteClient()
    skill = BilibiliVideoSkill(client=client)

    video = json.loads(
        await skill.execute("like_video", {"identifier": _VIDEO_URL, "confirm": True})
    )
    comment = json.loads(
        await skill.execute(
            "like_comment", {"identifier": "av170001", "rpid": "9", "confirm": True}
        )
    )
    resolved = json.loads(
        await skill.execute(
            "like_comment", {"identifier": _VIDEO_URL, "rpid": 9, "confirm": True}
        )
    )

    assert video["ok"] is True and video["liked"] is True
    assert client.like_calls == ["BV1xx411c7mD"]
    assert comment["ok"] is True
    assert comment["oid"] == 170001 and comment["rpid"] == 9
    assert resolved["oid"] == 170001
    assert client.like_comment_calls == [(170001, 9, 1), (170001, 9, 1)]


async def test_like_failure_missing_rpid_and_missing_capability() -> None:
    failing = BilibiliVideoSkill(client=WriteClient(result=False))
    video = json.loads(
        await failing.execute("like_video", {"identifier": "av170001", "confirm": True})
    )
    comment = json.loads(
        await failing.execute(
            "like_comment", {"identifier": "av170001", "rpid": 9, "confirm": True}
        )
    )
    assert video["ok"] is False and "风控" in video["error"]
    assert comment["ok"] is False and "风控" in comment["error"]

    bad_rpid = json.loads(
        await failing.execute(
            "like_comment", {"identifier": "av170001", "rpid": 0, "confirm": True}
        )
    )
    assert bad_rpid["ok"] is False and "rpid" in bad_rpid["error"]

    legacy = BilibiliVideoSkill(client=FakeClient())
    missing = json.loads(
        await legacy.execute("like_video", {"identifier": "av170001", "confirm": True})
    )
    missing_comment = json.loads(
        await legacy.execute(
            "like_comment", {"identifier": "av170001", "rpid": 9, "confirm": True}
        )
    )
    assert missing["ok"] is False and "like_video" in missing["error"]
    assert missing_comment["ok"] is False and "like_comment" in missing_comment["error"]

def test_video_skill_exposes_interaction_tools_with_public_action_warning() -> None:
    tools = {
        tool["function"]["name"]: tool["function"]
        for tool in BilibiliVideoSkill(client=FakeClient()).get_tools()
    }

    assert {"coin_video", "share_video", "favorite_video", "favorite_folders"} <= set(tools)
    for name in ("coin_video", "share_video", "favorite_video"):
        assert "确认用户意图后再调用" in tools[name]["description"]
        assert "公开" in tools[name]["description"]
    assert "folder_id" in tools["favorite_video"]["description"]
    assert "只读" in tools["favorite_folders"]["description"]
    multiply = tools["coin_video"]["parameters"]["properties"]["multiply"]
    assert multiply["default"] == 1 and multiply["enum"] == [1, 2]


async def test_coin_video_defaults_to_one_and_takes_two() -> None:
    client = WriteClient()
    skill = BilibiliVideoSkill(client=client)

    one = json.loads(
        await skill.execute("coin_video", {"identifier": _VIDEO_URL, "confirm": True})
    )
    two = json.loads(
        await skill.execute(
            "coin_video", {"identifier": "av170001", "multiply": "2", "confirm": True}
        )
    )

    assert one["ok"] is True
    assert one["multiply"] == 1 and one["coined"] is True
    assert two["ok"] is True and two["multiply"] == 2
    assert client.coin_calls == [("BV1xx411c7mD", 1), ("av170001", 2)]


async def test_share_and_favorite_video_call_client() -> None:
    client = WriteClient()
    skill = BilibiliVideoSkill(client=client)

    shared = json.loads(
        await skill.execute("share_video", {"identifier": _VIDEO_URL, "confirm": True})
    )
    favorited = json.loads(
        await skill.execute(
            "favorite_video",
            {"identifier": "av170001", "folder_id": "101", "confirm": True},
        )
    )

    assert shared["ok"] is True and shared["shared"] is True
    assert client.share_calls == ["BV1xx411c7mD"]
    assert favorited["ok"] is True
    assert favorited["folder_id"] == 101 and favorited["favorited"] is True
    assert client.favorite_calls == [("av170001", 101)]


async def test_favorite_folders_lists_ids_and_degrades() -> None:
    client = WriteClient()
    skill = BilibiliVideoSkill(client=client)

    listed = json.loads(await skill.execute("favorite_folders", {}))
    assert listed["ok"] is True and listed["count"] == 2
    assert listed["folders"][0] == {"id": 101, "title": "默认收藏夹", "count": 3}
    assert "只读" in listed["note"]
    assert client.folder_calls == [True]

    client.folders = []
    empty = json.loads(await skill.execute("favorite_folders", {}))
    assert empty["ok"] is True and empty["folders"] == []
    assert "没有读到收藏夹" in empty["note"]


async def test_interaction_tools_fail_and_require_capability() -> None:
    failing = BilibiliVideoSkill(client=WriteClient(result=False))
    coin = json.loads(
        await failing.execute("coin_video", {"identifier": "av170001", "confirm": True})
    )
    share = json.loads(
        await failing.execute("share_video", {"identifier": "av170001", "confirm": True})
    )
    favorite = json.loads(
        await failing.execute(
            "favorite_video", {"identifier": "av170001", "folder_id": 1, "confirm": True}
        )
    )
    assert coin["ok"] is False and "风控" in coin["error"]
    assert share["ok"] is False and "风控" in share["error"]
    assert favorite["ok"] is False and "风控" in favorite["error"]

    bad_folder = json.loads(
        await failing.execute(
            "favorite_video", {"identifier": "av170001", "folder_id": 0, "confirm": True}
        )
    )
    assert bad_folder["ok"] is False and "folder_id" in bad_folder["error"]

    broken = BilibiliVideoSkill(client=WriteClient(error=RuntimeError("接口炸了")))
    raised = json.loads(
        await broken.execute("coin_video", {"identifier": "av170001", "confirm": True})
    )
    assert raised["ok"] is False and "接口炸了" in raised["error"]
    broken_folders = json.loads(await broken.execute("favorite_folders", {}))
    assert broken_folders["ok"] is False and "接口炸了" in broken_folders["error"]

    legacy = BilibiliVideoSkill(client=FakeClient())
    cases = {
        "coin_video": {"identifier": "av170001", "confirm": True},
        "share_video": {"identifier": "av170001", "confirm": True},
        "favorite_video": {"identifier": "av170001", "folder_id": 1, "confirm": True},
        "favorite_folders": {},
    }
    for name, args in cases.items():
        missing = json.loads(await legacy.execute(name, args))
        assert missing["ok"] is False and name in missing["error"]


# ── 评论区树 / 消息通知（只读）──


def _root(
    rpid: int = 9, *, reply_count: int = 0, replies: list | None = None
) -> dict:
    raw = {
        "rpid": rpid,
        "member": {"uname": "甲", "mid": 2},
        "content": {"message": "好看"},
        "like": 3,
        "ctime": 1_700_000_000,
        "rcount": reply_count,
    }
    if replies is not None:
        raw["replies"] = replies
    return raw


def _reply(rpid: int, text: str = "同意") -> dict:
    return {
        "rpid": rpid,
        "member": {"uname": "乙", "mid": 3},
        "content": {"message": text},
        "like": 1,
        "rcount": 0,
    }


_REPLY_FEED_ITEM = {
    "id": 1,
    "reply_time": 1_710_000_000,
    "user": {"mid": 12, "nickname": "张三"},
    "item": {
        "subject_id": 170001,
        "source_id": 100,
        "root_id": 9,
        "business_id": 1,
        "message": "你的视频不错",
        "title": "视频标题",
        "uri": "https://www.bilibili.com/video/BV1xx411c7mD",
    },
}

_AT_FEED_ITEM = {
    "id": 2,
    "at_time": 1_710_000_100,
    "user": {"mid": 13, "nickname": "李四"},
    "item": {
        "subject_id": 55,
        "source_id": 66,
        "root_id": 0,
        "business_id": 17,
        "source_content": "这条评论 @了你",
        "title": "动态标题",
        "uri": "",
    },
}


class TreeClient(FakeClient):
    """评论区树 + 通知流替身：replies_of 按根评论 rpid 提供楼中楼。"""

    def __init__(
        self,
        roots: list | None = None,
        replies_of: dict[int, list] | None = None,
        reply_feed: list | None = None,
        at_feed: list | None = None,
        cursor: str = "",
        is_end: bool = True,
    ) -> None:
        super().__init__()
        self.roots = list(roots or [])
        self.replies_of = dict(replies_of or {})
        self.reply_feed = list(reply_feed or [])
        self.at_feed = list(at_feed or [])
        self.reply_calls: list[tuple[int, int, int]] = []
        self.feed_calls: list[int] = []
        self.at_calls: list[int] = []
        self.comment_cursor = cursor
        self.comment_is_end = is_end

    async def get_comments(
        self, oid, comment_type=1, *, mode="hot", cursor=None, page_size=20
    ):
        self.comment_calls.append((oid, comment_type, mode, cursor, page_size))
        return {
            "items": self.roots,
            "cursor": self.comment_cursor,
            "is_end": self.comment_is_end,
            "raw": {},
        }

    async def get_comment_replies(
        self, oid, root, *, page=1, page_size=20, type_=1
    ):
        self.reply_calls.append((oid, root, type_))
        return self.replies_of.get(root, [])

    async def get_reply_feed(self, limit=20):
        self.feed_calls.append(limit)
        return self.reply_feed

    async def get_at_feed(self, limit=20):
        self.at_calls.append(limit)
        return self.at_feed


async def test_comment_tree_uses_inline_replies() -> None:
    client = TreeClient(roots=[_root(9, reply_count=1, replies=[_reply(10)])])
    skill = BilibiliVideoSkill(client=client)

    result = json.loads(
        await skill.execute(
            "comment_tree", {"identifier": "av170001", "limit": 5}
        )
    )

    assert result["ok"] is True
    assert result["oid"] == 170001
    assert result["count"] == 1
    node = result["comments"][0]
    assert node["rpid"] == 9
    assert node["uname"] == "甲"
    assert node["reply_count"] == 1
    assert node["replies"][0]["rpid"] == 10
    assert node["replies"][0]["content"] == "同意"
    # 自带楼中楼时不再额外请求。
    assert client.reply_calls == []
    assert client.comment_calls == [(170001, 1, "hot", "", 5)]
    assert result["cursor"] == "" and result["is_end"] is True


async def test_comment_tree_fetches_missing_replies() -> None:
    client = TreeClient(
        roots=[_root(9, reply_count=2), _root(12)],
        replies_of={9: [_reply(10), _reply(11, "同感")]},
    )
    skill = BilibiliVideoSkill(client=client)

    result = json.loads(
        await skill.execute(
            "comment_tree", {"identifier": "av170001", "limit": 5}
        )
    )

    assert result["ok"] is True
    assert result["count"] == 2
    first, second = result["comments"]
    assert [item["rpid"] for item in first["replies"]] == [10, 11]
    assert second["replies"] == [] and second["reply_count"] == 0
    assert client.reply_calls == [(170001, 9, 1)]  # 只有带楼中楼的那条才补拉


async def test_comment_tree_expands_one_root() -> None:
    client = TreeClient(replies_of={9: [_reply(10)]})
    skill = BilibiliVideoSkill(client=client)

    result = json.loads(
        await skill.execute(
            "comment_tree", {"identifier": "av170001", "root_rpid": 9}
        )
    )

    assert result["ok"] is True
    assert result["root_rpid"] == 9
    assert [item["rpid"] for item in result["comments"]] == [10]
    assert client.comment_calls == []
    assert client.reply_calls == [(170001, 9, 1)]
    assert result["cursor"] == ""


async def test_comment_tree_supports_dynamic_and_returns_cursor() -> None:
    client = TreeClient(
        roots=[_root(9, reply_count=1)],
        replies_of={9: [_reply(10)]},
        cursor="next-root",
        is_end=False,
    )
    skill = BilibiliVideoSkill(client=client)

    result = json.loads(
        await skill.execute(
            "comment_tree",
            {
                "identifier": "https://t.bilibili.com/987654321",
                "comment_type": "dynamic",
                "limit": 5,
            },
        )
    )

    assert result["ok"] is True
    assert result["oid"] == 987654321
    assert result["comment_type"] == "dynamic"
    assert result["cursor"] == "next-root"
    assert result["is_end"] is False
    assert client.comment_calls == [(987654321, 17, "hot", "", 5)]
    assert client.reply_calls == [(987654321, 9, 17)]


def test_comment_tools_document_types_and_pagination() -> None:
    tools = {
        tool["function"]["name"]: tool["function"]
        for tool in BilibiliVideoSkill(client=FakeClient()).get_tools()
    }
    expected = ["video", "dynamic", "article", "opus", "bangumi"]
    for name in ("video_comments", "comment_tree"):
        params = tools[name]["parameters"]["properties"]
        assert params["comment_type"]["enum"] == expected
        assert "limit" in params and "cursor" in params
        assert "不自动回复" in tools[name]["description"]
    assert "翻页" in tools["video_comments"]["description"]


async def test_comment_tree_requires_video_id_and_reply_capability() -> None:
    skill = BilibiliVideoSkill(client=TreeClient())

    missing = json.loads(await skill.execute("comment_tree", {}))
    assert missing["ok"] is False and "identifier" in missing["error"]

    legacy = BilibiliVideoSkill(client=FakeClient())
    unsupported = json.loads(
        await legacy.execute("comment_tree", {"identifier": "av170001"})
    )
    assert unsupported["ok"] is False
    assert "get_comment_replies" in unsupported["error"]


async def test_read_bili_messages_normalizes_and_dedupes() -> None:
    client = TreeClient(
        reply_feed=[_REPLY_FEED_ITEM],
        at_feed=[_AT_FEED_ITEM, _REPLY_FEED_ITEM],
    )
    skill = BilibiliVideoSkill(client=client)

    result = json.loads(await skill.execute("read_bili_messages", {"limit": 10}))

    assert result["ok"] is True
    assert result["count"] == 2
    assert result["include_at"] is True
    assert client.feed_calls == [10] and client.at_calls == [10]
    # 按时间倒序；同一条评论出现在两个通知流里只留一条。
    at_message, reply_message = result["messages"]
    assert at_message["source"] == "at"
    assert at_message["type"] == "动态"
    assert at_message["url"] == "https://t.bilibili.com/55"
    assert at_message["comment"] == "这条评论 @了你"
    assert at_message["uname"] == "李四" and at_message["uid"] == 13
    # 通知里 root_id=0 时按根评论=本条评论处理（与 comment_monitor 一致）。
    assert at_message["root_rpid"] == 66 and at_message["parent_rpid"] == 66
    assert reply_message["source"] == "reply"
    assert reply_message["type"] == "视频"
    assert reply_message["url"] == _VIDEO_URL
    assert reply_message["title"] == "视频标题"
    assert reply_message["comment"] == "你的视频不错"
    assert reply_message["root_rpid"] == 9
    assert reply_message["parent_rpid"] == 100
    assert "只读" in result["note"]


async def test_read_bili_messages_can_skip_at() -> None:
    client = TreeClient(at_feed=[_AT_FEED_ITEM])
    skill = BilibiliVideoSkill(client=client)

    result = json.loads(
        await skill.execute(
            "read_bili_messages", {"limit": 5, "include_at": "false"}
        )
    )

    assert result["ok"] is True
    assert result["include_at"] is False
    assert result["messages"] == []
    assert "没有读到" in result["note"]
    assert client.feed_calls == [5]
    assert client.at_calls == []


def test_read_tools_are_explicitly_read_only() -> None:
    tools = {
        tool["function"]["name"]: tool["function"]
        for tool in BilibiliVideoSkill(client=FakeClient()).get_tools()
    }

    assert {"comment_tree", "read_bili_messages"} <= set(tools)
    for name in ("comment_tree", "read_bili_messages"):
        description = tools[name]["description"]
        assert "只读" in description
        assert "不自动回复" in description
        assert "comment_video" in description



async def test_follow_user_tool_passes_action() -> None:
    client = FakeClient()
    skill = BilibiliUserSkill(client=client)

    result = json.loads(
        await skill.execute(
            "follow_user", {"uid": "42", "action": "unfollow", "confirm": True}
        )
    )

    assert result["ok"] is True
    assert result["action"] == "unfollow"
    assert client.follow_calls == [(42, False)]


# ── 登录门禁 / 写操作确认 / 后台任务 ──


class RefreshService:
    """按 refresh() 结果切换可用性的 service 替身。"""

    def __init__(self, client, *, becomes_available: bool, error: str = "") -> None:
        self.client = client
        self.available = False
        self.becomes_available = becomes_available
        self.error = error
        self.refresh_calls = 0

    async def refresh(self) -> bool:
        self.refresh_calls += 1
        self.available = self.becomes_available
        return self.available

    def status(self) -> dict:
        return {"available": self.available, "error": self.error}


async def test_login_gate_refreshes_before_reporting_dormant() -> None:
    client = FakeClient()
    service = RefreshService(client, becomes_available=True)
    skill = BilibiliSearchSkill(service=service)

    result = json.loads(await skill.execute("search_video", {"keyword": "猫"}))

    assert result["ok"] is True and result["count"] == 1
    assert service.refresh_calls == 1
    assert client.search_calls == [("猫", "video", 1)]


async def test_login_gate_reports_real_reason_when_still_dormant() -> None:
    client = FakeClient()
    service = RefreshService(
        client,
        becomes_available=False,
        error="B站登录态校验失败（网络异常）：Timeout",
    )
    skill = BilibiliSearchSkill(service=service)

    result = json.loads(await skill.execute("search_video", {"keyword": "猫"}))

    assert result["ok"] is False
    assert "未登录" in result["error"]
    assert "网络异常" in result["error"]  # 网络失败 vs 凭证失效要分清
    assert service.refresh_calls == 1
    assert client.search_calls == []


def test_public_write_tools_require_confirm_parameter() -> None:
    video_tools = {
        tool["function"]["name"]: tool["function"]
        for tool in BilibiliVideoSkill(client=FakeClient()).get_tools()
    }
    user_tools = {
        tool["function"]["name"]: tool["function"]
        for tool in BilibiliUserSkill(client=FakeClient()).get_tools()
    }
    for name in (
        "comment_video",
        "like_video",
        "like_comment",
        "coin_video",
        "share_video",
        "favorite_video",
    ):
        params = video_tools[name]["parameters"]
        assert params["properties"]["confirm"]["type"] == "boolean"
        assert "confirm" in params["required"]
    assert "confirm" in user_tools["follow_user"]["parameters"]["required"]


async def test_write_tool_without_confirm_does_not_reach_client() -> None:
    client = WriteClient()
    skill = BilibiliVideoSkill(client=client)

    blocked = json.loads(
        await skill.execute("comment_video", {"identifier": _VIDEO_URL, "text": "好看"})
    )
    assert blocked["ok"] is False
    assert blocked["code"] == "CONFIRM_REQUIRED"
    assert "confirm" in blocked["error"]
    assert client.comment_calls == []

    # 模型常把布尔写成字符串，按 _flag 解析；"false" 仍然拒绝。
    refused = json.loads(
        await skill.execute("like_video", {"identifier": _VIDEO_URL, "confirm": "false"})
    )
    assert refused["code"] == "CONFIRM_REQUIRED"
    assert client.like_calls == []

    allowed = json.loads(
        await skill.execute(
            "comment_video",
            {"identifier": _VIDEO_URL, "text": "好看", "confirm": "true"},
        )
    )
    assert allowed["ok"] is True
    assert client.comment_calls == [("BV1xx411c7mD", "好看", 0, 0)]


async def test_watch_video_without_transcript_keeps_video_info() -> None:
    video = FakeVideoService(
        {
            "ok": False,
            "error": "没有可用字幕",
            "bvid": "BV1xx411c7mD",
            "title": "视频标题",
            "owner": "UP主",
            "desc": "简介",
        }
    )
    skill = BilibiliVideoSkill(video_service=video)

    result = json.loads(
        await skill.execute("watch_video", {"identifier": "BV1xx411c7mD"})
    )

    assert result["ok"] is True
    assert result["title"] == "视频标题"
    assert result["bvid"] == "BV1xx411c7mD"
    assert result["up"] == "UP主"
    assert result["transcript"] == ""
    assert "字幕" in result["note"]
    assert "没有可用字幕" in result["note"]


class FakeVideoTasks:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict] = []

    async def submit(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return {"ok": True, "task_id": "t1"}


def _invocation(chat_flow: str):
    from neobot_app.agent_tools.contracts import ToolContext
    from neobot_app.agent_tools.invocation import CURRENT_INVOCATION, ToolInvocation

    context = ToolContext(owner=f"{chat_flow}:main", chat_flow_id=chat_flow)
    return CURRENT_INVOCATION, CURRENT_INVOCATION.set(ToolInvocation(context))


async def test_watch_video_submits_to_background_with_flow() -> None:
    tasks = FakeVideoTasks()
    video = FakeVideoService({"ok": True, "title": "视频标题"})
    skill = BilibiliVideoSkill(video_service=video, task_manager=tasks)

    var, token = _invocation("group:1")
    try:
        result = json.loads(
            await skill.execute("watch_video", {"identifier": "BV1xx411c7mD"})
        )
    finally:
        var.reset(token)

    assert result["ok"] is True and result["task_id"] == "t1"
    assert tasks.calls[0]["flow_key"] == "group:1"
    assert video.calls == []  # 后台任务路径不再同步解析


async def test_watch_video_reports_retryable_error_instead_of_sync_fallback() -> None:
    video = FakeVideoService({"ok": True, "title": "视频标题"})
    broken = BilibiliVideoSkill(
        video_service=video, task_manager=FakeVideoTasks(error=RuntimeError("队列满了"))
    )

    var, token = _invocation("group:1")
    try:
        failed = json.loads(
            await broken.execute("watch_video", {"identifier": "BV1xx411c7mD"})
        )
    finally:
        var.reset(token)

    assert failed["ok"] is False
    assert failed["retryable"] is True
    assert "队列满了" in failed["error"]
    assert video.calls == []  # 提交失败不再偷偷同步解析


async def test_watch_video_without_invocation_stays_host_only_sync() -> None:
    video = FakeVideoService({"ok": True, "title": "视频标题"})
    skill = BilibiliVideoSkill(video_service=video, task_manager=FakeVideoTasks())

    result = json.loads(
        await skill.execute("watch_video", {"identifier": "BV1xx411c7mD"})
    )

    # 没有可信聊天流（宿主直调）：沿用同步解析，不提交后台任务。
    assert result["ok"] is True and result["title"] == "视频标题"
    assert video.calls == [("BV1xx411c7mD", 3000, 0)]


async def test_empty_search_and_comments_carry_note() -> None:
    class EmptySearchClient(FakeClient):
        async def search(self, keyword, *, search_type="video", page=1):
            self.search_calls.append((keyword, search_type, page))
            return {}

    searched = json.loads(
        await BilibiliSearchSkill(client=EmptySearchClient()).execute(
            "search_video", {"keyword": "猫"}
        )
    )
    assert searched["ok"] is True and searched["count"] == 0
    assert "接口失败" in searched["note"]

    class QuietCommentsClient(FakeClient):
        async def get_comments(
            self, oid, comment_type=1, *, mode="hot", cursor=None, page_size=20
        ):
            self.comment_calls.append((oid, comment_type, mode, cursor, page_size))
            return {"items": [], "cursor": "", "is_end": True, "raw": {}}

    comments = json.loads(
        await BilibiliVideoSkill(client=QuietCommentsClient()).execute(
            "video_comments", {"identifier": "av170001"}
        )
    )
    assert comments["ok"] is True and comments["count"] == 0
    assert "接口失败" in comments["note"]


async def test_comment_type_only_accepts_client_supported_codes() -> None:
    client = FakeClient()
    rejected = json.loads(
        await BilibiliVideoSkill(client=client).execute(
            "video_comments", {"identifier": "av170001", "comment_type": "2"}
        )
    )
    assert rejected["ok"] is False and "comment_type" in rejected["error"]
    assert client.comment_calls == []

    class TypedClient(FakeClient):
        # 与 client 契约一致：公开 COMMENT_TYPES 决定可用类型码。
        COMMENT_TYPES = {1: "视频", 2: "特殊评论区"}

        async def get_comments(
            self, oid, comment_type=1, *, mode="hot", cursor=None, page_size=20
        ):
            self.comment_calls.append((oid, comment_type, mode, cursor, page_size))
            return {"items": [], "cursor": "", "is_end": True, "raw": {}}

    typed = TypedClient()
    accepted = json.loads(
        await BilibiliVideoSkill(client=typed).execute(
            "video_comments", {"identifier": "av170001", "comment_type": "2"}
        )
    )
    assert accepted["ok"] is True and accepted["comment_type"] == "2"
    assert typed.comment_calls == [(170001, 2, "hot", "", 20)]
