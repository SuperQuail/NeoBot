"""基础配置段：模型 key 归一化、关键词规则、机器人与聊天基础配置。"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TypedDict


_MODEL_KEY_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def normalize_model_key(value: Any) -> str:
    """把模型 key 规范化为 [A-Za-z0-9_.-]{1,64}（非法字符替换为 -）。"""
    text = str(value or "").strip()
    text = _MODEL_KEY_RE.sub("-", text).strip("-.")
    return text[:64]


class KeyWordRule(TypedDict, total=False):
    """关键词规则类型。"""

    enabled: bool
    keywords: List[str]
    prompt_list: List[str]
    ignore_case: bool
    match_mode: str
    min_depth: int
    max_depth: int
    description: str


@dataclass
class Bot:
    """机器人基础配置。"""

    account: int = field(
        default=0,
        metadata={"description": "机器人QQ号", "placeholder": True},
    )
    nick_name: str = field(default="Neo Bot", metadata={"description": "Bot昵称"})
    alias_name: Optional[List[str]] = field(
        default_factory=lambda: ["Neo", "铸币bot"],
        metadata={"description": "Bot别称"},
    )
    bot_data: str = field(
        default="你是一个可爱的机器人,如果你对别人有备注,你会倾向于叫你备注对方的名字",
        metadata={"description": "描述机器人的人设"},
    )
    # [WIP · 尚未接线] 结婚玩法本身还没实现：本开关读得到但不生效（全仓没有任何消费方，
    # 改它不会产生任何效果）。面板与配置参考会显示 description 里的标记，提醒用户别把它
    # 当成可用开关。后续开发计划见 TODO/待办事项.md「待办」第 12 项（好感度系统与结婚系统）。
    enable_bot_get_married: bool = field(
        default=False,
        metadata={
            "description": (
                "[WIP · 尚未接线] 是否允许 Bot 与好友结婚（互动彩蛋）；"
                "当前不生效 —— 结婚玩法尚未实现，没有任何代码读取该开关。"
            )
        },
    )


@dataclass
class Chat:
    native_vision_default_image_count: int = field(
        default=4,
        metadata={"description": "原生视觉每轮默认自动加载的图片数量，0 关闭自动加载；手动加图工具不受此数量限制"},
    )
    max_group_chat_observations: Optional[int] = field(
        default=200,
        metadata={"description": "群聊观察上限"},
    )
    group_chat_chance: Optional[float] = field(
        default=0.3,
        metadata={"description": "群聊基础回复概率"},
    )
    group_use_black_list: Optional[bool] = field(
        default=True,
        metadata={"description": "群聊名单是否使用黑名单模式"},
    )
    group_list: Optional[List[str]] = field(
        default_factory=lambda: ["111111", "222222"],
        metadata={"description": "群名单"},
    )
    group_response_coefficient: Optional[Dict[str, float]] = field(
        default_factory=lambda: {"111111": 0.5, "222222": 0.5},
        metadata={"description": "群聊回复系数", "aliases": ("group_Response_coefficient",)},
    )
    group_description: Optional[Dict[str, str]] = field(
        default_factory=lambda: {"111111": "这是不知道谁不知道干什么的群"},
        metadata={"description": "群描述"},
    )
    max_friend_chat_observations: Optional[int] = field(
        default=200,
        metadata={"description": "私聊观察上限"},
    )
    friend_use_black_list: Optional[bool] = field(
        default=True,
        metadata={"description": "私聊名单是否使用黑名单模式"},
    )
    friend_list: Optional[List[str]] = field(
        default_factory=lambda: ["111111", "222222"],
        metadata={"description": "好友名单"},
    )
    reply_blacklist: Optional[List[int]] = field(
        default_factory=list,
        metadata={"description": "回复黑名单(QQ号)，名单内用户@Bot时不强制追加回复要求"},
    )
    friend_description: Optional[Dict[str, str]] = field(
        default_factory=lambda: {"111111": "这是不知道谁不知道干什么的人"},
        metadata={"description": "好友描述"},
    )
    key_word: Optional[List[KeyWordRule]] = field(
        default_factory=lambda: [
            {
                "enabled": True,
                "keywords": ["妈妈", "妈"],
                "prompt_list": ["你可以反问对方是不是叫夏亚"],
                "ignore_case": True,
                "match_mode": "any",
                "min_depth": -1,
                "max_depth": 0,
            },
            {
                "enabled": False,
                "keywords": ["测试"],
                "prompt_list": ["Test"],
                "ignore_case": True,
                "match_mode": "any",
                "min_depth": -1,
                "max_depth": -1,
            },
        ],
        metadata={"description": "关键词规则列表"},
    )
