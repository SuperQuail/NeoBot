from __future__ import annotations

from typing import TYPE_CHECKING

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.config.schemas.bot import BotConfig as BotConfigSchema
from neobot_app.prompt.keyword_reaction import KeywordReactionBuilder
from neobot_app.user_profiles import UserProfileService
from neobot_app.utils.time import get_current_time_and_lunar_date

if TYPE_CHECKING:
    from neobot_app.message.numbering import MessageNumbering


class PromptBuilder:
    """Assemble prompt text from queues plus stored profile information."""

    def __init__(
        self,
        config: BotConfigSchema,
        profile_service: UserProfileService,
        logger: Logger | None = None,
    ) -> None:
        self._config = config
        self._profile_service = profile_service
        self._logger = logger or NullLogger()
        self._keyword_reaction_builder = KeywordReactionBuilder(
            config.chat.key_word or [],
            logger=self._logger,
        )

    async def build_group_chat_prompt(
        self,
        group_id: int,
        message_queue: object,
        *,
        key_word_reaction_list: str = "",
        memory_list: str = "",
        numbering: MessageNumbering | None = None,
    ) -> str:
        current_time = get_current_time_and_lunar_date()
        group_id_str = str(group_id)
        group_name = await self._profile_service.get_group_name(group_id_str)
        group_description_map = self._config.chat.group_description or {}
        group_description = group_description_map.get(group_id_str, "")
        member_list = await self._profile_service.render_group_member_list(
            group_id,
            message_queue,
        )

        if numbering is not None:
            message_list = numbering.apply(message_queue, group_id_str)
            format_example = numbering.format_example()
            message_list = f"{format_example}\n\n{message_list}"
        else:
            message_list = message_queue.to_text(group_id_str)

        keyword_reaction_text = self._keyword_reaction_builder.build(
            queue=message_queue,
            queue_key=group_id_str,
            conversation_type="group",
        )
        merged_keyword_reaction_list = _merge_prompt_fragments(
            key_word_reaction_list,
            keyword_reaction_text,
        )

        prompt = self._config.chat.group_prompt_template.format(
            current_time=current_time,
            group_name=group_name,
            group_id=group_id,
            group_description=group_description,
            message_list=message_list,
            member_list=member_list,
            bot_name=self._config.bot.nick_name,
            bot_account=self._config.bot.account,
            other_name=_build_bot_other_name(self._config),
            bot_data=self._config.bot.bot_data,
            key_word_reaction_list=merged_keyword_reaction_list,
            memory_list=memory_list,
        )
        if keyword_reaction_text and "{key_word_reaction_list}" not in self._config.chat.group_prompt_template:
            prompt = _merge_prompt_fragments(prompt, keyword_reaction_text)
        return prompt

    async def build_friend_chat_prompt(
        self,
        user_id: int,
        message_queue: object,
        *,
        key_word_reaction_list: str = "",
        memory_list: str = "",
        numbering: MessageNumbering | None = None,
    ) -> str:
        current_time = get_current_time_and_lunar_date()
        user_id_str = str(user_id)
        profile = await self._profile_service.ensure_user_profile(user_id_str)
        friend_name = getattr(profile, "nick_name", None) or f"QQ:{user_id_str}"
        remark = getattr(profile, "remark", None) or ""
        friend_info = await self._profile_service.render_friend_info(
            user_id_str,
            profile=profile,
        )

        if numbering is not None:
            message_list = numbering.apply(message_queue, user_id_str)
            format_example = numbering.format_example()
            message_list = f"{format_example}\n\n{message_list}"
        else:
            message_list = message_queue.to_text(user_id_str)

        keyword_reaction_text = self._keyword_reaction_builder.build(
            queue=message_queue,
            queue_key=user_id_str,
            conversation_type="private",
        )
        merged_keyword_reaction_list = _merge_prompt_fragments(
            key_word_reaction_list,
            keyword_reaction_text,
        )

        prompt = self._config.chat.friend_prompt_template.format(
            current_time=current_time,
            friend_name=friend_name,
            remark=remark,
            profile=getattr(profile, "profile", None) or "",
            friend_info=friend_info,
            message_list=message_list,
            bot_name=self._config.bot.nick_name,
            bot_account=self._config.bot.account,
            other_name=_build_bot_other_name(self._config),
            bot_data=self._config.bot.bot_data,
            key_word_reaction_list=merged_keyword_reaction_list,
            memory_list=memory_list,
        )
        if keyword_reaction_text and "{key_word_reaction_list}" not in self._config.chat.friend_prompt_template:
            prompt = _merge_prompt_fragments(prompt, keyword_reaction_text)
        return prompt


def _build_bot_other_name(config: BotConfigSchema) -> str:
    alias_list = config.bot.alias_name or []
    valid_aliases = [alias.strip() for alias in alias_list if alias.strip()]
    if not valid_aliases:
        return ""
    return ",也有人叫你" + "、".join(valid_aliases)


def _merge_prompt_fragments(*parts: str) -> str:
    cleaned = [part.strip() for part in parts if part and part.strip()]
    return "\n".join(cleaned)


async def get_group_chat_prompt(
    config: BotConfigSchema,
    group_id: int,
    message_queue: object,
    profile_service: UserProfileService,
    *,
    key_word_reaction_list: str = "",
    memory_list: str = "",
    logger: Logger | None = None,
) -> str:
    builder = PromptBuilder(config, profile_service, logger=logger)
    return await builder.build_group_chat_prompt(
        group_id,
        message_queue,
        key_word_reaction_list=key_word_reaction_list,
        memory_list=memory_list,
    )


async def get_friend_chat_prompt(
    config: BotConfigSchema,
    user_id: int,
    message_queue: object,
    profile_service: UserProfileService,
    *,
    key_word_reaction_list: str = "",
    memory_list: str = "",
    logger: Logger | None = None,
) -> str:
    builder = PromptBuilder(config, profile_service, logger=logger)
    return await builder.build_friend_chat_prompt(
        user_id,
        message_queue,
        key_word_reaction_list=key_word_reaction_list,
        memory_list=memory_list,
    )
