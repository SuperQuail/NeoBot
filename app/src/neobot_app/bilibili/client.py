"""
Bilibili 私信客户端 — 封装 B站私信 API 的轮询监听与发送。

参考 BiliGo 实现，提供：
- 会话列表获取
- 消息拉取与去重
- 私信发送（文本/图片）
- 关注者检测
- 频率限制保护

使用方式：
    from .cookie_provider import BilibiliCookieProvider

    provider = BilibiliCookieProvider()
    client = BilibiliClient(*provider.load_credentials())
    client.start_monitoring(callback=my_handler)
"""
from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

# ── 常量 ──
BILIBILI_API_BASE = "https://api.vc.bilibili.com"
DEFAULT_DEVICE_ID = "B1994F2C-C5C9-4C0E-8F4C-F8E5F7E8F9E0"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


# ── 数据模型 ──

@dataclass
class BilibiliMessage:
    """B站私信消息模型。"""
    talker_id: int          # 对方 UID
    sender_uid: int         # 发送方 UID（判断收/发方向）
    msg_type: int           # 1=文本, 2=图片
    content: str            # 文本内容或图片 JSON
    timestamp: int          # Unix 时间戳
    msg_key: str = ""       # 去重键
    is_self: bool = False   # 是否是自己发出的消息

    @property
    def text(self) -> str:
        """提取纯文本内容。"""
        if self.msg_type == 1:
            try:
                return json.loads(self.content).get("content", "")
            except (json.JSONDecodeError, TypeError):
                return self.content
        return ""

    @classmethod
    def from_api(cls, raw: dict, my_uid: int = 0) -> "BilibiliMessage":
        """从 API 返回的原始消息构造。"""
        content = raw.get("content", "")
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False)
        msg = cls(
            talker_id=raw.get("receiver_id", 0) or raw.get("sender_uid", 0),
            sender_uid=raw.get("sender_uid", 0),
            msg_type=raw.get("msg_type", 1),
            content=str(content),
            timestamp=raw.get("timestamp", 0),
        )
        msg.is_self = (msg.sender_uid == my_uid)
        msg.msg_key = f"{msg.talker_id}_{msg.timestamp}_{msg.content[:20]}"
        return msg


@dataclass
class BilibiliSession:
    """B站私信会话模型。"""
    talker_id: int
    last_msg: BilibiliMessage | None = None

    @classmethod
    def from_api(cls, raw: dict) -> "BilibiliSession":
        session = cls(talker_id=raw.get("talker_id", 0))
        last_msg_data = raw.get("last_msg", {})
        if last_msg_data:
            session.last_msg = BilibiliMessage.from_api(last_msg_data)
        return session


# ── 主客户端 ──

