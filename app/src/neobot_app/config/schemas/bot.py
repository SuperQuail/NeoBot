from dataclasses import dataclass, field
from typing import Optional, List, Dict ,Any,TypedDict


class KeyWordRule(TypedDict, total=False):
    """关键词规则类型"""
    enabled: bool
    keywords: List[str]
    description: str


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
    alias_name: Optional[List[str]] = field(
        default_factory=lambda: ["Neo", "铸币bot"],metadata={
            "description": "Bot别称"
        }
    )
    bot_data : str = field(
        default="你是一个可爱的机器人",metadata={
            "description": "描述机器人的人设"
        }
    )
    enable_bot_get_married: bool = field(
        default=False,metadata={
            "description":"是否允许bot与好友结婚"
        }
    )

@dataclass
class Chat:
    group_prompt_template : str = field(
        default="""<当前时间>{current_time}</当前时间>
<群聊>{group_name}[群号:{group_id}]{group_description}</群聊>
<聊天记录>
{message_list}
</聊天记录>
<群友信息>
{member_list}
</群友信息>
<你是谁>
你的名字是{bot_name},你的QQ号是{bot_account}{other_name}.
{bot_data},现在你在这个群里聊天,你打算用日常,口语化的方式回复最后几句聊天记录里你比较感兴趣的内容,个性化一些,不用特意突出科学背景,聊天时你一般不会使用冒号,括号,句号也一般不使用,而是直接换行分成多条(多次调用回复工具).一次回复一句即可,不要太长.
</你是谁>
<你的印象>
{key_word_reaction_list}
你想起来之前:
{memory_list}
这些内容都是之前的内容,可能很久之前,也可能只是不久之前.
</你的印象>""",metadata={
            "description":"Bot提示词模板,非开发者不建议修改"
        }
    )
    max_group_chat_observations : int = field(
        default=100,metadata={
            "description":"群聊观察上限,决定bot最多可以看到多少条聊天记录"
        }
    )
    group_chat_chance : float = field(
        default=0.5,metadata={
            "description":"群聊基础回复概率"
        }
    )
    group_use_black_list : bool = field(
        default=True,metadata={
            "description":"true为群聊列表使用黑名单,false表示使用白名单"
        }
    )
    group_list : Optional[List[str]] = field(
        default_factory=lambda: ["111111","222222"],metadata={
            "description": "群名单，根据 group_use_black_list 字段确定是白名单/黑名单，决定 bot 是否会在对应群聊对话"
        }
    )
    group_Response_coefficient : Optional[Dict[str,float]] = field(
        default_factory=lambda: {"111111":0.5,"222222":0.5},metadata={
            "description": "群聊回复系数，根据群聊 ID 配置回复概率，会在结算时与基础回复概率相乘"
        }
    )
    group_description : Optional[Dict[str,str]] = field(
        default_factory=lambda: {"111111":"这是不知道谁不知道干什么的群"},metadata={
            "description": "群描述，可以为特定群配置专属简介"
        }
    )
    friend_prompt_template : str = field(
        default="""<当前时间>{current_time}</当前时间>
<聊天对象>{friend_name}(你的备注:{remark})</聊天对象>
<你对ta的印象>{profile}</你对ta的印象>
<你的记忆>
你想起来{memory_list}
</你的记忆>
<聊天记录>
{message_list}
</聊天记录>
<你是谁>
你的名字是{bot_name},你的QQ号是{bot_account}{other_name}.
{bot_data},现在你在这个群里聊天,你打算用日常,口语化的方式回复最后几句聊天记录里你比较感兴趣的内容,个性化一些,不用特意突出科学背景,聊天时你一般不会使用冒号,括号,句号也一般不使用,而是直接换行分成多条.一次回复一句即可,不要超过三小句.
</你是谁>"""
    )
    max_friend_chat_observations: int = field(
        default=100, metadata={
            "description": "群聊观察上限,决定bot最多可以看到多少条聊天记录"
        }
    )
    friend_chat_chance : float = field(
        default=0.5,metadata={
            "description":"私聊基础回复概率"
        }
    )
    friend_use_black_list : bool = field(
        default=True,metadata={
            "description":"true时私聊使用黑名单,false使用黑名单"
        }
    )
    friend_list: Optional[List[str]] = field(
        default_factory=lambda: ["111111", "222222"], metadata={
            "description": "好友名单，根据 friend_use_black_list 字段确定是白名单/黑名单，决定 bot 是否会在对应私聊对话"
        }
    )
    friend_description: Optional[Dict[str, str]] = field(
        default_factory=lambda: {"111111": "这是不知道谁不知道干什么的人"}, metadata={
            "description": "好友描述，可以为特定好友配置专属简介"
        }
    )
    key_word: Optional[List[KeyWordRule]] = field(
        default_factory=lambda: [
            {
                "enabled": False,
                "keywords": ["妈妈", "妈"],
                "description": "当有人叫你妈妈，你可以反问对方是不是叫夏亚"
            }
        ],
        metadata={
            "description": "关键词规则列表，每个规则包含 enabled(bool), keywords(List[str]), description(str)"
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
