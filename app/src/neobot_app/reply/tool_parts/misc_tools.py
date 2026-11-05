"""等待、语音与戳一戳工具（由 reply/tools.py 拆分）。"""

from __future__ import annotations

from neobot_contracts.ports.speaking import SpeechBlocked

from neobot_app.reply.output_guard import clean_text
from neobot_app.time_context import monotonic_seconds
from neobot_chat.schema.types import ToolDefinition

from neobot_app.reply.tool_parts.common import _tool_def


class _MiscToolsMixin:
    async def _execute_wait(self, args: dict) -> str:
        if self._wait is None:
            return "错误：wait 处理器未配置"
        raw_seconds = args.get("seconds", 20)
        if raw_seconds is None:
            seconds = 20
        elif isinstance(raw_seconds, bool):
            return f"错误：seconds 必须为整数，收到 {raw_seconds}"
        else:
            try:
                if isinstance(raw_seconds, float) and not raw_seconds.is_integer():
                    raise ValueError
                seconds = int(raw_seconds)
            except (ValueError, TypeError, OverflowError):
                return f"错误：seconds 必须为整数，收到 {raw_seconds}"
        if seconds < 0:
            return f"错误：seconds 不能为负数，收到 {raw_seconds}"

        now = monotonic_seconds()
        elapsed = now - self._last_wait_time
        if self._last_wait_time > 0 and elapsed < self._wait_cooldown_seconds:
            remaining = int(self._wait_cooldown_seconds - elapsed)
            return (
                f"wait 处于冷却中，还需等待 {remaining} 秒后才可再次调用。"
                "【提示】如果是在等待后台任务完成，可以继续聊天或处理其他事情；系统会在完成后通知你，不要轮询。"
            )
        self._last_wait_time = now
        return await self._wait(seconds=seconds)

    async def _execute_speak(self, args: dict) -> str:
        if self._tts_service is None:
            return "错误：TTS 服务未配置"
        if not getattr(self._tts_service, "enabled", False):
            return "错误：TTS 服务当前不可用"
        if self._speak_handler is None:
            return "错误：speak 处理器未配置"
        text = str(args.get("text") or "").strip()
        if not text:
            return "错误：text 不能为空"
        text = clean_text(text, known_sender_names=self._sender_names())
        if not text.strip():
            return "错误：text 清洗后为空，请只提供要朗读的正文，不要带系统标注或思考草稿"
        try:
            return await self._speak_handler(text=text)
        except SpeechBlocked:
            raise
        except Exception as exc:
            self._logger.warning("语音生成失败", error_type=type(exc).__name__)
            return "语音生成失败"

    async def _execute_poke_user(self, args: dict) -> str:
        if self._poke_user is None:
            return "错误：poke_user 处理器未配置"
        try:
            user_id = int(args.get("user_id", -1))
        except (ValueError, TypeError):
            return "错误：user_id 必须为整数"
        if user_id <= 0:
            return f"错误：user_id 无效，收到 {args.get('user_id')}"
        return await self._poke_user(user_id=user_id)

    def _define_wait_tool(self, tools: list[ToolDefinition]) -> None:
        if self._wait is not None:
            tools.append(
                _tool_def(
                    "wait",
                    "等待一段时间让其他人发言。当认为当前话题未结束或聊天还可继续时调用。"
                    "等待期间的新消息会被收集并在返回结果中呈现。默认等待20秒。",
                    {
                        "properties": {
                            "seconds": {
                                "type": "integer",
                                "description": "等待秒数，默认20秒，最大值受配置限制。",
                            },
                        },
                        "required": [],
                    },
                ),
            )

    def _define_speak_tool(self, tools: list[ToolDefinition]) -> None:
        if self._tts_service is not None and getattr(
            self._tts_service, "enabled", False
        ):
            tools.append(
                _tool_def(
                    "speak",
                    "将文本转为语音消息并发送到当前会话。适合用于需要语音回复、朗读内容等场景。"
                    "text 只放要念出来的正文本身：不要带编号/发送者名字/[msg_id=...] 等系统标注，"
                    "也不要写思考过程（发送和写回对话历史前会做输出安全清洗）。",
                    {
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "需要转为语音的文本内容，只放正文本身，不要带系统标注或思考过程。",
                            },
                        },
                        "required": ["text"],
                    },
                ),
            )

    def _define_poke_tool(self, tools: list[ToolDefinition]) -> None:
        if self._poke_user is not None:
            tools.append(
                _tool_def(
                    "poke_user",
                    "戳一戳指定的QQ用户。在群聊中自动使用群戳一戳，在私聊中自动使用好友戳一戳。"
                    "只需提供目标QQ号，Bot会自动判断会话类型。",
                    {
                        "properties": {
                            "user_id": {
                                "type": "integer",
                                "description": "要戳一戳的目标QQ号。",
                            },
                        },
                        "required": ["user_id"],
                    },
                ),
            )
