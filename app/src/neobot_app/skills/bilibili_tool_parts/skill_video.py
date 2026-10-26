"""B站视频 Skill 的工具声明。"""

from __future__ import annotations

from neobot_app.skills.bilibili_tool_parts.base import _BilibiliToolBase
from neobot_app.skills.bilibili_tool_parts.common import (
    _COMMENT_ORDERS,
    _CONFIRM_SCHEMA,
    _comment_type_schema,
)


class BilibiliVideoSkill(_BilibiliToolBase):
    """B站视频 Skill — 基本信息、看视频、评论。"""

    @property
    def name(self) -> str:
        return "bilibili_video"

    @property
    def description(self) -> str:
        return (
            "B站视频：查资料、看视频（字幕/语音转写）、拉评论/评论树、"
            "读消息通知、发评论、点赞、投币、分享与收藏"
        )

    @property
    def instructions(self) -> str:
        return (
            "B站视频 Skill 提供以下能力：\n\n"
            "  video_info — 查视频基本资料：标题、UP主、时长、简介、播放量、链接。\n"
            "  watch_video — 后台看视频：拉取B站页面字幕或语音识别转写（可带评论），"
            "立即返回 task_id；完成后通过通知管线回到当前聊天流，每群最多并发 3 个，不要重复提交。"
            "超过 3000 字符的完整转写会自动存档，可用 read_video_transcript 按需读取。\n"
            "  read_video_transcript — 读取之前 watch_video 存档的完整转写（按 BV 号）。\n"
            "  video_comments — 拉评论区列表（只读，不自动回复）：comment_type=video（视频，"
            "默认）/dynamic（动态）/article（专栏）/opus（图文）/bangumi（番剧）；"
            "order=hot（默认，热门）或 time（最新）；cursor 传上一页返回的 cursor 翻页。\n"
            "  comment_tree — 拉评论区树：顶级评论 + 楼中楼（comment_type 同上）；"
            "root_rpid 非 0 时只展开这条评论下的回复；返回 cursor 可继续翻页。"
            "只读，不自动回复；看完可用 comment_video 回复。\n"
            "  read_bili_messages — 读「回复我的」+「@我的」通知（标题、链接、评论、用户）。"
            "只读，不自动回复；看完可用 comment_video / comment_tree 继续。\n"
            "  comment_video — 给视频发评论；root/parent 非 0 时回复指定楼中楼。\n"
            "  like_video — 点赞视频。\n"
            "  like_comment — 点赞视频下的一条评论（rpid 为评论ID）。\n"
            "  coin_video — 给视频投币：multiply=1（默认）投一枚，2 投两枚。\n"
            "  share_video — 把视频分享到动态。\n"
            "  favorite_video — 把视频收藏到指定收藏夹，folder_id 用 favorite_folders 查。\n"
            "  favorite_folders — 列出当前账号的收藏夹（只读，返回收藏夹ID/标题/视频数）。\n\n"
            "identifier 支持 BV号（如 BV1xx411c7mD）、av号（如 av170001）或完整视频链接。"
            "看视频比查资料慢，先确认是不是目标视频；不要反复看同一个视频。\n"
            "写操作（评论/点赞/投币/分享/收藏）会以当前登录B站账号公开操作，"
            "确认用户意图后再调用，并带上 confirm=true（不带会被拒绝）；"
            "失败通常是登录失效、已经操作过或触发风控，不要反复重试。"
        )

    def get_tools(self) -> list[dict]:
        if not (
            self._has_client_source() or self._video_service is not None
        ):
            return []
        tools = [
            self._tool_def(
                "video_info",
                "查询B站视频的基本资料（标题、UP主、时长、简介、播放量、链接）。",
                {
                    "properties": {
                        "identifier": {
                            "type": "string",
                            "description": "BV号、av号或视频链接",
                        },
                    },
                    "required": ["identifier"],
                },
            ),
            self._tool_def(
                "watch_video",
                "后台看B站视频：拉取标题、简介、页面字幕或语音识别转写（可带评论）；立即返回 task_id，完成后通知当前聊天流。",
                {
                    "properties": {
                        "identifier": {
                            "type": "string",
                            "description": "BV号、av号或视频链接",
                        },
                        "max_chars": {
                            "type": "integer",
                            "description": "转写文本最多保留多少字符，默认3000；超长部分自动存档",
                            "default": 3000,
                        },
                        "include_comments": {
                            "type": "integer",
                            "description": "附带多少条热门评论，默认0（不附带）",
                            "default": 0,
                        },
                    },
                    "required": ["identifier"],
                },
            ),
            self._tool_def(
                "video_comments",
                "拉取B站评论区列表（视频/动态/专栏/图文/番剧），可按热门或最新排序，"
                "用 cursor 翻页；只读，不自动回复。",
                {
                    "properties": {
                        "identifier": {
                            "type": "string",
                            "description": "BV号、av号、视频链接，或动态/专栏/opus 的 ID/链接",
                        },
                        "comment_type": _comment_type_schema(),
                        "order": {
                            "type": "string",
                            "description": "排序：hot=热门（默认），time=最新",
                            "enum": list(_COMMENT_ORDERS),
                            "default": "hot",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "本页最多返回多少条评论，默认20，最大50",
                            "default": 20,
                        },
                        "cursor": {
                            "type": "string",
                            "description": "翻页游标：传上一页返回的 cursor，空=第一页",
                            "default": "",
                        },
                    },
                    "required": ["identifier"],
                },
            ),
            self._tool_def(
                "comment_tree",
                "拉取B站评论区树（顶级评论 + 楼中楼回复），支持视频/动态/专栏/图文/番剧。"
                "只读，不自动回复；看完可用 comment_video 回复、"
                "comment_tree（root_rpid）继续展开某条楼中楼。",
                {
                    "properties": {
                        "identifier": {
                            "type": "string",
                            "description": "BV号、av号、视频链接，或动态/专栏/opus 的 ID/链接",
                        },
                        "comment_type": _comment_type_schema(),
                        "root_rpid": {
                            "type": "integer",
                            "description": "根评论ID：0=拉顶级评论树；非0=只展开这条评论下的楼中楼",
                            "default": 0,
                        },
                        "limit": {
                            "type": "integer",
                            "description": "最多返回多少条评论/回复，默认20",
                            "default": 20,
                        },
                        "cursor": {
                            "type": "string",
                            "description": "翻页游标：传上一页返回的 cursor，空=第一页",
                            "default": "",
                        },
                    },
                    "required": ["identifier"],
                },
            ),
            self._tool_def(
                "read_bili_messages",
                "读取B站的「回复我的」和「@我的」通知（标题、链接、评论、用户）。"
                "只读，不自动回复；看完可用 comment_video 回复或 comment_tree 展开评论树。",
                {
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "最多读取多少条通知，默认20",
                            "default": 20,
                        },
                        "include_at": {
                            "type": "boolean",
                            "description": "是否同时读「@我的」通知，默认true",
                            "default": True,
                        },
                    },
                    "required": [],
                },
            ),
            self._tool_def(
                "comment_video",
                "给B站视频发评论（会以当前登录B站账号公开发言，确认用户意图后再调用）；"
                "root/parent 非0时回复指定楼中楼。",
                {
                    "properties": {
                        "identifier": {
                            "type": "string",
                            "description": "BV号、av号或视频链接",
                        },
                        "text": {"type": "string", "description": "评论正文；像真人随口说的短句，不带QQ群号/客服腔/markdown/前后缀，公开场合不透露他人档案或私聊内容"},
                        "root": {
                            "type": "integer",
                            "description": "楼中楼回复的根评论ID，0=发顶级评论",
                            "default": 0,
                        },
                        "parent": {
                            "type": "integer",
                            "description": "楼中楼回复的目标评论ID，0=回复根评论",
                            "default": 0,
                        },
                        "confirm": _CONFIRM_SCHEMA,
                    },
                    "required": ["identifier", "text", "confirm"],
                },
            ),
            self._tool_def(
                "like_video",
                "点赞B站视频（会以当前登录B站账号公开点赞，确认用户意图后再调用，必须传 confirm=true）。",
                {
                    "properties": {
                        "identifier": {
                            "type": "string",
                            "description": "BV号、av号或视频链接",
                        },
                        "confirm": _CONFIRM_SCHEMA,
                    },
                    "required": ["identifier", "confirm"],
                },
            ),
            self._tool_def(
                "like_comment",
                "点赞B站视频下的一条评论（会以当前登录B站账号公开点赞，确认用户意图后再调用）；"
                "identifier 用于解析视频号，rpid 是评论ID。",
                {
                    "properties": {
                        "identifier": {
                            "type": "string",
                            "description": "BV号、av号或视频链接",
                        },
                        "rpid": {"type": "integer", "description": "要点赞的评论ID"},
                        "confirm": _CONFIRM_SCHEMA,
                    },
                    "required": ["identifier", "rpid", "confirm"],
                },
            ),
            self._tool_def(
                "coin_video",
                "给B站视频投币（会以当前登录B站账号公开投币，确认用户意图后再调用）；"
                "multiply=2 投两枚，默认投一枚。",
                {
                    "properties": {
                        "identifier": {"type": "string", "description": "BV号、av号或视频链接"},
                        "multiply": {
                            "type": "integer",
                            "description": "投币数量：1=投一枚（默认），2=投两枚",
                            "enum": [1, 2],
                            "default": 1,
                        },
                        "confirm": _CONFIRM_SCHEMA,
                    },
                    "required": ["identifier", "confirm"],
                },
            ),
            self._tool_def(
                "share_video",
                "把B站视频分享到动态（会以当前登录B站账号公开发布分享，确认用户意图后再调用，必须传 confirm=true）。",
                {
                    "properties": {
                        "identifier": {"type": "string", "description": "BV号、av号或视频链接"},
                        "confirm": _CONFIRM_SCHEMA,
                    },
                    "required": ["identifier", "confirm"],
                },
            ),
            self._tool_def(
                "favorite_video",
                "把B站视频收藏到指定收藏夹（会以当前登录B站账号公开收藏，确认用户意图后再调用）；"
                "folder_id 必填，可先用 favorite_folders 查。",
                {
                    "properties": {
                        "identifier": {"type": "string", "description": "BV号、av号或视频链接"},
                        "folder_id": {
                            "type": "integer",
                            "description": "收藏夹ID（用 favorite_folders 查）",
                        },
                        "confirm": _CONFIRM_SCHEMA,
                    },
                    "required": ["identifier", "folder_id", "confirm"],
                },
            ),
            self._tool_def(
                "favorite_folders",
                "列出当前登录B站账号的收藏夹（只读，不会改动任何收藏），返回收藏夹ID、"
                "标题与视频数；favorite_video 需要这里的 folder_id。",
            ),
        ]
        if self._archive is not None:
            tools.append(
                self._tool_def(
                    "read_video_transcript",
                    "读取 watch_video 自动存档的完整视频转写（超过 3000 字符时才有）；"
                    "返回存档中的全文。",
                    {
                        "properties": {
                            "identifier": {
                                "type": "string",
                                "description": "BV号、av号或视频链接",
                            },
                        },
                        "required": ["identifier"],
                    },
                )
            )
        return tools
