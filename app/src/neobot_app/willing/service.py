from __future__ import annotations

import hashlib
import importlib.util
import inspect
import re
from pathlib import Path
from typing import Any

from neobot_adapter.model.message import GroupMessage, PrivateMessage
from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.config.schemas.bot import BotConfig
from neobot_app.core.paths import get_data_dir
from neobot_app.message.queue import MessageQueue
from neobot_app.willing.builtin import QuailWillingManager, clamp_probability
from neobot_app.willing.models import (
    BaseWillingManager,
    RuntimeWillingConfig,
    WillingContext,
    WillingDecision,
)

ChatMessage = PrivateMessage | GroupMessage


class WillingService:
    _README_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "README.md"

    def __init__(
        self,
        config: BotConfig,
        logger: Logger | None = None,
    ) -> None:
        self._config = config
        self._logger = logger or NullLogger()
        self._custom_dir = get_data_dir() / "Willing"
        self._custom_dir.mkdir(parents=True, exist_ok=True)
        self._sync_runtime_documents()
        self._manager = self._load_manager(config.willing.manager_name)
        self._runtime_config = RuntimeWillingConfig()

    @property
    def manager(self) -> BaseWillingManager:
        return self._manager

    @property
    def custom_dir(self) -> Path:
        return self._custom_dir

    @property
    def runtime_config(self) -> RuntimeWillingConfig:
        return self._runtime_config

    def evaluate(
        self,
        *,
        message: ChatMessage,
        queue: MessageQueue,
        queue_key: str,
        reply_mode: str | None = None,
    ) -> WillingDecision:
        if reply_mode is None:
            reply_mode = getattr(self._config.chat, "reply_mode", "common") or "common"
        context = self._build_context(
            message=message,
            queue=queue,
            queue_key=queue_key,
            reply_mode=reply_mode,
        )
        return self._manager.evaluate(context)

    # ── Part B 运行时系数调整（供 AI 工具调用） ──

    def set_runtime_global_coefficient(self, value: float) -> str:
        self._runtime_config.global_coefficient = clamp_probability(value)
        self._logger.info("runtime global coefficient updated", value=value)
        return f"全局回复系数已设为 {self._runtime_config.global_coefficient:.3f}"

    def set_runtime_conversation_coefficient(self, conv_id: str, value: float) -> str:
        conv_id = str(conv_id).strip()
        self._runtime_config.conversation_coefficients[conv_id] = clamp_probability(value)
        self._logger.info("runtime conversation coefficient updated", conv_id=conv_id, value=value)
        return f"会话 {conv_id} 的回复系数已设为 {clamp_probability(value):.3f}"

    def add_runtime_blacklist(self, conv_id: str) -> str:
        conv_id = str(conv_id).strip()
        self._runtime_config.blacklisted_conversations.add(conv_id)
        self._logger.info("runtime blacklist added", conv_id=conv_id)
        return f"已将 {conv_id} 加入临时黑名单"

    def remove_runtime_blacklist(self, conv_id: str) -> str:
        conv_id = str(conv_id).strip()
        self._runtime_config.blacklisted_conversations.discard(conv_id)
        self._logger.info("runtime blacklist removed", conv_id=conv_id)
        return f"已将 {conv_id} 从临时黑名单移除"

    def remove_runtime_conversation_coefficient(self, conv_id: str) -> str:
        conv_id = str(conv_id).strip()
        removed = self._runtime_config.conversation_coefficients.pop(conv_id, None)
        if removed is not None:
            self._logger.info("runtime conversation coefficient removed", conv_id=conv_id)
            return f"已移除会话 {conv_id} 的临时回复系数（原值 {removed:.3f}）"
        return f"会话 {conv_id} 没有临时回复系数"

    def get_runtime_config_summary(self) -> str:
        rt = self._runtime_config
        parts = [f"全局系数: {rt.global_coefficient:.3f}"]
        if rt.conversation_coefficients:
            items = ", ".join(f"{k}={v:.3f}" for k, v in rt.conversation_coefficients.items())
            parts.append(f"会话系数: {items}")
        if rt.blacklisted_conversations:
            parts.append(f"临时黑名单: {', '.join(sorted(rt.blacklisted_conversations))}")
        return "\n".join(parts)

    def _sync_runtime_documents(self) -> None:
        template_path = self._README_TEMPLATE_PATH
        if not template_path.exists():
            self._logger.warning("willing readme template missing", template_path=template_path)
            return

        target_path = self._custom_dir / template_path.name
        should_write = (not target_path.exists()) or (
            self._sha256_file(target_path) != self._sha256_file(template_path)
        )
        if not should_write:
            return

        target_path.write_text(template_path.read_text(encoding="utf-8"), encoding="utf-8")
        self._logger.info(
            "synced willing runtime document",
            target_path=target_path,
            template_path=template_path,
        )

    def _load_manager(self, manager_name: str) -> BaseWillingManager:
        normalized = (manager_name or "").strip() or "Quail"
        if normalized.casefold() == "quail":
            return QuailWillingManager()

        module_path = self._resolve_custom_manager_path(normalized)
        if module_path is None:
            raise FileNotFoundError(
                f"Custom WillingManager '{normalized}' was not found under {self._custom_dir}"
            )

        module_name = f"neobot_app_custom_willing_{normalized}"
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to load custom WillingManager module: {module_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        manager_obj = getattr(module, "WillingManager", None)
        if manager_obj is None:
            raise AttributeError(
                f"Custom manager module '{module_path.name}' must define a WillingManager"
            )

        manager = self._instantiate_manager(manager_obj)
        if not isinstance(manager, BaseWillingManager) and not hasattr(manager, "evaluate"):
            raise TypeError("Custom WillingManager must inherit BaseWillingManager or provide evaluate()")

        return manager

    def _instantiate_manager(self, manager_obj: Any) -> BaseWillingManager:
        if isinstance(manager_obj, BaseWillingManager):
            return manager_obj

        if not inspect.isclass(manager_obj):
            return manager_obj

        kwargs: dict[str, Any] = {}
        signature = inspect.signature(manager_obj)
        parameters = signature.parameters
        if "config" in parameters:
            kwargs["config"] = self._config
        if "logger" in parameters:
            kwargs["logger"] = self._logger.bind(component="willing.custom")
        return manager_obj(**kwargs)

    def _resolve_custom_manager_path(self, manager_name: str) -> Path | None:
        safe_name = manager_name.strip()
        candidates = [
            self._custom_dir / f"{safe_name}.py",
            self._custom_dir / safe_name / "__init__.py",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _build_context(
        self,
        *,
        message: ChatMessage,
        queue: MessageQueue,
        queue_key: str,
        reply_mode: str = "common",
    ) -> WillingContext:
        conversation_type = "group" if isinstance(message, GroupMessage) else "private"
        text = self._render_message_text(message)
        observed_messages = self._observed_messages(queue, queue_key)
        allowed, block_reason = self._is_conversation_allowed(conversation_type, queue_key)
        base_probability = self._base_probability(conversation_type)
        conversation_coefficient = self._conversation_coefficient(message)
        mentioned_bot = self._mentioned_bot(message)
        called_bot_name = self._called_bot_name(text)
        replied_to_message = self._has_reply_segment(message)
        matched_keywords = self._matched_keywords(text)

        at_guaranteed = (
            self._config.chat.at_mention_guaranteed_reply
            and mentioned_bot
        )

        if reply_mode == "agent":
            config_global_coeff = self._config.chat.willing_agent_global_coefficient
        else:
            config_global_coeff = self._config.chat.willing_global_coefficient

        return WillingContext(
            manager_name=self._manager.name,
            conversation_type=conversation_type,
            conversation_id=queue_key,
            sender_id=str(message.user_id or ""),
            message_id=message.message_id,
            text=text,
            raw_message=str(message.raw_message or ""),
            queue=queue,
            queue_size=queue.size(queue_key),
            queue_text=queue.to_text(queue_key),
            observe_window=max(1, int(self._config.willing.observe_window)),
            observed_messages_text=tuple(observed_messages),
            base_probability=base_probability,
            conversation_coefficient=conversation_coefficient,
            reply_threshold=self._config.willing.reply_threshold,
            bot_account=int(self._config.bot.account),
            bot_name=self._config.bot.nick_name,
            bot_aliases=tuple(self._config.bot.alias_name or []),
            mentioned_bot=mentioned_bot,
            called_bot_name=called_bot_name,
            replied_to_message=replied_to_message,
            has_question=self._has_question(text),
            matched_keywords=tuple(matched_keywords),
            is_direct_message=isinstance(message, PrivateMessage),
            is_allowed=allowed,
            block_reason=block_reason,
            message=message,
            at_guaranteed_reply=at_guaranteed,
            config_global_coefficient=config_global_coeff,
            runtime_config=self._runtime_config,
        )

    def _observed_messages(self, queue: MessageQueue, queue_key: str) -> list[str]:
        window = max(1, int(self._config.willing.observe_window))
        recent_messages = list(queue.iterate_from_newest(queue_key))[:window]
        rendered = [self._render_message_text(item) for item in reversed(recent_messages)]
        return [item for item in rendered if item]

    def _is_conversation_allowed(self, conversation_type: str, queue_key: str) -> tuple[bool, str]:
        if conversation_type == "group":
            if self._config.message.enable_group is False:
                return False, "group_disabled"
            return self._check_list_rule(
                queue_key,
                self._config.chat.group_use_black_list,
                self._config.chat.group_list or [],
                black_list_reason="group_blacklisted",
                white_list_reason="group_not_in_whitelist",
            )

        if self._config.message.enable_private is False:
            return False, "private_disabled"
        return self._check_list_rule(
            queue_key,
            self._config.chat.friend_use_black_list,
            self._config.chat.friend_list or [],
            black_list_reason="friend_blacklisted",
            white_list_reason="friend_not_in_whitelist",
        )

    @staticmethod
    def _check_list_rule(
        queue_key: str,
        use_black_list: bool,
        configured_list: list[str],
        *,
        black_list_reason: str,
        white_list_reason: str,
    ) -> tuple[bool, str]:
        normalized = {str(item) for item in configured_list if str(item).strip()}
        if not normalized:
            return True, ""

        in_list = queue_key in normalized
        if use_black_list and in_list:
            return False, black_list_reason
        if not use_black_list and not in_list:
            return False, white_list_reason
        return True, ""

    def _base_probability(self, conversation_type: str) -> float:
        if conversation_type == "group":
            return self._clamp_probability(self._config.chat.group_chat_chance)
        return self._clamp_probability(self._config.chat.friend_chat_chance)

    def _conversation_coefficient(self, message: ChatMessage) -> float:
        if isinstance(message, GroupMessage) and message.group_id is not None:
            coefficients = self._config.chat.group_Response_coefficient or {}
            return max(0.0, float(coefficients.get(str(message.group_id), 1.0)))

        if isinstance(message, PrivateMessage) and message.user_id is not None:
            coefficients = getattr(self._config.chat, "friend_Response_coefficient", None) or {}
            return max(0.0, float(coefficients.get(str(message.user_id), 1.0)))

        return 1.0

    def _mentioned_bot(self, message: ChatMessage) -> bool:
        target = str(self._config.bot.account)
        if message.message:
            for segment in message.message:
                segment_type = getattr(segment, "type", None)
                if hasattr(segment_type, "value"):
                    segment_type = segment_type.value
                if str(segment_type) != "at":
                    continue
                raw_data = getattr(segment, "data", None)
                data = raw_data if isinstance(raw_data, dict) else (
                    raw_data.model_dump(exclude_none=True) if hasattr(raw_data, "model_dump") else {}
                )
                if str(data.get("qq") or "") == target:
                    return True

        raw_message = str(message.raw_message or "")
        return f"[CQ:at,qq={target}" in raw_message

    def _called_bot_name(self, text: str) -> bool:
        names = [self._config.bot.nick_name, *(self._config.bot.alias_name or []), str(self._config.bot.account)]
        lowered_text = text.casefold()
        return any(name and str(name).casefold() in lowered_text for name in names)

    @staticmethod
    def _has_reply_segment(message: ChatMessage) -> bool:
        if message.message:
            for segment in message.message:
                segment_type = getattr(segment, "type", None)
                if hasattr(segment_type, "value"):
                    segment_type = segment_type.value
                if str(segment_type) == "reply":
                    return True
        return "[CQ:reply" in str(message.raw_message or "")

    @staticmethod
    def _has_question(text: str) -> bool:
        return ("?" in text) or ("\uFF1F" in text)

    def _matched_keywords(self, text: str) -> list[str]:
        lowered_text = text.casefold()
        matched: list[str] = []
        for rule in self._config.chat.key_word or []:
            if not rule.get("enabled", False):
                continue
            for keyword in rule.get("keywords", []):
                keyword_text = str(keyword).strip()
                if keyword_text and keyword_text.casefold() in lowered_text:
                    matched.append(keyword_text)
        return matched

    @staticmethod
    def _render_message_text(message: ChatMessage) -> str:
        if message.message:
            parts: list[str] = []
            for segment in message.message:
                segment_type = getattr(segment, "type", None)
                if hasattr(segment_type, "value"):
                    segment_type = segment_type.value
                raw_data = getattr(segment, "data", None)
                if isinstance(raw_data, dict):
                    data = raw_data
                elif hasattr(raw_data, "model_dump"):
                    data = raw_data.model_dump(exclude_none=True)
                else:
                    data = {}

                if str(segment_type) == "text":
                    parts.append(str(data.get("text") or ""))
                elif str(segment_type) == "at":
                    qq = str(data.get("qq") or "")
                    name = str(data.get("name") or qq or "unknown")
                    parts.append(f"@{name}")
                elif str(segment_type) == "reply":
                    parts.append("[reply]")
                elif str(segment_type) in {"image", "cardimage"}:
                    parts.append("[image]")
                elif str(segment_type) == "face":
                    parts.append("[face]")
                elif str(segment_type):
                    parts.append(f"[{segment_type}]")
            text = "".join(parts).strip()
            if text:
                return text

        raw_message = str(message.raw_message or "").strip()
        if not raw_message:
            return ""

        text = re.sub(r"\[CQ:at,qq=([^,\]]+)(?:,[^\]]*)?\]", r"@\1", raw_message)
        text = re.sub(r"\[CQ:reply(?:,[^\]]*)?\]", "[reply]", text)
        text = re.sub(r"\[CQ:(image|cardimage)(?:,[^\]]*)?\]", "[image]", text)
        text = re.sub(r"\[CQ:face(?:,[^\]]*)?\]", "[face]", text)
        text = re.sub(r"\[CQ:([^,\]]+)(?:,[^\]]*)?\]", r"[\1]", text)
        return text.strip()

    @staticmethod
    def _clamp_probability(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @staticmethod
    def _sha256_file(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
