"""Chat 配置读取（默认值统一来自 schema）。"""
from __future__ import annotations

from typing import Any
from neobot_app.reply.event import ReplyEvent

def _safe_int(value: object) -> int:
    """把配置值安全解析为 int；非数字/None/空串一律返回 0。

    避免畸形配置（如 bot.account 填了 "your_qq"）在 int() 处抛 ValueError，
    导致每次 agent 回复管线崩溃。
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
_CHAT_FIELD_DEFAULTS: dict[str, Any] | None = None
def _chat_default(name: str) -> Any:
    """Chat 配置字段的缺省值唯一来源（schema），避免 getter 手写第二份默认值。"""
    global _CHAT_FIELD_DEFAULTS
    if _CHAT_FIELD_DEFAULTS is None:
        from dataclasses import MISSING, fields

        from neobot_app.config.schemas.bot import Chat

        _CHAT_FIELD_DEFAULTS = {
            item.name: item.default for item in fields(Chat) if item.default is not MISSING
        }
    return _CHAT_FIELD_DEFAULTS[name]

class SettingsMixin:
    def _resolve_mode(self) -> str:
        # 回退值统一取自 schema（见 fix(23)），不再手写第二份默认值。
        if self._config is not None:
            mode = getattr(self._config.chat, "reply_mode", None)
            if mode in ("common", "agent"):
                return mode
        return _chat_default("reply_mode")
    def _get_cooldown_seconds(self) -> int:
        if self._config is not None:
            val = getattr(self._config.chat, "reply_cooldown_seconds", None)
            if isinstance(val, int):
                return val
        return _chat_default("reply_cooldown_seconds")
    def _get_wait_cooldown_seconds(self) -> int:
        if self._config is not None:
            val = getattr(self._config.chat, "wait_cooldown_seconds", None)
            if isinstance(val, int):
                return val
        return _chat_default("wait_cooldown_seconds")
    def _get_sentence_cooldown_seconds(self) -> float:
        if self._config is not None:
            val = getattr(self._config.chat, "reply_sentence_cooldown_seconds", None)
            if isinstance(val, (int, float)):
                return float(val)
        return float(_chat_default("reply_sentence_cooldown_seconds"))
    def _get_private_chat_sentence_cooldown_seconds(self) -> float:
        if self._config is not None:
            val = getattr(
                self._config.chat, "private_chat_sentence_cooldown_seconds", None
            )
            if isinstance(val, (int, float)):
                return float(val)
        return float(_chat_default("private_chat_sentence_cooldown_seconds"))
    def _get_max_wait_seconds(self) -> int:
        if self._config is not None:
            val = getattr(self._config.chat, "agent_wait_max_seconds", None)
            if isinstance(val, int) and val > 0:
                return val
        return _chat_default("agent_wait_max_seconds")
    def _get_private_chat_suspend_wait_seconds(self) -> int:
        if self._config is not None:
            val = getattr(self._config.chat, "private_chat_suspend_wait_seconds", None)
            if isinstance(val, int) and val > 0:
                return val
        return _chat_default("private_chat_suspend_wait_seconds")
    def _get_agent_max_iterations(self) -> int:
        if self._config is not None:
            val = getattr(self._config.chat, "agent_max_iterations", None)
            if isinstance(val, int) and val > 0:
                return val
        return _chat_default("agent_max_iterations")
    def _get_group_agent_silent_timeout_seconds(self) -> float:
        if self._config is not None:
            val = getattr(self._config.chat, "group_agent_silent_timeout_seconds", None)
            if isinstance(val, (int, float)):
                return max(0.0, float(val))
        return float(_chat_default("group_agent_silent_timeout_seconds"))
    def _get_silent_nudge_settings(self) -> tuple[bool, int, int, float, int]:
        """读取沉默提醒(nudge)配置,容忍缺省与 None:返回 (开关, 首次轮数, 后续轮数, 秒数, 上限)。"""
        enabled = bool(_chat_default("silent_nudge_enabled"))
        first_rounds = int(_chat_default("silent_nudge_first_rounds"))
        repeat_rounds = int(_chat_default("silent_nudge_repeat_rounds"))
        seconds = float(_chat_default("silent_nudge_seconds"))
        max_emitted = int(_chat_default("silent_nudge_max"))
        if self._config is not None:
            chat = getattr(self._config, "chat", None)
            val = getattr(chat, "silent_nudge_enabled", None)
            if isinstance(val, bool):
                enabled = val
            val = getattr(chat, "silent_nudge_first_rounds", None)
            if isinstance(val, int) and not isinstance(val, bool):
                first_rounds = max(0, val)
            val = getattr(chat, "silent_nudge_repeat_rounds", None)
            if isinstance(val, int) and not isinstance(val, bool):
                repeat_rounds = max(0, val)
            val = getattr(chat, "silent_nudge_seconds", None)
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                seconds = max(0.0, float(val))
            val = getattr(chat, "silent_nudge_max", None)
            if isinstance(val, int) and not isinstance(val, bool):
                max_emitted = max(0, val)
        return enabled, first_rounds, repeat_rounds, seconds, max_emitted
    def _get_io_timeout_seconds(self) -> float:
        return 30.0
    def _get_dependency_timeout_seconds(self) -> float:
        return 10.0
    def _get_private_image_wait_timeout_seconds(self) -> float:
        # 视觉模型单次调用上限 60s；图片解析可能含下载(≤15s)+推理(≤60s)，
        # 取 90s 作为私聊回复等待图片解析的上限，避免无限阻塞。
        return 90.0
    def _get_prompt_timeout_seconds(self) -> float:
        return 30.0
    def _get_model_response_timeout_seconds(self, event: ReplyEvent) -> float:
        if (
            event.conversation_ref is not None
            and event.conversation_ref.kind == "group"
        ):
            timeout = self._get_group_agent_silent_timeout_seconds()
            if timeout > 0:
                return timeout
        return 120.0
    def _get_private_chat_max_tokens(self) -> int:
        if self._config is not None:
            val = getattr(self._config.chat, "private_chat_max_tokens", None)
            if isinstance(val, int) and val > 0:
                return val
        return _chat_default("private_chat_max_tokens")
    def _get_private_chat_new_message_collect_seconds(self) -> float:
        if self._config is not None:
            val = getattr(
                self._config.chat, "private_chat_new_message_collect_seconds", None
            )
            if isinstance(val, (int, float)) and val > 0:
                return float(val)
        return float(_chat_default("private_chat_new_message_collect_seconds"))
    def _get_native_vision_default_image_count(self) -> int:
        default = _chat_default("native_vision_default_image_count")
        value = getattr(getattr(self._config, "chat", None), "native_vision_default_image_count", None)
        return value if type(value) is int and value >= 0 else default
    def _get_ai_reply_check(self) -> bool:
        default = bool(_chat_default("ai_reply_check"))
        if self._config is None:
            return default
        chat = getattr(self._config, "chat", None)
        value = getattr(chat, "ai_reply_check", None)
        return value if isinstance(value, bool) else default
    def _get_ai_reply_check_lightweight(self) -> bool:
        """轻量检查仅在完整检查关闭时生效。"""
        if self._get_ai_reply_check():
            return False
        default = bool(_chat_default("ai_reply_check_lightweight"))
        if self._config is None:
            return default
        chat = getattr(self._config, "chat", None)
        value = getattr(chat, "ai_reply_check_lightweight", None)
        return value if isinstance(value, bool) else default
    def _get_bot_name(self) -> str:
        if self._config is None:
            return "Bot"
        bot = getattr(self._config, "bot", None)
        value = getattr(bot, "nick_name", "Bot")
        return value.strip() if isinstance(value, str) and value.strip() else "Bot"
    def _get_bot_account(self) -> int:
        if self._config is None:
            return 0
        bot = getattr(self._config, "bot", None)
        value = getattr(bot, "account", 0) or 0
        return value
    def _show_boundary_markers(self) -> bool:
        if self._config is None:
            return False
        chat = getattr(self._config, "chat", None)
        return bool(getattr(chat, "show_last_reply_markers", _chat_default("show_last_reply_markers")))
    def _inject_member_archives(self) -> bool:
        """群聊是否注入群员个人档案（默认 False，由 agent 按需读取）。"""
        if self._config is None:
            return False
        chat = getattr(self._config, "chat", None)
        return bool(getattr(chat, "inject_member_archives", _chat_default("inject_member_archives")))
    def _cost_pipeline_enabled(self) -> bool:
        if self._config is None:
            return False
        chat = getattr(self._config, "chat", None)
        enabled = bool(getattr(chat, "cost_pipeline_enabled", _chat_default("cost_pipeline_enabled")))
        return enabled and self._cache_calculator is not None
    def _get_cost_pipeline_threshold(self) -> int:
        if self._config is not None:
            chat = getattr(self._config, "chat", None)
            val = getattr(chat, "cost_pipeline_threshold", None)
            if isinstance(val, int) and val >= 0:
                return val
        return _chat_default("cost_pipeline_threshold")
    def _get_long_reply_fallback_template(self) -> str:
        default = "{bot_name}懒得和你说道理，你不配听"
        if self._prompt_store is not None:
            value = self._prompt_store.template("long_reply_fallback", default=default)
            if value and value.strip():
                return value
        return default
    def _get_long_reply_max_length(self) -> int:
        if self._config is None:
            return 300
        chat = getattr(self._config, "chat", None)
        value = getattr(chat, "long_reply_max_length", 300)
        return value if isinstance(value, int) and value > 0 else 300
    def _get_long_reply_max_sentence_count(self) -> int:
        if self._config is None:
            return 12
        chat = getattr(self._config, "chat", None)
        value = getattr(chat, "long_reply_max_sentence_count", 12)
        return value if isinstance(value, int) and value > 0 else 12
    def _get_enable_ai_reply_regenerate(self) -> bool:
        if self._config is None:
            return True
        chat = getattr(self._config, "chat", None)
        value = getattr(chat, "enable_ai_reply_regenerate_on_length_limit", True)
        return bool(value)
    def _get_group_chat_reply_lifespan(self) -> int:
        if self._config is not None:
            val = getattr(self._config.chat, "group_chat_reply_lifespan", None)
            if isinstance(val, int) and val >= 0:
                return val
        return 5
    def _get_group_chat_suspend_wait_seconds(self) -> int:
        if self._config is not None:
            val = getattr(self._config.chat, "group_chat_suspend_wait_seconds", None)
            if isinstance(val, int) and val > 0:
                return val
        return 3600
    def _get_at_mention_reply_delay_seconds(self) -> float:
        if self._config is not None:
            val = getattr(self._config.chat, "at_mention_reply_delay_seconds", None)
            if isinstance(val, (int, float)) and val >= 0:
                return float(val)
        return 0.0
