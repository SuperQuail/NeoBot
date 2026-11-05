"""搜索、视频信息/互动、用户空间与媒体下载。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from ..errors import BilibiliError
from .common import (
    _FAV_FOLDER_LIST_URL,
    _FAV_RESOURCE_DEAL_URL,
    _PLAYER_INFO_URL,
    _PLAYURL_URL,
    _SEARCH_URL,
    _SPACE_INFO_URL,
    _SPACE_VIDEOS_URL,
    _VIDEO_COIN_URL,
    _VIDEO_LIKE_URL,
    _VIDEO_SHARE_URL,
    _VIDEO_VIEW_URL,
    _to_int,
    parse_video_id,
)


class _ContentMixin:
    """搜索、视频、收藏、用户空间与播放器/媒体读取。"""

    # ── 搜索 / 视频 / 用户空间 ──

    def search(
        self,
        keyword: str,
        *,
        search_type: str = "video",
        page: int = 1,
        page_size: int = 20,
        order: str = "totalrank",
    ) -> dict[str, Any]:
        """综合搜索，返回 data 原样（视频搜索的结果在 data["result"]）；失败返回空 dict。"""
        text = (keyword or "").strip()
        if not text:
            return {}
        params = self._sign_wbi(
            {
                "search_type": search_type or "video",
                "keyword": text,
                "page": max(_to_int(page), 1),
                "page_size": max(_to_int(page_size), 1),
                "order": order or "totalrank",
            }
        )
        try:
            payload = self._fetch(
                "GET",
                _SEARCH_URL,
                params=params,
                headers={"Referer": "https://search.bilibili.com/"},
            )
        except BilibiliError as exc:
            self._log_read_error("视频搜索", exc)
            return {}
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    def get_video_info(self, identifier: str) -> dict[str, Any]:
        """视频信息（view 接口的 data）；identifier 支持 BV 号 / av 号 / 视频 URL。"""
        bvid, aid = parse_video_id(identifier)
        if not bvid and not aid:
            self._logger.warning(f"B站视频号解析失败: {identifier!r}")
            return {}
        params: dict[str, Any] = {"bvid": bvid} if bvid else {"aid": aid}
        try:
            payload = self._fetch("GET", _VIDEO_VIEW_URL, params=params)
        except BilibiliError as exc:
            self._log_read_error("视频信息读取", exc)
            return {}
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    def like_video(self, identifier: str) -> bool:
        """给视频点赞：identifier 支持 BV/av/URL（BV 会先查 aid）。"""
        aid = self._resolve_video_aid(identifier)
        if not aid:
            self._logger.warning(f"B站视频点赞失败：无法解析视频号 {identifier!r}")
            return False
        form: dict[str, Any] = {"aid": aid, "like": 1, "csrf": self._bili_jct}
        self._rate_limit_wait()
        try:
            self._fetch("POST", _VIDEO_LIKE_URL, data=form)
        except BilibiliError as exc:
            self._on_write_error("视频点赞", exc)
            return False
        self._logger.info(f"B站视频点赞成功: aid={aid}")
        return True

    def coin_video(self, identifier: str, multiply: int = 1) -> bool:
        """给视频投币：multiply=1 投一枚、2 投两枚；identifier 支持 BV/av/URL。"""
        if not self._require_login("视频投币"):
            return False
        aid = self._resolve_video_aid(identifier)
        if not aid:
            self._logger.warning(f"B站视频投币失败：无法解析视频号 {identifier!r}")
            return False
        form: dict[str, Any] = {
            "aid": aid,
            "multiply": 2 if _to_int(multiply) >= 2 else 1,
            "csrf": self._bili_jct,
        }
        self._rate_limit_wait()
        try:
            self._fetch("POST", _VIDEO_COIN_URL, data=form)
        except BilibiliError as exc:
            self._on_write_error("视频投币", exc)
            return False
        self._logger.info(f"B站视频投币成功: aid={aid} multiply={form['multiply']}")
        return True

    def share_video(self, identifier: str) -> bool:
        """把视频分享到动态：identifier 支持 BV/av/URL（av 会先查 bvid）。"""
        if not self._require_login("视频分享"):
            return False
        bvid, aid = parse_video_id(identifier)
        if not bvid and aid:
            bvid = str(self.get_video_info(f"av{aid}").get("bvid") or "").strip()
        if not bvid:
            self._logger.warning(f"B站视频分享失败：无法解析视频号 {identifier!r}")
            return False
        form: dict[str, Any] = {"bvid": bvid, "csrf": self._bili_jct}
        self._rate_limit_wait()
        try:
            self._fetch("POST", _VIDEO_SHARE_URL, data=form)
        except BilibiliError as exc:
            self._on_write_error("视频分享", exc)
            return False
        self._logger.info(f"B站视频分享成功: bvid={bvid}")
        return True

    def get_favorite_folders(self) -> list[dict[str, Any]]:
        """当前账号自建的收藏夹列表（folder/created/list-all 的 data.list）；失败返回空列表。"""
        if not self._require_login("收藏夹读取"):
            return []
        up_mid = self.my_uid
        if up_mid <= 0:
            self._logger.debug("B站收藏夹读取失败：未取到自己的 UID")
            return []
        try:
            payload = self._fetch("GET", _FAV_FOLDER_LIST_URL, params={"up_mid": up_mid})
        except BilibiliError as exc:
            self._log_read_error("收藏夹读取", exc)
            return []
        data = payload.get("data")
        folders = data.get("list") if isinstance(data, dict) else None
        return [item for item in folders or [] if isinstance(item, dict)]

    def favorite_video(self, identifier: str, folder_id: int) -> bool:
        """把视频收藏到指定收藏夹：folder_id 来自 get_favorite_folders。"""
        if not self._require_login("视频收藏"):
            return False
        folder_id = _to_int(folder_id)
        if folder_id <= 0:
            self._logger.warning("B站视频收藏失败：缺少有效的收藏夹ID")
            return False
        aid = self._resolve_video_aid(identifier)
        if not aid:
            self._logger.warning(f"B站视频收藏失败：无法解析视频号 {identifier!r}")
            return False
        form: dict[str, Any] = {
            "rid": aid,
            "type": 2,
            "add_media_ids": folder_id,
            "del_media_ids": "",
            "csrf": self._bili_jct,
        }
        self._rate_limit_wait()
        try:
            self._fetch("POST", _FAV_RESOURCE_DEAL_URL, data=form)
        except BilibiliError as exc:
            self._on_write_error("视频收藏", exc)
            return False
        self._logger.info(f"B站视频收藏成功: aid={aid} folder={folder_id}")
        return True

    # ── 用户空间 ──

    def get_space_info(self, mid: int) -> dict[str, Any]:
        """用户空间信息（space/wbi/acc/info 的 data）；失败返回空 dict。"""
        mid = _to_int(mid)
        if not mid:
            return {}
        params = self._sign_wbi({"mid": mid})
        try:
            payload = self._fetch(
                "GET",
                _SPACE_INFO_URL,
                params=params,
                headers={"Referer": f"https://space.bilibili.com/{mid}"},
            )
        except BilibiliError as exc:
            self._log_read_error("用户空间信息读取", exc)
            return {}
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    def get_user_videos(
        self, mid: int, *, page: int = 1, page_size: int = 20
    ) -> list[dict[str, Any]]:
        """用户投稿视频（space/arc/search 的 vlist）；失败返回空列表。"""
        mid = _to_int(mid)
        if not mid:
            return []
        params = {
            "mid": mid,
            "ps": max(_to_int(page_size), 1),
            "pn": max(_to_int(page), 1),
            "order": "pubdate",
        }
        try:
            payload = self._fetch(
                "GET",
                _SPACE_VIDEOS_URL,
                params=params,
                headers={"Referer": f"https://space.bilibili.com/{mid}"},
            )
        except BilibiliError as exc:
            self._log_read_error("用户投稿读取", exc)
            return []
        data = payload.get("data")
        listing = data.get("list") if isinstance(data, dict) else None
        vlist = listing.get("vlist") if isinstance(listing, dict) else None
        return [item for item in vlist or [] if isinstance(item, dict)]

    def get_player_info(self, bvid: str, cid: int) -> dict[str, Any]:
        """播放器信息（player/wbi/v2 的 data）；字幕在 data["subtitle"]["subtitles"]。"""
        bvid = (bvid or "").strip()
        cid = _to_int(cid)
        if not bvid or not cid:
            return {}
        params = self._sign_wbi({"bvid": bvid, "cid": cid})
        try:
            payload = self._fetch(
                "GET",
                _PLAYER_INFO_URL,
                params=params,
                headers={"Referer": f"https://www.bilibili.com/video/{bvid}"},
            )
        except BilibiliError as exc:
            self._log_read_error("播放器信息读取", exc)
            return {}
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    def get_playurl_audio(self, bvid: str, cid: int) -> str | None:
        """DASH 音频流地址：取 bandwidth 最大的一条；失败返回 None。"""
        bvid = (bvid or "").strip()
        cid = _to_int(cid)
        if not bvid or not cid:
            return None
        params = self._sign_wbi(
            {"bvid": bvid, "cid": cid, "fnval": 16, "fourk": 1}
        )
        try:
            payload = self._fetch(
                "GET",
                _PLAYURL_URL,
                params=params,
                headers={"Referer": f"https://www.bilibili.com/video/{bvid}"},
            )
        except BilibiliError as exc:
            self._log_read_error("音频地址读取", exc)
            return None
        data = payload.get("data")
        dash = data.get("dash") if isinstance(data, dict) else None
        audios = dash.get("audio") if isinstance(dash, dict) else None
        best = max(
            (
                item
                for item in audios or []
                if isinstance(item, dict) and (item.get("base_url") or item.get("baseUrl"))
            ),
            key=lambda item: _to_int(item.get("bandwidth")),
            default=None,
        )
        if not best:
            return None
        return str(best.get("base_url") or best.get("baseUrl"))

    def fetch_text(self, url: str) -> str | None:
        """下载文本资源（字幕 JSON 等）；失败返回 None。"""
        if not url:
            return None
        response = self._request("GET", url)
        if response is None or response.status_code >= 400:
            self._logger.warning(f"B站文本下载失败: {url}")
            return None
        try:
            return response.text
        except (requests.RequestException, OSError, ValueError) as exc:
            self._logger.warning(f"B站文本下载失败: {url}（{exc}）")
            return None

    def fetch_bytes(self, url: str) -> bytes | None:
        """下载二进制资源（头像等）；失败返回 None。"""
        if not url:
            return None
        response = self._request("GET", url)
        if response is None or response.status_code >= 400:
            self._logger.warning(f"B站二进制下载失败: {url}")
            return None
        try:
            content = response.content
        except (requests.RequestException, OSError, ValueError) as exc:
            self._logger.warning(f"B站二进制下载失败: {url}（{exc}）")
            return None
        if not content:
            self._logger.warning(f"B站二进制下载失败: {url}（空响应）")
            return None
        return content

    def download_file(self, url: str, path: Path) -> bool:
        """把 url 流式下载到 path（先写 .part 再替换）；失败返回 False 并清理半成品。"""
        target = Path(path)
        # 先落 .part：下载中断时不会把已有文件截成半截，调用方也读不到不完整内容。
        partial = target.with_name(f"{target.name}.part")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            response = self._http.get(url, stream=True, timeout=self._timeout)
            try:
                if response.status_code >= 400:
                    self._logger.warning(f"B站文件下载失败: HTTP {response.status_code} {url}")
                    return False
                with partial.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1 << 16):
                        if chunk:
                            handle.write(chunk)
            finally:
                response.close()
            if partial.stat().st_size <= 0:
                self._logger.warning(f"B站文件下载失败: {url}（空响应）")
                partial.unlink(missing_ok=True)
                return False
            partial.replace(target)
        except (requests.RequestException, OSError) as exc:
            self._logger.warning(f"B站文件下载失败: {url}（{exc}）")
            partial.unlink(missing_ok=True)
            return False
        return True
