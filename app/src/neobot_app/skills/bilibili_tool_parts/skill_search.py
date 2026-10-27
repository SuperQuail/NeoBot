"""B站搜索 Skill 的工具声明。"""

from __future__ import annotations

from neobot_app.skills.bilibili_tool_parts.base import _BilibiliToolBase
from neobot_app.skills.bilibili_tool_parts.common import _VIDEO_ORDERS


class BilibiliSearchSkill(_BilibiliToolBase):
    """B站搜索 Skill — 视频、用户、专栏。"""

    @property
    def name(self) -> str:
        return "bilibili_search"

    @property
    def description(self) -> str:
        return "B站搜索：按关键词搜视频、UP主（昵称/UID/空间链接）、专栏"

    @property
    def instructions(self) -> str:
        return (
            "B站搜索 Skill 提供以下能力：\n\n"
            "  search_video — 按关键词搜视频，可指定排序 order（totalrank=综合，click=播放，"
            "pubdate=最新，dm=弹幕，stow=收藏）。返回标题、BV号、UP主、播放量、链接、简介。\n"
            "  search_user — 按昵称、UID 或空间链接搜用户，返回UID、昵称、签名、粉丝数、空间链接；"
            "给 UID/空间链接时直接返回该用户的完整名片（含粉丝/关注/投稿/获赞）。\n"
            "  search_article — 按关键词搜专栏，返回CV号、标题、作者、阅读量、链接、摘要。\n\n"
            "搜到视频后，把 BV号 或链接交给 bilibili_video 的 video_info / watch_video 继续看；"
            "查用户资料/统计/动态/投稿时，把 UID 或昵称交给 bilibili_user 的 user_info / user_home。"
        )

    def get_tools(self) -> list[dict]:
        if not self._has_client_source():
            return []
        page_schema = {
            "type": "integer",
            "description": "页码，默认1",
            "default": 1,
        }
        return [
            self._tool_def(
                "search_video",
                "按关键词搜索B站视频，返回标题、BV号、UP主、播放量、链接与简介。",
                {
                    "properties": {
                        "keyword": {"type": "string", "description": "搜索关键词"},
                        "page": page_schema,
                        "order": {
                            "type": "string",
                            "description": "排序：totalrank=综合（默认），click=播放最多，"
                            "pubdate=最新发布，dm=弹幕最多，stow=收藏最多",
                            "enum": list(_VIDEO_ORDERS),
                            "default": "totalrank",
                        },
                    },
                    "required": ["keyword"],
                },
            ),
            self._tool_def(
                "search_user",
                "按昵称、UID 或空间链接搜B站用户（UP主），返回UID、昵称、签名、粉丝数与空间链接；"
                "UID/空间链接直接返回完整名片（含粉丝/关注/投稿/获赞）。",
                {
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "搜索关键词；也可以是 UID 或空间链接",
                        },
                        "page": page_schema,
                    },
                    "required": ["keyword"],
                },
            ),
            self._tool_def(
                "search_article",
                "按关键词搜索B站专栏文章，返回CV号、标题、作者、阅读量与链接。",
                {
                    "properties": {
                        "keyword": {"type": "string", "description": "搜索关键词"},
                        "page": page_schema,
                    },
                    "required": ["keyword"],
                },
            ),
        ]
