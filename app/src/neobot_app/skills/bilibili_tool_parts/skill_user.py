"""B站用户 Skill 的工具声明。"""

from __future__ import annotations

from neobot_app.skills.bilibili_tool_parts.base import _BilibiliToolBase
from neobot_app.skills.bilibili_tool_parts.common import _CONFIRM_SCHEMA


class BilibiliUserSkill(_BilibiliToolBase):
    """B站用户 Skill — 用户资料、投稿、关联的 QQ 主页。"""

    @property
    def name(self) -> str:
        return "bilibili_user"

    @property
    def description(self) -> str:
        return "B站用户：查资料与统计、统一主页（资料+动态+投稿）、投稿视频、关注/取关、该用户关联的QQ主页"

    @property
    def instructions(self) -> str:
        return (
            "B站用户 Skill 提供以下能力：\n\n"
            "  user_info — 查B站用户资料与统计：昵称、签名、等级、粉丝、关注、投稿数、"
            "专栏数、获赞数、空间链接。\n"
            "  user_home — 查B站用户统一主页：资料+统计+最近动态（类型/正文/发布时间/互动数/链接）"
            "+最近投稿；留空=自己，与看别人走同一条路径。\n"
            "  user_videos — 查该用户的投稿视频（标题、BV号、播放量、链接）。\n"
            "  follow_user — 关注/取消关注该 B站用户（公开写操作，确认意图后带 confirm=true 调用）。\n"
            "  linked_qq_profile — 按B站UID查该用户关联的QQ主页资料：QQ号、好友备注、"
            "你对Ta的印象，以及 user_summary / user_profile 长期档案。\n\n"
            "uid 支持纯数字 UID、space.bilibili.com 空间链接或昵称；user_info / user_home "
            "留空=当前登录账号。没有关联QQ时会明确提示，不要编造QQ号或资料。"
        )

    def get_tools(self) -> list[dict]:
        if not self._has_client_source():
            return []
        return [
            self._tool_def(
                "user_info",
                "查询B站用户资料与统计（昵称、签名、等级、粉丝、关注、投稿数、专栏数、获赞数、"
                "空间链接）；uid 可填 UID/空间链接/昵称，留空=自己。",
                {
                    "properties": {
                        "uid": {
                            "type": "string",
                            "description": "B站UID（纯数字）、空间链接或昵称；留空=当前登录账号",
                        },
                    },
                    "required": [],
                },
            ),
            self._tool_def(
                "user_home",
                "查询B站用户统一主页：资料+统计+最近动态（类型/正文/发布时间/互动数/链接）"
                "+最近投稿；uid 可填 UID/空间链接/昵称，留空=自己。",
                {
                    "properties": {
                        "uid": {
                            "type": "string",
                            "description": "B站UID、空间链接或昵称；留空=当前登录账号",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "动态和投稿各返回多少条，默认5，范围1-20",
                            "default": 5,
                        },
                    },
                    "required": [],
                },
            ),
            self._tool_def(
                "user_videos",
                "查询B站用户的投稿视频列表。",
                {
                    "properties": {
                        "uid": {
                            "type": "string",
                            "description": "B站UID（纯数字）或空间链接",
                        },
                        "page": {"type": "integer", "description": "页码，默认1", "default": 1},
                    },
                    "required": ["uid"],
                },
            ),
            self._tool_def(
                "follow_user",
                "关注或取消关注一个B站用户（会以当前登录B站账号公开操作，确认用户意图后再调用）。",
                {
                    "properties": {
                        "uid": {
                            "type": "string",
                            "description": "B站UID（纯数字）或空间链接",
                        },
                        "action": {
                            "type": "string",
                            "enum": ["follow", "unfollow"],
                            "description": "follow=关注，unfollow=取消关注",
                            "default": "follow",
                        },
                        "confirm": _CONFIRM_SCHEMA,
                    },
                    "required": ["uid", "confirm"],
                },
            ),
            self._tool_def(
                "linked_qq_profile",
                "查询某个B站用户关联的QQ主页资料（备注、印象与长期档案）；没有关联会明确提示。",
                {
                    "properties": {
                        "uid": {
                            "type": "string",
                            "description": "B站UID（纯数字）或空间链接",
                        },
                    },
                    "required": ["uid"],
                },
            ),
        ]
