"""从消息队列与已保存的用户资料信息收集提示词取值。

取值（群友信息、印象、档案、时间…）在本模块；**块的顺序与启停**在注册表
``prompt/blocks.py``，拼装由 ``prompt/composer.py`` 完成。新增提示词块不需要
改本模块，除非块需要新的占位符取值。

架构(贴近 agent 的消息形态):
- system 提示词只承载稳定内容:人设 + 回复规则 + 群/好友元信息 + 编号格式;
- 聊天记录按发送者拆分为真实的 user/assistant 消息(bot 自己的发言是 assistant);
- 每轮会变的上下文(群友信息、对方档案、印象)渲染成独立的 user 块追加在 system 之后;
- 调用模型前再追加一个独立的 <当前时间> user 块。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.config.schemas.bot import BotConfig as BotConfigSchema
from neobot_app.prompt.composer import PromptComposer, make_context
from neobot_app.prompt.context import Scope
from neobot_app.prompt.keyword_reaction import KeywordReactionBuilder
from neobot_app.prompt.render import render_template
from neobot_app.prompt.role_messages import build_role_messages
from neobot_app.prompt.store import PromptStore, get_template_value
from neobot_app.time_context import get_current_time_values
from neobot_app.user_profiles import UserProfileService

if TYPE_CHECKING:
    from neobot_app.message.numbering import MessageNumbering


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
        self._composer = PromptComposer(prompt_store, logger=self._logger)
        self._keyword_reaction_builder = KeywordReactionBuilder(
            config.chat.key_word or [],
            logger=self._logger,
            prompt_store=prompt_store,
        )
        self._adaptive_prompt_path = adaptive_prompt_path
        self._adaptive_prompt_cache: str | None = None
        self._adaptive_prompt_mtime: float | None = None

    # ── 模板读取 ──

    def _template(self, key: str, sub: str = "template") -> str:
        """读取分区模板：统一走 assets（custom → 内置 → 兜底），未注册分区退回 store。"""
        from neobot_app.prompt.assets import raw_text

        try:
            return raw_text(key, sub, store=self._store)
        except KeyError:
            return get_template_value(self._store, key, sub)

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

    # ── 构建上下文 ──

    def _make_ctx(
        self,
        *,
        scope: Scope,
        values: dict[str, Any] | None = None,
        dynamic: dict[str, Any] | None = None,
    ):
        """构造一次构建的 PromptContext（统一读取 config/store/logger）。"""
        return make_context(
            config=self._config,
            store=self._store,
            scope=scope,
            values=values if values is not None else self._time_values(),
            dynamic=dynamic,
            logger=self._logger,
        )

    # ── 运行时 user 块（时间 / 提醒 / 等待指引） ──

    def build_current_time_message(self) -> dict[str, str] | None:
        """渲染完整 <当前时间> user 块;分区关闭或内容为空时返回 None。

        调用方在每次调用模型前追加一次,并保留历史时间块(不做清理),
        模型因此能看到时间推进。
        """
        ctx = self._make_ctx(scope=Scope.GROUP, dynamic={"time_variant": "full"})
        return self._composer.build_user_block("current_time", ctx)

    def build_short_time_message(self) -> dict[str, str] | None:
        """渲染短时间戳 user 块(仅 YYYY-MM-DD HH:MM:SS);分区关闭或为空时返回 None。

        同一轮管线激活里的第一次模型调用用完整 [current_time],之后的调用由调用方
        改用本方法,避免长管线反复渲染整段时间描述。
        """
        ctx = self._make_ctx(scope=Scope.GROUP, dynamic={"time_variant": "short"})
        return self._composer.build_user_block("current_time_short", ctx)

    def build_avoid_repeat_message(self) -> dict[str, str] | None:
        """渲染防重复提醒 user 块（每次管线激活追加一次）。"""
        ctx = self._make_ctx(scope=Scope.GROUP)
        return self._composer.build_user_block("avoid_repeat", ctx)

    def build_at_mention_wait_message(self) -> dict[str, str] | None:
        """渲染「被 @ 但没说清要做什么」的等待指引 user 块（仅群聊）。"""
        ctx = self._make_ctx(scope=Scope.GROUP, dynamic={"at_mention_wait": True})
        return self._composer.build_user_block("at_mention_wait", ctx)

    # ── 群聊 ──

    def _bot_account_value(self, override: int | None) -> int:
        """提示词里的机器人 QQ 号：事件账号优先（双待模式每通道不同），否则配置值。"""
        return int(override) if override else int(getattr(self._config.bot, "account", 0) or 0)

    async def _group_context_values(
        self,
        group_id: int,
        message_queue: object,
        *,
        key_word_reaction_list: str = "",
        memory_list: str = "",
        bot_account: int | None = None,
    ) -> dict[str, Any]:
        """计算群聊 system / 上下文块共用的占位符取值。"""
        group_id_str = str(group_id)
        account = self._bot_account_value(bot_account)
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
            member_list = f"{member_list}\n{self.member_archive_hint()}"
        bot_group_admin_status = await self._profile_service.render_bot_group_admin_status(
            group_id,
            account,
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
            "bot_account": account,
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
        bot_account: int | None = None,
    ) -> str:
        """构建群聊 system 提示词。

        context_blocks 非 None 时,把本轮上下文(群友信息/印象等)渲染成 user 块
        追加进该列表,由调用方插到 system 之后、聊天记录之前。
        每轮变化的 system 块（@ 提示 / agent 技能说明 / 原生视觉）由编排器另行
        append；本方法只构建稳定 system。
        """
        values = await self._group_context_values(
            group_id,
            message_queue,
            key_word_reaction_list=key_word_reaction_list,
            memory_list=memory_list,
            bot_account=bot_account,
        )
        values.update(self._time_values())
        values["numbering_guide"] = _build_numbering_guide(numbering)

        ctx = self._make_ctx(
            scope=Scope.GROUP,
            values=values,
            dynamic={"adaptive_text": self._adaptive_block()},
        )
        system = self._composer.build_system(ctx)
        if context_blocks is not None:
            context_blocks.extend(self._composer.build_context_messages(ctx, system))
        return system.text

    # ── 私聊 ──

    async def _friend_context_values(
        self,
        user_id: int,
        message_queue: object,
        *,
        key_word_reaction_list: str = "",
        memory_list: str = "",
        bot_account: int | None = None,
    ) -> dict[str, Any]:
        user_id_str = str(user_id)
        account = self._bot_account_value(bot_account)
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
            "bot_account": account,
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
        bot_account: int | None = None,
    ) -> str:
        """构建私聊 system 提示词;context_blocks 语义同群聊。"""
        values = await self._friend_context_values(
            user_id,
            message_queue,
            key_word_reaction_list=key_word_reaction_list,
            memory_list=memory_list,
            bot_account=bot_account,
        )
        values.update(self._time_values())
        values["numbering_guide"] = _build_numbering_guide(numbering)

        ctx = self._make_ctx(
            scope=Scope.PRIVATE,
            values=values,
            dynamic={"adaptive_text": self._adaptive_block()},
        )
        system = self._composer.build_system(ctx)
        if context_blocks is not None:
            context_blocks.extend(self._composer.build_context_messages(ctx, system))
        return system.text

    # ── 聊天记录 ──

    async def build_group_chat_messages(
        self,
        group_id: int,
        message_queue: object,
        *,
        numbering: MessageNumbering | None = None,
        last_reply_message_id: int | None = None,
        all_new: bool = False,
        bot_account: int | None = None,
    ) -> list[dict[str, str]]:
        """群聊聊天记录 -> 角色消息列表(user/assistant)。"""
        return build_role_messages(
            message_queue,
            str(group_id),
            numbering=numbering,
            bot_account=self._bot_account_value(bot_account),
            include_boundary_markers=self._show_boundary_markers(),
            last_reply_message_id=last_reply_message_id,
            all_new=all_new,
            prompt_store=self._store,
        )

    async def build_friend_chat_messages(
        self,
        user_id: int,
        message_queue: object,
        *,
        numbering: MessageNumbering | None = None,
        last_reply_message_id: int | None = None,
        all_new: bool = False,
        bot_account: int | None = None,
    ) -> list[dict[str, str]]:
        """私聊聊天记录 -> 角色消息列表(user/assistant)。"""
        return build_role_messages(
            message_queue,
            str(user_id),
            numbering=numbering,
            bot_account=self._bot_account_value(bot_account),
            include_boundary_markers=self._show_boundary_markers(),
            last_reply_message_id=last_reply_message_id,
            all_new=all_new,
            prompt_store=self._store,
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

    def member_archive_hint(self) -> str:
        """群员档案未注入时给模型的按需读取提示（增量新成员块复用）。"""
        return self._template("member_archive_hint")

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

    def _adaptive_block(self) -> str:
        """自适应提示词块内容（``data/自适应提示词.txt``）；无内容时块自动跳过。"""
        adaptive = self._get_adaptive_prompt()
        if not adaptive:
            return ""
        return f"<自适应提示词>\n{adaptive}\n</自适应提示词>"

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
