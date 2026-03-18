from neobot_app.config.instance import  BotConfig
from neobot_adapter.model import *
from neobot_app.utils.time import get_current_time_and_lunar_date

basic_prompt = BotConfig.chat.group_prompt_template

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
