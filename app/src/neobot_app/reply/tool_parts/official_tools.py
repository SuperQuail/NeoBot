"""官方通道专用 Markdown 发送工具（仅 official 平台暴露）。"""

from __future__ import annotations

import json
import re

from neobot_chat.schema.types import ToolDefinition

from neobot_app.reply.tool_parts.common import _tool_def

_CONTENT_LIMIT = 4000
_TAG_RE = re.compile(r"<[^>]*>")
_AT_USER_RE = re.compile(r'<qqbot-at-user\s+id="(\d{13})"\s*/>')
_AT_EVERYONE_RE = re.compile(r"<qqbot-at-everyone\s*/>")
_CMD_RE = re.compile(r"<qqbot-cmd-(?:enter|input)\s+[^>]*/>")


def _validate_markdown_tags(content: str) -> str | None:
    """只允许官方契约里的内嵌标签；其余 <...> 一律拒绝，避免伪造 @/按钮。"""
    tags = _TAG_RE.findall(content)
    for tag in tags:
        if (
            _AT_USER_RE.fullmatch(tag)
            or _AT_EVERYONE_RE.fullmatch(tag)
            or _CMD_RE.fullmatch(tag)
        ):
            continue
        return f"Markdown 中出现了不支持的标签：{tag[:80]}"
    return None


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
                "内嵌 @ 或指令按钮时才用本工具。支持官方内嵌标签："
                '<qqbot-at-user id="13位合成ID" />、<qqbot-at-everyone />、'
                '<qqbot-cmd-enter text="..." />、<qqbot-cmd-input text="..." show="..." />；'
                "群聊不支持 qqbot-cmd-enter。表格和代码块官方不支持，请改用 send_long_reply。"
                "本工具一条消息发完，不切分、不降级；发送失败会直接返回错误，请修正参数或告知用户无法发送。",
                {
                    "properties": {
                        "content": {"type": "string", "description": "官方 Markdown 卡片内容，≤4000 字符。"},
                        "reply_to_number": {
                            "type": "integer",
                            "description": "可选，要引用回复的消息编号（消息行首编号）。",
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
                        "group_id": {"type": "integer", "description": "官方群的合成群 ID（13 位数字）。"},
                        "user_id": {"type": "integer", "description": "目标用户的合成 ID（13 位数字）；robot_status 不需要。"},
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
        try:
            group_id = int(args.get("group_id"))
        except (TypeError, ValueError):
            return "错误：group_id 必须是官方合成群 ID 整数"
        params: dict[str, object] = {"group_id": group_id}
        if action != "robot_status":
            try:
                params["user_id"] = int(args.get("user_id"))
            except (TypeError, ValueError):
                return "错误：user_id 必须是官方合成用户 ID 整数"
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
            return "错误：send_official_markdown 仅在官方机器人通道可用"
        content = str(args.get("content") or "")
        if not content.strip():
            return "错误：content 不能为空"
        if len(content) > _CONTENT_LIMIT:
            return f"错误：content 超过 {_CONTENT_LIMIT} 字符，请缩短或改用 send_long_reply"
        if "```" in content:
            return "错误：官方 Markdown 不支持代码块，请改用 send_long_reply"
        tag_error = _validate_markdown_tags(content)
        if tag_error:
            return f"错误：{tag_error}"
        raw_reply = args.get("reply_to_number")
        try:
            reply_to = int(raw_reply) if raw_reply not in (None, "") else None
        except (TypeError, ValueError):
            return "错误：reply_to_number 必须是整数"
        result = await self._send_official_markdown(
            content=content, reply_to_number=reply_to
        )
        failed = getattr(result, "status", None) == "failed" or (
            isinstance(result, dict) and result.get("status") == "failed"
        )
        if failed or result is False or result is None:
            message = getattr(result, "message", None)
            if not message and isinstance(result, dict):
                message = result.get("message")
            self._logger.info("官方 Markdown 卡片发送失败", error=str(message or "unknown"))
            return json.dumps(
                {"ok": False, "error": f"发送失败：{message or '未知错误'}"},
                ensure_ascii=False,
            )
        self._ai_check_pending = False
        return json.dumps(
            {"ok": True, "sent_count": 1, "summary": "已发送 1 条官方 Markdown 消息"},
            ensure_ascii=False,
        )
