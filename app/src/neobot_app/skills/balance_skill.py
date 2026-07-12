"""BalanceSkill — 查询 DeepSeek 账户余额。

仅在 BalanceChecker 已启用（DeepSeek API 已配置）时注册。
Agent 可调用 query_balance 查看当前账户余额。
"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class BalanceSkill(SkillModule):
    """DeepSeek 余额查询。"""

    def __init__(self, balance_checker: Any = None) -> None:
        self._balance_checker = balance_checker

    @property
    def name(self) -> str:
        return "deepseek_balance"

    @property
    def description(self) -> str:
        return "DeepSeek 账户余额查询"

    @property
    def instructions(self) -> str:
        return (
            "deepseek_balance 工具可以查询 DeepSeek 账户的实时余额（CNY）。\n"
            "当余额低于预警阈值时系统会自动通知管理员，无需频繁手动检查。\n"
        )

    def get_tools(self) -> list[dict]:
        return [
            self._tool_def(
                "query_balance",
                "查询 DeepSeek 账户当前余额（CNY），返回总余额和余额明细。",
                {
                    "properties": {},
                    "required": [],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        if tool_name == "query_balance":
            return await self._execute_query_balance()
        return f"未知工具: {tool_name}"

    async def _execute_query_balance(self) -> str:
        checker = self._balance_checker
        if checker is None or not checker.is_enabled:
            return _json({
                "ok": False,
                "error": "DeepSeek 余额查询未启用（API Key 或管理员账户未配置）",
            })
        try:
            raw = await checker._query_balance()
        except Exception as exc:
            return _json({"ok": False, "error": f"余额查询失败: {exc}"})

        total = checker._extract_total_balance(raw)
        if total is None:
            return _json({"ok": False, "error": "无法解析余额数据", "raw": raw})
        return _json({
            "ok": True,
            "balance_cny": round(total, 4),
            "threshold_cny": checker._threshold,
            "below_threshold": total < checker._threshold,
        })

    @staticmethod
    def _tool_def(
        name: str, description: str, parameters: dict | None = None
    ) -> dict:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters or {"type": "object", "properties": {}},
            },
        }
