from dataclasses import dataclass, field
from typing import Optional, List, Dict


@dataclass
class Bot:
    """机器人基础配置"""

    account: int = field(
        default=0, metadata={
            "description": "机器人QQ号",
            "placeholder": True
        }
    )
    nick_name: str = field(
        default="Neo Bot",metadata={
            "description": "Bot昵称"
        }
    )
    alias_name: List[str] = field(
        default_factory=["Neo","铸币bot"],metadata={
            "description": "Bot别称"
        }
    )
    bot_data : str = field(
        default="你是一个可爱的机器人",metadata={
            "description": "描述机器人的人设"
        }
    )

@dataclass
class Chat:
    group_use_black_list : bool = field(
        default=True,metadata={
            "description":"true为群聊列表使用黑名单,false表示使用白名单"
        }
    )
    group_list : Optional[List[int]] = field(
        default_factory=[111111,222222],metadata={
            "description": "群名单,根据group_use_black_list字段确定是白名单/黑名单,决定bot是否会在对应群聊对话"
        }
    )
    group_description : Optional[Dict[int,str]] = field(
        default_factory={111111:"这是不知道谁不知道干什么的群"},metadata={
            "description": "群描述,可以为特定群配置专属简介"
        }
    )
    friend_use_black_list : bool = field(
        default=True,metadata={
            "description":"true时私聊使用黑名单,false使用黑名单"
        }
    )
    friend_list: Optional[List[int]] = field(
        default_factory=[111111, 222222], metadata={
            "description": "好友名单,根据friend_use_black_list字段确定是白名单/黑名单,决定bot是否会在对应私聊对话"
        }
    )
    friend_description: Optional[Dict[int, str]] = field(
        default_factory={111111: "这是不知道谁不知道干什么的人"}, metadata={
            "description": "好友描述,可以为特定好友配置专属简介"
        }
    )
    key_word : Optional[List[Dict[bool,Dict[List[str],str]]]] = field(
        default_factory={False,{["妈妈", "妈"]: "当有人叫你妈妈,你可以反问对方是不是叫夏亚"}},metadata={
            "description": "关键词,满足关键词会在提示词中加入描述,可通过bool变量来控制开关,是列表,,注意Bot不知道是因为什么关键词触发,需要自己描述清楚"
        }
    )



@dataclass
class Plugins:
    """插件配置"""

    enabled: bool = field(default=True, metadata={"description": "是否启用插件"})
    dir: str = field(default="./plugins", metadata={"description": "插件目录"})


@dataclass
class Message:
    """消息处理配置"""

    max_length: Optional[int] = field(
        default=1000, metadata={"description": "消息最大长度"}
    )
    enable_group: Optional[bool] = field(
        default=True, metadata={"description": "是否处理群消息"}
    )
    enable_private: Optional[bool] = field(
        default=True, metadata={"description": "是否处理私聊消息"}
    )


@dataclass
class BotConfig:
    """机器人主配置"""

    version: str = field(default="0.2.0", metadata={"description": "配置文件版本"})
    bot: Bot = field(default_factory=Bot)
    chat: Chat = field(default_factory=Chat)
    plugins: Plugins = field(default_factory=Plugins)
    message: Message = field(default_factory=Message)
