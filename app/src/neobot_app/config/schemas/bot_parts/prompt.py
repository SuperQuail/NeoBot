"""提示词板块开关配置段：[prompt_optimizations]。"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PromptOptimizations:
    """全局 cot 提示词板块的启停开关（默认全部开启）。"""

    cot_enabled: Optional[bool] = field(
        default=True,
        metadata={
            "description": "cot 提示词板块总开关：关闭后 system 最前面的整个 <cot>…</cot> "
            "前缀不再注入，下面的子块开关随之失效"
        },
    )
    at_mention_reply: Optional[bool] = field(
        default=True,
        metadata={
            "description": "cot 子块开关：<@消息回复> 提醒优先回复最新 @ 你的消息，"
            "并判断自己是否已经回复过"
        },
    )
    gentle_language: Optional[bool] = field(
        default=True,
        metadata={
            "description": "cot 子块开关：温和语言风格（原 chat.gentle_language_enabled，"
            "升级时自动迁移到这里）"
        },
    )
    avoid_bot_chat: Optional[bool] = field(
        default=True,
        metadata={
            "description": "cot 子块开关：<减少Bot聊天> 确认在场角色都是 Bot、没有真人参与时"
            "尽量不交流，避免浪费部署者资金"
        },
    )
    no_bluffing: Optional[bool] = field(
        default=True,
        metadata={
            "description": "cot 子块开关：<禁止不懂装懂> 不确定的内容不猜测，"
            "被明确询问但没有依据时直接说不知道"
        },
    )
    no_game_topics: Optional[bool] = field(
        default=True,
        metadata={
            "description": "cot 子块开关：<禁止主动参与游戏话题> 没人主动找你时不参与游戏讨论、"
            "不猜游戏机制"
        },
    )
    cross_chat: Optional[bool] = field(
        default=True,
        metadata={
            "description": "cot 子块开关：<跨聊天交互> 有事情需要对某个人私聊说、"
            "或者在别的群聊说时，可以使用 cross_chat 工具"
        },
    )
    no_echo_images: Optional[bool] = field(
        default=True,
        metadata={
            "description": "cot 子块开关：<禁止附和与解说图片> 不复述别人的话再评论，"
            "不主动描述图片内容"
        },
    )
    valuable_reply: Optional[bool] = field(
        default=True,
        metadata={
            "description": "cot 子块开关：<有价值的回复> 发送回复前先判断内容是否有意义，"
            "不点评群友话题、不做无意义附和；想不到有价值的回答就直接 cancel"
        },
    )
