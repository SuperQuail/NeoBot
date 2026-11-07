"""B站交互提示词 — 评论回复 / 私信回复 / 跨聊天任务 / 动态日记。

与 QQ 提示词完全独立：B站是公开评论区（短评、楼中楼）+ 一对一的私信，
没有 QQ 群聊语境，因此不套用 QQ 模板。本模块只负责拼装文本，
调用 LLM、记忆档案读取与发送都在 reply_engine / monitors 里。

提示词文本统一在 ``prompt/templates/prompts.toml`` 的 ``bili_*`` 分区（纯数据），
本模块只做加载与组装；builder 可传 ``prompt_store``，让 custom 覆盖生效。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from neobot_app.prompt.assets import raw_text as _asset_raw
from neobot_app.prompt.render import render_template
from neobot_app.time_context import get_current_time_values

# ── 提示词数据 ──


def _text(section: str, key: str = "template", store: Any = None) -> str:
    """读取一个 B 站提示词块（全局注册为 bili_* 分区，由 assets 统一解析）。"""
    return _asset_raw(f"bili_{section}", key, store=store, strip=False)


#: B站场景的通用风格规则（评论与私信共用）。
#: B站独立维护说话方式，不跟随 QQ 的 [human_feel]（场景/边界不同，避免互相污染）。
def _style_rules(store: Any = None) -> str:
    return "\n".join(
        [
            _text("reply_requirements", store=store),
            _text("human_feel", store=store),
            _text("reply_tool_rule", store=store),
            _text("data_rule", store=store),
        ]
    )


def _data(text: Any) -> str:
    """把外部文本当纯数据处理：尖括号转全角，避免伪造标签越权。"""
    return str(text or "").replace("<", "＜").replace(">", "＞")


# ── 数据模型 ──


@dataclass
class CommentNode:
    """评论树节点。"""

    rpid: int
    uid: int
    uname: str
    content: str
    ctime: int = 0
    children: list["CommentNode"] = field(default_factory=list)
    up_replied: bool = False


@dataclass
class CommentContext:
    """评论回复上下文。"""

    bot_name: str = ""
    bot_uid: int = 0
    bot_data: str = ""
    other_name: str = ""
    target_oid: int = 0
    target_type: str = "视频"
    business_id: int = 1
    target_title: str = ""
    target_url: str = ""
    target_up_name: str = ""
    target_desc: str = ""
    comment_tree: list[CommentNode] = field(default_factory=list)
    reply_target_rpid: int = 0
    reply_root_rpid: int = 0
    #: 评论者档案（由 reply_engine 从记忆档案/账号关联里补），每人一条 dict。
    commenter_profiles: list[dict] = field(default_factory=list)
    #: 注入到提示词的额外记忆文本。
    memory: str = ""
    #: 正文/评论树里出现的视频摘要（由 reply_engine 拉取，失败留空）。
    video_context: str = ""
    current_time: datetime | None = None


@dataclass
class PrivateMessageContext:
    """私信回复上下文。"""

    bot_name: str = ""
    bot_uid: int = 0
    bot_data: str = ""
    other_name: str = ""
    sender_name: str = ""
    sender_uid: int = 0
    sender_remark: str = ""
    sender_profile: str = ""
    memory_list: str = ""
    history: list[dict] = field(default_factory=list)
    current_message: str = ""
    #: 正文/历史里出现的视频摘要（由 reply_engine 拉取，失败留空）。
    video_context: str = ""
    current_time: datetime | None = None


# ── 对外入口 ──


def build_comment_prompt(
    ctx: CommentContext, max_comments: int = 100, *, prompt_store: Any = None
) -> tuple[str, str]:
    """返回评论回复的 (system, user) 两段提示词。"""
    return (
        _comment_system_prompt(ctx, store=prompt_store),
        _comment_user_prompt(ctx, max_comments, store=prompt_store),
    )


def build_private_prompt(
    ctx: PrivateMessageContext, max_history: int = 30, *, prompt_store: Any = None
) -> tuple[str, str]:
    """返回私信回复的 (system, user) 两段提示词。"""
    return (
        _private_system_prompt(ctx, store=prompt_store),
        _private_user_prompt(ctx, max_history, store=prompt_store),
    )


def build_task_prompt(
    task: str,
    *,
    history: str = "",
    live: bool = False,
    bot_name: str = "",
    bot_uid: int = 0,
    bot_data: str = "",
    other_name: str = "",
    prompt_store: Any = None,
) -> tuple[str, str]:
    """跨聊天任务：让 B站侧用一次 LLM 生成要发出去的那句话。"""
    system = "\n".join(
        [
            _identity(bot_name, bot_uid, bot_data, other_name, store=prompt_store),
            (
                _live_adjust(prompt_store)
                if live
                else _style_rules(prompt_store)
                + "\n"
                + _text("scene", "general", store=prompt_store)
            ),
            _text("task", "cross_chat", store=prompt_store),
        ]
    )
    parts = []
    if history:
        parts.append(
            _text("task", "background", store=prompt_store).format(
                history=_data(history)
            )
        )
    parts.append(
        _text("task", "instruction", store=prompt_store).format(
            task=_data(task) or _text("defaults", "empty_task", store=prompt_store)
        )
    )
    return system, "\n".join(parts)


def build_diary_prompt(
    material: str,
    *,
    date_text: str,
    bot_name: str = "",
    bot_data: str = "",
    max_chars: int = 600,
    max_material_chars: int = 6000,
    requirement: str = "",
    prompt_store: Any = None,
) -> tuple[str, str]:
    """B站动态日记：把今天的聊天/档案素材写成一条动态。"""
    system = "\n".join(
        [
            _identity(bot_name, 0, bot_data, "", store=prompt_store),
            _text("human_feel", store=prompt_store),
            _text("diary", "cot", store=prompt_store),
            _text("diary", "material_tool", store=prompt_store),
            _text("diary", "rules", store=prompt_store),
            _text("data_rule", store=prompt_store),
            (
                _text("diary", "requirement", store=prompt_store).format(
                    requirement=requirement
                )
                if str(requirement or "").strip()
                else ""
            ),
            _text("diary", "length", store=prompt_store).format(max_chars=max_chars),
        ]
    )
    body = str(material or "").strip()
    if max_material_chars > 0 and len(body) > max_material_chars:
        body = body[:max_material_chars] + _text(
            "diary", "truncated", store=prompt_store
        )
    body = _data(body)
    user = _text("diary", "date", store=prompt_store).format(date_text=date_text)
    if body:
        user += "\n" + _text("diary", "material", store=prompt_store).format(
            material=body
        )
    return system, user


# ── system 提示词 ──


def _identity(
    bot_name: str,
    bot_uid: int,
    bot_data: str,
    other_name: str,
    *,
    store: Any = None,
) -> str:
    who = _text("identity", "name", store=store).format(
        bot_name=bot_name or _text("defaults", "bot_name", store=store)
    )
    if bot_uid:
        who += _text("identity", "uid", store=store).format(bot_uid=bot_uid)
    if other_name:
        who += _text("identity", "alias", store=store).format(other_name=other_name)
    who += "."
    if bot_data:
        who += f"\n{bot_data}"
    return _text("identity", "block", store=store).format(who=who)


def _time_text(moment: datetime | None) -> str:
    return get_current_time_values(moment)["current_time"]


def _comment_system_prompt(ctx: CommentContext, *, store: Any = None) -> str:
    return "\n".join(
        [
            _identity(
                ctx.bot_name, ctx.bot_uid, ctx.bot_data, ctx.other_name, store=store
            ),
            _style_rules(store),
            _text("scene", "comment", store=store),
        ]
    )


def _private_system_prompt(ctx: PrivateMessageContext, *, store: Any = None) -> str:
    return "\n".join(
        [
            _identity(
                ctx.bot_name, ctx.bot_uid, ctx.bot_data, ctx.other_name, store=store
            ),
            _style_rules(store),
            _text("scene", "private", store=store),
        ]
    )


# ── user 提示词 ──


def _comment_user_prompt(
    ctx: CommentContext, max_comments: int, *, store: Any = None
) -> str:
    parts: list[str] = [
        _text("shared", "current_time", store=store).format(
            current_time=_time_text(ctx.current_time)
        )
    ]
    parts.append(
        _text("comment", "target_info", store=store).format(
            target_info=_target_info(ctx, store=store)
        )
    )
    if ctx.memory:
        parts.append(
            _text("comment", "your_memory", store=store).format(
                memory=_data(ctx.memory)
            )
        )
    profiles = _commenter_profiles_section(ctx.commenter_profiles, store=store)
    if profiles:
        parts.append(profiles)
    if ctx.video_context:
        parts.append(
            _text("shared", "related_video", store=store).format(
                video_context=_data(ctx.video_context)
            )
        )
    parts.append(
        _text("comment", "target_comment_section", store=store).format(
            target_comment=_target_comment(ctx, store=store)
        )
    )
    if ctx.comment_tree:
        parts.append(
            _text("comment", "comment_tree_section", store=store).format(
                comment_tree=_render_comment_tree(ctx, max_comments, store=store)
            )
        )
    parts.append(_text("comment", "reply_guide", store=store))
    return "\n".join(parts)


def _private_user_prompt(
    ctx: PrivateMessageContext, max_history: int, *, store: Any = None
) -> str:
    parts: list[str] = [
        _text("shared", "current_time", store=store).format(
            current_time=_time_text(ctx.current_time)
        )
    ]
    sender_name = _data(ctx.sender_name) or _text(
        "defaults", "private_peer", store=store
    )
    if ctx.sender_remark:
        target = _text("private", "peer_with_remark", store=store).format(
            sender_name=sender_name,
            remark=_data(ctx.sender_remark),
            uid=ctx.sender_uid,
        )
    else:
        target = _text("private", "peer", store=store).format(
            sender_name=sender_name, uid=ctx.sender_uid
        )
    parts.append(_text("private", "target", store=store).format(target=target))
    if ctx.sender_profile:
        parts.append(
            _text("private", "impression", store=store).format(
                impression=_data(ctx.sender_profile)
            )
        )
    if ctx.memory_list:
        parts.append(
            _text("private", "memory", store=store).format(
                memory=_data(ctx.memory_list)
            )
        )
    if ctx.video_context:
        parts.append(
            _text("shared", "related_video", store=store).format(
                video_context=_data(ctx.video_context)
            )
        )
    parts.append(
        _text("private", "history_section", store=store).format(
            history=_history_text(ctx, max_history, store=store)
        )
    )
    parts.append(
        _text("private", "current_message", store=store).format(
            message=_data(ctx.current_message)
            or _text("defaults", "empty_message", store=store)
        )
    )
    return "\n".join(parts)


# ── 渲染细节 ──


def _target_info(ctx: CommentContext, *, store: Any = None) -> str:
    prefix = (
        _text("comment", "up_prefix", store=store).format(
            up_name=_data(ctx.target_up_name)
        )
        if ctx.target_up_name
        else ""
    )
    text = _text("comment", "summary", store=store).format(
        prefix=prefix,
        target_type=ctx.target_type,
        title=_data(ctx.target_title) or _text("defaults", "unknown", store=store),
        oid=ctx.target_oid,
    )
    if ctx.target_url:
        text += _text("comment", "url", store=store).format(
            url=_data(ctx.target_url)
        )
    if ctx.target_desc:
        text += _text("comment", "desc", store=store).format(
            desc=_data(ctx.target_desc)[:500]
        )
    return text


def _target_comment(ctx: CommentContext, *, store: Any = None) -> str:
    if not ctx.reply_target_rpid:
        return _text("defaults", "no_target_comment", store=store)
    node = _find_node(ctx.comment_tree, ctx.reply_target_rpid)
    if node is None:
        return _text("defaults", "missing_comment", store=store).format(
            rpid=ctx.reply_target_rpid
        )
    return _text("comment", "target_detail", store=store).format(
        uname=_data(node.uname),
        uid=node.uid,
        when=_format_ts(node.ctime),
        content=_data(node.content),
        replied=_text("comment", "replied_note", store=store)
        if node.up_replied
        else "",
    )


def _render_comment_tree(
    ctx: CommentContext, max_comments: int, *, store: Any = None
) -> str:
    nodes = _flatten(ctx.comment_tree)
    if max_comments > 0 and len(nodes) > max_comments:
        keep = nodes[:max_comments]
        head = _text("comment_tree", "truncated_head", store=store).format(
            total=len(nodes), kept=len(keep)
        )
        lines = [head]
        _render_nodes(keep, ctx.reply_target_rpid, lines, store=store)
        return "\n".join(lines)
    lines: list[str] = []
    _render_nodes(ctx.comment_tree, ctx.reply_target_rpid, lines, store=store)
    return "\n".join(lines)


def _render_nodes(
    nodes: list[CommentNode],
    target_rpid: int,
    parts: list[str],
    depth: int = 0,
    *,
    store: Any = None,
) -> None:
    indent = "  " * depth
    for node in nodes:
        marker = (
            _text("comment_tree", "target_marker", store=store)
            if node.rpid == target_rpid
            else ""
        )
        replied = (
            _text("comment_tree", "replied_marker", store=store)
            if node.up_replied
            else ""
        )
        parts.append(
            _text("comment_tree", "node_line", store=store).format(
                indent=indent,
                uname=_data(node.uname),
                uid=node.uid,
                marker=marker,
                replied=replied,
                time=_format_ts(node.ctime),
            )
        )
        content = _data(node.content).replace("\n", " ")[:200]
        if len(node.content) > 200:
            content += _text("comment_tree", "content_truncated", store=store)
        parts.append(
            _text("comment_tree", "content_line", store=store).format(
                indent=indent, content=content
            )
        )
        if node.children:
            _render_nodes(
                node.children, target_rpid, parts, depth + 1, store=store
            )


def _commenter_profiles_section(
    profiles: list[dict], *, store: Any = None
) -> str:
    if not profiles:
        return ""
    entries: list[str] = []
    for index, profile in enumerate(profiles, start=1):
        parts = [
            _text("profile", "uname", store=store).format(
                uname=_data(profile.get("uname", "?"))
            ),
            _text("profile", "uid", store=store).format(uid=profile.get("uid", "?")),
        ]
        for key in (
            "remark",
            "profile",
            "known_gender",
            "avatar_analysis",
            "bilibili_memory",
            "qq_memory",
        ):
            value = str(profile.get(key) or "").strip()
            if value:
                parts.append(
                    _text("profile", "line", store=store).format(
                        label=_text("profile_labels", key, store=store),
                        value=_data(value),
                    )
                )
        entries.append(
            _text("profile", "entry", store=store).format(
                index=index, parts=",".join(parts)
            )
        )
    return _text("profile", "section", store=store).format(entries="\n".join(entries))


def _history_text(
    ctx: PrivateMessageContext, max_history: int, *, store: Any = None
) -> str:
    if not ctx.history:
        return _text("history", "empty", store=store)
    history = ctx.history
    lines: list[str] = []
    if max_history > 0 and len(history) > max_history:
        lines.append(
            _text("history", "truncated", store=store).format(
                total=len(history), kept=max_history
            )
        )
        history = history[-max_history:]
    for index, msg in enumerate(history, start=1):
        content = str(msg.get("content", ""))
        role = msg.get("role", "")
        when = _format_ts(int(msg.get("time", 0) or 0))
        if role in ("bot", "self"):
            lines.append(
                _text("history", "bot_line", store=store).format(
                    index=index,
                    when=when,
                    bot_name=ctx.bot_name,
                    content=_data(content),
                )
            )
        else:
            who = msg.get("sender_name") or _text(
                "history", "sender_fallback", store=store
            ).format(uid=msg.get("sender_uid", "?"))
            lines.append(
                _text("history", "peer_line", store=store).format(
                    index=index, when=when, who=_data(who), content=_data(content)
                )
            )
    return "\n".join(lines)


def _flatten(nodes: list[CommentNode]) -> list[CommentNode]:
    result: list[CommentNode] = []
    for node in nodes:
        result.append(node)
        if node.children:
            result.extend(_flatten(node.children))
    return result


def _find_node(nodes: list[CommentNode], rpid: int) -> CommentNode | None:
    for node in nodes:
        if node.rpid == rpid:
            return node
        if node.children:
            found = _find_node(node.children, rpid)
            if found is not None:
                return found
    return None


def _format_ts(timestamp: int) -> str:
    if not timestamp:
        return ""
    return datetime.fromtimestamp(int(timestamp)).strftime("%m-%d %H:%M")


# ── 直播间弹幕提示词（复用 B站风格与群聊历史一致性，单独补直播调整块）──

#: B站直播弹幕硬上限；发送前必须预拦截。
MAX_LIVE_DANMAKU_CHARS = 20


#: QQ 群/评论区规则搬到直播间时需要调整的差异，集中在一个块里。
def _live_adjust(store: Any = None) -> str:
    return "\n".join(
        [
            _text("scene", "live", store=store),
            _text("human_feel", store=store),
            _text("reply_tool_rule", store=store),
            _text("data_rule", store=store),
        ]
    )


@dataclass
class LiveDanmakuContext:
    """直播间弹幕回复上下文。"""

    bot_name: str = ""
    bot_data: str = ""
    room_name: str = ""
    viewer_name: str = ""
    #: 当前弹幕发送者 UID：直接给模型，省得它去 500 行历史里猜该 @ 谁。
    viewer_uid: int = 0
    #: 当前这条弹幕是否点名了 bot（历史行不再标注，只标当前）。
    viewer_at_me: bool = False
    text: str = ""
    recent_history: str = ""
    frame_context: str = ""
    scheduled_prompt: str = ""
    memory: str = ""
    room_memory: str = ""
    viewer_memory: str = ""


def _render_live_persona(
    live_persona: str, ctx: LiveDanmakuContext, *, store: Any = None
) -> str:
    if not live_persona.strip():
        return ""
    return render_template(
        live_persona,
        {
            "bot_name": ctx.bot_name
            or _text("defaults", "live_bot_name", store=store),
            "bot_data": ctx.bot_data,
        },
    ).strip()


def build_live_danmaku_prompt(
    ctx: LiveDanmakuContext, live_persona: str = "", *, prompt_store: Any = None
) -> tuple[str, str]:
    """组装直播间弹幕的 system/user；live_chat 配了独立人格就用它。"""
    system = _render_live_persona(
        live_persona, ctx, store=prompt_store
    ) or "\n".join(
        [
            _identity(ctx.bot_name, 0, ctx.bot_data, "", store=prompt_store),
            _live_adjust(prompt_store),
            _text("live", "danmaku_history", store=prompt_store).format(
                bot_name=ctx.bot_name
                or _text("defaults", "live_bot_name", store=prompt_store)
            ),
            _text("live", "reply_to_rule", store=prompt_store),
        ]
    )
    parts = [
        _text("shared", "current_time", store=prompt_store).format(
            current_time=_time_text(None)
        )
    ]
    parts.append(
        _text("live", "room", store=prompt_store).format(
            room=_data(ctx.room_name)
            or _text("defaults", "live_room", store=prompt_store)
        )
    )
    parts.append(
        _text("live", "viewer", store=prompt_store).format(
            viewer=_data(ctx.viewer_name)
            or _text("defaults", "live_viewer", store=prompt_store)
        )
    )
    if ctx.room_memory or ctx.memory:
        parts.append(
            _text("live", "room_memory", store=prompt_store).format(
                memory=_data(ctx.room_memory or ctx.memory)
            )
        )
    if ctx.viewer_memory:
        parts.append(
            _text("live", "viewer_memory", store=prompt_store).format(
                memory=_data(ctx.viewer_memory)
            )
        )
    if ctx.recent_history:
        parts.append(
            _text("live", "recent_history", store=prompt_store).format(
                history=_data(ctx.recent_history)
            )
        )
    if ctx.frame_context:
        parts.append(
            _text("live", "frame", store=prompt_store).format(
                frame=_data(ctx.frame_context)
            )
        )
    parts.append(
        _text("live", "pending_danmaku", store=prompt_store).format(
            attrs=f' uid="{ctx.viewer_uid}"' if ctx.viewer_uid else "",
            text=("[@了我] " if ctx.viewer_at_me else "") + _data(ctx.text),
        )
    )
    return system, "\n".join(parts)


def build_live_scheduled_prompt(
    ctx: LiveDanmakuContext, live_persona: str = "", *, prompt_store: Any = None
) -> tuple[str, str]:
    """组装直播间主动定时弹幕的 system/user。"""
    system = _render_live_persona(
        live_persona, ctx, store=prompt_store
    ) or "\n".join(
        [
            _identity(ctx.bot_name, 0, ctx.bot_data, "", store=prompt_store),
            _live_adjust(prompt_store),
            _text("live", "scheduled_history", store=prompt_store).format(
                bot_name=ctx.bot_name
                or _text("defaults", "live_bot_name", store=prompt_store)
            ),
            _text("live", "scheduled_task", store=prompt_store),
        ]
    )
    parts = [
        _text("shared", "current_time", store=prompt_store).format(
            current_time=_time_text(None)
        )
    ]
    parts.append(
        _text("live", "room", store=prompt_store).format(
            room=_data(ctx.room_name)
            or _text("defaults", "live_room", store=prompt_store)
        )
    )
    if ctx.room_memory or ctx.memory:
        parts.append(
            _text("live", "room_memory", store=prompt_store).format(
                memory=_data(ctx.room_memory or ctx.memory)
            )
        )
    if ctx.viewer_memory:
        parts.append(
            _text("live", "viewer_memory", store=prompt_store).format(
                memory=_data(ctx.viewer_memory)
            )
        )
    if ctx.recent_history:
        parts.append(
            _text("live", "recent_history", store=prompt_store).format(
                history=_data(ctx.recent_history)
            )
        )
    if ctx.frame_context:
        parts.append(
            _text("live", "frame", store=prompt_store).format(
                frame=_data(ctx.frame_context)
            )
        )
    parts.append(
        _text("live", "scheduled_message", store=prompt_store).format(
            text=_data(ctx.scheduled_prompt)
        )
    )
    return system, "\n".join(parts)


def build_live_observation_prompt(
    ctx: LiveDanmakuContext, live_persona: str = "", *, prompt_store: Any = None
) -> tuple[str, str]:
    """组装主动观察直播画面的 system/user；允许 cancel。"""
    system = _render_live_persona(
        live_persona, ctx, store=prompt_store
    ) or "\n".join(
        [
            _identity(ctx.bot_name, 0, ctx.bot_data, "", store=prompt_store),
            _live_adjust(prompt_store),
            _text("live", "observation_task", store=prompt_store),
        ]
    )
    parts = [
        _text("shared", "current_time", store=prompt_store).format(
            current_time=_time_text(None)
        )
    ]
    parts.append(
        _text("live", "room", store=prompt_store).format(
            room=_data(ctx.room_name)
            or _text("defaults", "live_room", store=prompt_store)
        )
    )
    if ctx.room_memory or ctx.memory:
        parts.append(
            _text("live", "room_memory", store=prompt_store).format(
                memory=_data(ctx.room_memory or ctx.memory)
            )
        )
    if ctx.viewer_memory:
        parts.append(
            _text("live", "viewer_memory", store=prompt_store).format(
                memory=_data(ctx.viewer_memory)
            )
        )
    if ctx.recent_history:
        parts.append(
            _text("live", "recent_history", store=prompt_store).format(
                history=_data(ctx.recent_history)
            )
        )
    if ctx.frame_context:
        parts.append(
            _text("live", "frame", store=prompt_store).format(
                frame=_data(ctx.frame_context)
            )
        )
    parts.append(_text("live", "observation_user", store=prompt_store))
    return system, "\n".join(parts)
