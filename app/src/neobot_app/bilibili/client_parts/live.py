"""直播：房间信息、拉流地址、弹幕发送与关注操作。"""

from __future__ import annotations

import time
from typing import Any

from ..errors import BilibiliError
from .common import (
    MAX_LIVE_DANMAKU_CHARS,
    _LIVE_DANMU_INFO_URL,
    _LIVE_PLAY_INFO_URL,
    _LIVE_ROOM_INFO_URL,
    _LIVE_SEND_DANMAKU_URL,
    _RELATION_MODIFY_URL,
    _live_stream_url,
    _to_int,
)


class _LiveMixin:
    """直播间信息、拉流地址、弹幕发送与关注。"""

    # ── 直播 ──

    def get_live_room_info(self, room_id: int) -> dict[str, Any]:
        """直播间信息（getInfoByRoom 的 data：room_info/anchor_info 等）；失败返回空 dict。"""
        room_id = _to_int(room_id)
        if room_id <= 0:
            return {}
        try:
            payload = self._fetch(
                "GET", _LIVE_ROOM_INFO_URL, params={"room_id": room_id}
            )
        except BilibiliError as exc:
            self._log_read_error("直播间信息读取", exc)
            return {}
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    def get_live_playurl(self, room_id: int) -> dict[str, Any]:
        """直播拉流地址：优先 http_stream/flv/avc，其次 http_hls/fmp4/avc。

        返回 {ok, room_id, url, format, expires, error}；取不到返回空 dict。
        expires 是地址剩余有效秒数；FLV CDN 需要 UA/Referer/Origin（ffmpeg 拉流时带上）。
        """
        room_id = _to_int(room_id)
        if room_id <= 0:
            return {}
        real_room_id = self._resolve_live_room_id(room_id)
        if real_room_id <= 0:
            return {}
        params = {
            "room_id": real_room_id,
            "protocol": "0,1",
            "format": "0,1,2",
            "codec": "0,1",
            "qn": 150,
            "platform": "web",
            "ptype": 8,
        }
        try:
            payload = self._fetch(
                "GET",
                _LIVE_PLAY_INFO_URL,
                params=params,
                headers={
                    "Referer": f"https://live.bilibili.com/{real_room_id}",
                    "Origin": "https://live.bilibili.com",
                },
            )
        except BilibiliError as exc:
            self._log_read_error("直播拉流地址读取", exc)
            return {}
        data = payload.get("data")
        playurl_info = data.get("playurl_info") if isinstance(data, dict) else None
        playurl = (
            playurl_info.get("playurl") if isinstance(playurl_info, dict) else None
        )
        streams = playurl.get("stream") if isinstance(playurl, dict) else None
        for protocol, format_name, codec_name in (
            ("http_stream", "flv", "avc"),
            ("http_hls", "fmp4", "avc"),
        ):
            for stream in streams or []:
                if not isinstance(stream, dict) or stream.get("protocol_name") != protocol:
                    continue
                for fmt in stream.get("format") or []:
                    if not isinstance(fmt, dict) or fmt.get("format_name") != format_name:
                        continue
                    for codec in fmt.get("codec") or []:
                        if not isinstance(codec, dict) or codec.get("codec_name") != codec_name:
                            continue
                        url, expires = _live_stream_url(codec)
                        if not url:
                            continue
                        return {
                            "ok": True,
                            "room_id": _to_int(data.get("room_id")) or real_room_id,
                            "url": url,
                            "format": format_name,
                            "expires": expires,
                            "error": "",
                        }
        return {}

    def get_live_danmu_info(self, room_id: int) -> dict[str, Any]:
        """弹幕服务器信息（getDanmuInfo 的 data：token/host_list）；失败返回空 dict。"""
        real_room_id = self._resolve_live_room_id(room_id)
        if real_room_id <= 0:
            return {}
        try:
            # getDanmuInfo 2026 起要求 wbi 签名；未签名会返回 -352（实测）。
            params = self._sign_wbi({"id": real_room_id, "type": 0})
            payload = self._fetch(
                "GET",
                _LIVE_DANMU_INFO_URL,
                params=params,
                headers={"Referer": f"https://live.bilibili.com/{real_room_id}"},
            )
        except BilibiliError as exc:
            self._log_read_error("直播弹幕服务器信息读取", exc)
            return {}
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    def send_danmaku(
        self, room_id: int, text: str, *, reply_mid: int = 0, reply_uname: str = ""
    ) -> bool:
        """发送直播弹幕；reply_mid/reply_uname 非空时 @ 目标观众。"""
        room_id = _to_int(room_id)
        message = (text or "").strip()
        if room_id <= 0 or not message:
            self._logger.warning("B站直播弹幕参数不完整（room_id/text 不能为空）")
            return False
        if len(message) > MAX_LIVE_DANMAKU_CHARS:
            self._logger.warning(
                f"B站直播弹幕超过 {MAX_LIVE_DANMAKU_CHARS} 字，已拦截发送"
            )
            return False
        if not self._sessdata or not self._bili_jct:
            return False
        real_room_id = self._resolve_live_room_id(room_id)
        form: dict[str, Any] = {
            "roomid": real_room_id,
            "msg": message,
            "color": 16777215,
            "mode": 1,
            "fontsize": 25,
            "rnd": int(time.time()),
            "csrf": self._bili_jct,
            "csrf_token": self._bili_jct,
            "reply_mid": _to_int(reply_mid),
            "reply_uname": str(reply_uname or ""),
            "reply_attr": 0,
        }
        self._rate_limit_wait()
        try:
            self._fetch(
                "POST",
                _LIVE_SEND_DANMAKU_URL,
                data=form,
                headers={
                    "Referer": f"https://live.bilibili.com/{real_room_id}",
                    "Origin": "https://live.bilibili.com",
                },
            )
        except BilibiliError as exc:
            self._on_write_error("直播弹幕发送", exc)
            return False
        self._logger.info(f"B站直播弹幕已发送: room={real_room_id}")
        return True

    def follow_user(self, uid: int, *, follow: bool = True) -> bool:
        """关注/取消关注一个 B站用户；失败返回 False（不抛）。"""
        if not self._require_login("关注用户"):
            return False
        target = _to_int(uid)
        if target <= 0 or target == self.my_uid:
            self._logger.warning(f"B站关注用户失败：无效 UID {uid!r}")
            return False
        form: dict[str, Any] = {
            "fid": target,
            "act": 1 if follow else 2,
            "re_src": 11,
            "csrf": self._bili_jct,
        }
        self._rate_limit_wait()
        try:
            self._fetch("POST", _RELATION_MODIFY_URL, data=form)
        except BilibiliError as exc:
            self._on_write_error("关注用户", exc)
            return False
        self._logger.info(f"B站{'关注用户' if follow else '取消关注'}成功: uid={target}")
        return True
