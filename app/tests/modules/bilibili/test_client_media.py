"""B 站视频能力：搜索/视频信息/空间/播放地址，以及视频理解服务。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from neobot_app.bilibili.client import BilibiliClient, parse_video_id
from neobot_app.bilibili.media import BilibiliVideoService

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
_BVID = "BV1xx411c7mD"
_VIEW = {
    "bvid": _BVID,
    "aid": 170001,
    "cid": 0,
    "title": "测试视频",
    "duration": 125,
    "desc": "视频简介",
    "owner": {"mid": 9, "name": "UP主"},
    "pages": [{"cid": 111}, {"cid": 222}],
}
_SUBTITLE_BODY = json.dumps(
    {"body": [{"from": 0, "to": 1, "content": "第一句"}, {"content": "第二句"}]},
    ensure_ascii=False,
)


class _TextResponse(FakeResponse):
    def __init__(self, text: str, *, status_code: int = 200) -> None:
        super().__init__(None, status_code=status_code)
        self.text = text


class _BytesResponse(FakeResponse):
    def __init__(self, content: bytes, *, status_code: int = 200) -> None:
        super().__init__(None, status_code=status_code)
        self.content = content


class _StreamResponse(FakeResponse):
    def __init__(self, chunks: list[bytes], *, status_code: int = 200) -> None:
        super().__init__(None, status_code=status_code)
        self._chunks = chunks

    def iter_content(self, chunk_size: int = 65536) -> list[bytes]:
        return self._chunks

    def close(self) -> None:
        pass


class _BrokenStreamResponse(_StreamResponse):
    def iter_content(self, chunk_size: int = 65536):
        yield self._chunks[0]
        raise OSError("连接中断")


def _client(session: FakeSession) -> BilibiliClient:
    return BilibiliClient("sessdata", "bili-jct", 7, session=session)


class _FakeVideoClient:
    """视频链路的最小 client 替身。"""

    def __init__(
        self,
        *,
        info: dict[str, Any] | None = None,
        player: dict[str, Any] | None = None,
        subtitles: dict[str, str | None] | None = None,
        audio_url: str | None = "https://cdn/audio.m4s",
        comments: list[dict[str, Any]] | None = None,
        fail_info: bool = False,
    ) -> None:
        self.info = _VIEW if info is None else info
        self.player = player
        self.subtitles = subtitles or {}
        self.audio_url = audio_url
        self.comments = comments or []
        self.fail_info = fail_info
        self.downloads: list[Path] = []
        self.calls: list[tuple[Any, ...]] = []

    def get_video_info(self, identifier: str) -> dict[str, Any]:
        self.calls.append(("info", identifier))
        if self.fail_info:
            raise RuntimeError("接口炸了")
        return self.info

    def get_player_info(self, bvid: str, cid: int) -> dict[str, Any]:
        self.calls.append(("player", bvid, cid))
        return self.player or {}

    def fetch_text(self, url: str) -> str | None:
        self.calls.append(("text", url))
        return self.subtitles.get(url)

    def get_playurl_audio(self, bvid: str, cid: int) -> str | None:
        self.calls.append(("audio", bvid, cid))
        return self.audio_url

    def download_file(self, url: str, path: Path) -> bool:
        self.calls.append(("download", url))
        target = Path(path)
        target.write_bytes(b"fake-audio")
        self.downloads.append(target)
        return True

    def get_video_comments(
        self, oid: int, page: int = 1, *, order: str = "time"
    ) -> list[dict[str, Any]]:
        self.calls.append(("comments", oid, order))
        return self.comments


class _FakeAsr:
    def __init__(self, text: str = "语音识别文本") -> None:
        self.text = text
        self.sources: list[Path] = []

    async def transcribe(self, source: Any) -> str:
        self.sources.append(Path(source))
        return self.text


# ── client：搜索 / 视频 / 空间 / 播放地址 ──


def test_parse_video_id_supports_bv_av_and_urls() -> None:
    assert parse_video_id(_BVID) == (_BVID, 0)
    assert parse_video_id("av170001") == ("", 170001)
    assert parse_video_id(f"https://www.bilibili.com/video/{_BVID}/?p=2") == (_BVID, 0)
    assert parse_video_id("https://www.bilibili.com/video/av170001") == ("", 170001)
    assert parse_video_id("没有视频号") == ("", 0)


def test_get_video_info_uses_bvid_from_url() -> None:
    session = FakeSession(
        [FakeResponse({"code": 0, "data": {"bvid": _BVID, "aid": 170001}})]
    )
    info = _client(session).get_video_info(f"https://www.bilibili.com/video/{_BVID}/?p=2")
    assert info["aid"] == 170001
    assert session.calls[0]["url"].endswith("/x/web-interface/view")
    assert session.calls[0]["params"] == {"bvid": _BVID}


def test_get_video_info_av_and_invalid_identifier_degrade() -> None:
    session = FakeSession([FakeResponse({"code": -404, "message": "啥都木有"})])
    assert _client(session).get_video_info("av170001") == {}
    assert session.calls[0]["params"] == {"aid": 170001}
    assert _client(FakeSession()).get_video_info("随便写点什么") == {}


def test_search_signs_wbi_and_returns_data() -> None:
    session = FakeSession(
        [
            FakeResponse(_NAV_WBI),
            FakeResponse({"code": 0, "data": {"result": [{"bvid": _BVID}], "numResults": 1}}),
        ]
    )
    data = _client(session).search(" 原神 ", page=2, page_size=5)
    assert data["result"] == [{"bvid": _BVID}]
    call = session.calls[-1]
    assert call["url"].endswith("/x/web-interface/wbi/search/type")
    assert call["params"]["keyword"] == "原神"
    assert call["params"]["page"] == "2"
    assert call["params"]["page_size"] == "5"
    assert call["params"]["search_type"] == "video"
    assert len(call["params"]["w_rid"]) == 32
    assert call["headers"]["Referer"] == "https://search.bilibili.com/"


def test_search_returns_empty_without_keyword_or_on_error() -> None:
    assert _client(FakeSession()).search("   ") == {}
    session = FakeSession(
        [FakeResponse(_NAV_WBI), FakeResponse({"code": -412, "message": "请求被拦截"})]
    )
    assert _client(session).search("原神") == {}


def test_get_space_info_signs_wbi() -> None:
    session = FakeSession(
        [
            FakeResponse(_NAV_WBI),
            FakeResponse({"code": 0, "data": {"mid": 9, "name": "UP主"}}),
        ]
    )
    data = _client(session).get_space_info(9)
    assert data["name"] == "UP主"
    call = session.calls[-1]
    assert call["url"].endswith("/x/space/wbi/acc/info")
    assert call["params"]["mid"] == "9"
    assert len(call["params"]["w_rid"]) == 32


def test_get_user_videos_returns_vlist_and_degrades() -> None:
    session = FakeSession(
        [
            FakeResponse(
                {"code": 0, "data": {"list": {"vlist": [{"bvid": _BVID}, "bad"]}}}
            )
        ]
    )
    videos = _client(session).get_user_videos(9, page=2, page_size=10)
    assert videos == [{"bvid": _BVID}]
    assert session.calls[0]["params"] == {
        "mid": 9,
        "ps": 10,
        "pn": 2,
        "order": "pubdate",
    }
    denied = FakeSession([FakeResponse({"code": -352, "message": "风控校验失败"})])
    assert _client(denied).get_user_videos(9) == []


def test_get_player_info_returns_subtitle_payload() -> None:
    session = FakeSession(
        [
            FakeResponse(_NAV_WBI),
            FakeResponse(
                {"code": 0, "data": {"subtitle": {"subtitles": [{"lan": "zh-CN"}]}}}
            ),
        ]
    )
    info = _client(session).get_player_info(_BVID, 111)
    assert info["subtitle"]["subtitles"][0]["lan"] == "zh-CN"
    assert session.calls[-1]["url"].endswith("/x/player/wbi/v2")
    assert session.calls[-1]["params"]["cid"] == "111"


def test_get_playurl_audio_picks_highest_bandwidth() -> None:
    payload = {
        "code": 0,
        "data": {
            "dash": {
                "audio": [
                    {"id": 30216, "bandwidth": 64000, "base_url": "https://cdn/low.m4s"},
                    {"id": 30280, "bandwidth": 256000, "baseUrl": "https://cdn/high.m4s"},
                    {"id": 30232, "bandwidth": 128000, "base_url": "https://cdn/mid.m4s"},
                ]
            }
        },
    }
    session = FakeSession([FakeResponse(_NAV_WBI), FakeResponse(payload)])
    assert _client(session).get_playurl_audio(_BVID, 111) == "https://cdn/high.m4s"
    params = session.calls[-1]["params"]
    assert params["fnval"] == "16"
    assert params["cid"] == "111"
    assert len(params["w_rid"]) == 32

    empty = FakeSession([FakeResponse(_NAV_WBI), FakeResponse({"code": 0, "data": {}})])
    assert _client(empty).get_playurl_audio(_BVID, 111) is None
    assert _client(FakeSession()).get_playurl_audio("", 0) is None


def test_fetch_text_returns_body_or_none() -> None:
    assert _client(FakeSession([_TextResponse(_SUBTITLE_BODY)])).fetch_text(
        "https://x/sub.json"
    ) == _SUBTITLE_BODY
    denied = FakeSession([_TextResponse("", status_code=403)])
    assert _client(denied).fetch_text("https://x/sub.json") is None


def test_fetch_bytes_returns_body_or_none() -> None:
    payload = b"\x89PNG\r\n\x1a\n avatar"
    assert _client(FakeSession([_BytesResponse(payload)])).fetch_bytes("https://x/face.png") == payload
    denied = FakeSession([_BytesResponse(b"", status_code=403)])
    assert _client(denied).fetch_bytes("https://x/face.png") is None
    empty = FakeSession([_BytesResponse(b"")])
    assert _client(empty).fetch_bytes("https://x/face.png") is None
    assert _client(FakeSession()).fetch_bytes("") is None


def test_download_file_streams_and_cleans_up_on_failure(tmp_path) -> None:
    target = tmp_path / "a.m4s"
    session = FakeSession()
    session.get = lambda url, **kwargs: _StreamResponse([b"abc", b"", b"def"])  # type: ignore[method-assign]
    assert _client(session).download_file("https://cdn/a.m4s", target) is True
    assert target.read_bytes() == b"abcdef"

    broken = tmp_path / "b.m4s"
    session.get = lambda url, **kwargs: _BrokenStreamResponse([b"partial"])  # type: ignore[method-assign]
    assert _client(session).download_file("https://cdn/b.m4s", broken) is False
    assert broken.exists() is False

    missing = tmp_path / "c.m4s"
    session.get = lambda url, **kwargs: _StreamResponse([], status_code=404)  # type: ignore[method-assign]
    assert _client(session).download_file("https://cdn/c.m4s", missing) is False
    assert missing.exists() is False



# ── client：直播拉流地址 ──

_LIVE_ROOM = {"code": 0, "data": {"room_info": {"room_id": 5050, "live_status": 1}}}
_LIVE_EXPIRES_AT = int(time.time()) + 3600


def _live_playurl_payload(*, flv: bool = True, hls: bool = True) -> dict[str, Any]:
    streams: list[dict[str, Any]] = []
    if flv:
        streams.append(
            {
                "protocol_name": "http_stream",
                "format": [
                    {
                        "format_name": "flv",
                        "codec": [
                            {
                                "codec_name": "avc",
                                "base_url": "/live-bvc/5050/live.flv?",
                                "url_info": [
                                    {
                                        "host": "https://flv.bilivideo.com",
                                        "extra": f"expires={_LIVE_EXPIRES_AT}&qn=150",
                                        "stream_ttl": 0,
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        )
    if hls:
        streams.append(
            {
                "protocol_name": "http_hls",
                "format": [
                    {
                        "format_name": "fmp4",
                        "codec": [
                            {
                                "codec_name": "avc",
                                "base_url": "/live-bvc/5050/live.m4s",
                                "url_info": [
                                    {
                                        "host": "https://hls.bilivideo.com",
                                        "extra": "?expires=9999999999",
                                        "stream_ttl": 3598,
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        )
    return {"code": 0, "data": {"room_id": 5050, "playurl_info": {"playurl": {"stream": streams}}}}


def test_get_live_playurl_resolves_room_and_prefers_flv() -> None:
    session = FakeSession([FakeResponse(_LIVE_ROOM), FakeResponse(_live_playurl_payload())])
    result = _client(session).get_live_playurl(1234)
    assert result["ok"] is True
    assert result["room_id"] == 5050
    assert result["format"] == "flv"
    assert result["url"] == (
        f"https://flv.bilivideo.com/live-bvc/5050/live.flv?expires={_LIVE_EXPIRES_AT}&qn=150"
    )
    assert 3500 < result["expires"] <= 3600
    room_call, play_call = session.calls
    assert room_call["url"].endswith("/xlive/web-room/v1/index/getInfoByRoom")
    assert room_call["params"] == {"room_id": 1234}
    assert play_call["url"].endswith("/xlive/web-room/v2/index/getRoomPlayInfo")
    assert play_call["params"] == {
        "room_id": 5050,
        "protocol": "0,1",
        "format": "0,1,2",
        "codec": "0,1",
        "qn": 150,
        "platform": "web",
        "ptype": 8,
    }
    assert play_call["headers"] == {
        "Referer": "https://live.bilibili.com/5050",
        "Origin": "https://live.bilibili.com",
    }


def test_get_live_playurl_falls_back_to_hls_fmp4() -> None:
    session = FakeSession(
        [FakeResponse(_LIVE_ROOM), FakeResponse(_live_playurl_payload(flv=False))]
    )
    result = _client(session).get_live_playurl(5050)
    assert result["format"] == "fmp4"
    assert result["url"] == "https://hls.bilivideo.com/live-bvc/5050/live.m4s?expires=9999999999"
    assert result["expires"] == 3598


def test_get_live_playurl_degrades() -> None:
    assert _client(FakeSession()).get_live_playurl(0) == {}

    denied = FakeSession(
        [
            FakeResponse({"code": -400, "message": "房间不存在"}),
            FakeResponse({"code": -400, "message": "房间不存在"}),
        ]
    )
    assert _client(denied).get_live_playurl(5050) == {}

    offline = FakeSession(
        [
            FakeResponse(_LIVE_ROOM),
            FakeResponse({"code": 0, "data": {"room_id": 5050, "playurl_info": None}}),
        ]
    )
    assert _client(offline).get_live_playurl(5050) == {}

    no_host = _live_playurl_payload(hls=False)
    no_host["data"]["playurl_info"]["playurl"]["stream"][0]["format"][0]["codec"][0]["url_info"] = [{}]
    assert _client(FakeSession([FakeResponse(_LIVE_ROOM), FakeResponse(no_host)])).get_live_playurl(5050) == {}

# ── 视频理解服务 ──


async def test_watch_prefers_site_chinese_subtitle() -> None:
    zh_url = "https://aisubtitle.hdslb.com/zh.json"
    player = {
        "subtitle": {
            "subtitles": [
                {"lan": "en", "lan_doc": "English", "subtitle_url": "//aisubtitle.hdslb.com/en.json"},
                {"lan": "zh-CN", "lan_doc": "中文（中国）", "subtitle_url": "//aisubtitle.hdslb.com/zh.json"},
            ]
        }
    }
    client = _FakeVideoClient(player=player, subtitles={zh_url: _SUBTITLE_BODY})
    asr = _FakeAsr("不该用到语音识别")
    result = await BilibiliVideoService(client, asr).watch(
        f"https://www.bilibili.com/video/{_BVID}"
    )
    assert result["ok"] is True
    assert result["source"] == "site"
    assert result["transcript"] == "第一句\n第二句"
    assert result["bvid"] == _BVID
    assert result["aid"] == 170001
    assert result["cid"] == 111
    assert result["owner"] == "UP主"
    assert result["duration"] == 125
    assert result["url"] == f"https://www.bilibili.com/video/{_BVID}"
    assert [call for call in client.calls if call[0] == "text"] == [("text", zh_url)]
    assert asr.sources == []


async def test_watch_subtitle_fetch_failure_falls_back_to_asr() -> None:
    player = {
        "subtitle": {
            "subtitles": [{"lan": "zh-CN", "subtitle_url": "//aisubtitle.hdslb.com/x.json"}]
        }
    }
    client = _FakeVideoClient(player=player)
    asr = _FakeAsr("兜底转写")
    result = await BilibiliVideoService(client, asr).watch(_BVID)
    assert result["ok"] is True
    assert result["source"] == "asr"
    assert result["transcript"] == "兜底转写"


async def test_watch_falls_back_to_asr_and_cleans_temp_file() -> None:
    client = _FakeVideoClient(player={"subtitle": {"subtitles": []}})
    asr = _FakeAsr("音频里说的话")
    result = await BilibiliVideoService(client, asr).watch(_BVID)
    assert result["ok"] is True
    assert result["source"] == "asr"
    assert result["transcript"] == "音频里说的话"
    assert asr.sources[0].name == "audio.m4s"
    assert client.downloads[0].parent.exists() is False


async def test_watch_without_subtitles_or_asr_degrades() -> None:
    client = _FakeVideoClient(player={"subtitle": {"subtitles": []}})
    result = await BilibiliVideoService(client).watch(_BVID)
    assert result["ok"] is False
    assert result["source"] == "none"
    assert result["transcript"] == ""
    assert "未配置语音识别" in result["error"]
    assert result["title"] == "测试视频"


async def test_watch_asr_failure_text_degrades() -> None:
    client = _FakeVideoClient(player=None)
    asr = _FakeAsr("语音识别失败：未找到 ffmpeg（请安装后加入 PATH）")
    result = await BilibiliVideoService(client, asr).watch(_BVID)
    assert result["ok"] is False
    assert result["source"] == "none"
    assert "语音识别失败" in result["error"]


async def test_watch_missing_audio_stream_degrades() -> None:
    client = _FakeVideoClient(player=None, audio_url=None)
    asr = _FakeAsr()
    result = await BilibiliVideoService(client, asr).watch(_BVID)
    assert result["ok"] is False
    assert "音频流" in result["error"]
    assert asr.sources == []


async def test_watch_metadata_failure_and_unknown_video() -> None:
    broken = _FakeVideoClient(fail_info=True)
    result = await BilibiliVideoService(broken).watch(_BVID)
    assert result["ok"] is False
    assert "获取视频信息失败" in result["error"]
    assert result["bvid"] == ""

    empty = _FakeVideoClient(info={})
    result = await BilibiliVideoService(empty).watch(_BVID)
    assert result["ok"] is False
    assert "未找到视频" in result["error"]


async def test_watch_truncates_transcript() -> None:
    client = _FakeVideoClient(player=None)
    asr = _FakeAsr("0123456789")
    result = await BilibiliVideoService(client, asr).watch(_BVID, max_chars=4)
    assert result["transcript"] == "0123"


async def test_watch_includes_hot_comments() -> None:
    comments = [
        {"like": 12, "member": {"uname": "甲"}, "content": {"message": "好看"}},
        {"like": 3, "member": {"uname": "乙"}, "content": {"message": "   "}},
        {"like": 1, "member": {"uname": "丙"}, "content": {"message": "三连"}},
    ]
    client = _FakeVideoClient(player=None, comments=comments)
    service = BilibiliVideoService(client, _FakeAsr("转写"))
    result = await service.watch(_BVID, include_comments=2)
    assert result["comments"] == [
        {"uname": "甲", "content": "好看", "like": 12},
        {"uname": "丙", "content": "三连", "like": 1},
    ]
    assert ("comments", 170001, "hot") in client.calls


async def test_watch_resolves_client_getter_and_dormant() -> None:
    dormant = await BilibiliVideoService(lambda: None).watch(_BVID)
    assert dormant["ok"] is False
    assert "未登录" in dormant["error"]

    client = _FakeVideoClient(player=None)
    service = BilibiliVideoService(lambda: client, _FakeAsr("getter 转写"))
    assert (await service.watch(_BVID))["source"] == "asr"


class _FakeArchive:
    def __init__(self) -> None:
        self.saved = {}

    async def set(self, table, key, value, tags=None):
        self.saved[(table, key)] = (value, list(tags or []))


async def test_watch_archives_long_transcript_for_on_demand_read() -> None:
    client = _FakeVideoClient(player=None)
    asr = _FakeAsr("0123456789")
    archive = _FakeArchive()
    service = BilibiliVideoService(client, asr, archive_service=archive)

    result = await service.watch(_BVID, max_chars=4)

    assert result["transcript"] == "0123"
    assert result["archived"] is True
    assert result["archive_key"] == _BVID
    saved_text, tags = archive.saved[("bilibili_video", _BVID)]
    assert saved_text == "0123456789"
    assert "auto" in tags


async def test_watch_short_transcript_not_archived() -> None:
    client = _FakeVideoClient(player=None)
    asr = _FakeAsr("短")
    archive = _FakeArchive()
    result = await BilibiliVideoService(client, asr, archive_service=archive).watch(
        _BVID, max_chars=3000
    )
    assert "archived" not in result
    assert archive.saved == {}
