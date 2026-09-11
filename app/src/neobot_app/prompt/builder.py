"""从消息队列与已保存的用户资料信息组装提示词。

架构(贴近 agent 的消息形态):
- system 提示词只承载稳定内容:人设 + 回复规则 + 群/好友元信息 + 编号格式;
- 聊天记录按发送者拆分为真实的 user/assistant 消息(bot 自己的发言是 assistant);
- 每轮会变的上下文(群友信息、对方档案、印象)渲染成独立的 user 块追加在 system 之后;
- 调用模型前再追加一个独立的 <当前时间> user 块。

所有文本都来自 prompts.toml 分区模板,占位符与转义规则见
templates/prompts.toml 顶部说明与 store.py 模块文档。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.config.schemas.bot import BotConfig as BotConfigSchema
from neobot_app.prompt.keyword_reaction import KeywordReactionBuilder
from neobot_app.prompt.render import render_template, template_placeholders
from neobot_app.prompt.role_messages import build_role_messages
from neobot_app.prompt.store import PromptStore, get_template_value
from neobot_app.time_context import get_current_time_values
from neobot_app.user_profiles import UserProfileService

if TYPE_CHECKING:
    from neobot_app.message.numbering import MessageNumbering

# 已在 system 模板中渲染过的内容,不再重复出现在上下文 user 块中
_DEDUP_KEYS_GROUP = (
    "member_list",
    "key_word_reaction_list",
    "memory_list",
    "group_info",
    "group_admin",
    "bot_group_admin_status",
)
_DEDUP_KEYS_FRIEND = (
    "profile",
    "friend_info",
    "key_word_reaction_list",
    "memory_list",
)


class PromptBuilder:
    """从消息队列与已保存的用户资料信息组装提示词。"""

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

    def _template(self, key: str, sub: str = "template") -> str:
        """读取分区模板:文件(自定义覆盖默认) -> 内置兜底。"""
        return get_template_value(self._store, key, sub)

    def _section_enabled(self, key: str, default: bool = True) -> bool:
        """分区是否启用(分区内 enabled = false 可关闭该区块)。"""
        if self._store is None:
            return default
        return self._store.enabled(key, default=default)

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

    def _time_values(self) -> dict[str, str]:
        return dict(get_current_time_values())

    # ── 当前时间块(调用模型前追加的独立 user 块) ──

    def build_current_time_message(self) -> dict[str, str] | None:
        """渲染 <当前时间> user 块;分区关闭或内容为空时返回 None。

        调用方在每次调用模型前追加一次,并保留历史时间块(不做清理),
        模型因此能看到时间推进。
        """
        if not self._section_enabled("current_time"):
            return None
        template = self._template("current_time")
        text = render_template(template, self._time_values())
        if not text:
            return None
        return {"role": "user", "content": text}

    # ── 群聊 ──

    async def _group_context_values(
        self,
        group_id: int,
        message_queue: object,
        *,
        key_word_reaction_list: str = "",
        memory_list: str = "",
    ) -> dict[str, Any]:
        """计算群聊 system / 上下文块共用的占位符取值。"""
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
        group_info = (
            await self._fetch_group_memory(group_id_str) or ""
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
        return {
            "group_id": group_id_str,
            "group_name": group_name or "",
            "group_description": group_description,
            "group_admin": group_admin or "",
            "group_info": group_info,
            "bot_group_admin_status": bot_group_admin_status or "",
            "member_list": member_list or "",
            "key_word_reaction_list": merged_keyword_reaction_list,
            "memory_list": memory_list or "",
            "bot_name": self._config.bot.nick_name,
            "bot_account": self._config.bot.account,
            "other_name": _build_bot_other_name(self._config),
            "bot_data": self._config.bot.bot_data,
        }

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
        context_blocks: list[dict[str, str]] | None = None,
    ) -> str:
        """构建群聊 system 提示词。

        context_blocks 非 None 时,把本轮上下文(群友信息/印象等)渲染成 user 块
        追加进该列表,由调用方插到 system 之后、聊天记录之前。
        """
        values = await self._group_context_values(
            group_id,
            message_queue,
            key_word_reaction_list=key_word_reaction_list,
            memory_list=memory_list,
        )
        values.update(self._time_values())
        values["numbering_guide"] = _build_numbering_guide(numbering)

        template = self._template("group_chat")
        prompt = render_template(template, values)

        # 编号格式是给模型的固定约定,不属于用户上下文;模板漏写时补回 system
        if (
            numbering is not None
            and "numbering_guide" not in template_placeholders(template)
            and values["numbering_guide"]
        ):
            prompt = _merge_prompt_fragments(
                prompt,
                f"<消息编号说明>\n{values['numbering_guide']}\n</消息编号说明>",
            )

        if context_blocks is not None and self._section_enabled("group_context"):
            block = render_template(
                self._template("group_context"),
                self._context_values(template, values, _DEDUP_KEYS_GROUP),
            )
            if block:
                context_blocks.append({"role": "user", "content": block})

        return self._append_adaptive(prompt)

    def _context_values(
        self,
        system_template: str,
        values: dict[str, Any],
        dedup_keys: tuple[str, ...],
    ) -> dict[str, Any]:
        """生成上下文块取值:system 模板已消费的内容置空,避免重复。"""
        consumed = template_placeholders(system_template)
        context_values = dict(values)
        for key in dedup_keys:
            if key in consumed:
                context_values[key] = ""
        return context_values

    # ── 私聊 ──

    async def _friend_context_values(
        self,
        user_id: int,
        message_queue: object,
        *,
        key_word_reaction_list: str = "",
        memory_list: str = "",
    ) -> dict[str, Any]:
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
        return {
            "friend_name": friend_name,
            "remark": remark,
            "profile": getattr(profile, "profile", None) or "",
            "friend_info": friend_info or "",
            "key_word_reaction_list": _merge_prompt_fragments(
                key_word_reaction_list,
                keyword_reaction_text,
            ),
            "memory_list": memory_list or "",
            "bot_name": self._config.bot.nick_name,
            "bot_account": self._config.bot.account,
            "other_name": _build_bot_other_name(self._config),
            "bot_data": self._config.bot.bot_data,
        }

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
        context_blocks: list[dict[str, str]] | None = None,
    ) -> str:
        """构建私聊 system 提示词;context_blocks 语义同群聊。"""
        values = await self._friend_context_values(
            user_id,
            message_queue,
            key_word_reaction_list=key_word_reaction_list,
            memory_list=memory_list,
        )
        values.update(self._time_values())
        values["numbering_guide"] = _build_numbering_guide(numbering)

        template = self._template("friend_chat")
        prompt = render_template(template, values)

        if (
            numbering is not None
            and "numbering_guide" not in template_placeholders(template)
            and values["numbering_guide"]
        ):
            prompt = _merge_prompt_fragments(
                prompt,
                f"<消息编号说明>\n{values['numbering_guide']}\n</消息编号说明>",
            )

        if context_blocks is not None and self._section_enabled("friend_context"):
            block = render_template(
                self._template("friend_context"),
                self._context_values(template, values, _DEDUP_KEYS_FRIEND),
            )
            if block:
                context_blocks.append({"role": "user", "content": block})

        # 私聊专属提示:独立分区,可用 enabled = false 关闭
        if self._section_enabled("friend_chat_hint"):
            hint = render_template(self._template("friend_chat_hint"), values)
            if hint:
                prompt = _merge_prompt_fragments(prompt, hint)

        return self._append_adaptive(prompt)

    # ── 聊天记录 ──

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

    # ── 新出现的群友档案 ──

    def build_new_member_profiles_text(
        self,
        member_profiles: str,
        *,
        group_name: str = "",
        group_id: str = "",
    ) -> str:
        """把群友档案渲染成 [new_member_profiles] 模板文本(空内容返回空串)。"""
        if not member_profiles or not member_profiles.strip():
            return ""
        return render_template(
            self._template("new_member_profiles"),
            {
                "member_profiles": member_profiles,
                "group_name": group_name,
                "group_id": group_id,
            },
        )

    def build_group_chat_resume_text(
        self,
        *,
        new_member_profiles: str = "",
        current_time: str = "",
    ) -> str:
        """渲染群聊挂起恢复说明文本。"""
        values = self._time_values()
        if current_time:
            values["current_time"] = current_time
        values["new_member_profiles"] = new_member_profiles
        return render_template(self._template("group_chat_resume"), values)

    # ── 自适应提示词 ──

    def _append_adaptive(self, prompt: str) -> str:
        adaptive = self._get_adaptive_prompt()
        if adaptive:
            prompt += f"\n<自适应提示词>\n{adaptive}\n</自适应提示词>"
        return prompt

    # ── 群聊记忆 ──

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
        """群聊是否注入群员个人档案;默认 False,群员档案由 agent 按需读取。"""
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
