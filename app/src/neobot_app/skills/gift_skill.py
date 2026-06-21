"""GiftSkill — 礼物准备与发送管理 Skill。

管理 sandbox/gift/ 目录下的礼物计划，与 ScheduledTaskManager 集成。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from neobot_app.skills.base import SkillModule
from neobot_contracts.models import ConversationRef
from neobot_contracts.models.scheduled_task import ScheduledTaskRecurrence

GIFT_DIR = "gift"
GIFT_MD = "gift.md"
PREPARED_MARKER = "prepared"
_STORAGE_DOC = "文件存储.md"

def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)

class GiftSkill(SkillModule):
    """礼物管理 Skill — 创建、列表、取消礼物，与定时任务集成。"""

    @property
    def name(self) -> str:
        return "gift"

    @property
    def description(self) -> str:
        return "礼物管理：创建礼物计划、列出礼物状态、取消礼物、标记发送完成"

    @property
    def instructions(self) -> str:
        return (
            "礼物管理 Skill 用于在沙箱中准备和发送礼物（图片/文档等）。\n\n"
            "## 礼物目录结构\n"
            "  sandbox/gift/\n"
            "  └── {user_qq}/          — 按目标用户 QQ 号分文件夹\n"
            "      ├── gift.md         — 礼物计划详情\n"
            "      ├── prepared        — 标记文件（存在=已准备完毕）\n"
            "      └── ...             — 实际礼物文件\n\n"
            "## 工具列表\n"
            "  create_gift — 创建礼物计划（查重，不允许同一用户已有活跃礼物时再创建）\n"
            "  list_gifts — 列出所有礼物及其状态\n"
            "  cancel_gift — 取消礼物（删除文件夹和对应定时任务）\n"
            "  mark_gift_sent — 标记礼物已发送（清理文件夹，允许再次为该用户创建礼物）\n\n"
            "## 工作流\n"
            "1. 用户提出送礼需求 → 调用 create_gift 创建礼物计划\n"
            "2. 若 prepare_now=true，立即开始准备礼物文件\n"
            "3. 准备完毕后创建 prepared 标记文件\n"
            "4. 定时任务触发时发送礼物，完成后调用 mark_gift_sent 清理"
        )

    def __init__(
        self,
        sandbox_service: Any = None,
        scheduled_task_manager: Any = None,
        notification_hub: Any = None,
    ) -> None:
        self._sandbox = sandbox_service
        self._scheduled_tasks = scheduled_task_manager
        self._notification_hub = notification_hub

    def reset(self) -> None:
        pass

    def _gift_root(self) -> Path:
        if self._sandbox is not None:
            return self._sandbox.resolve_path(GIFT_DIR)
        return Path(GIFT_DIR)

    def _user_gift_dir(self, user_id: str) -> Path:
        return self._gift_root() / user_id

    def get_tools(self) -> list[dict]:
        return [
            self._tool_def(
                "create_gift",
                "为指定用户创建礼物计划。同一用户已有活跃礼物时无法创建（需等上一个礼物发送完成或取消）。"
                "trigger_type: birthday=生日礼物, manual=手动请求, other=其他。"
                "prepare_now=true 立即准备礼物文件；false 由定时维护系统稍后准备。",
                {
                    "properties": {
                        "user_id": {"type": "string", "description": "目标用户 QQ 号"},
                        "idea": {"type": "string", "description": "礼物想法描述，如'手写祝福卡片+原创小诗'"},
                        "trigger_type": {
                            "type": "string",
                            "enum": ["birthday", "manual", "other"],
                            "description": "礼物触发类型：birthday/manual/other",
                        },
                        "trigger_date": {
                            "type": "string",
                            "description": "触发日期，ISO 格式如 2026-07-01T09:00:00+08:00",
                        },
                        "prepare_now": {
                            "type": "boolean",
                            "description": "是否立即准备礼物文件，默认 false",
                        },
                        "group_id": {
                            "type": "string",
                            "description": "可选，目标群号（在群内送出）",
                        },
                    },
                    "required": ["user_id", "idea", "trigger_type", "trigger_date"],
                },
            ),
            self._tool_def(
                "list_gifts",
                "列出所有礼物及其状态（用户、触发日期、是否已准备、定时任务状态）。",
                {"properties": {}, "required": []},
            ),
            self._tool_def(
                "cancel_gift",
                "取消指定用户的礼物计划，删除对应文件夹和定时任务。",
                {
                    "properties": {
                        "user_id": {"type": "string", "description": "目标用户 QQ 号"},
                    },
                    "required": ["user_id"],
                },
            ),
            self._tool_def(
                "mark_gift_sent",
                "标记礼物已发送完毕。清理该用户的礼物文件夹和定时任务，允许再次为该用户创建礼物。"
                "应在发送完所有礼物文件后调用。",
                {
                    "properties": {
                        "user_id": {"type": "string", "description": "目标用户 QQ 号"},
                    },
                    "required": ["user_id"],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown gift tool: {tool_name}"})
        return await handler(self, args)

# ── Handlers ──

async def _handle_create_gift(self: GiftSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    if self._scheduled_tasks is None:
        return _json({"ok": False, "error": "scheduled_task_manager 未配置"})

    user_id = str(args.get("user_id", "")).strip()
    idea = str(args.get("idea", "")).strip()
    trigger_type = str(args.get("trigger_type", "manual")).strip()
    trigger_date_str = str(args.get("trigger_date", "")).strip()
    prepare_now = bool(args.get("prepare_now", False))
    group_id = str(args.get("group_id", "")).strip()

    if not user_id or not idea or not trigger_date_str:
        return _json({"ok": False, "error": "缺少必要参数 user_id/idea/trigger_date"})

    # 查重
    gift_root = self._gift_root()
    gift_root.mkdir(parents=True, exist_ok=True)
    user_dir = self._user_gift_dir(user_id)
    if user_dir.exists():
        return _json({
            "ok": False,
            "error": f"用户 {user_id} 已有活跃礼物，请等待该礼物发送完成或取消后再创建",
        })

    # 解析日期
    try:
        trigger_date = datetime.fromisoformat(trigger_date_str)
    except ValueError:
        return _json({"ok": False, "error": f"trigger_date 格式无效: {trigger_date_str}"})

    if trigger_date.tzinfo is None:
        from neobot_app.time_context import to_local
        trigger_date = to_local(trigger_date)
    end_date = trigger_date + timedelta(hours=16)  # 给 16 小时发送窗口

    # 创建礼物目录
    user_dir.mkdir(parents=True, exist_ok=True)

    # 写入 gift.md
    gift_md_content = _build_gift_md(
        user_id=user_id,
        idea=idea,
        trigger_type=trigger_type,
        trigger_date=trigger_date_str,
        prepared=False,
    )
    gift_md_path = user_dir / GIFT_MD
    await self._sandbox.write_file(gift_md_path, gift_md_content.encode("utf-8"))

    # 创建定时任务
    bindings: list[ConversationRef] = []
    if group_id:
        bindings.append(ConversationRef(kind="group", id=group_id))
    bindings.append(ConversationRef(kind="private", id=user_id))

    task_title = f"送出给 {user_id} 的礼物"
    if trigger_type == "birthday":
        task_title = f"送出给 {user_id} 的生日礼物"

    try:
        task = await self._scheduled_tasks.create_task(
            title=task_title,
            detail=(
                f"今天是送出礼物的日子。\n"
                f"目标用户：{user_id}\n"
                f"礼物文件夹：gift/{user_id}/\n"
                f"礼物想法：{idea}\n\n"
                "请按以下步骤操作：\n"
                "1. 调用 file_storage__read_storage_doc 查看文件索引\n"
                "2. 用 sandbox_manager__list_files 查看 gift/{user_id}/ 下的礼物文件\n"
                "3. 将礼物文件用 sandbox_manager__send_file 或 send_chat_file 发送给目标用户\n"
                "4. 发送完毕后，调用 gift__mark_gift_sent user_id={user_id} 清理礼物文件夹\n"
                f"{'5. 如果是群聊，请在群聊中 @ 目标用户送出祝福' if group_id else ''}"
            ),
            recurrence=ScheduledTaskRecurrence.ONCE,
            start_at=trigger_date,
            end_at=end_date,
            bindings=bindings,
            metadata={
                "type": "gift",
                "user_id": user_id,
                "trigger_type": trigger_type,
                "gift_dir": f"gift/{user_id}",
                "prepared": False,
                "one_shot_notification": False,  # 持续通知直到发送完成
            },
        )
    except Exception as e:
        # 回滚：删除已创建的目录
        import shutil
        shutil.rmtree(str(user_dir), ignore_errors=True)
        return _json({"ok": False, "error": f"创建定时任务失败: {e}"})

    # 如果选择立即准备，发布通知
    prepare_status = "not_prepared"
    if prepare_now and self._notification_hub is not None:
        try:
            await self._notification_hub.publish(
                source="gift",
                kind="private",
                conversation_id=user_id,
                content=(
                    "<新的必须回复内容>\n"
                    "这是一条礼物准备请求。\n"
                    f"目标用户：{user_id}\n"
                    f"礼物文件夹：gift/{user_id}/\n"
                    f"礼物想法：{idea}\n\n"
                    "请根据礼物想法，在 sandbox/gift/{user_id}/ 下创建礼物文件（图片、文字卡片等）。\n"
                    "准备完成后：\n"
                    "1. 调用 file_storage__update_storage_doc 更新文件索引\n"
                    "2. 在 gift/{user_id}/ 下创建 prepared 标记文件确认准备完毕\n"
                    "</新的必须回复内容>"
                ),
                manager_name="gift",
                reasons=["gift preparation"],
                metadata={"user_id": user_id, "gift_dir": f"gift/{user_id}"},
            )
            prepare_status = "preparing"
        except Exception:
            pass

    return _json({
        "ok": True,
        "user_id": user_id,
        "gift_dir": f"gift/{user_id}",
        "task_uuid": task.task_uuid,
        "trigger_date": trigger_date_str,
        "prepare_status": prepare_status,
    })

async def _handle_list_gifts(self: GiftSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})

    gift_root = self._gift_root()
    gifts: list[dict] = []
    if not gift_root.is_dir():
        return _json({"ok": True, "gifts": gifts})

    for user_dir in sorted(gift_root.iterdir()):
        if not user_dir.is_dir():
            continue
        user_id = user_dir.name
        gift_md_path = user_dir / GIFT_MD
        prepared = (user_dir / PREPARED_MARKER).exists()

        gift_info = {
            "user_id": user_id,
            "prepared": prepared,
            "files": [],
        }

        if gift_md_path.is_file():
            try:
                content = gift_md_path.read_text("utf-8")
                gift_info["gift_md"] = content[:1000]  # 截断
            except Exception:
                pass

        for f in sorted(user_dir.iterdir()):
            if f.is_file() and f.name not in (GIFT_MD, PREPARED_MARKER):
                gift_info["files"].append({
                    "name": f.name,
                    "size": f.stat().st_size,
                })

        gifts.append(gift_info)

    return _json({"ok": True, "gifts": gifts})

async def _handle_cancel_gift(self: GiftSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})

    user_id = str(args.get("user_id", "")).strip()
    if not user_id:
        return _json({"ok": False, "error": "user_id 不能为空"})

    user_dir = self._user_gift_dir(user_id)
    if not user_dir.exists():
        return _json({"ok": False, "error": f"用户 {user_id} 没有活跃的礼物"})

    # 尝试获取定时任务 UUID 并删除
    task_deleted = False
    gift_md_path = user_dir / GIFT_MD
    if gift_md_path.is_file() and self._scheduled_tasks is not None:
        try:
            content = gift_md_path.read_text("utf-8")
            import re
            m = re.search(r"定时任务UUID[：:]\s*(\S+)", content)
            if m:
                task_uuid = m.group(1)
                async with self._scheduled_tasks._uow_factory() as uow:
                    await uow.scheduled_tasks.delete(task_uuid)
                    await uow.commit()
                    task_deleted = True
        except Exception:
            pass

    # 删除礼物文件夹
    import shutil
    shutil.rmtree(str(user_dir), ignore_errors=True)

    return _json({
        "ok": True,
        "user_id": user_id,
        "task_deleted": task_deleted,
    })

async def _handle_mark_gift_sent(self: GiftSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})

    user_id = str(args.get("user_id", "")).strip()
    if not user_id:
        return _json({"ok": False, "error": "user_id 不能为空"})

    user_dir = self._user_gift_dir(user_id)
    if not user_dir.exists():
        return _json({"ok": True, "note": f"用户 {user_id} 的礼物文件夹已不存在"})

    # 删除定时任务
    task_deleted = False
    gift_md_path = user_dir / GIFT_MD
    if gift_md_path.is_file() and self._scheduled_tasks is not None:
        try:
            content = gift_md_path.read_text("utf-8")
            import re
            m = re.search(r"定时任务UUID[：:]\s*(\S+)", content)
            if m:
                task_uuid = m.group(1)
                async with self._scheduled_tasks._uow_factory() as uow:
                    await uow.scheduled_tasks.delete(task_uuid)
                    await uow.commit()
                    task_deleted = True
        except Exception:
            pass

    # 删除礼物文件夹
    import shutil
    shutil.rmtree(str(user_dir), ignore_errors=True)

    return _json({
        "ok": True,
        "user_id": user_id,
        "cleaned": True,
        "task_deleted": task_deleted,
    })

def _build_gift_md(
    user_id: str,
    idea: str,
    trigger_type: str,
    trigger_date: str,
    prepared: bool = False,
    task_uuid: str = "",
) -> str:
    return (
        f"# 给 {user_id} 的礼物\n\n"
        "## 基本信息\n"
        f"- 目标用户：{user_id}\n"
        f"- 触发类型：{trigger_type}\n"
        f"- 触发日期：{trigger_date}\n"
        f"- 定时任务UUID：{task_uuid}\n\n"
        "## 礼物想法\n"
        f"{idea}\n\n"
        "## 礼物内容\n"
        "（待准备）\n\n"
        "## 状态\n"
        f"- prepared: {'true' if prepared else 'false'}\n"
    )

_HANDLERS = {
    "create_gift": _handle_create_gift,
    "list_gifts": _handle_list_gifts,
    "cancel_gift": _handle_cancel_gift,
    "mark_gift_sent": _handle_mark_gift_sent,
}
