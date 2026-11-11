"""官方通道专用 Markdown 发送工具（仅 official 平台暴露）。"""

from __future__ import annotations

import ipaddress
import json
import re
import time
from urllib.parse import urlsplit

from neobot_adapter.official.send import neutralize_official_tags
from neobot_chat.schema.types import ToolDefinition

from neobot_app.reply.output_guard import clean_text
from neobot_app.reply.tool_parts.common import _tool_def

_CONTENT_LIMIT = 4000
_COMMAND_LIMIT = 100
_TAG_RE = re.compile(r"<[^>]*>")
_AT_USER_RE = re.compile(r'<qqbot-at-user\s+id="([A-Za-z0-9_-]{1,128})"\s*/>')
#: 官方协议标签：除内嵌 @用户 外，正文里出现的一律全角化（不能真的 @/弹出按钮）。
_OFFICIAL_TAG_RE = re.compile(r"</?qqbot-[^>]*>|<@!?[^>]*>")
#: Markdown 链接/图片：[text](url) / ![alt](url)；只校验目标 URL（允许尖括号/空白）。
_LINK_RE = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]*)>?\s*\)")
#: 引用式链接定义：[ref]: url；与正文链接一起校验。
_LINK_DEF_RE = re.compile(r"(?m)^\s*\[[^\]]+\]:\s*<?(\S+?)>?\s*$")
#: 危险 scheme 兜底：即使解析不到链接，也不允许正文出现这些协议。
_DANGEROUS_SCHEME_RE = re.compile(r"(?i)\b(?:javascript|vbscript|data|file)\s*:")
#: @全体本地节流：群 openid -> 本地自然日；重启清空可接受（官方限制才是权威）。
_AT_EVERYONE_SENT: dict[str, str] = {}


def _error(message: str) -> str:
    """参数/发送错误回执；文案保留既有「错误：」前缀，便于模型识别。"""
    text = message if message.startswith("错误") else f"错误：{message}"
    return json.dumps({"ok": False, "error": text}, ensure_ascii=False)


def _local_day() -> str:
    return time.strftime("%Y-%m-%d", time.localtime())


def _at_everyone_available(conversation_id: str) -> bool:
    return _AT_EVERYONE_SENT.get(conversation_id) != _local_day()


def _remember_at_everyone(conversation_id: str) -> None:
    today = _local_day()
    for key, day in list(_AT_EVERYONE_SENT.items()):
        if day != today:
            del _AT_EVERYONE_SENT[key]
    _AT_EVERYONE_SENT[conversation_id] = today


def _id_param(value: object) -> int | str:
    """官方 target ID：openid 原样字符串；旧版合成号/数字保留 int（兼容旧适配器）。"""
    text = str(value or "").strip()
    if not text:
        return ""
    return int(text) if text.isdigit() else text


def _unsupported_tag(content: str) -> str | None:
    """官方协议标签交给全角化；其它 <...>（HTML 等）直接拒绝。"""
    for tag in _TAG_RE.findall(content):
        if _AT_USER_RE.fullmatch(tag) or _OFFICIAL_TAG_RE.fullmatch(tag):
            continue
        return (
            f"Markdown 中出现了不支持的标签：{tag[:80]}；"
            "官方 Markdown 不解析 HTML，请去掉尖括号或改用 send_long_reply"
        )
    return None


def _unsafe_link(content: str) -> str | None:
    """链接只允许 http(s)：拒绝 javascript:/data:/file: 与回环/内网地址。"""
    if _DANGEROUS_SCHEME_RE.search(content):
        return "Markdown 中出现了不安全的链接协议（只允许 http(s)）"
    candidates = [m.group(1) for m in _LINK_RE.finditer(content)]
    candidates.extend(m.group(1) for m in _LINK_DEF_RE.finditer(content))
    for raw in candidates:
        url = raw.strip()
        if not url:
            continue
        parts = urlsplit(url)
        if parts.scheme.lower() not in {"http", "https"}:
            return f"链接只允许 http(s)：{url[:120]}"
        host = (parts.hostname or "").strip().lower()
        if not host:
            return f"链接缺少可访问的主机名：{url[:120]}"
        if host == "localhost" or host.endswith((".localhost", ".local")):
            return f"不允许发送内网/本机链接：{url[:120]}"
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            continue
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_unspecified
        ):
            return f"不允许发送内网/本机链接：{url[:120]}"
    return None


