"""工具名 -> 处理函数的分发表；处理函数散在 handlers_* 里，这里唯一登记。"""

from __future__ import annotations

from neobot_app.skills.bilibili_tool_parts.handlers_comments import (
    _handle_comment_tree,
    _handle_read_bili_messages,
    _handle_video_comments,
)
from neobot_app.skills.bilibili_tool_parts.handlers_user import (
    _handle_follow_user,
    _handle_linked_qq_profile,
    _handle_user_home,
    _handle_user_info,
    _handle_user_videos,
)
from neobot_app.skills.bilibili_tool_parts.handlers_video import (
    _handle_read_video_transcript,
    _handle_search_article,
    _handle_search_user,
    _handle_search_video,
    _handle_video_info,
    _handle_watch_video,
)
from neobot_app.skills.bilibili_tool_parts.handlers_write import (
    _handle_coin_video,
    _handle_comment_video,
    _handle_favorite_folders,
    _handle_favorite_video,
    _handle_like_comment,
    _handle_like_video,
    _handle_share_video,
)


_HANDLERS = {
    "search_video": _handle_search_video,
    "search_user": _handle_search_user,
    "search_article": _handle_search_article,
    "video_info": _handle_video_info,
    "watch_video": _handle_watch_video,
    "read_video_transcript": _handle_read_video_transcript,
    "video_comments": _handle_video_comments,
    "comment_tree": _handle_comment_tree,
    "read_bili_messages": _handle_read_bili_messages,
    "comment_video": _handle_comment_video,
    "like_video": _handle_like_video,
    "like_comment": _handle_like_comment,
    "coin_video": _handle_coin_video,
    "share_video": _handle_share_video,
    "favorite_video": _handle_favorite_video,
    "favorite_folders": _handle_favorite_folders,
    "user_info": _handle_user_info,
    "user_home": _handle_user_home,
    "user_videos": _handle_user_videos,
    "follow_user": _handle_follow_user,
    "linked_qq_profile": _handle_linked_qq_profile,
}
