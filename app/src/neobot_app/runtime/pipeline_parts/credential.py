"""命令同步回复与凭据签发链路。"""

from __future__ import annotations

import time
from typing import Any

from neobot_adapter.model.message import GroupMessage
from neobot_adapter.model.message import PrivateMessage
from neobot_app.bot_accounts import bot_account_for_message
from neobot_app.message.queue import MessageQueue

from .helpers import _credential_message_text, _safe_int


class _PipelineCredentialMixin:
    def _start_command_sync_reply(
        self,
        *,
        message: PrivateMessage | GroupMessage,
        queue: MessageQueue,
        queue_key: str,
        background: str = "",
        preactivate: tuple[str, ...] = (),
    ) -> None:
        """sync_reply 命令 / 插件消息意图:把背景内容交给回复管线触发一次回复。

        preactivate 是本轮要在模型工具表里预先激活的技能包（插件意图入口用）。
        """
        if self._reply_orchestrator is None:
            return
        from neobot_app.willing.models import WillingDecision

        decision = WillingDecision(
            manager_name="command",
            probability=1.0,
            should_reply=True,
            reasons=("command_sync_reply",),
        )
        pre_reply_msg_id = queue.get_last_message_id(queue_key)

        async def on_reply_done() -> None:
            self._replying_queues.discard(queue_key)
            await self._process_post_reply_queue(queue_key)

        started = self._reply_orchestrator.start_reply(
            message=message,
            queue=queue,
            queue_key=queue_key,
            decision=decision,
            pre_reply_message_id=pre_reply_msg_id,
            on_reply_done=on_reply_done,
            background_content=background,
            preactivate=tuple(preactivate or ()),
        )
        if started is None:
            # 管线被拒（编排器已关闭／同会话管线在跑／冷却中）：此时不能 discard ——
            # 标记可能属于另一条**正在运行**的管线（同会话管线在跑正是这里的常见
            # 拒绝原因），删掉它会破坏那条管线的分流守卫，让后续消息走意愿路径并
            # 在同样被拒时丢失。标记改为「启动成功后才打」，这里什么都不用做。
            self._logger.debug(
                "命令同步回复未能启动，未设置回复中标记", queue_key=queue_key
            )
            return
        self._replying_queues.add(queue_key)

    async def _try_issue_credential(
        self,
        message: PrivateMessage | GroupMessage,
        *,
        kind: str,
        queue_key: str,
        queue: MessageQueue,
    ) -> bool:
        """检查消息是否为待签发凭据文本;是则签发并返回 True(已处理)。"""
        credential_manager = self._credential_manager
        if credential_manager is None:
            return False
        from neobot_app.bot_accounts import identity_text
        from neobot_app.user_identity import trusted_qq_for_user

        raw_user = getattr(message, "user_id", None)
        user_text = identity_text(raw_user)
        bot_account = self._bot_account_id(message)
        # bot 自己发送的消息不能触发自我签发(防审批失效)；user_id 可能是 openid 字符串
        if bot_account and user_text and user_text == identity_text(bot_account):
            return False
        # 凭据签发沿用管理员真实 QQ 号：openid 用户只能通过 /linkqq 绑定的 trusted
        # 映射换算出 QQ 号；未绑定则不具签发权限（issuer_id=0 必然被权限校验拒绝）。
        issuer_id = trusted_qq_for_user(raw_user, getattr(message, "neobot_channel", None)) or (
            _safe_int(user_text) or 0
        )
        # 使用纯文本内容匹配(不含"发送者: "前缀)
        text = _credential_message_text(message)
        text = text.strip()
        if not text:
            return False
        self._maybe_cleanup_credentials()
        chat_flow = f"{kind}:{queue_key}"
        # 该会话既没有待签发、也没有可用凭据时直接放行：没有可签发的目标，后面的
        # 查表与计数都没有意义，普通聊天也不会被误算成「猜码失败」。
        if not credential_manager.has_pending_or_active(chat_flow=chat_flow):
            return False
        issue = credential_manager.try_issue(
            chat_flow=chat_flow,
            code=text,
            issuer_id=issuer_id,
        )
        if not issue.ok:
            if issue.error == "permission_denied" and issue.credential is not None:
                # 权限不足:明确拒绝,避免 AI 误回复
                await self._send_credential_notice(
                    message, queue, queue_key,
                    "该凭据需要更高级别的管理员签发,你没有权限。",
                )
                return True
            if (
                issue.error == "rate_limited"
                and credential_manager.looks_like_code(text)
                and credential_manager.can_issue_pending(
                    chat_flow=chat_flow, issuer_id=issuer_id
                )
                and credential_manager.take_rate_limit_notice(chat_flow)
            ):
                # 冷却期里连正确码也不签发：只对能签发的人提示一次，避免任意
                # 成员反复触发回执，也避免用回执探测会话是否在冷却。
                await self._send_credential_notice(
                    message, queue, queue_key,
                    "签发尝试太频繁，等几分钟后再发一次凭据码。",
                )
                return True
            self._logger.debug(
                "凭据签发未命中，按普通消息处理",
                chat_flow=chat_flow,
                error=issue.error,
                issuer_id=issuer_id,
            )
            return False  # 非凭据文本(not_found/expired/状态异常):正常管线
        credential = issue.credential
        if credential is None:
            return False
        # 仅首次签发(pending → active)时通知并触发 bot 继续执行;
        # 重复发送(幂等)静默,避免任意成员反复触发
        if issue.newly_issued:
            await self._send_credential_notice(
                message, queue, queue_key,
                f"凭据已确认(用途: {credential.action}),可以执行对应操作了。",
            )
            background = (
                f"凭据已签发: 用途 {credential.action},会话 {chat_flow}。\n"
                "如正在等待此凭据执行风险操作(踢人/退群等),现在可以继续执行。"
            )
            self._start_command_sync_reply(
                message=message, queue=queue, queue_key=queue_key, background=background,
            )
        return True

    def _bot_account_id(self, message: Any = None) -> int:
        """机器人自身 QQ 号：统一提供者按消息 self_id / 通道 / 配置解析。"""
        return bot_account_for_message(message, self._config)

    def _maybe_cleanup_credentials(self) -> None:
        """定期清理过期/已用凭据(避免内存无界增长)。"""
        credential_manager = self._credential_manager
        if credential_manager is None:
            return
        now = time.time()
        if now - getattr(self, "_last_credential_cleanup", 0.0) < 60.0:
            return
        self._last_credential_cleanup = now
        try:
            credential_manager.cleanup()
        except Exception:
            pass

    async def _send_credential_notice(
        self,
        message: PrivateMessage | GroupMessage,
        queue: MessageQueue,
        queue_key: str,
        text: str,
    ) -> None:
        """发送凭据相关提示(不触发 AI 回复)。"""
        from neobot_contracts.models import ConversationRef

        conv_ref = ConversationRef(
            kind="group" if isinstance(message, GroupMessage) else "private",
            id=queue_key,
        )
        try:
            await self.adapter.send(
                conv_ref, [{"type": "text", "data": {"text": text}}]
            )
        except Exception as exc:
            self._logger.warning(f"凭据提示发送失败: {exc}")
