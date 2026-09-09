from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.config.schemas.bot import BotConfig as BotConfigSchema
from neobot_app.prompt.keyword_reaction import KeywordReactionBuilder
from neobot_app.prompt.role_messages import build_role_messages
from neobot_app.prompt.store import PromptStore, fallback_template
from neobot_app.user_profiles import UserProfileService
from neobot_app.time_context import get_current_time_and_lunar_date
from neobot_app.utils.formater import safe_format

if TYPE_CHECKING:
    from neobot_app.message.numbering import MessageNumbering


class PromptBuilder:
    """从消息队列与已保存的用户资料信息组装提示词。

    新架构(角色拆分):
    - system 提示词:人设 + 回复规则 + 动态上下文(时间/群信息/成员/记忆等),
      不再包含聊天记录本身;
    - 聊天记录:由 build_group_chat_messages / build_friend_chat_messages 按
      发送者拆分为真实的 user/assistant 消息(bot 自己的回复为 assistant)。
    """

    def __init__(
        self,
        config: BotConfigSchema,
        profile_service: UserProfileService,
        logger: Logger | None = None,
        archive_memory_service: Any | None = None,
        adaptive_prompt_path: Path | None = None,
        uow_factory: Any = None,
        prompt_store: PromptStore | None = None,
    ) -> None:
        self._config = config
        self._profile_service = profile_service
        self._logger = logger or NullLogger()
        self._archive_memory_service = archive_memory_service
        self._uow_factory = uow_factory
        self._store = prompt_store
        self._keyword_reaction_builder = KeywordReactionBuilder(
            config.chat.key_word or [],
            logger=self._logger,
        )
        self._adaptive_prompt_path = adaptive_prompt_path
        self._adaptive_prompt_cache: str | None = None
        self._adaptive_prompt_mtime: float | None = None

    # ── 模板读取 ──

    def _template(self, key: str) -> str:
        if self._store is not None:
            return self._store.template(key, default=fallback_template(key))
        return fallback_template(key)

    def _show_boundary_markers(self) -> bool:
        return bool(
            getattr(getattr(self._config, "chat", None), "show_last_reply_markers", False)
        )

    def _get_adaptive_prompt(self) -> str:
        """读取自适应提示词内容（带 mtime 缓存,ns 精度）。"""
        if self._adaptive_prompt_path is None:
            return ""
        try:
            path = self._adaptive_prompt_path
            if not path.is_file():
                return ""
            mtime_ns = path.stat().st_mtime_ns
            if self._adaptive_prompt_cache is not None and self._adaptive_prompt_mtime == mtime_ns:
                return self._adaptive_prompt_cache
            content = path.read_text("utf-8-sig").strip()
            self._adaptive_prompt_cache = content
            self._adaptive_prompt_mtime = mtime_ns
            return content
        except Exception:
            return ""

    # ── 群聊 system 提示词 ──

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
        inject_member_archives = self._inject_member_archives()
        member_list = await self._profile_service.render_group_member_list(
            group_id,
            message_queue,
            archive_fetch_window=archive_fetch_window,
            include_archives=inject_member_archives,
        )
        if member_list and not inject_member_archives:
            member_list = f"{member_list}\n{_MEMBER_ARCHIVE_HINT}"
        bot_group_admin_status = await self._profile_service.render_bot_group_admin_status(
            group_id,
            self._config.bot.account,
            message_queue,
        )

        group_admin = await self._profile_service.render_group_owner_text(
            group_id,
            message_queue,
        )

        group_info = _merge_labeled_prompt_fragments(
            ("群聊档案", await self._fetch_group_memory(group_id_str) or ""),
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

        template = self._template("group_chat")
        prompt = safe_format(
            template,
            current_time=current_time,
            group_name=group_name,
            group_id=group_id,
            group_description=group_description,
            group_admin=group_admin,
            group_info=group_info,
            member_list=member_list,
            bot_name=self._config.bot.nick_name,
            bot_account=self._config.bot.account,
            other_name=_build_bot_other_name(self._config),
            bot_data=self._config.bot.bot_data,
            key_word_reaction_list=merged_keyword_reaction_list,
            memory_list=memory_list,
            numbering_guide=_build_numbering_guide(numbering),
        )
        if group_admin and "{group_admin}" not in template:
            prompt = _merge_prompt_fragments(prompt, group_admin)
        if bot_group_admin_status and "{bot_group_admin_status}" not in template:
            prompt = _merge_prompt_fragments(prompt, bot_group_admin_status)
        if group_info and "{group_info}" not in template:
            prompt = _merge_prompt_fragments(prompt, group_info)
        if keyword_reaction_text and "{key_word_reaction_list}" not in template:
            prompt = _merge_prompt_fragments(prompt, keyword_reaction_text)
        if memory_list and "{memory_list}" not in template:
            prompt = _merge_prompt_fragments(prompt, memory_list)
        if numbering is not None and "{numbering_guide}" not in template:
            prompt = _merge_prompt_fragments(
                prompt,
                f"<消息编号说明>\n{_build_numbering_guide(numbering)}\n</消息编号说明>",
            )
        elif numbering is None:
            prompt = _strip_empty_numbering_guide(prompt)
        adaptive = self._get_adaptive_prompt()
        if adaptive:
            prompt += f"\n<自适应提示词>\n{adaptive}\n</自适应提示词>"
        return prompt

    async def build_group_chat_messages(
        self,
        group_id: int,
        message_queue: object,
        *,
        numbering: MessageNumbering | None = None,
        last_reply_message_id: int | None = None,
        all_new: bool = False,
    ) -> list[dict[str, str]]:
        """群聊聊天记录 -> 角色消息列表(user/assistant)。"""
        return build_role_messages(
            message_queue,
            str(group_id),
            numbering=numbering,
            bot_account=self._config.bot.account or 0,
            include_boundary_markers=self._show_boundary_markers(),
            last_reply_message_id=last_reply_message_id,
            all_new=all_new,
        )

    # ── 私聊 system 提示词 ──

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

        keyword_reaction_text = self._keyword_reaction_builder.build(
            queue=message_queue,
            queue_key=user_id_str,
            conversation_type="private",
        )
        merged_keyword_reaction_list = _merge_prompt_fragments(
            key_word_reaction_list,
            keyword_reaction_text,
        )

        merged_memory_list = _merge_labeled_prompt_fragments(
            ("既有记忆", memory_list),
        )

        template = self._template("friend_chat")
        prompt = safe_format(
            template,
            current_time=current_time,
            friend_name=friend_name,
            remark=remark,
            profile=getattr(profile, "profile", None) or "",
            friend_info=friend_info,
            bot_name=self._config.bot.nick_name,
            bot_account=self._config.bot.account,
            other_name=_build_bot_other_name(self._config),
            bot_data=self._config.bot.bot_data,
            key_word_reaction_list=merged_keyword_reaction_list,
            memory_list=merged_memory_list,
            numbering_guide=_build_numbering_guide(numbering),
        )
        if merged_memory_list and "{memory_list}" not in template:
            prompt = _merge_prompt_fragments(prompt, merged_memory_list)
        if keyword_reaction_text and "{key_word_reaction_list}" not in template:
            prompt = _merge_prompt_fragments(prompt, keyword_reaction_text)
        if numbering is not None and "{numbering_guide}" not in template:
            prompt = _merge_prompt_fragments(
                prompt,
                f"<消息编号说明>\n{_build_numbering_guide(numbering)}\n</消息编号说明>",
            )
        elif numbering is None:
            prompt = _strip_empty_numbering_guide(prompt)
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

    async def build_friend_chat_messages(
        self,
        user_id: int,
        message_queue: object,
        *,
        numbering: MessageNumbering | None = None,
        last_reply_message_id: int | None = None,
        all_new: bool = False,
    ) -> list[dict[str, str]]:
        """私聊聊天记录 -> 角色消息列表(user/assistant)。"""
        return build_role_messages(
            message_queue,
            str(user_id),
            numbering=numbering,
            bot_account=self._config.bot.account or 0,
            include_boundary_markers=self._show_boundary_markers(),
            last_reply_message_id=last_reply_message_id,
            all_new=all_new,
        )

    async def _fetch_group_memory(self, group_id_str: str) -> str | None:
        """读群聊记忆:优先受限 summary(group_summary),回退全量档案(group_profile)。

        超长时截取开头部分(总体总结在前)并附分页查阅引导;完整内容
        由模型用 archive_crud__read_archive 的 offset 参数按页读取。
        """
        return await self._fetch_archive_prefer_summary(
            summary_table="group_summary",
            full_table="group_profile",
            key=group_id_str,
            limit=self._group_profile_max_chars(),
        )

    async def _fetch_archive_prefer_summary(
        self,
        *,
        summary_table: str,
        full_table: str,
        key: str,
        limit: int,
    ) -> str | None:
        if self._archive_memory_service is None:
            return None
        for table in (summary_table, full_table):
            try:
                item = await self._archive_memory_service.get(table, key)
            except Exception:
                item = None
            if item is not None and item.value:
                value = item.value.strip()
                if limit > 0 and len(value) > limit:
                    head = value[:limit]
                    return (
                        f"[记忆较长(共{len(value)}字),以下为开头部分]\n"
                        f"{head}\n"
                        "[完整记忆用 archive_crud__read_archive 按需读取:"
                        "先 mode='outline' 看大纲,再 offset 分页读正文;"
                        "offset 为负数时从尾部向前翻页(越后的内容越新)]"
                    )
                return value
        return None

    def _inject_member_archives(self) -> bool:
        """群聊是否注入群员个人档案；默认 False，群员档案由 agent 按需读取。"""
        return bool(
            getattr(
                getattr(self._config, "chat", None),
                "inject_member_archives",
                False,
            )
        )

    def _group_profile_max_chars(self) -> int:
        archive = getattr(
            getattr(getattr(self._config, "agent", None), "memory", None),
            "archive",
            None,
        )
        if archive is not None:
            limit = getattr(archive, "group_profile_max_chars", None)
            if isinstance(limit, int) and limit > 0:
                return limit
        return 1500


_MEMBER_ARCHIVE_HINT = (
    "<群友记忆>群友的长期记忆未在此注入。需要某位群友的记忆时，用 "
    "archive_crud__read_archive 按需读取：table_name 优先 user_summary、缺失时用 user_profile，"
    "key 为该群友的 QQ 号；先 mode='outline' 看大纲，再用 offset 分页读正文，"
    "offset 为负数时从尾部向前翻页（越靠后的内容越新）。</群友记忆>"
)


def _build_bot_other_name(config: BotConfigSchema) -> str:
    alias_list = config.bot.alias_name or []
    valid_aliases = [alias.strip() for alias in alias_list if alias.strip()]
    if not valid_aliases:
        return ""
    return ",也有人叫你" + "、".join(valid_aliases)


def _build_numbering_guide(numbering: MessageNumbering | None) -> str:
    """构建消息编号说明(格式说明;message_id 已直接标注在每条消息行首)。"""
    if numbering is None:
        return ""
    return numbering.format_example()


def _strip_empty_numbering_guide(prompt: str) -> str:
    """无编号时移除模板中空的 <消息编号说明> 区块。"""
    import re

    return re.sub(r"\n?<消息编号说明>\s*</消息编号说明>", "", prompt)


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
    prompt_store: PromptStore | None = None,
) -> str:
    builder = PromptBuilder(
        config, profile_service, logger=logger, prompt_store=prompt_store
    )
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
    prompt_store: PromptStore | None = None,
) -> str:
    builder = PromptBuilder(
        config, profile_service, logger=logger, prompt_store=prompt_store
    )
    return await builder.build_friend_chat_prompt(
        user_id,
        message_queue,
        key_word_reaction_list=key_word_reaction_list,
        memory_list=memory_list,
    )
