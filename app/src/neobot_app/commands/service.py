"""命令服务:消息进入 → 触发判断 → 解析 → 权限 → 执行 → 回复。

接入 EventPipeline:群聊/私聊消息在 _is_bot_self 检查之前调用 handle_message。
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from neobot_app.commands.builtin import build_builtin_commands
from neobot_app.commands.model import (
    CommandContext,
    CommandHandleResult,
)
from neobot_app.commands.permissions import PermissionManager
from neobot_app.commands.registry import CommandRegistry

SendCallback = Callable[[str, str, str, int | None], Awaitable[Any]]
ConfigSaveCallback = Callable[[list[int]], Awaitable[str]]
RestartCallback = Callable[[], Any]
ConfigReloadCallback = Callable[[], Awaitable[Any]]


class CommandService:
    """命令系统入口与执行器。"""

    def __init__(
        self,
        *,
        config: Any,
        adapter: Any = None,
        registry: CommandRegistry | None = None,
        send_callback: SendCallback | None = None,
        config_save_callback: ConfigSaveCallback | None = None,
        logger: Any = None,
        register_builtins: bool = True,
        markdown_image_converter: Any = None,
        file_server: Any = None,
        sleep_service: Any = None,
        freeze_service: Any = None,
        config_reload_callback: ConfigReloadCallback | None = None,
    ) -> None:
        self._config = config
        self._adapter = adapter
        self._registry = registry if registry is not None else CommandRegistry()
        self._permissions = PermissionManager(config)
        self._send_callback = send_callback
        self._config_save_callback = config_save_callback
        self._logger = logger
        self._restart_callback: RestartCallback | None = None
        self._markdown_image_converter = markdown_image_converter
        self._file_server = file_server
        self._sleep_service = sleep_service
        self._freeze_service = freeze_service
        self._config_reload_callback = config_reload_callback
        if register_builtins:
            for command in build_builtin_commands(self):
                self._registry.register(command)

    # ── 注入 ──

    def set_restart_callback(self, callback: RestartCallback) -> None:
        """注入重启回调(/reboot 使用)。"""
        self._restart_callback = callback

    def request_restart(self) -> bool:
        if self._restart_callback is None:
            return False
        self._restart_callback()
        return True

    def set_config_reload_callback(self, callback: ConfigReloadCallback) -> None:
        """注入配置热重载回调（/reload 命令使用）。"""
        self._config_reload_callback = callback

    async def reload_config(self) -> dict[str, Any] | None:
        """触发不重启进程的配置热重载；未注入回调时返回 None。"""
        callback = self._config_reload_callback
        if callback is None:
            return None
        result = callback()
        if hasattr(result, "__await__"):
            result = await result
        return result if isinstance(result, dict) else None

    @property
    def permissions(self) -> PermissionManager:
        return self._permissions

    @property
    def registry(self) -> CommandRegistry:
        return self._registry

    @property
    def sleep_service(self) -> Any:
        """睡眠服务(/sleep /awake 命令使用;未注入时为 None)。"""
        return self._sleep_service

    @property
    def freeze_service(self) -> Any:
        """冻结服务(/freeze /unfreeze 命令使用;未注入时为 None)。"""
        return self._freeze_service

    # ── 消息入口 ──

    async def handle_message(
        self,
        message: Any,
        *,
        kind: str,
        queue_key: str,
    ) -> CommandHandleResult:
        """处理一条消息,返回是否已消费及是否需同步触发回复管线。

        - 群聊:必须被 @bot 且文本为命令形态
        - 私聊:文本为命令形态即可
        - 非命令形态 / 未注册命令:返回 consumed=False(移交正常管线)
        """
        bot_account = self._bot_account()
        at_qqs = self._collect_at_qqs(message)
        text = self._message_text(message)

        # 触发条件:群聊需被 @bot
        if kind == "group":
            if bot_account not in at_qqs:
                return CommandHandleResult(consumed=False)
        elif kind not in ("private", "friend"):
            return CommandHandleResult(consumed=False)

        user_id = int(getattr(message, "user_id", 0) or 0)
        parsed = self._registry.match(text)
        if parsed is None:
            # 非命令形态(如"大家 /help"):移交正常管线
            return CommandHandleResult(consumed=False)
        command, raw_args, args = parsed
        if command is None:
            # / 开头但命令未注册:移交正常管线
            return CommandHandleResult(consumed=False)

        # 权限检查
        if not self._permissions.can(user_id, command.permission):
            await self._send_text(
                kind, queue_key,
                f"你没有权限使用 {command.display_name}"
                f"(需要权限:{_permission_label(command.permission)})",
                at_user_id=user_id,
            )
            return CommandHandleResult(consumed=True)

        context = CommandContext(
            service=self,
            kind=kind,
            conv_id=queue_key,
            user_id=user_id,
            command=command,
            raw_args=raw_args,
            args=args,
            at_qqs=sorted(at_qqs),
            message=message,
        )
        try:
            result_text = await command.handler(context)
        except Exception as exc:
            self._log(f"命令 /{command.name} 执行失败: {exc}")
            result_text = f"命令执行失败: {exc}"

        if command.sync_reply:
            # 同步触发回复管线:结果作为背景内容交给主 Agent 处理
            background = (
                "<这是新的必须要回答的内容>\n"
                f"命令 /{command.name} 执行结果:\n{result_text}\n"
                "</这是新的必须要回答的内容>"
            )
            return CommandHandleResult(consumed=True, background=background)

        if result_text is not None:
            # handler 返回 None 表示已自行发送回复(如图片),不再重复发送
            await self._send_text(kind, queue_key, result_text, at_user_id=user_id)
        return CommandHandleResult(consumed=True)

    # ── 消息解析辅助 ──

    def _bot_account(self) -> int:
        try:
            return int(getattr(getattr(self._config, "bot", None), "account", 0) or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _segment_type(segment: Any) -> str:
        value = (
            segment.get("type")
            if isinstance(segment, dict)
            else getattr(segment, "type", None)
        )
        value = getattr(value, "value", value)
        return str(value or "")

    @staticmethod
    def _segment_data(segment: Any) -> dict[str, Any]:
        if isinstance(segment, dict):
            data = segment.get("data", {}) or {}
            return data if isinstance(data, dict) else {}
        data = getattr(segment, "data", None)
        if isinstance(data, dict):
            return data
        return {}

    @staticmethod
    def _collect_at_qqs(message: Any) -> set[int]:
        """收集消息中 at 段的 QQ 号。"""
        result: set[int] = set()
        segments = getattr(message, "message", None)
        if not segments:
            return result
        for segment in segments:
            if CommandService._segment_type(segment) not in ("at", "mention"):
                continue
            data = CommandService._segment_data(segment)
            raw_qq = data.get("qq") or data.get("user_id")
            try:
                qq = int(str(raw_qq))
            except (TypeError, ValueError):
                continue
            if qq > 0:
                result.add(qq)
        return result

    @staticmethod
    def _message_text(message: Any) -> str:
        """提取消息的纯文本(不含 at/图片等段)。"""
        parts: list[str] = []
        segments = getattr(message, "message", None)
        if not segments:
            return ""
        for segment in segments:
            if CommandService._segment_type(segment) != "text":
                continue
            data = CommandService._segment_data(segment)
            text = data.get("text")
            if text:
                parts.append(str(text))
        return "".join(parts)

    # ── 发送与日志 ──

    async def reply_to(
        self, kind: str, conv_id: str, text: str, *, at_user_id: int | None
    ) -> None:
        await self._send_text(kind, conv_id, text, at_user_id=at_user_id)

    async def send_markdown_image(
        self,
        kind: str,
        conv_id: str,
        markdown: str,
        *,
        at_user_id: int | None = None,
    ) -> bool:
        """将 markdown 渲染为图片发送;成功返回 True,失败返回 False(调用方降级)。

        依赖 markdown_image_converter 与 file_server;任一缺失即返回 False。
        """
        if (
            self._markdown_image_converter is None
            or self._file_server is None
            or self._adapter is None
        ):
            return False
        try:
            image_path = await self._markdown_image_converter.convert(markdown)
        except Exception as exc:
            self._log(f"markdown 渲染失败,降级文本发送: {exc}")
            return False

        from neobot_app.utils.media_sender import prepare_image_segment

        from neobot_contracts.models import ConversationRef

        segments: list[dict[str, Any]] = []
        if kind == "group" and at_user_id is not None:
            segments.append({"type": "at", "data": {"qq": str(at_user_id)}})
        segments.append(prepare_image_segment(self._file_server, image_path))
        conv_ref = ConversationRef(
            kind="group" if kind == "group" else "private", id=str(conv_id)
        )
        try:
            await self._adapter.send(conv_ref, segments)
            return True
        except Exception as exc:
            self._log(f"命令图片发送失败: {exc}")
            return False

    async def _send_text(
        self, kind: str, conv_id: str, text: str, *, at_user_id: int | None
    ) -> None:
        if self._send_callback is not None:
            await self._send_callback(kind, conv_id, text, at_user_id)
            return
        if self._adapter is None:
            return
        from neobot_contracts.models import ConversationRef

        segments: list[dict[str, Any]] = []
        if kind == "group" and at_user_id is not None:
            segments.append({"type": "at", "data": {"qq": str(at_user_id)}})
        if text:
            segments.append({"type": "text", "data": {"text": text}})
        if not segments:
            return
        conv_ref = ConversationRef(kind="group" if kind == "group" else "private", id=str(conv_id))
        try:
            await self._adapter.send(conv_ref, segments)
        except Exception as exc:
            self._log(f"命令回复发送失败: {exc}")

    async def save_sub_admins(self, new_list: list[int]) -> str:
        """保存次级管理员列表(经注入的回调,含配置写回与热重载)。"""
        if self._config_save_callback is None:
            return "错误: 配置保存能力未注入"
        return await self._config_save_callback(new_list)

    def _log(self, message: str) -> None:
        logger = self._logger
        if logger is None:
            return
        try:
            logger.warning(message)
        except Exception:
            pass


def _permission_label(level: int) -> str:
    from neobot_app.commands.model import permission_name

    return permission_name(level)
