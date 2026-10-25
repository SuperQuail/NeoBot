"""BilibiliLinkSkill — B站 UID 与 QQ 号关联，关联后共享记忆档案。

迁移自 dev-test/recovered_bilibili/app/src/neobot_app/bilibili/skills/account_link.py：
- 存储改为 packages/storage 的 bilibili_links 表（迁移 0020，uow.bilibili_links）；
- 档案合并改用 ArchiveMemoryService（get/set），不再写 UserData.profile；
- 首次关联把 bilibili_user/<uid> 的档案并入 user_profile/<qq>（带 [B站UID:x] 标记，
  重复关联不会重复写入）。B站回复引擎也会通过关联反查 QQ 档案，两个方向不重复搬。
"""

from __future__ import annotations

import json
import re
from typing import Any

from neobot_app.bilibili._compat import call_client, get_field
from neobot_app.skills.base import SkillModule
from neobot_app.utils.logger import get_module_logger

logger = get_module_logger("bilibili.link_skill")

_LINK_MARKER = "[B站UID:{uid}]"
#: 合并进 QQ user_profile 的 B站档案最多多少字符（防止一条关联把档案撑爆）。
_MAX_MERGE_CHARS = 1500
#: QQ 号：5~12 位纯数字。
_QQ_RE = re.compile(r"^\d{5,12}$")


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _parse_uid(value: Any) -> tuple[int, str]:
    """校验 B站UID：只接受正整数；返回 (uid, 错误文本)。"""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return 0, "bilibili_uid 必须是正整数"
    try:
        uid = int(str(value).strip())
    except (TypeError, ValueError):
        return 0, "bilibili_uid 必须是正整数"
    if uid <= 0:
        return 0, "bilibili_uid 必须是正整数"
    return uid, ""


def _parse_qq(value: Any) -> tuple[str, str]:
    """校验 QQ 号：5~12 位纯数字；返回 (qq, 错误文本)。"""
    qq = str(value or "").strip()
    if not qq:
        return "", "缺少 qq_number"
    if not _QQ_RE.match(qq):
        return "", "qq_number 必须是 5~12 位纯数字"
    return qq, ""


def _linked_values(links: Any, field: str) -> list[str]:
    """取关联行里的某个字段（去空、去重、保序），用于冲突提示。"""
    values: list[str] = []
    for link in links or []:
        value = str(get_field(link, field, "") or "").strip()
        if value and value not in values:
            values.append(value)
    return values


class _ArchiveReadError(RuntimeError):
    """读档案失败：必须中止合并，否则"空档案"会把原档案整行覆盖掉。"""


