"""BilibiliLinkSkill — B站-QQ账户关联。

关联后，两个平台的用户共享同一份记忆档案（备注、好感度、印象等）。
首次链接自动触发记忆融合。
"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class BilibiliLinkSkill(SkillModule):
    """B站账户关联 Skill — 将 B站 UID 关联到 QQ 号，共享记忆档案。"""

    @property
    def name(self) -> str:
        return "bilibili_link"

    @property
    def description(self) -> str:
        return "B站账户关联：将B站UID关联到QQ号，共享记忆档案"

    @property
    def instructions(self) -> str:
        return (
            "B站账户关联 Skill 提供以下能力：\n\n"
            "  link_account — 将B站UID关联到QQ号。首次关联时自动合并两者的记忆档案。\n"
            "  unlink_account — 取消关联。\n"
            "  get_link — 查询关联关系。\n\n"
            "关联后，与B站用户互动时会使用QQ账号的记忆档案（包括备注、好感度、印象等）。\n"
            "首次关联会自动从B站用户档案中提取关键信息合并到QQ用户档案。"
        )

    def __init__(
        self,
        uow_factory: Any = None,
        profile_service: Any = None,
        archive_memory_service: Any = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._profile_service = profile_service
        self._archive = archive_memory_service

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        if self._uow_factory is None:
            return []
        return [
            self._tool_def(
                "link_account",
                "将B站UID关联到QQ号。首次关联时自动合并两者的记忆档案。",
                {
                    "properties": {
                        "bilibili_uid": {
                            "type": "integer",
                            "description": "B站用户UID（纯数字）",
                        },
                        "qq_number": {
                            "type": "string",
                            "description": "QQ号",
                        },
                    },
                    "required": ["bilibili_uid", "qq_number"],
                },
            ),
            self._tool_def(
                "unlink_account",
                "取消B站-QQ账户关联。可以取消单个关联或所有关联。",
                {
                    "properties": {
                        "qq_number": {
                            "type": "string",
                            "description": "QQ号",
                        },
                        "bilibili_uid": {
                            "type": "integer",
                            "description": "可选：指定取消哪个B站UID的关联；不填则取消该QQ的所有B站关联",
                        },
                    },
                    "required": ["qq_number"],
                },
            ),
            self._tool_def(
                "get_link",
                "查询账户关联关系。可按QQ号查或按B站UID查。",
                {
                    "properties": {
                        "bilibili_uid": {
                            "type": "integer",
                            "description": "可选：按B站UID查询",
                        },
                        "qq_number": {
                            "type": "string",
                            "description": "可选：按QQ号查询",
                        },
                    },
                    "required": [],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown tool: {tool_name}"})
        return await handler(self, args)

    @staticmethod
    def _tool_def(name: str, desc: str, params: dict | None = None) -> dict:
        p = {"type": "object", "properties": {}, "required": []}
        if params:
            p["properties"] = params.get("properties", {})
            p["required"] = params.get("required", [])
        return {
            "type": "function",
            "function": {"name": name, "description": desc, "parameters": p},
        }


# ── Handlers ──

async def _handle_link_account(self: BilibiliLinkSkill, args: dict) -> str:
    bilibili_uid = int(args.get("bilibili_uid", 0))
    qq_number = str(args.get("qq_number", "")).strip()

    if not bilibili_uid or not qq_number:
        return _json({"ok": False, "error": "缺少 bilibili_uid 或 qq_number"})

    try:
        async with self._uow_factory() as uow:
            # 检查是否已存在
            existing = await uow.bilibili_link_repo.find_by_uid_and_qq(bilibili_uid, qq_number)
            if existing:
                return _json({"ok": True, "merged": False, "message": "该关联已存在"})

            # 创建关联记录
            await uow.bilibili_link_repo.create(bilibili_uid, qq_number)
            await uow.commit()

        # 首次关联：尝试融合记忆档案
        merged = False
        merge_details = ""
        if self._archive and self._profile_service:
            try:
                bili_profile = await self._archive.read("bilibili_user", str(bilibili_uid))
                qq_profile = await self._profile_service.get_user(qq_number)

                if bili_profile and qq_profile:
                    # 将B站档案信息合并到QQ user_profile
                    bili_value = bili_profile.get("value", "")
                    existing_notes = qq_profile.profile or ""
                    merged_notes = (
                        f"{existing_notes}\n[B站UID:{bilibili_uid}]\n{bili_value}"
                        if existing_notes
                        else f"[B站UID:{bilibili_uid}]\n{bili_value}"
                    )
                    await self._profile_service.update_user_field(
                        qq_number, "profile", merged_notes[:2000]
                    )
                    merged = True
                    merge_details = "已合并B站用户档案到QQ档案"
                elif bili_profile:
                    merged = True
                    merge_details = "B站档案已关联但QQ用户尚未初始化"
            except Exception as e:
                merge_details = f"记忆合并失败: {e}"

        return _json({
            "ok": True,
            "merged": merged,
            "message": f"关联成功 (B站UID:{bilibili_uid} ↔ QQ:{qq_number}). {merge_details}",
        })
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


async def _handle_unlink_account(self: BilibiliLinkSkill, args: dict) -> str:
    qq_number = str(args.get("qq_number", "")).strip()
    bilibili_uid_raw = args.get("bilibili_uid")

    if not qq_number:
        return _json({"ok": False, "error": "缺少 qq_number"})

    try:
        async with self._uow_factory() as uow:
            if bilibili_uid_raw is not None:
                count = await uow.bilibili_link_repo.delete_one(
                    int(bilibili_uid_raw), qq_number
                )
            else:
                count = await uow.bilibili_link_repo.delete_all_for_qq(qq_number)
            await uow.commit()

        return _json({"ok": True, "removed": count, "message": f"已移除 {count} 条关联"})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


async def _handle_get_link(self: BilibiliLinkSkill, args: dict) -> str:
    bilibili_uid_raw = args.get("bilibili_uid")
    qq_number = str(args.get("qq_number", "")).strip()

    try:
        async with self._uow_factory() as uow:
            if bilibili_uid_raw is not None:
                links = await uow.bilibili_link_repo.find_by_uid(int(bilibili_uid_raw))
            elif qq_number:
                links = await uow.bilibili_link_repo.find_by_qq(qq_number)
            else:
                return _json({"ok": False, "error": "请提供 bilibili_uid 或 qq_number"})
        return _json({"ok": True, "links": links})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


_HANDLERS = {
    "link_account": _handle_link_account,
    "unlink_account": _handle_unlink_account,
    "get_link": _handle_get_link,
}
