from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.config.schemas.bot import BotConfig as BotConfigSchema
from neobot_app.prompt.keyword_reaction import KeywordReactionBuilder
from neobot_app.user_profiles import UserProfileService
from neobot_app.time_context import get_current_time_and_lunar_date

if TYPE_CHECKING:
    from neobot_app.message.numbering import MessageNumbering


class PromptBuilder:
    """Assemble prompt text from queues plus stored profile information."""

    def __init__(
        self,
        config: BotConfigSchema,
        profile_service: UserProfileService,
        logger: Logger | None = None,
        archive_memory_service: Any | None = None,
        adaptive_prompt_path: Path | None = None,
    ) -> None:
        self._config = config
        self._profile_service = profile_service
        self._logger = logger or NullLogger()
        self._archive_memory_service = archive_memory_service
        self._keyword_reaction_builder = KeywordReactionBuilder(
            config.chat.key_word or [],
            logger=self._logger,
        )
        self._adaptive_prompt_path = adaptive_prompt_path
        self._adaptive_prompt_cache: str | None = None
        self._adaptive_prompt_mtime: float | None = None

    def _get_adaptive_prompt(self) -> str:
        """读取自适应提示词内容（带 mtime 缓存）。"""
        if self._adaptive_prompt_path is None:
            return ""
        try:
            path = self._adaptive_prompt_path
            if not path.is_file():
                return ""
            mtime = path.stat().st_mtime
            if self._adaptive_prompt_cache is not None and self._adaptive_prompt_mtime == mtime:
                return self._adaptive_prompt_cache
            content = path.read_text("utf-8").strip()
            self._adaptive_prompt_cache = content
            self._adaptive_prompt_mtime = mtime
            return content
        except Exception:
            return ""

    async def build_group_chat_prompt(
        self,
        group_id: int,
        message_queue: object,
        *,
        key_word_reaction_list: str = "",
        memory_list: str = "",
        numbering: MessageNumbering | None = None,
        last_reply_message_id: int | None = None,
        all_new: bool = False,
    ) -> str:
        current_time = get_current_time_and_lunar_date()
        group_id_str = str(group_id)
        group_name = await self._profile_service.get_group_name(group_id_str)
        group_description_map = self._config.chat.group_description or {}
        group_description = group_description_map.get(group_id_str, "")
        archive_fetch_window = getattr(self._config.chat, "archive_fetch_window", None)
        member_list = await self._profile_service.render_group_member_list(
            group_id,
            message_queue,
            archive_fetch_window=archive_fetch_window,
        )
        bot_group_admin_status = await self._profile_service.render_bot_group_admin_status(
            group_id,
            self._config.bot.account,
            message_queue,
        )

        group_admin = await self._profile_service.render_group_owner_text(
            group_id,
            message_queue,
        )

        # 查询群聊档案记忆（table_name='group_profile', key=群号）
        group_profile = await self._fetch_archive("group_profile", group_id_str) or ""
        group_summary = await self._fetch_archive("group_summary", group_id_str) or ""
        group_info = _merge_labeled_prompt_fragments(
            ("群聊档案", group_profile),
            ("近期阶段摘要", group_summary),
        )

        if numbering is not None:
            message_list = numbering.apply(
                message_queue, group_id_str,
                last_reply_message_id=last_reply_message_id,
                all_new=all_new,
            )
            format_example = numbering.format_example()
            message_list = f"{format_example}\n\n{message_list}"
        else:
            message_list = message_queue.to_text(
                group_id_str,
                last_reply_message_id=last_reply_message_id,
                all_new=all_new,
            )

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
            group_admin=group_admin,
            group_info=group_info,
            message_list=message_list,
            member_list=member_list,
            bot_name=self._config.bot.nick_name,
            bot_account=self._config.bot.account,
            other_name=_build_bot_other_name(self._config),
            bot_data=self._config.bot.bot_data,
            key_word_reaction_list=merged_keyword_reaction_list,
            memory_list=memory_list,
        )
        prompt = _merge_prompt_fragments(prompt, bot_group_admin_status)
        if group_admin and "{group_admin}" not in self._config.chat.group_prompt_template:
            prompt = _merge_prompt_fragments(prompt, group_admin)
        if group_info and "{group_info}" not in self._config.chat.group_prompt_template:
            prompt = _merge_prompt_fragments(prompt, group_info)
        if keyword_reaction_text and "{key_word_reaction_list}" not in self._config.chat.group_prompt_template:
            prompt = _merge_prompt_fragments(prompt, keyword_reaction_text)
        adaptive = self._get_adaptive_prompt()
        if adaptive:
            prompt += f"\n<自适应提示词>\n{adaptive}\n</自适应提示词>"
        return prompt

    async def build_friend_chat_prompt(
        self,
        user_id: int,
        message_queue: object,
        *,
        key_word_reaction_list: str = "",
        memory_list: str = "",
        numbering: MessageNumbering | None = None,
        last_reply_message_id: int | None = None,
        all_new: bool = False,
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
            message_list = numbering.apply(
                message_queue, user_id_str,
                last_reply_message_id=last_reply_message_id,
                all_new=all_new,
            )
            format_example = numbering.format_example()
            message_list = f"{format_example}\n\n{message_list}"
        else:
            message_list = message_queue.to_text(
                user_id_str,
                last_reply_message_id=last_reply_message_id,
                all_new=all_new,
            )

        keyword_reaction_text = self._keyword_reaction_builder.build(
            queue=message_queue,
            queue_key=user_id_str,
            conversation_type="private",
        )
        merged_keyword_reaction_list = _merge_prompt_fragments(
            key_word_reaction_list,
            keyword_reaction_text,
        )

        private_summary = await self._fetch_archive("private_summary", user_id_str) or ""
        merged_memory_list = _merge_labeled_prompt_fragments(
            ("既有记忆", memory_list),
            ("近期阶段摘要", private_summary),
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
            memory_list=merged_memory_list,
        )
        if merged_memory_list and "{memory_list}" not in self._config.chat.friend_prompt_template:
            prompt = _merge_prompt_fragments(prompt, merged_memory_list)
        if keyword_reaction_text and "{key_word_reaction_list}" not in self._config.chat.friend_prompt_template:
            prompt = _merge_prompt_fragments(prompt, keyword_reaction_text)
        adaptive = self._get_adaptive_prompt()
        if adaptive:
            prompt += f"\n<自适应提示词>\n{adaptive}\n</自适应提示词>"
        prompt += (
            "\n<私聊提示>"
            "\n这是私聊对话。必须先正常回复对方的消息，回复内容根据聊天内容自然决定。"
            "\n发送回复后，如果对方明显还有更多内容要说，请使用 wait 工具等待新消息进行后续回复（一般等待10秒即可），不要直接结束对话。"
            "\n</私聊提示>"
        )
        return prompt


    async def _fetch_archive(self, table_name: str, key: str) -> str | None:
        if self._archive_memory_service is None:
            return None
        try:
            item = await self._archive_memory_service.get(table_name, key)
        except Exception:
            return None
        if item is not None and item.value:
            return item.value.strip()
        return None


def _build_bot_other_name(config: BotConfigSchema) -> str:
    alias_list = config.bot.alias_name or []
    valid_aliases = [alias.strip() for alias in alias_list if alias.strip()]
    if not valid_aliases:
        return ""
    return ",也有人叫你" + "、".join(valid_aliases)


def _merge_prompt_fragments(*parts: str) -> str:
    cleaned = [part.strip() for part in parts if part and part.strip()]
    return "\n".join(cleaned)


def _merge_labeled_prompt_fragments(*parts: tuple[str, str]) -> str:
    cleaned = [
        f"<{label}>\n{value.strip()}\n</{label}>"
        for label, value in parts
        if value and value.strip()
    ]
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