def _command_entries(raw: object, *, private: bool) -> tuple[list[dict], str | None]:
    """校验 commands；返回 (条目, 错误)。回车指令只在单聊可用。"""
    if raw in (None, ""):
        return [], None
    if not isinstance(raw, list):
        return [], "commands 必须是对象数组"
    entries: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            return [], "commands 必须是对象数组"
        text = str(item.get("text") or "").strip()
        if not 1 <= len(text) <= _COMMAND_LIMIT:
            return [], f"指令按钮文本必须在 1~{_COMMAND_LIMIT} 字符内"
        show = str(item.get("show") or "").strip()
        if len(show) > _COMMAND_LIMIT:
            return [], f"指令按钮显示文本必须在 1~{_COMMAND_LIMIT} 字符内"
        enter = bool(item.get("enter"))
        if enter and not private:
            return [], "群聊不支持回车指令；请去掉 enter 或改用 send_reply"
        entries.append(
            {
                "text": text,
                "show": show,
                "enter": enter,
                "reference": bool(item.get("reference")) and not enter,
            }
        )
    return entries, None


class _OfficialToolsMixin:
    def _define_official_markdown_tool(self, tools: list[ToolDefinition]) -> None:
        if not self._official_platform or self._send_official_markdown is None:
            return
        tools.append(
            _tool_def(
                "send_official_markdown",
                "发送一条 QQ 官方 Markdown 卡片（仅官方通道）。它和我们自己的「Markdown 图片」"
                "（send_long_reply 把 Markdown 渲染成图片）不是一回事。普通 send_reply 只发纯文本，"
                "不会渲染 Markdown，也不能真正 @ 用户。只有需要标题、列表、引用、链接、图片、"
                "内嵌 @、@全体成员或指令按钮时才用本工具。content 里只允许内嵌 "
                '<qqbot-at-user id="openid" />（openid 见群友资料），其它官方标签会被转义成普通文字；'
                "@全体成员只能由 at_everyone=true 生成（仅群聊、每群每天 1 次、需要机器人是群管理员）；"
                "指令按钮只能由 commands 数组生成（text/show ≤100 字符，群聊不支持 enter）。"
                "表格和代码块官方不支持，请改用 send_long_reply。本工具一轮最多 1 条，不切分、"
                "不降级；发送失败会直接返回错误，请修正参数或告知用户无法发送。",
                {
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": (
                                "官方 Markdown 卡片正文，≤4000 字符；只允许内嵌 "
                                '<qqbot-at-user id="openid" />，其余官方标签会被转义。'
                            ),
                        },
                        "reply_to_number": {
                            "type": "integer",
                            "description": "可选，要引用回复的消息编号（消息行首编号）。",
                        },
                        "at_everyone": {
                            "type": "boolean",
                            "description": (
                                "仅群聊。为 true 时在正文最前面 @全体成员；每群每天最多 1 次，"
                                "且机器人必须是群管理员。"
                            ),
                        },
                        "commands": {
                            "type": "array",
                            "description": "可选，追加在正文末尾的指令按钮。",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "text": {
                                        "type": "string",
                                        "description": "点击后发送/插入的文本，1~100 字符。",
                                    },
                                    "show": {
                                        "type": "string",
                                        "description": "按钮上显示的文本，≤100 字符；缺省取 text。",
                                    },
                                    "enter": {
                                        "type": "boolean",
                                        "description": "true 生成回车指令（点一下直接发送）；仅单聊可用。",
                                    },
                                    "reference": {
                                        "type": "boolean",
                                        "description": "参数指令是否带引用，默认 false。",
                                    },
                                },
                                "required": ["text"],
                            },
                        },
                    },
                    "required": ["content"],
                },
            )
        )

    def _define_official_group_manage_tool(self, tools: list[ToolDefinition]) -> None:
        if not self._official_platform or self._official_group_manage is None:
            return
        tools.append(
            _tool_def(
                "official_group_manage",
                "官方 QQ 机器人群管理（仅官方通道，需要机器人是群管理员）。"
                "只提供官方真实接口：查询机器人状态、禁言/解除禁言、踢人、入群审批。"
                "成功返回 ok；失败返回官方错误，不会降级或伪装成功。",
                {
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["robot_status", "ban", "unban", "kick", "approve_join", "reject_join"],
                            "description": "要执行的管理动作。",
                        },
                        "group_id": {"type": ["string", "integer"], "description": "官方群的本地群 ID（openid 字符串）。"},
                        "user_id": {"type": ["string", "integer"], "description": "目标用户的本地 ID（openid 字符串）；robot_status 不需要。"},
                        "duration_seconds": {"type": "integer", "description": "禁言时长秒数；ban 必填，最长 30 天。"},
                        "flag": {"type": "string", "description": "入群申请事件里的 flag（join_request_id）；审批时传。"},
                        "reason": {"type": "string", "description": "拒绝理由；reject_join 可选。"},
                        "reject_add_request": {"type": "boolean", "description": "踢人时是否同时拉黑；默认 false。"},
                    },
                    "required": ["action", "group_id"],
                },
            )
        )

    async def _execute_official_group_manage(self, args: dict) -> str:
        if not self._official_platform or self._official_group_manage is None:
            return "错误：official_group_manage 仅在官方机器人通道可用"
        action = str(args.get("action") or "").strip()
        if action not in {"robot_status", "ban", "unban", "kick", "approve_join", "reject_join"}:
            return "错误：action 必须是 robot_status/ban/unban/kick/approve_join/reject_join"
        group_id = _id_param(args.get("group_id"))
        if not group_id:
            return "错误：缺少 group_id（官方群 openid）"
        params: dict[str, object] = {"group_id": group_id}
        if action != "robot_status":
            user_id = _id_param(args.get("user_id"))
            if not user_id:
                return "错误：缺少 user_id（目标用户 openid）"
            params["user_id"] = user_id
        if action == "ban":
            try:
                params["duration"] = int(args.get("duration_seconds"))
            except (TypeError, ValueError):
                return "错误：ban 需要 duration_seconds 整数"
        elif action == "unban":
            params["duration"] = 0
        elif action == "kick":
            params["reject_add_request"] = bool(args.get("reject_add_request"))
        elif action in {"approve_join", "reject_join"}:
            params["approve"] = action == "approve_join"
            if args.get("flag"):
                params["flag"] = str(args["flag"])
            if action == "reject_join" and args.get("reason"):
                params["reason"] = str(args["reason"])
        result = await self._official_group_manage(action=action, params=params)
        status = result.get("status") if isinstance(result, dict) else None
        if status != "ok":
            message = result.get("message") if isinstance(result, dict) else "未知错误"
            self._logger.info("官方群管理动作失败", action=action, error=str(message))
            return json.dumps({"ok": False, "error": f"官方群管理失败：{message}"}, ensure_ascii=False)
        return json.dumps({"ok": True, "action": action}, ensure_ascii=False)

    async def _execute_official_markdown(self, args: dict) -> str:
        if not self._official_platform or self._send_official_markdown is None:
            return _error("send_official_markdown 仅在官方机器人通道可用")
        # 被动回复额度按条消耗：一轮最多 1 条，避免模型反复改格式重发。
        if getattr(self, "_official_markdown_sent", False):
            return _error("本轮回复已发送过 1 条官方 Markdown 卡片；同一轮最多 1 条，请不要重复发送")
        raw_content = args.get("content")
        if not isinstance(raw_content, str) or not raw_content.strip():
            return _error("Markdown 内容为空")
        content = clean_text(raw_content, known_sender_names=self._sender_names())
        if not content.strip():
            return _error("Markdown 内容清洗后为空，请只提供正文，不要带系统标注或思考草稿")
        if len(content) > _CONTENT_LIMIT:
            return _error(
                f"Markdown 内容 {len(content)} 字，超过单条上限 {_CONTENT_LIMIT}；"
                "请精简后重发，或改用 send_long_reply"
            )
        if "```" in content:
            return _error("官方 Markdown 不支持代码块，请改用 send_long_reply")
        is_group = self._conv_kind == "group"
        is_private = self._conv_kind == "private"
        raw_at_everyone = args.get("at_everyone", False)
        if raw_at_everyone is None:
            raw_at_everyone = False
        if not isinstance(raw_at_everyone, bool):
            return _error("at_everyone 必须是布尔值")
        at_everyone = raw_at_everyone
        if at_everyone and not is_group:
            return _error("单聊不支持 @全体成员；请直接写提醒并去掉 at_everyone")
        if is_private and _AT_USER_RE.search(content):
            return _error("单聊不支持 @；请直接写昵称，去掉 <qqbot-at-user> 标签")
        commands, command_error = _command_entries(args.get("commands"), private=is_private)
        if command_error:
            return _error(command_error)
        tag_error = _unsupported_tag(content)
        if tag_error:
            return _error(tag_error)
        link_error = _unsafe_link(content)
        if link_error:
            return _error(link_error)
        # 正文只放行内嵌 @；@全体与按钮只能来自结构化参数。
        content, neutralized = neutralize_official_tags(content, allow_at_user=True)
        raw_reply = args.get("reply_to_number")
        reply_to: int | None = None
        if raw_reply not in (None, ""):
            try:
                reply_to = int(raw_reply)
            except (TypeError, ValueError):
                return _error(f"reply_to_number 必须为整数，收到 {raw_reply}")
            mapping = (
                getattr(self._numbering, "mapping", None)
                if self._numbering is not None
                else None
            )
            if (
                isinstance(mapping, dict)
                and mapping
                and self._numbering.get_message_id(reply_to) is None
            ):
                return _error(f"消息编号 {reply_to} 不存在于当前上下文中")
        conversation_id = str(self._conv_id or "")
        if at_everyone and not _at_everyone_available(conversation_id):
            return _error(
                "本群今天的 @全体成员已用掉（官方限制每群每天 1 次）；请改用普通提醒"
            )
        # 写回历史用去标签的可读版，否则下一轮上下文会教模型在普通 send_reply 里手写标签。
        display = _AT_USER_RE.sub("@用户", content)
        if at_everyone:
            display = f"@全体成员 {display}"
        for command in commands:
            display = f"{display}\n\n[按钮：{command['show'] or command['text']}]"
        history_args: dict = {"content": content}
        if reply_to is not None:
            history_args["reply_to_number"] = reply_to
        if at_everyone:
            history_args["at_everyone"] = True
        if commands:
            history_args["commands"] = commands
        result = await self._send_official_markdown(
            content=content,
            reply_to_number=reply_to,
            at_everyone=at_everyone,
            commands=commands,
            display_text=display,
            tool_arguments=history_args,
        )
        failed = getattr(result, "status", None) == "failed" or (
            isinstance(result, dict) and result.get("status") == "failed"
        )
        if failed or result is False or result is None:
            message = getattr(result, "message", None)
            if not message and isinstance(result, dict):
                message = result.get("message")
            self._logger.info("官方 Markdown 卡片发送失败", error=str(message or "unknown"))
            return _error(f"发送失败：{message or '未知错误'}")
        self._official_markdown_sent = True
        if at_everyone:
            _remember_at_everyone(conversation_id)
        self._ai_check_pending = False
        payload: dict = {"ok": True, "sent_count": 1, "summary": "已发送 1 条官方 Markdown 消息"}
        if neutralized:
            payload["neutralized"] = neutralized
        return json.dumps(payload, ensure_ascii=False)
