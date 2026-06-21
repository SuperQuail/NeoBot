"""
B站交互提示词组装器 — 严格参考 NeoBot QQ 群聊/私聊提示词模板。

模板结构取自 app/src/neobot_app/config/schemas/bot.py:
  group_prompt_template / friend_prompt_template

针对 B站场景适配：
  - QQ号 → B站UID
  - 群聊/群友 → 评论区/评论树
  - 聊天对象 → 私信对话者
  - 保留 <你是谁> <回复要求> <cot> <回复样例> <当前时间> 等全部核心节
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import _datetime as datetime


# ── 数据模型 ──

@dataclass
class CommentNode:
    """评论树节点。"""
    rpid: int                    # 评论 ID
    uid: int                     # 用户 UID
    uname: str                   # 用户名
    content: str                 # 评论内容
    ctime: int                   # 发布时间戳
    children: list[CommentNode] = field(default_factory=list)
    up_replied: bool = False     # UP 主是否已回复


@dataclass
class CommentContext:
    """评论回复提示词上下文。"""
    bot_name: str
    bot_uid: int
    bot_data: str = ""            # Bot 个性/背景描述
    other_name: str = ""          # Bot 别名
    target_oid: int = 0           # 视频/动态 oid
    target_type: str = "视频"     # "视频" / "动态" / "专栏"
    business_id: int = 1          # B站 reply_feed business_id，直接作为 reply type_
    target_title: str = ""
    target_url: str = ""
    target_up_name: str = ""      # UP 主昵称
    target_desc: str = ""         # 视频/动态简介描述
    comment_tree: list[CommentNode] = field(default_factory=list)
    reply_target_rpid: int = 0    # ★ 标记的目标评论 rpid（=parent）
    reply_root_rpid: int = 0      # 根评论 rpid（嵌套回复时 ≠ reply_target_rpid）


@dataclass
class PrivateMessageContext:
    """私信回复提示词上下文。"""
    bot_name: str
    bot_uid: int
    bot_data: str = ""
    other_name: str = ""
    sender_name: str = ""         # 对方昵称
    sender_uid: int = 0
    sender_remark: str = ""       # 你对 ta 的备注
    sender_profile: str = ""      # 你对 ta 的印象/资料
    memory_list: str = ""         # 历史记忆摘要
    history: list[dict] = field(default_factory=list)
    current_message: str = ""


# ── 评论回复提示词 ──

def assemble_comment_reply_prompt(
    ctx: CommentContext,
    max_comments: int = 100,
    profiles: list[dict] | None = None,
) -> str:
    """组装评论回复提示词，格式对齐 QQ 群聊模板。"""
    now = datetime.datetime.now()
    current_time = now.strftime("%Y年%m月%d日 %H:%M, %A")

    # 构建 <你是谁>
    who_am_i = f"你的名字是{ctx.bot_name},你的B站UID是{ctx.bot_uid}"
    if ctx.other_name:
        who_am_i += f",也有人叫你{ctx.other_name}"
    who_am_i += "."
    if ctx.bot_data:
        who_am_i += f"\n{ctx.bot_data}"

    # 构建评论树
    comment_tree_text = _build_comment_tree_text(ctx, max_comments)

    # 构建待回复评论
    target_comment_text = _build_target_comment(ctx)

    # 构建评论者档案块
    commenter_profiles_text = _build_commenter_profiles_section(profiles or [])

    template = f"""<你是谁>
{who_am_i}
</你是谁><回复要求>请注意把握聊天内容,不要回复的太有条理,可以有个性.请回复的平淡一些，简短一些,不要刻意突出自身学科背景，尽量不要说你说过的话.不要输出多余内容(包括前后缀，冒号和引号，括号，表情包等 ),不要使用markdown,和正常聊天一样,回复短句即可.只有在有人询问你说的是哪句的时候,或者有明显歧义可能的情况下,引用原评论内容;其他情况不要引用.如果有人要求你做什么事情,你不一定要答应.</回复要求>
<cot>
[思维模式要求]在你的思考过程(<think>标签内)中，请遵守以下规则：
1. 检查当前待回复内容的话题是否已经回复过,如果已经回复过,并且没有需要补充的内容,则跳过该评论不回复
2. 确定对于回复对象的称呼,检查有没有明确的要求,如果有明确的对于称呼的要求,应该按照要求来称呼对方,并且保持称呼的一致性
3. 对于任务请求,你应该判断基于你的性格以及对方与你的关系,你是否会答应,不需要答应任何请求
</cot>
<回复样例>
回复1:好哦
回复2:我这就去看看
注意,短句分开回复,而不是以整段回复
** 严格禁止使用()来描述你的行为和思考,不要发送这样的内容 **</回复样例>
<当前时间>{current_time}</当前时间>
<评论区内容>{_build_target_info(ctx)}
</评论区内容>{commenter_profiles_text}
<待回复评论>
{target_comment_text}
</待回复评论>
<评论树>
{comment_tree_text}
</评论树>
<回复指引>
★ 标记的评论是你需要回复的目标。直接输出回复文本即可。
如果对应的评论不值得回复(刷屏/无意义/已回复过),则跳过。
</回复指引>"""
    return template


# ── 私信回复提示词 ──

def assemble_private_message_prompt(ctx: PrivateMessageContext, max_history: int = 50) -> str:
    """组装私信回复提示词，格式对齐 QQ 私聊模板。"""
    now = datetime.datetime.now()
    current_time = now.strftime("%Y年%m月%d日 %H:%M, %A")

    # <你是谁>
    who_am_i = f"你的名字是{ctx.bot_name},你的B站UID是{ctx.bot_uid}"
    if ctx.other_name:
        who_am_i += f",也有人叫你{ctx.other_name}"
    who_am_i += "."
    if ctx.bot_data:
        who_am_i += f"\n{ctx.bot_data}"

    # <聊天对象>
    chat_target = f"{ctx.sender_name}(UID:{ctx.sender_uid})"
    if ctx.sender_remark:
        chat_target = f"{ctx.sender_name}(你的备注:{ctx.sender_remark},UID:{ctx.sender_uid})"

    # <你对ta的印象>
    profile_line = f"\n<你对ta的印象>{ctx.sender_profile}</你对ta的印象>" if ctx.sender_profile else ""

    # <你的记忆>
    memory_line = f"\n<你的记忆>你想起来{ctx.memory_list}</你的记忆>" if ctx.memory_list else ""

    # 对话历史
    history_text = _build_history_text(ctx, max_history)

    template = f"""<你是谁>
{who_am_i}
</你是谁><回复要求>请注意把握聊天内容,不要回复的太有条理,可以有个性.请回复的平淡一些，简短一些,不要刻意突出自身学科背景，尽量不要说你说过的话.不要输出多余内容(包括前后缀，冒号和引号，括号，表情包等 ),不要使用markdown,和正常聊天一样,回复短句即可.当有人让你使用工具时,你可以先告诉对方你打算这么做再去调用工具,但不要在对话中提及你调用的具体工具.如果工具调用失败且你无法让其正常工作,你可以在聊天中告知你操作失败了,如果成功,在对方没有要求你成功后告知的情况下不需要再告诉对方你完成了.如果有人要求你做什么事情,你不一定要答应,如果你觉得可以答应,使用你可用的工具来完成,不要只表示去做而不使用工具完成,如果你发现你没有合适的工具或者工具无法完成任务,则回复你做不到如果你不确定你的工具能否完成指定任务,不要先回复做不到,先回复试试看.</回复要求>
<cot>
[思维模式要求]在你的思考过程(<think>标签内)中，请遵守以下规则：
1. 检查当前待回复内容的话题是否已经回复过,如果已经回复过,并且没有需要补充的内容,使用cancel直接取消回复,而不要对一个话题反复重复回复
2. 确定对于回复对象的称呼,检查有没有明确的要求,如果有明确的对于称呼的要求,应该按照要求来称呼对方,并且保持称呼的一致性
3. 对于任务请求,你应该判断基于你的性格以及对方与你的关系,你是否会答应,不需要答应任何请求
</cot>
<回复样例>
回复1:好哦
回复2:我这就去看看
注意,短句分开回复,而不是以整段回复
** 严格禁止使用()来描述你的行为和思考,不要发送这样的内容 **</回复样例>
<当前时间>{current_time}</当前时间>
<聊天对象>{chat_target}</聊天对象>{profile_line}{memory_line}
<对话历史>
{history_text}
</对话历史>
<待回复消息>
{ctx.current_message or '(空消息)'}
</待回复消息>"""
    return template


# ── 内部构建函数 ──

def _build_comment_tree_text(ctx: CommentContext, max_comments: int) -> str:
    """构建评论树文本，含截断逻辑。"""
    all_nodes = _flatten_comment_tree(ctx.comment_tree)

    if len(all_nodes) > max_comments:
        bot_branches = _collect_bot_related_branches(ctx.comment_tree, ctx.bot_name, ctx.bot_uid)
        other_nodes = [n for n in all_nodes if n.rpid not in {b.rpid for b in bot_branches}]
        keep = bot_branches[:max_comments // 2]
        remaining = max_comments - len(keep)
        keep.extend(other_nodes[:remaining])
        lines = [f"(评论区共 {len(all_nodes)} 条，已截断至 {len(keep)} 条，优先保留你参与过的对话)", ""]
        _render_nodes(keep, ctx.reply_target_rpid, lines)
    else:
        lines = []
        _render_nodes(ctx.comment_tree, ctx.reply_target_rpid, lines)

    return "\n".join(lines)


def _build_target_info(ctx: CommentContext) -> str:
    """构建评论区目标信息行。"""
    parts: list[str] = []
    if ctx.target_up_name:
        parts.append(f"{ctx.target_up_name}的")
    parts.append(f"{ctx.target_type}「{ctx.target_title or '未知'}」[oid:{ctx.target_oid}]")
    url = ctx.target_url or ""
    if url:
        parts.append(f"\n{url}")
    if ctx.target_desc:
        parts.append(f"\n简介：{ctx.target_desc[:500]}")
    return "".join(parts)


def _build_target_comment(ctx: CommentContext) -> str:
    """构建待回复评论的详细展示。"""
    if ctx.reply_target_rpid == 0 or not ctx.comment_tree:
        return "(未指定待回复评论)"

    node = _find_node_by_rpid(ctx.comment_tree, ctx.reply_target_rpid)
    if node is None:
        return f"(未找到 rpid={ctx.reply_target_rpid} 的评论)"

    time_str = _format_timestamp(node.ctime)
    lines = [
        f"作者：@{node.uname}(UID:{node.uid})",
        f"时间：{time_str}",
        f"内容：{node.content}",
    ]
    if node.up_replied:
        lines.append("注意：你已回复过这条评论")
    return "\n".join(lines)


def _find_node_by_rpid(nodes: list[CommentNode], rpid: int) -> CommentNode | None:
    """在评论树中按 rpid 查找节点。"""
    for n in nodes:
        if n.rpid == rpid:
            return n
        if n.children:
            result = _find_node_by_rpid(n.children, rpid)
            if result:
                return result
    return None


def _build_history_text(ctx: PrivateMessageContext, max_history: int) -> str:
    """构建私信对话历史文本。"""
    if not ctx.history:
        return "(无历史消息)"

    history = ctx.history[-max_history:] if len(ctx.history) > max_history else ctx.history
    lines = []
    if len(ctx.history) > max_history:
        lines.append(f"(共 {len(ctx.history)} 条消息，仅显示最近 {max_history} 条)")

    for i, msg in enumerate(history):
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        ts = msg.get("time", 0)
        time_str = _format_timestamp(ts)
        if role in ("bot", "self"):
            lines.append(f"[{i + 1}] {time_str} 你（{ctx.bot_name}）：{content}")
        else:
            who = msg.get("sender_name", f"UID:{msg.get('sender_uid', '?')}")
            lines.append(f"[{i + 1}] {time_str} {who}：{content}")

    return "\n".join(lines)


def _flatten_comment_tree(nodes: list[CommentNode]) -> list[CommentNode]:
    result: list[CommentNode] = []
    for n in nodes:
        result.append(n)
        if n.children:
            result.extend(_flatten_comment_tree(n.children))
    return result


def _collect_bot_related_branches(
    nodes: list[CommentNode], bot_name: str, bot_uid: int
) -> list[CommentNode]:
    result: list[CommentNode] = []
    for n in nodes:
        is_bot = (n.uname == bot_name) or (n.uid == bot_uid)
        child_bot_related = bool(_collect_bot_related_branches(n.children, bot_name, bot_uid))
        if is_bot or child_bot_related:
            result.append(n)
            if child_bot_related:
                result.extend(_collect_bot_related_branches(n.children, bot_name, bot_uid))
    return result


def _render_nodes(
    nodes: list[CommentNode],
    target_rpid: int,
    parts: list[str],
    depth: int = 0,
) -> None:
    indent = "  " * depth
    for n in nodes:
        marker = " ★  ← 需要回复" if n.rpid == target_rpid else ""
        replied_tag = " [已回复]" if n.up_replied else ""
        time_str = _format_timestamp(n.ctime)
        parts.append(
            f"{indent}├─ @{n.uname}(UID:{n.uid}){marker}{replied_tag} [{time_str}]"
        )
        for line in n.content.replace("\n", " ")[:200].split("\n"):
            parts.append(f"{indent}│  {line}")
        if len(n.content) > 200:
            parts.append(f"{indent}│  ...(截断)")

        if n.children:
            _render_nodes(n.children, target_rpid, parts, depth + 1)


def _build_commenter_profiles_section(profiles: list[dict]) -> str:
    """构建评论者档案块，每人只显示一次，对齐群聊 <群友列表> 格式。"""
    if not profiles:
        return ""
    lines = ["<评论者档案>"]
    for i, p in enumerate(profiles, start=1):
        uname = p.get("uname", "?")
        uid = p.get("uid", "?")
        parts: list[str] = [f"B站昵称:{uname}", f"UID:{uid}"]
        remark = p.get("remark")
        if remark:
            parts.append(f"你对Ta的备注:{remark}")
        profile_text = p.get("profile")
        if profile_text:
            parts.append(f"你对Ta的印象:{profile_text}")
        known_gender = p.get("known_gender")
        if known_gender:
            parts.append(f"Ta告诉你的性别:{known_gender}")
        avatar = p.get("avatar_analysis")
        if avatar:
            parts.append(f"头像记忆:{avatar}")
        bili_archive = p.get("bilibili_archive")
        if bili_archive:
            parts.append(f"你记得关于Ta的事:{bili_archive}")
        qq_archive = p.get("qq_archive")
        if qq_archive:
            parts.append(f"QQ相关记忆:{qq_archive}")
        lines.append(f"<评论者_{i}>{','.join(parts)}</评论者_{i}>")
    lines.append("</评论者档案>")
    return "\n".join(lines)


def _format_timestamp(ts: int) -> str:
    if ts <= 0:
        return ""
    dt = datetime.datetime.fromtimestamp(ts)
    return dt.strftime("%m-%d %H:%M")
