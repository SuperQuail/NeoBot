"""B站工具 Skill — 搜索、看视频、查用户与关联的QQ主页。

按 duck typing 调用并行实现的接口，不 import client/video 模块：
- BilibiliService.client 提供 search / get_video_info / get_space_info /
  get_user_videos / get_comments / get_work_comments / get_video_comments / get_comment_replies；
- 消息通知 get_reply_feed / get_at_feed（只读；复用 comment_monitor.parse_feed_item 归一化）；
- 写操作 post_video_comment / like_video / like_comment / coin_video / share_video /
  favorite_video 与只读的 favorite_folders（客户端缺能力时返回明确错误）；
- BilibiliVideoService.watch 提供视频页面信息 + 字幕/ASR 转写。

所有失败都返回 {"ok": false, "error": "中文说明"}，不把异常栈丢给模型。
可选关键字参数按目标函数签名过滤，兼容尚未冻结的客户端接口。

公开写工具（评论/点赞/投币/分享/收藏/关注）必须显式传 confirm=true：Skill 这一层
拿不到可信的调用者上下文（CURRENT_INVOCATION 只在 agent_tools 系技能里设置），
只能要求模型在确认用户意图后再调用，属于弱门禁。

实现在 neobot_app.skills.bilibili_tool_parts（Skill 声明按类分文件、处理函数在
handlers_*，由 dispatch 登记），本模块只做门面 re-export。
"""

from __future__ import annotations

from neobot_app.skills.bilibili_tool_parts.skill_search import BilibiliSearchSkill
from neobot_app.skills.bilibili_tool_parts.skill_user import BilibiliUserSkill
from neobot_app.skills.bilibili_tool_parts.skill_video import BilibiliVideoSkill

__all__ = ["BilibiliSearchSkill", "BilibiliUserSkill", "BilibiliVideoSkill"]
