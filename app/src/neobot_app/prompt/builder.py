from neobot_app.config.schemas.bot import BotConfig as BotConfigSchema
from neobot_app.utils.time import get_current_time_and_lunar_date


async def get_group_chat_prompt(
    config: BotConfigSchema,
    group_id: int,
    message_list: str,
    member_list: str,
    key_world_message: str,
    memory_list: str,
) -> str:
    """
    获取群聊提示词

    Args:
        config: 机器人配置实例（注入）
    """
    current_time = get_current_time_and_lunar_date()
    group_description = config.chat.group_description
    alias_list = config.bot.alias_name or []
    valid_aliases = [alias.strip() for alias in alias_list if alias.strip()]
    other_name = ""
    if valid_aliases:
        other_name = "、".join(valid_aliases)
        other_name = ",也有人叫你" + other_name
    return config.chat.group_prompt_template.format(
        current_time=current_time,
        group_id=group_id,
        group_description=group_description,
        message_list=message_list,
        member_list=member_list,
        bot_name=config.bot.nick_name,
        bot_account=config.bot.account,
        other_name=other_name,
        bot_data=config.bot.bot_data,
        key_word_reaction_list=key_world_message,
        memory_list=memory_list,
    )