class BilibiliLinkSkill(SkillModule):
    """B站账户关联 Skill — 把 B站 UID 关联到 QQ 号，共享记忆档案。"""

    def __init__(
        self,
        uow_factory: Any = None,
        archive_service: Any = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._archive = archive_service

    @property
    def name(self) -> str:
        return "bilibili_link"

    @property
    def description(self) -> str:
        return "B站账户关联：把B站UID关联到QQ号，关联后两边的记忆档案互通"

    @property
    def instructions(self) -> str:
        return (
            "B站账户关联 Skill 提供以下能力：\n\n"
            "  link_account — 把B站UID关联到QQ号；首次关联会把B站用户档案合并进QQ档案。\n"
            "  unlink_account — 取消关联（可按QQ号全部取消，或指定B站UID）。\n"
            "  get_link — 查询关联关系（按B站UID或QQ号）。\n\n"
            "关联后：B站用户私信/评论你时，会读到该QQ号的备注、印象与长期记忆，"
            "两个平台共享同一份人物档案。"
        )

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        if self._uow_factory is None:
            return []
        return [
            self._tool_def(
                "link_account",
                "把B站UID关联到QQ号。首次关联时自动合并B站用户档案到QQ档案。",
                {
                    "properties": {
                        "bilibili_uid": {"type": "integer", "description": "B站用户UID（纯数字）"},
                        "qq_number": {"type": "string", "description": "QQ号"},
                    },
                    "required": ["bilibili_uid", "qq_number"],
                },
            ),
            self._tool_def(
                "unlink_account",
                "取消B站-QQ账户关联。不填 bilibili_uid 时取消该QQ的全部B站关联。",
                {
                    "properties": {
                        "qq_number": {"type": "string", "description": "QQ号"},
                        "bilibili_uid": {
                            "type": "integer",
                            "description": "可选：只取消这个B站UID的关联",
                        },
                    },
                    "required": ["qq_number"],
                },
            ),
            self._tool_def(
                "get_link",
                "查询账户关联关系：可按B站UID查或按QQ号查。",
                {
                    "properties": {
                        "bilibili_uid": {"type": "integer", "description": "可选：按B站UID查询"},
                        "qq_number": {"type": "string", "description": "可选：按QQ号查询"},
                    },
                    "required": [],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown tool: {tool_name}"})
        try:
            return await handler(self, args)
        except Exception as exc:
            logger.warning(f"B站关联工具执行失败: {tool_name}: {type(exc).__name__}: {exc}")
            return _json({"ok": False, "error": str(exc)})

    # ── 内部：存储与档案 ──

    async def _links_by_uid(self, bilibili_uid: int) -> list[dict]:
        async with self._uow_factory() as uow:
            repo = getattr(uow, "bilibili_links", None)
            if repo is None:
                raise RuntimeError("storage 未提供 bilibili_links 仓库")
            result = await call_client(repo.find_by_uid, bilibili_uid)
        return list(result or [])

    async def _links_by_qq(self, qq_number: str) -> list[dict]:
        async with self._uow_factory() as uow:
            repo = getattr(uow, "bilibili_links", None)
            if repo is None:
                raise RuntimeError("storage 未提供 bilibili_links 仓库")
            result = await call_client(repo.find_by_qq, qq_number)
        return list(result or [])

    async def _archive_get(self, table: str, key: str) -> Any:
        """读一条档案条目（没有条目返回 None）；读失败抛 _ArchiveReadError。

        读失败不能当成"空档案"：合并会因此整行覆盖掉原有 QQ 档案。
        """
        if self._archive is None:
            return None
        try:
            return await call_client(self._archive.get, table, key)
        except Exception as exc:
            raise _ArchiveReadError(f"读取档案失败 {table}/{key}: {exc}") from exc

    async def _merge_archive(self, bilibili_uid: int, qq_number: str) -> str:
        """把 bilibili_user/<uid> 合并进 user_profile/<qq>；返回说明文本。"""
        if self._archive is None:
            return "未配置档案服务，跳过记忆合并"
        try:
            bili_item = await self._archive_get("bilibili_user", str(bilibili_uid))
            profile_item = await self._archive_get("user_profile", qq_number)
        except _ArchiveReadError as exc:
            logger.warning(f"读取B站档案失败，已中止记忆合并: {exc}")
            return "读取档案失败，已中止记忆合并（原档案未改动）"
        bili_memory = str(get_field(bili_item, "value", "") or "").strip()
        if not bili_memory:
            return "B站侧暂无档案"
        marker = _LINK_MARKER.format(uid=bilibili_uid)
        existing = str(get_field(profile_item, "value", "") or "").strip()
        if marker in existing:
            return "记忆已合并过"
        # 整行写入不能把 QQ 档案原有的 tags 清掉：读到的 tags 原样透传。
        tags = [str(tag) for tag in (get_field(profile_item, "tags", []) or [])]
        merged = f"{existing}\n\n{marker}\n{bili_memory[:_MAX_MERGE_CHARS]}".strip()
        try:
            await call_client(self._archive.set, "user_profile", qq_number, merged, tags)
        except Exception as exc:
            return f"记忆合并失败: {exc}"
        return "已合并B站档案到QQ档案"


# ── Handlers ──


async def _handle_link_account(skill: BilibiliLinkSkill, args: dict) -> str:
    bilibili_uid, uid_error = _parse_uid(args.get("bilibili_uid"))
    qq_number, qq_error = _parse_qq(args.get("qq_number"))
    if uid_error or qq_error:
        return _json({"ok": False, "error": uid_error or qq_error})

    created = False
    async with skill._uow_factory() as uow:
        repo = getattr(uow, "bilibili_links", None)
        if repo is None:
            return _json({"ok": False, "error": "storage 未提供 bilibili_links 仓库"})
        existing = await call_client(repo.find_by_uid_and_qq, bilibili_uid, qq_number)
        if not existing:
            # 一个 B站UID / 一个 QQ 只允许一条关联，否则记忆档案不知道该并给谁。
            other_qqs = _linked_values(
                await call_client(repo.find_by_uid, bilibili_uid), "qq_number"
            )
            if other_qqs:
                return _json(
                    {
                        "ok": False,
                        "error": f"B站UID:{bilibili_uid} 已关联其他QQ（{', '.join(other_qqs)}），"
                        "请先 unlink_account 取消旧关联再绑定",
                    }
                )
            other_uids = _linked_values(
                await call_client(repo.find_by_qq, qq_number), "bilibili_uid"
            )
            if other_uids:
                return _json(
                    {
                        "ok": False,
                        "error": f"QQ:{qq_number} 已关联其他B站UID（{', '.join(other_uids)}），"
                        "请先 unlink_account 取消旧关联再绑定",
                    }
                )
            await call_client(repo.create, bilibili_uid, qq_number)
            await uow.commit()
            created = True

    # 已有重复关联也补做一次合并：上次可能因档案读失败而没并成功（合并本身幂等）。
    detail = await skill._merge_archive(bilibili_uid, qq_number)
    prefix = "关联成功" if created else "该关联已存在"
    return _json(
        {
            "ok": True,
            "created": created,
            "merged": detail.startswith("已合并"),
            "message": f"{prefix} (B站UID:{bilibili_uid} ↔ QQ:{qq_number})。{detail}",
        }
    )


async def _handle_unlink_account(skill: BilibiliLinkSkill, args: dict) -> str:
    qq_number, qq_error = _parse_qq(args.get("qq_number"))
    if qq_error:
        return _json({"ok": False, "error": qq_error})
    bilibili_uid_raw = args.get("bilibili_uid")
    bilibili_uid = 0
    if bilibili_uid_raw is not None:
        bilibili_uid, uid_error = _parse_uid(bilibili_uid_raw)
        if uid_error:
            return _json({"ok": False, "error": uid_error})

    async with skill._uow_factory() as uow:
        repo = getattr(uow, "bilibili_links", None)
        if repo is None:
            return _json({"ok": False, "error": "storage 未提供 bilibili_links 仓库"})
        if bilibili_uid:
            count = await call_client(repo.delete_one, bilibili_uid, qq_number)
        else:
            count = await call_client(repo.delete_all_for_qq, qq_number)
        await uow.commit()
    return _json({"ok": True, "removed": int(count or 0), "message": f"已移除 {int(count or 0)} 条关联"})


async def _handle_get_link(skill: BilibiliLinkSkill, args: dict) -> str:
    bilibili_uid_raw = args.get("bilibili_uid")
    qq_number = str(args.get("qq_number") or "").strip()
    if qq_number:
        qq_number, qq_error = _parse_qq(qq_number)
        if qq_error:
            return _json({"ok": False, "error": qq_error})
    if bilibili_uid_raw is not None:
        bilibili_uid, uid_error = _parse_uid(bilibili_uid_raw)
        if uid_error:
            return _json({"ok": False, "error": uid_error})
        links = await skill._links_by_uid(bilibili_uid)
    elif qq_number:
        links = await skill._links_by_qq(qq_number)
    else:
        return _json({"ok": False, "error": "请提供 bilibili_uid 或 qq_number"})
    return _json({"ok": True, "links": links})


_HANDLERS = {
    "link_account": _handle_link_account,
    "unlink_account": _handle_unlink_account,
    "get_link": _handle_get_link,
}
