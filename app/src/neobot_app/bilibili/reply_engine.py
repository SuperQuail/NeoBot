"""B站回复引擎 — 用一次 LLM 调用生成回复。

不经过 QQ 的 ReplyOrchestrator：B站链路没有常驻会话与工具循环，
每次评论/私信只做「拼提示词 -> 调 provider -> 清理输出」。
记忆档案可选（archive_service / uow_factory），缺失时退化为纯人设回复。
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from neobot_app.bilibili._compat import call_client, get_field
from neobot_app.bilibili.tool_reply import run_tool_reply
from neobot_app.bilibili.prompts import (
    CommentContext,
    CommentNode,
    PrivateMessageContext,
    build_comment_prompt,
    build_private_prompt,
    build_task_prompt,
)
from neobot_app.statistics.tracker import get_usage_tracker
from neobot_app.utils.logger import get_module_logger

logger = get_module_logger("bilibili.reply_engine")

_THINK_RE = re.compile(r"<think\b[^>]*>.*?</think\s*>", re.IGNORECASE | re.DOTALL)
_FENCE = chr(96) * 3
_PREFIX_RE = re.compile(r"^(回复|回答)\s*[:：]\s*")
_SKIP_RE = re.compile(r"^\[?\s*(skip|cancel|跳过|不回复)\s*\]?$", re.IGNORECASE)
_QUOTES = " \t\r\n\"“”'‘’「」『』"
#: 截断时优先落在句读处，避免把半句话发出去。
_SENTENCE_END = "。！？!?.；;，, "
#: 注入提示词的档案内容上限（字符）。
_PROFILE_MEMORY_CHARS = 800
#: 视频增强：只认一条视频，摘要上限 1500 字，取不到就跳过、不阻断回复。
_VIDEO_BV_RE = re.compile(r"BV[0-9A-Za-z]{10}")
_VIDEO_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.|m\.)?bilibili\.com/video/[A-Za-z0-9]+", re.IGNORECASE
)
_VIDEO_CONTEXT_CHARS = 3000
_VIDEO_ENRICH_TIMEOUT_SECONDS = 15.0


#: 模型输出清理：去思考块/markdown/前后缀，超长在句读处截断。
#: 目前只有测试直接调用；等 tool_reply 的输出清理接上它（T2）后由工具层复用。
def clean_reply(text: Any, max_chars: int = 0) -> str:
    """清理模型输出：去思考块/markdown/前后缀，超长在句读处截断。

    返回空字符串表示「不回复」（模型输出 [SKIP] 或清理后为空）。
    """
    value = str(text or "")
    value = _THINK_RE.sub("", value)
    value = value.replace(_FENCE, "")
    value = value.strip()
    value = _PREFIX_RE.sub("", value)
    value = value.strip(_QUOTES)
    value = re.sub(r"\*\*(.+?)\*\*", r"\1", value)
    value = value.strip()
    if not value or _SKIP_RE.match(value):
        return ""
    if max_chars > 0 and len(value) > max_chars:
        head = value[:max_chars]
        cut = max(head.rfind(ch) for ch in _SENTENCE_END)
        if cut < max_chars // 3:
            cut = max_chars
        value = head[:cut].rstrip(_SENTENCE_END + " \t\r\n")
    return value.strip()


class BilibiliReplyEngine:
    """B站评论/私信回复生成器（一次性 LLM 调用）。"""

    def __init__(
        self,
        provider: Any = None,
        *,
        archive_service: Any = None,
        uow_factory: Any = None,
        video_service: Any = None,
        bot_name: str = "",
        bot_uid: int = 0,
        bot_data: str = "",
        other_name: str = "",
        max_comment_chars: int = 200,
        max_private_chars: int = 500,
        max_task_chars: int = 300,
        timeout_seconds: float = 60.0,
        flow_registry: Any = None,
    ) -> None:
        self._provider = provider
        self._archive = archive_service
        self._uow_factory = uow_factory
        self._video_service = video_service
        self._bot_name = bot_name
        self._bot_uid = int(bot_uid or 0)
        self._bot_data = bot_data
        self._other_name = other_name
        self._max_comment_chars = max(0, int(max_comment_chars))
        self._max_private_chars = max(0, int(max_private_chars))
        self._max_task_chars = max(0, int(max_task_chars))
        self._timeout_seconds = float(timeout_seconds)
        self._flow_registry = flow_registry

    @property
    def available(self) -> bool:
        return self._provider is not None

    # ── 对外生成入口 ──

    async def generate_comment_reply(self, ctx: CommentContext) -> str | None:
        """生成评论回复。

        只有模型显式 cancel/[SKIP] 才返回 None；provider 超时/异常向上抛，
        由调用方（评论/私信监控器）回池稍后重试，别把生成失败当成不回复。
        """
        ctx.bot_name = ctx.bot_name or self._bot_name
        ctx.bot_uid = ctx.bot_uid or self._bot_uid
        ctx.bot_data = ctx.bot_data or self._bot_data
        ctx.other_name = ctx.other_name or self._other_name
        await self._enrich_comment(ctx)
        system, user = build_comment_prompt(ctx)
        key = f"bilibili_comment:{ctx.target_oid}"
        return await self._generate(
            system,
            user,
            self._max_comment_chars,
            pipeline_key=key,
            conversation_kind="bilibili_comment",
            conversation_id=str(ctx.target_oid),
        )

    async def generate_private_reply(self, ctx: PrivateMessageContext) -> str | None:
        """生成私信回复；语义同 generate_comment_reply（只有显式 cancel 才 None）。"""
        ctx.bot_name = ctx.bot_name or self._bot_name
        ctx.bot_uid = ctx.bot_uid or self._bot_uid
        ctx.bot_data = ctx.bot_data or self._bot_data
        ctx.other_name = ctx.other_name or self._other_name
        await self._enrich_private(ctx)
        system, user = build_private_prompt(ctx)
        key = f"bilibili_private:{ctx.sender_uid}"
        return await self._generate(
            system,
            user,
            self._max_private_chars,
            pipeline_key=key,
            conversation_kind="bilibili_private",
            conversation_id=str(ctx.sender_uid),
        )

    async def generate_task_reply(
        self, task: str, *, history: str = "", live: bool = False
    ) -> str | None:
        """跨聊天任务：生成一句要发到 B站 的回复；异常同样向上抛。"""
        system, user = build_task_prompt(
            task,
            history=history,
            live=live,
            bot_name=self._bot_name,
            bot_uid=self._bot_uid,
            bot_data=self._bot_data,
            other_name=self._other_name,
        )
        return await self._generate(
            system,
            user,
            self._max_task_chars,
            pipeline_key="bilibili_task",
            conversation_kind="bilibili_task",
            conversation_id="task",
        )

    # ── LLM 调用 ──

    async def _generate(
        self,
        system: str,
        user: str,
        max_chars: int,
        *,
        pipeline_key: str = "",
        conversation_kind: str = "",
        conversation_id: str = "",
    ) -> str | None:
        if self._provider is None:
            return None
        if self._flow_registry is not None and pipeline_key:
            try:
                model = str(getattr(self._provider, "model", "") or "")
                messages = [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ]
                self._flow_registry.record_prompt(
                    pipeline_key,
                    system_prompt=system,
                    model=model,
                    conversation_kind=conversation_kind,
                    conversation_id=conversation_id,
                )
                self._flow_registry.record_request(
                    pipeline_key, messages=messages, model=model, iteration=1
                )
            except Exception:
                pass
        try:
            reply = await run_tool_reply(
                self._provider,
                system,
                user,
                max_chars=max_chars,
                timeout=self._timeout_seconds,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # 按任务间契约：provider 超时/异常要抛给调用方回池重试，
            # 不能返回 None —— 那会被监控器记成「模型不回复」而永久跳过。
            logger.warning(f"B站回复生成失败，本次不记已回复：{type(exc).__name__}: {exc}")
            raise
        try:
            await self._record_usage(
                {"extensions": {"usage": reply.usage or {}}}
            )
        except Exception:
            pass
        return reply.text

    async def _record_usage(self, response: Any) -> None:
        """记录本次调用的 usage；provider 未提供 usage 时也落一条 0 token 记录。"""
        usage = get_field(
            get_field(response, "extensions", {}) or {}, "usage", {}
        )
        if not isinstance(usage, dict):
            usage = {}
        try:
            await get_usage_tracker().record(
                module="bilibili",
                model_name=str(getattr(self._provider, "model", "") or ""),
                registered_key=str(getattr(self._provider, "registered_key", "") or ""),
                input_tokens=int(usage.get("input_tokens", 0) or 0),
                output_tokens=int(usage.get("output_tokens", 0) or 0),
                cache_hit_tokens=int(usage.get("cache_hit_tokens", 0) or 0),
                cache_miss_tokens=int(usage.get("cache_miss_tokens", 0) or 0),
            )
        except Exception as exc:
            logger.debug(f"B站用量记录失败：{type(exc).__name__}: {exc}")

    # ── 记忆档案注入 ──

    async def _enrich_comment(self, ctx: CommentContext) -> None:
        """给评论树里的作者补档案；目标评论作者排在最前。"""
        nodes = _iter_nodes(ctx.comment_tree)
        if ctx.reply_target_rpid:
            nodes.sort(key=lambda n: n.rpid != ctx.reply_target_rpid)
        profiles: list[dict] = []
        seen: set[int] = set()
        for node in nodes[:6]:
            if node.uid in seen:
                continue
            seen.add(node.uid)
            profile = await self._load_profile(node.uid, node.uname)
            if profile is not None:
                profiles.append(profile)
        ctx.commenter_profiles = profiles
        if not ctx.video_context:
            ctx.video_context = await self._load_video_context(
                [node.content for node in nodes]
            )

    async def _enrich_private(self, ctx: PrivateMessageContext) -> None:
        if not ctx.video_context:
            ctx.video_context = await self._load_video_context(
                [ctx.current_message, *(str(msg.get("content", "")) for msg in ctx.history)]
            )
        profile = await self._load_profile(ctx.sender_uid, ctx.sender_name)
        if profile is None:
            return
        ctx.sender_remark = ctx.sender_remark or str(profile.get("remark") or "")
        ctx.sender_profile = ctx.sender_profile or str(profile.get("profile") or "")
        memories = [
            str(profile.get("bilibili_memory") or ""),
            str(profile.get("qq_memory") or ""),
        ]
        joined = "；".join(m for m in memories if m)
        ctx.memory_list = ctx.memory_list or joined

    async def _load_video_context(self, texts: list[str]) -> str:
        """正文/评论树里最多找一条BV号或视频链接，取标题+来源+摘要；失败留空。"""
        if self._video_service is None:
            return ""
        identifier = _find_video_identifier(texts)
        if not identifier:
            return ""
        try:
            result = await asyncio.wait_for(
                call_client(
                    self._video_service.watch,
                    identifier,
                    max_chars=_VIDEO_CONTEXT_CHARS,
                    include_comments=0,
                ),
                timeout=_VIDEO_ENRICH_TIMEOUT_SECONDS,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug(f"B站视频上下文获取失败（{identifier}）：{type(exc).__name__}: {exc}")
            return ""
        if not isinstance(result, dict) or not bool(get_field(result, "ok", True)):
            return ""
        title = str(get_field(result, "title", "") or "").strip()
        source = str(get_field(result, "source", "") or "").strip()
        transcript = str(get_field(result, "transcript", "") or "").strip()
        if not (title or transcript):
            return ""
        lines = []
        if title:
            lines.append(f"标题：{title}")
        if source:
            lines.append(f"来源：{source}")
        if transcript:
            lines.append(f"摘要：{transcript[:_VIDEO_CONTEXT_CHARS]}")
        url = str(get_field(result, "url", "") or "").strip()
        if url:
            lines.append(f"链接：{url}")
        return "\n".join(lines)

    async def _load_profile(self, uid: int, uname: str) -> dict | None:
        """读 B站记忆 + 账号关联到的 QQ 档案，合成一份评论者档案。"""
        if not uid:
            return None
        data: dict[str, Any] = {"uname": uname, "uid": uid}
        bili_memory = await self._archive_get("bilibili_user", str(uid))
        if bili_memory:
            data["bilibili_memory"] = bili_memory[:_PROFILE_MEMORY_CHARS]
        qq_number = await self._linked_qq(uid)
        if qq_number:
            user_data = await self._load_user_data(qq_number)
            if user_data is not None:
                remark = str(get_field(user_data, "remark", "") or "").strip()
                profile = str(get_field(user_data, "profile", "") or "").strip()
                gender = str(get_field(user_data, "known_gender", "") or "").strip()
                if remark:
                    data["remark"] = remark
                if profile:
                    data["profile"] = profile[:_PROFILE_MEMORY_CHARS]
                if gender:
                    data["known_gender"] = gender
            qq_memory = await self._archive_get("user_summary", qq_number)
            if not qq_memory:
                qq_memory = await self._archive_get("user_profile", qq_number)
            if qq_memory:
                data["qq_memory"] = qq_memory[:_PROFILE_MEMORY_CHARS]
        return data if len(data) > 2 else None

    async def _archive_get(self, table: str, key: str) -> str:
        if self._archive is None:
            return ""
        try:
            item = await call_client(self._archive.get, table, key)
        except Exception as exc:
            logger.debug(f"读取B站档案失败（{table}:{key}）：{type(exc).__name__}: {exc}")
            return ""
        return str(get_field(item, "value", "") or "").strip()

    async def _linked_qq(self, bilibili_uid: int) -> str:
        if self._uow_factory is None:
            return ""
        try:
            async with self._uow_factory() as uow:
                repo = getattr(uow, "bilibili_links", None)
                if repo is None:
                    return ""
                links = await call_client(repo.find_by_uid, bilibili_uid)
        except Exception as exc:
            logger.debug(f"查询B站-QQ关联失败（uid={bilibili_uid}）：{type(exc).__name__}: {exc}")
            return ""
        for link in links or []:
            qq_number = str(get_field(link, "qq_number", "") or "").strip()
            if qq_number:
                return qq_number
        return ""

    async def _load_user_data(self, qq_number: str) -> Any:
        if self._uow_factory is None:
            return None
        try:
            async with self._uow_factory() as uow:
                profiles = getattr(uow, "profiles", None)
                if profiles is None:
                    return None
                return await call_client(profiles.get_user, qq_number)
        except Exception as exc:
            logger.debug(f"读取QQ用户资料失败（qq={qq_number}）：{type(exc).__name__}: {exc}")
            return None


def _find_video_identifier(texts: list[str]) -> str:
    for text in texts:
        match = _VIDEO_BV_RE.search(text or "")
        if match:
            return match.group(0)
    for text in texts:
        match = _VIDEO_URL_RE.search(text or "")
        if match:
            return match.group(0)
    return ""


def _iter_nodes(nodes: list[CommentNode]) -> list[CommentNode]:
    result: list[CommentNode] = []
    for node in nodes:
        result.append(node)
        if node.children:
            result.extend(_iter_nodes(node.children))
    return result
