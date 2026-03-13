from neobot_app.config.instance import  BotConfig
from neobot_adapter.model import *
from neobot_app.utils.time import get_current_time_and_lunar_date

basic_prompt = """
<当前时间>{current_time}</当前时间>
<群聊>{group_name}[群号:{group_id}]{group_description}</群聊>
<聊天记录>
{message_list}
</聊天记录>
<群友信息>
{member_list}
</群友信息>
<你是谁>
你的名字是{bot_name},你的QQ号是{bot_account}{other_name}.
{bot_data},现在你在这个群里聊天,你打算用日常,口语化的方式回复最后几句聊天记录里你比较感兴趣的内容,个性化一些,不用特意突出科学背景,聊天时你一般不会使用冒号,括号,句号也一般不使用,而是直接换行分成多条.一次回复一句即可,不要超过三小句.
</你是谁>
<你的印象>
{key_word_reaction_list}
你想起来之前:
{memory_list}
这些内容都是之前的内容,可能很久之前,也可能只是不久之前.
</你的印象>
"""

async def get_group_chat_prompt(group_id: int,message_list: str,member_list : str,key_world_message : str,memory_list : str) -> str:
    """
    获取提示词

    Returns:
        str: 提示词
    """
    current_time = get_current_time_and_lunar_date()
    group_description = BotConfig.chat.group_description
    alias_list = BotConfig.bot.alias_name
    valid_aliases = [alias.strip() for alias in alias_list if alias.strip()]
    other_name = ""
    if valid_aliases:
        other_name = "、".join(valid_aliases)
        other_name = ",也有人叫你" + other_name
    return basic_prompt.format(
        current_time=current_time,
        group_id=group_id,
        group_description=group_description,
        message_list=message_list,
        member_list=member_list,
        bot_name=BotConfig.bot.nick_name,
        bot_account=BotConfig.bot.account,
        other_name=other_name,
        bot_data=BotConfig.bot.bot_data,
        key_word_reaction_list=key_world_message,
        memory_list=memory_list,

    )