class BilibiliClient:
    """B站私信 API 客户端。

    封装 HTTP 请求、认证、限流。轮询逻辑在 monitor 循环中实现。
    """

    def __init__(self, sessdata: str, bili_jct: str, my_uid: int = 0):
        if not sessdata or not bili_jct:
            raise ValueError("SESSDATA 和 bili_jct 不能为空")

        self._sessdata = sessdata
        self._bili_jct = bili_jct
        self._my_uid: int = my_uid

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": DEFAULT_UA,
            "Referer": "https://message.bilibili.com/",
        })
        # Cookie 用 requests 的 cookie jar 设置，避免 latin-1 编码问题
        self.session.cookies.set("SESSDATA", sessdata, domain=".bilibili.com", path="/")
        self.session.cookies.set("bili_jct", bili_jct, domain=".bilibili.com", path="/")

        # 限流状态
        self._last_send_time: float = 0
        self._send_interval: float = 1.0  # 最小发送间隔（秒）

        # 去重缓存
        self._seen_msg_keys: set[str] = set()
        self._last_msg_times: dict[int, int] = defaultdict(int)  # talker_id → timestamp

        # WBI 签名缓存
        self._wbi_mixin_key: str = ""

    # ── 认证 ──

    @property
    def my_uid(self) -> int:
        """自己的 UID。"""
        if self._my_uid == 0:
            self._my_uid = self._extract_uid()
        return self._my_uid

    def _extract_uid(self) -> int:
        """从 API 获取自己的 UID，同时缓存 WBI 签名密钥。"""
        try:
            resp = self.session.get(
                "https://api.bilibili.com/x/web-interface/nav",
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == 0:
                    self._cache_wbi_keys(data["data"])
                    mid = data["data"].get("mid", 0)
                    if mid:
                        self._my_uid = mid
                    return mid
        except Exception:
            pass
        return 0

    # ── WBI 签名 ──

    _WBI_MIXIN_INDICES = [
        46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
        27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
        37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
        22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 52, 44, 34,
    ]

    def _cache_wbi_keys(self, nav_data: dict) -> None:
        """从 nav 接口响应中提取并缓存 WBI 混合密钥。"""
        if self._wbi_mixin_key:
            return
        wbi_img = nav_data.get("wbi_img")
        if not wbi_img or not isinstance(wbi_img, dict):
            logger.debug("nav 响应中无 wbi_img 字段，跳过 WBI 签名")
            return
        # 兼容 img_key/img_url 两种字段名
        img_raw = str(wbi_img.get("img_key") or wbi_img.get("img_url") or "")
        sub_raw = str(wbi_img.get("sub_key") or wbi_img.get("sub_url") or "")
        img_key = img_raw.rsplit("/", 1)[-1].split(".")[0]
        sub_key = sub_raw.rsplit("/", 1)[-1].split(".")[0]
        if not img_key or not sub_key:
            logger.debug("WBI 密钥提取失败: img=%s sub=%s", img_key[:8] if img_key else "", sub_key[:8] if sub_key else "")
            return
        combined = img_key + sub_key
        self._wbi_mixin_key = "".join(
            combined[i] for i in self._WBI_MIXIN_INDICES if i < len(combined)
        )[:32]

    def _sign_wbi(self, params: dict) -> dict:
        """为请求参数添加 WBI 签名（w_rid + wts）。"""
        if not self._wbi_mixin_key:
            self._extract_uid()
        if not self._wbi_mixin_key:
            logger.warning("WBI 密钥未缓存，跳过签名")
            return params

        signed = dict(params)
        # 确保 mid 使用真实 UID（而非 cookie 中的 DedeUserID）
        if "mid" in signed and self._my_uid and self._my_uid != signed["mid"]:
            signed["mid"] = self._my_uid
        signed["wts"] = int(time.time())
        # 按 key 排序并构建查询字符串
        sorted_params = sorted(signed.items(), key=lambda x: x[0])
        query_str = urlencode(sorted_params)
        w_rid = hashlib.md5((query_str + self._wbi_mixin_key).encode()).hexdigest()
        signed["w_rid"] = w_rid
        return signed

    # ── 会话 ──

    def get_sessions(self, count: int = 30) -> list[BilibiliSession]:
        """获取私信会话列表（按最后消息时间排序）。"""
        try:
            resp = self.session.get(
                f"{BILIBILI_API_BASE}/session_svr/v1/session_svr/get_sessions",
                params={
                    "session_type": 1,
                    "group_fold": 1,
                    "unfollow_fold": 0,
                    "sort_rule": 2,
                    "build": 0,
                    "mobi_app": "web",
                },
                timeout=2,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != 0:
                self._handle_api_error(data.get("code"), data.get("message", ""))
                return []

            sessions = data.get("data", {}).get("session_list", [])
            sessions.sort(
                key=lambda s: s.get("last_msg", {}).get("timestamp", 0),
                reverse=True,
            )
            return [
                BilibiliSession.from_api(s)
                for s in sessions[:count]
            ]
        except requests.RequestException as e:
            logger.error("获取会话列表失败: %s", e)
            return []

    # ── 消息 ──

    def get_messages(self, talker_id: int, size: int = 5) -> list[BilibiliMessage]:
        """获取指定会话的最新消息。"""
        try:
            resp = self.session.get(
                f"{BILIBILI_API_BASE}/svr_sync/v1/svr_sync/fetch_session_msgs",
                params={
                    "sender_device_id": 1,
                    "talker_id": talker_id,
                    "session_type": 1,
                    "size": size,
                    "build": 0,
                    "mobi_app": "web",
                },
                timeout=1,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != 0:
                return []

            messages = data.get("data", {}).get("messages", [])
            return [
                BilibiliMessage.from_api(m, self.my_uid)
                for m in messages
            ]
        except requests.RequestException as e:
            logger.debug("获取会话 %d 消息失败: %s", talker_id, e)
            return []

    def get_new_messages(self, session: BilibiliSession) -> list[BilibiliMessage]:
        """获取会话的新消息（自动去重）。"""
        messages = self.get_messages(session.talker_id, size=3)
        new_msgs = []
        for msg in messages:
            if msg.msg_key in self._seen_msg_keys:
                continue
            if msg.sender_uid == self.my_uid:
                continue  # 跳过自己发的
            last_ts = self._last_msg_times.get(session.talker_id, 0)
            if msg.timestamp <= last_ts:
                continue
            self._seen_msg_keys.add(msg.msg_key)
            new_msgs.append(msg)
        if new_msgs:
            self._last_msg_times[session.talker_id] = max(
                m.timestamp for m in new_msgs
            )
        return new_msgs

    # ── 发送 ──

    def send_message(self, receiver_id: int, content: str) -> bool:
        """发送文本私信。"""
        self._rate_limit_wait()

        data = {
            "msg[sender_uid]": self.my_uid,
            "msg[receiver_id]": receiver_id,
            "msg[receiver_type]": 1,
            "msg[msg_type]": 1,
            "msg[msg_status]": 0,
            "msg[content]": json.dumps({"content": content}, ensure_ascii=False),
            "msg[timestamp]": int(time.time()),
            "msg[new_face_version]": 0,
            "msg[dev_id]": DEFAULT_DEVICE_ID,
            "build": 0,
            "mobi_app": "web",
            "csrf": self._bili_jct,
            "csrf_token": self._bili_jct,
        }

        try:
            resp = self.session.post(
                f"{BILIBILI_API_BASE}/web_im/v1/web_im/send_msg",
                data=data,
                timeout=3,
            )
            resp.raise_for_status()
            result = resp.json()
            self._last_send_time = time.time()

            code = result.get("code", -1)
            if code == 0:
                return True
            if code == -412:
                logger.warning("频率限制 (-412)，增加冷却时间")
                self._send_interval *= 1.5
            elif code == -101:
                logger.error("登录态失效 (-101)，请更新 SESSDATA")
            else:
                logger.warning("发送失败: code=%d msg=%s", code, result.get("message", ""))
            return False
        except requests.RequestException as e:
            logger.error("发送消息异常: %s", e)
            self._last_send_time = time.time()
            return False

    # ── 图片发送 ──

    def upload_image(self, image_path: str) -> dict | None:
        """上传图片到 B站，返回图片信息 dict（含 image_url 等）。"""
        if not os.path.exists(image_path):
            logger.error("图片文件不存在: %s", image_path)
            return None
        file_size = os.path.getsize(image_path)
        if file_size > 20 * 1024 * 1024:
            logger.error("图片文件过大: %.1fMB", file_size / 1024 / 1024)
            return None

        # 方案 A: 直接上传到 im 专用接口
        result = self._direct_upload_image(image_path)
        if result:
            return result
        # 方案 B: BFS 上传
        return self._upload_to_bfs(image_path)

    def _direct_upload_image(self, image_path: str) -> dict | None:
        """直接上传图片（im 业务接口）。"""
        file_name = os.path.basename(image_path)
        mime_type = mimetypes.guess_type(image_path)[0] or "image/png"

        upload_configs = [
            {
                "url": "https://api.vc.bilibili.com/api/v1/drawImage/upload",
                "data": {"biz": "im", "category": "daily", "csrf": self._bili_jct},
                "headers": {
                    "Origin": "https://message.bilibili.com",
                    "Referer": "https://message.bilibili.com/",
                },
            },
            {
                "url": "https://api.bilibili.com/x/dynamic/feed/draw/upload_bfs",
                "data": {"biz": "new_dyn", "category": "daily", "csrf": self._bili_jct},
                "headers": {
                    "Origin": "https://t.bilibili.com",
                    "Referer": "https://t.bilibili.com/",
                },
            },
        ]

        with open(image_path, "rb") as f:
            image_data = f.read()

        for config in upload_configs:
            try:
                saved_headers = dict(self.session.headers)
                self.session.headers.update(config["headers"])
                resp = self.session.post(
                    config["url"],
                    files={"file_up": (file_name, image_data, mime_type)},
                    data=config["data"],
                    timeout=15,
                )
                self.session.headers.clear()
                self.session.headers.update(saved_headers)

                if resp.status_code == 200:
                    result = resp.json()
                    if result.get("code") == 0:
                        logger.info("图片上传成功: %s", file_name)
                        return result.get("data", {})
            except Exception:
                continue
        return None

    def _upload_to_bfs(self, image_path: str) -> dict | None:
        """通过 BFS 流程上传图片。"""
        try:
            upload_info = self._get_upload_info()
            if not upload_info or "upos_uri" not in upload_info:
                return None
            upos_uri = upload_info["upos_uri"]
            upload_url = f"https:{upos_uri}" if not upos_uri.startswith("http") else upos_uri

            with open(image_path, "rb") as f:
                image_data = f.read()

            headers = {
                "Content-Type": "application/octet-stream",
                "Referer": "https://message.bilibili.com/",
            }
            resp = self.session.put(upload_url, data=image_data, headers=headers, timeout=30)
            if resp.status_code == 200:
                return {
                    "image_url": upload_url,
                    "image_width": 0,
                    "image_height": 0,
                }
        except Exception as e:
            logger.debug("BFS 上传失败: %s", e)
        return None

    def _get_upload_info(self) -> dict | None:
        """获取 B站 上传凭证。"""
        try:
            resp = self.session.get(
                "https://member.bilibili.com/preupload",
                params={
                    "name": "image.png",
                    "size": 1024,
                    "r": "upos",
                    "profile": "ugcupos/bup",
                    "ssl": "0",
                    "version": "2.10.4",
                    "build": "2100400",
                },
                timeout=10,
            )
            if resp.status_code == 200:
                result = resp.json()
                if result.get("OK") == 1:
                    return result
        except Exception:
            pass
        return None

    def send_image_message(self, receiver_id: int, image_path: str) -> bool:
        """发送图片私信（上传 + 发送）。"""
        image_info = self.upload_image(image_path)
        if not image_info:
            return False

        image_content = {
            "url": image_info.get("image_url", ""),
            "height": image_info.get("image_height", 0),
            "width": image_info.get("image_width", 0),
            "imageType": "jpeg",
            "original": 1,
            "size": image_info.get("image_size", 0),
        }

        self._rate_limit_wait()

        data = {
            "msg[sender_uid]": self.my_uid,
            "msg[receiver_id]": receiver_id,
            "msg[receiver_type]": 1,
            "msg[msg_type]": 2,
            "msg[msg_status]": 0,
            "msg[content]": json.dumps(image_content, ensure_ascii=False),
            "msg[timestamp]": int(time.time()),
            "msg[new_face_version]": 0,
            "msg[dev_id]": DEFAULT_DEVICE_ID,
            "build": 0,
            "mobi_app": "web",
            "csrf": self._bili_jct,
            "csrf_token": self._bili_jct,
        }

        try:
            resp = self.session.post(
                f"{BILIBILI_API_BASE}/web_im/v1/web_im/send_msg",
                data=data,
                timeout=3,
            )
            resp.raise_for_status()
            result = resp.json()
            self._last_send_time = time.time()

            code = result.get("code", -1)
            if code == 0:
                return True
            if code == -412:
                logger.warning("频率限制 (-412)，增加冷却时间")
                self._send_interval *= 1.5
            elif code == -101:
                logger.error("登录态失效 (-101)，请更新 SESSDATA")
            else:
                logger.warning("图片发送失败: code=%d msg=%s", code, result.get("message", ""))
            return False
        except requests.RequestException as e:
            logger.error("发送图片消息异常: %s", e)
            self._last_send_time = time.time()
            return False

    # ── 关注者 ──

    def get_followers(self, page: int = 1, page_size: int = 20) -> list[dict]:
        """获取关注者列表。"""
        try:
            resp = self.session.get(
                "https://api.bilibili.com/x/relation/followers",
                params={"vmid": self.my_uid, "pn": page, "ps": page_size},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") == 0:
                return data.get("data", {}).get("list", [])
        except requests.RequestException as e:
            logger.error("获取关注者失败: %s", e)
        return []

    # ── 评论 ──

    def get_reply_feed(self, limit: int = 20) -> list[dict]:
        """获取"回复我的"评论通知列表。

        GET https://api.bilibili.com/x/msgfeed/reply
        返回别人回复我评论的通知。
        """
        try:
            resp = self.session.get(
                "https://api.bilibili.com/x/msgfeed/reply",
                params={"platform": "web", "build": 0, "mobi_app": "web"},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                logger.warning("获取评论回复失败: code=%d msg=%s", data.get("code"), data.get("message", ""))
                return []
            items = data.get("data", {}).get("items", []) or []
            return items[:limit]
        except requests.RequestException as e:
            logger.error("获取评论回复异常: %s", e)
            return []

    def get_video_comments(
        self, oid: int, page: int = 1, *, order: str = "time"
    ) -> list[dict]:
        """获取指定稿件/动态的评论列表。

        oid: 稿件 aid 或动态 ID
        order: "time"=按时间, "hot"=按热度
        返回 data.replies[] 列表。
        """
        mode = 2 if order == "time" else 3
        try:
            resp = self.session.get(
                "https://api.bilibili.com/x/v2/reply/main",
                params={"type": 1, "oid": oid, "mode": mode, "next": (page - 1) if page > 1 else 0},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                return []
            return data.get("data", {}).get("replies", []) or []
        except requests.RequestException as e:
            logger.debug("获取视频 %d 评论失败: %s", oid, e)
            return []

    def send_comment_reply(
        self, oid: int, root: int, parent: int, text: str, *, type_: int = 1
    ) -> bool:
        """回复一条评论。
        oid: 稿件/动态 ID
        root: 根评论 rpid
        parent: 父评论 rpid（回复顶层评论时=root）
        type_: 1=视频, 12=专栏, 17=动态
        """
        self._rate_limit_wait()

        data = {
            "oid": oid,
            "type": type_,
            "root": root,
            "parent": parent,
            "message": text,
            "csrf": self._bili_jct,
            "csrf_token": self._bili_jct,
        }

        try:
            resp = self.session.post(
                "https://api.bilibili.com/x/v2/reply/add",
                data=data,
                timeout=5,
            )
            resp.raise_for_status()
            result = resp.json()
            self._last_send_time = time.time()

            code = result.get("code", -1)
            if code == 0:
                return True
            if code == -799:
                logger.warning("评论限流 (-799)，增加冷却时间")
                self._send_interval = min(self._send_interval * 2, 60)
            elif code == 12002:
                logger.warning("评论区已关闭 (12002)")
            elif code == 12016:
                logger.warning("评论包含敏感词 (12016)")
            else:
                logger.warning("评论回复失败: code=%d msg=%s", code, result.get("message", ""))
            return False
        except requests.RequestException as e:
            logger.error("发送评论回复异常: %s", e)
            self._last_send_time = time.time()
            return False

    def like_comment(self, oid: int, rpid: int, type_: int = 1) -> bool:
        """点赞评论。"""
        self._rate_limit_wait()

        data = {
            "oid": oid,
            "type": type_,
            "rpid": rpid,
            "action": 1,
            "csrf": self._bili_jct,
            "csrf_token": self._bili_jct,
        }

        try:
            resp = self.session.post(
                "https://api.bilibili.com/x/v2/reply/action",
                data=data,
                timeout=5,
            )
            resp.raise_for_status()
            result = resp.json()
            self._last_send_time = time.time()
            return result.get("code") == 0
        except requests.RequestException as e:
            logger.error("点赞评论异常: %s", e)
            self._last_send_time = time.time()
            return False

    def get_my_videos(self, page: int = 1, page_size: int = 10) -> list[dict]:
        """获取自己投稿的视频列表。返回 list[{aid, bvid, title, ...}]。"""
        try:
            raw_params = {"mid": self.my_uid, "ps": page_size, "pn": page, "order": "pubdate"}
            params = self._sign_wbi(raw_params)
            resp = self.session.get(
                "https://api.bilibili.com/x/space/wbi/arc/search",
                params=params,
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                return []
            return data.get("data", {}).get("list", {}).get("vlist", []) or []
        except requests.RequestException as e:
            logger.error("获取视频列表失败: %s", e)
            return []

    # ── 限流 ──

    def _rate_limit_wait(self) -> None:
        """在发送前等待（满足最小发送间隔）。"""
        elapsed = time.time() - self._last_send_time
        if elapsed < self._send_interval:
            time.sleep(self._send_interval - elapsed)

    # ── 错误处理 ──

    @staticmethod
    def _handle_api_error(code: int, message: str) -> None:
        if code == -101:
            logger.error("登录态失效: %s", message)
        elif code == -111:
            logger.error("账号被限制: %s", message)
        elif code == -400:
            logger.error("请求参数错误: %s", message)
        elif code == -412:
            logger.warning("请求被拦截(风控): %s", message)
        else:
            logger.warning("API 错误 code=%d: %s", code, message)

    # ── 工具 ──

    def get_my_info(self) -> dict:
        """获取自己的账号信息。"""
        try:
            resp = self.session.get(
                "https://api.bilibili.com/x/web-interface/nav",
                timeout=5,
            )
            if resp.status_code == 200:
                return resp.json().get("data", {})
        except Exception:
            pass
        return {}

    def verify_auth(self) -> bool:
        """验证当前登录态是否有效。"""
        info = self.get_my_info()
        return bool(info.get("mid", 0))


# ── 便利函数 ──

def create_client_from_browser(browser_data_dir: str = "") -> Optional[BilibiliClient]:
    """从浏览器持久化数据创建 BilibiliClient。

    这是推荐的一站式入口。
    """
    from .cookie_provider import BilibiliCookieProvider
    provider = BilibiliCookieProvider(browser_data_dir)
    sd, jct = provider.load_credentials()
    if not sd or not jct:
        logger.error(
            "未找到 B站 cookie。请先使用浏览器登录 bilibili.com，"
            "确保 SESSDATA 和 bili_jct 已保存至 %s",
            provider._data_dir,
        )
        return None
    uid = provider.load_dedeuserid() or 0
    return BilibiliClient(sd, jct, uid)
