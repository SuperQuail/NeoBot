from __future__ import annotations

import time
from typing import Any

import httpx

from neobot_contracts.ports.logging import Logger, NullLogger


class BalanceChecker:
    """DeepSeek 余额检查与低余额预警。

    仅在主模型使用 DeepSeek 且配置了管理员账户时生效。
    余额低于阈值时触发一次性通知，余额回升后自动重置，下次低于阈值时再次通知。
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        notification_hub: Any = None,
        admin_accounts: list[str] | None = None,
        balance_threshold: float = 1.0,
        cooldown_seconds: int = 300,
        logger: Logger | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._hub = notification_hub
        self._admin_accounts = admin_accounts or []
        self._threshold = balance_threshold
        self._cooldown = cooldown_seconds
        self._logger = logger or NullLogger()
        self._last_check_time: float = 0.0
        self._notification_sent: bool = False

    @property
    def is_enabled(self) -> bool:
        return bool(self._api_key and self._admin_accounts)

    async def check_and_notify(self) -> None:
        if not self.is_enabled:
            return

        now = time.monotonic()
        if now - self._last_check_time < self._cooldown:
            return

        self._last_check_time = now

        try:
            balance_data = await self._query_balance()
        except Exception as exc:
            self._logger.warning("余额查询失败", error=str(exc))
            return

        total_balance = self._extract_total_balance(balance_data)
        if total_balance is None:
            self._logger.debug("无法从余额数据中提取余额信息", data=balance_data)
            return

        self._logger.debug(
            "余额查询成功",
            balance=total_balance,
            threshold=self._threshold,
            notification_sent=self._notification_sent,
        )

        if total_balance < self._threshold and not self._notification_sent:
            self._notification_sent = True
            await self._send_low_balance_notification(total_balance)
        elif total_balance >= self._threshold and self._notification_sent:
            self._notification_sent = False
            self._logger.info("余额已恢复至阈值以上，通知状态已重置", balance=total_balance)

    async def _query_balance(self) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{self._base_url}/user/balance",
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def _extract_total_balance(data: dict[str, Any]) -> float | None:
        balance_infos = data.get("balance_infos")
        if not isinstance(balance_infos, list):
            return None
        total = 0.0
        for info in balance_infos:
            if isinstance(info, dict) and info.get("currency") == "CNY":
                try:
                    total += float(info.get("total_balance", 0))
                except (TypeError, ValueError):
                    continue
        return total

    async def _send_low_balance_notification(self, balance: float) -> None:
        if self._hub is None:
            self._logger.warning("通知中心未配置，无法发送余额不足通知")
            return

        content = (
            f"【系统通知】DeepSeek 账户余额不足\n"
            f"当前余额：{balance:.4f} CNY\n"
            f"预警阈值：{self._threshold} CNY\n"
            f"请尽快充值以避免服务中断。"
        )
        self._logger.warning("余额不足，发送通知", balance=balance, threshold=self._threshold)

        for admin_id in self._admin_accounts:
            try:
                await self._hub.publish(
                    source="balance_checker",
                    kind="private",
                    conversation_id=str(admin_id),
                    content=content,
                    reasons=["DeepSeek 余额不足预警"],
                )
            except Exception as exc:
                self._logger.error(
                    "发送余额不足通知失败",
                    admin_id=admin_id,
                    error=str(exc),
                )
