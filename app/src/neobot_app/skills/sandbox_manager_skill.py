"""SandboxManagerSkill — 沙箱文件操作 Skill（读写/删除/列表/移动/复制/发送）。"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from neobot_app.skills.base import SkillModule


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class SandboxManagerSkill(SkillModule):
    """沙箱文件操作 Skill — 沙箱内文件读写删列移拷贝及发送到聊天。"""

    @property
    def name(self) -> str:
        return "sandbox_manager"

    @property
    def description(self) -> str:
        return "沙箱文件管理：读取/写入/删除/列表/移动/复制文件，发送文件到聊天"

    @property
    def instructions(self) -> str:
        return (
            "沙箱文件管理 Skill 提供聊天可操作的文件系统，用于保存生成的文件（截图/图片/文档/PDF等）"
            "以及临时存储各类数据。\n\n"
            "## 目录结构\n"
            "  temp/{chat_flow_id}/ — 临时目录（30分钟无修改自动清理，重要文件用 hold_temp 保活）\n"
            "  tools/             — 可复用工具脚本（Python/shell 等），持久保存\n"
            "  docs/              — 参考文档和备忘，持久保存\n"
            "  assets/            — 静态资源（模板、字体等），持久保存\n"
            "  gift/              — 礼物准备目录（由 gift skill 管理）\n"
            "  文件存储.md         — 持久化文件索引文档\n"
            "  TODO.md            — 待实现工具清单\n\n"
            "## 持久化文件操作规则（操作 tools/docs/assets 时必须遵守）\n"
            "  1. 操作前必须先调用 file_storage__read_storage_doc 查看当前文件索引\n"
            "  2. 修改后必须调用 file_storage__update_storage_doc 更新文档\n"
            "  3. 文档要求精简：工具类写文件名+用法用途，文档类写文件名+大概内容（一行以内）\n"
            "  4. 需要但暂未实现的复杂脚本，调用 file_storage__update_todo 写入 TODO.md\n\n"
            "文件路径相对于沙箱根目录如 tmp/{chat_flow_id}/...（写入时自动拼接）。\n"
            "可使用 write_file 创建文件、list_files 浏览目录结构、read_file 读取内容。\n"
            "生成文件（如代码/文档/PDF/图片等）后可先存入沙箱，再用 send_file 发送到聊天。\n\n"
            "工具列表：\n"
            "  read_file — 读取文件内容（返回 base64）\n"
            "  write_file — 写入文件到沙箱临时目录\n"
            "  delete_file — 删除文件\n"
            "  list_files — 列出目录内容\n"
            "  move_file — 移动/重命名文件\n"
            "  copy_file — 复制文件\n"
            "  send_file — 将沙箱内的图片发送到聊天（以图片消息）\n"
            "  send_chat_file — 将沙箱内任意文件（PDF/文档等）发送到聊天（以文件附件形式）\n"
            "  download_file — 从 URL 下载文件到沙箱临时目录\n"
            "  hold_temp — 保活临时文件目录（最长 2 小时）\n\n"
            "写入操作需要沙箱锁（同一时间只有一个 agent 可写）。\n"
            "临时文件 30 分钟无修改自动清理，重要文件请用 hold_temp 保活。"
        )

    def __init__(
        self,
        sandbox_service: Any = None,
        sandbox_lock: Any = None,
        adapter: Any = None,
        file_server: Any = None,
        hold_max_minutes: int = 120,
    ) -> None:
        self._sandbox = sandbox_service
        self._lock = sandbox_lock
        self._adapter = adapter
        self._file_server = file_server
        self._hold_max_minutes = hold_max_minutes

    def reset(self) -> None:
        pass

    def _resolve_send_path(self, path_str: str, chat_flow_id: str | None = None) -> Path:
        """解析发送文件的路径：先尝试原路径，再通过沙箱解析。"""
        p = Path(path_str)
        if p.is_absolute() and p.exists():
            return p
        if self._sandbox is not None:
            try:
                resolved = self._sandbox.resolve_path(path_str, chat_flow_id)
                if resolved.exists():
                    return resolved
            except Exception:
                pass
        return p

    def get_tools(self) -> list[dict]:
        return [
            self._tool_def(
                "read_file",
                "读取沙箱内文件的内容，返回 base64 编码数据。",
                {
                    "properties": {
                        "path": {"type": "string", "description": "文件路径（相对于沙箱根）"},
                    },
                    "required": ["path"],
                },
            ),
            self._tool_def(
                "write_file",
                "写入文件到沙箱临时目录。需要 chat_flow_id 指定聊天流。",
                {
                    "properties": {
                        "path": {"type": "string", "description": "文件路径（相对于临时目录）"},
                        "content_base64": {"type": "string", "description": "文件内容的 base64 编码"},
                        "chat_flow_id": {"type": "string", "description": "聊天流 ID，如 Group_12345"},
                    },
                    "required": ["path", "content_base64", "chat_flow_id"],
                },
            ),
            self._tool_def(
                "delete_file",
                "删除沙箱内的文件或空目录。",
                {
                    "properties": {
                        "path": {"type": "string", "description": "文件路径（相对于沙箱根）"},
                        "chat_flow_id": {"type": "string", "description": "可选，聊天流 ID"},
                    },
                    "required": ["path"],
                },
            ),
            self._tool_def(
                "list_files",
                "列出沙箱目录下的内容。",
                {
                    "properties": {
                        "path": {"type": "string", "description": "目录路径（相对于沙箱根），默认为 /"},
                        "pattern": {"type": "string", "description": "可选，glob 模式过滤如 *.txt"},
                    },
                    "required": [],
                },
            ),
            self._tool_def(
                "move_file",
                "移动或重命名沙箱内的文件/目录。",
                {
                    "properties": {
                        "source": {"type": "string", "description": "源路径（相对于沙箱根）"},
                        "destination": {"type": "string", "description": "目标路径（相对于沙箱根）"},
                        "chat_flow_id": {"type": "string", "description": "可选，聊天流 ID"},
                    },
                    "required": ["source", "destination"],
                },
            ),
            self._tool_def(
                "copy_file",
                "复制沙箱内的文件。",
                {
                    "properties": {
                        "source": {"type": "string", "description": "源路径（相对于沙箱根）"},
                        "destination": {"type": "string", "description": "目标路径（相对于沙箱根）"},
                        "chat_flow_id": {"type": "string", "description": "可选，聊天流 ID"},
                    },
                    "required": ["source", "destination"],
                },
            ),
            self._tool_def(
                "send_file",
                "将沙箱内的图片发送到聊天（以图片消息）。",
                {
                    "properties": {
                        "path": {"type": "string", "description": "文件路径（相对于沙箱根）"},
                        "group_id": {"type": "string", "description": "可选，目标群号"},
                        "user_id": {"type": "string", "description": "可选，目标QQ号"},
                        "chat_flow_id": {"type": "string", "description": "可选，当 path 不包含 temp/ 前缀时需要此 ID 来定位文件"},
                    },
                    "required": ["path"],
                },
            ),
            self._tool_def(
                "send_chat_file",
                "将沙箱内的任意文件（PDF/文档/代码等）发送到聊天（以文件附件形式）。",
                {
                    "properties": {
                        "path": {"type": "string", "description": "文件路径（相对于沙箱根）"},
                        "group_id": {"type": "string", "description": "目标群号"},
                        "user_id": {"type": "string", "description": "目标QQ号"},
                        "chat_flow_id": {"type": "string", "description": "可选，当 path 不包含 temp/ 前缀时需要此 ID 来定位文件"},
                    },
                    "required": ["path"],
                },
            ),
            self._tool_def(
                "hold_temp",
                "保活当前聊天流的临时文件目录，防止被自动清理。最长保活2小时。",
                {
                    "properties": {
                        "chat_flow_id": {"type": "string", "description": "聊天流 ID"},
                        "minutes": {"type": "integer", "description": "保活分钟数，默认120", "default": 120},
                    },
                    "required": ["chat_flow_id"],
                },
            ),
            self._tool_def(
                "download_file",
                "从 URL 下载文件到沙箱。支持下载聊天中的文件、网络图片等。"
                "下载后文件保存到沙箱临时目录，供后续读取或发送。",
                {
                    "properties": {
                        "url": {"type": "string", "description": "文件的下载 URL"},
                        "save_name": {"type": "string", "description": "保存的文件名，如 image.png、document.pdf"},
                        "chat_flow_id": {"type": "string", "description": "聊天流 ID，如 Group_12345"},
                    },
                    "required": ["url", "save_name", "chat_flow_id"],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown sandbox_manager tool: {tool_name}"})
        return await handler(self, args)

    @staticmethod
    def _tool_def(name: str, desc: str, params: dict | None = None) -> dict:
        p = {"type": "object", "properties": {}, "required": []}
        if params:
            p["properties"] = params.get("properties", {})
            p["required"] = params.get("required", [])
        return {"type": "function", "function": {"name": name, "description": desc, "parameters": p}}


# ── Handlers ──

async def _handle_read_file(self: SandboxManagerSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    rel_path = str(args.get("path", "")).strip().lstrip("/")
    if not rel_path:
        return _json({"ok": False, "error": "缺少 path"})
    try:
        path = self._sandbox.resolve_path(rel_path)
        data = await self._sandbox.read_file(path)
        return _json({"ok": True, "content_base64": base64.b64encode(data).decode(), "size": len(data)})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_write_file(self: SandboxManagerSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    rel_path = str(args.get("path", "")).strip()
    content_b64 = args.get("content_base64", "")
    chat_flow_id = str(args.get("chat_flow_id", "")).strip()
    if not rel_path or not content_b64 or not chat_flow_id:
        return _json({"ok": False, "error": "缺少必要参数 path/content_base64/chat_flow_id"})
    try:
        data = base64.b64decode(content_b64)
        path = self._sandbox.resolve_path(rel_path, chat_flow_id)
        await self._sandbox.write_file(path, data)
        return _json({"ok": True, "path": str(path)})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_delete_file(self: SandboxManagerSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    rel_path = str(args.get("path", "")).strip()
    chat_flow_id = str(args.get("chat_flow_id", "")).strip()
    if not rel_path:
        return _json({"ok": False, "error": "缺少 path"})
    try:
        path = self._sandbox.resolve_path(rel_path, chat_flow_id or None)
        await self._sandbox.delete_file(path)
        return _json({"ok": True})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_list_files(self: SandboxManagerSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    rel_path = str(args.get("path", "")).strip().lstrip("/") or "."
    pattern = args.get("pattern")
    try:
        path = self._sandbox.resolve_path(rel_path)
        files = await self._sandbox.list_files(path, pattern)
        return _json({"ok": True, "files": files})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_move_file(self: SandboxManagerSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    src = str(args.get("source", "")).strip()
    dst = str(args.get("destination", "")).strip()
    chat_flow_id = str(args.get("chat_flow_id", "")).strip()
    if not src or not dst:
        return _json({"ok": False, "error": "缺少 source 或 destination"})
    try:
        src_path = self._sandbox.resolve_path(src, chat_flow_id or None)
        dst_path = self._sandbox.resolve_path(dst, chat_flow_id or None)
        await self._sandbox.move_file(src_path, dst_path)
        return _json({"ok": True})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_copy_file(self: SandboxManagerSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    src = str(args.get("source", "")).strip()
    dst = str(args.get("destination", "")).strip()
    chat_flow_id = str(args.get("chat_flow_id", "")).strip()
    if not src or not dst:
        return _json({"ok": False, "error": "缺少 source 或 destination"})
    try:
        src_path = self._sandbox.resolve_path(src, chat_flow_id or None)
        dst_path = self._sandbox.resolve_path(dst, chat_flow_id or None)
        await self._sandbox.copy_file(src_path, dst_path)
        return _json({"ok": True})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_send_file(self: SandboxManagerSkill, args: dict) -> str:
    if self._adapter is None:
        return _json({"ok": False, "error": "adapter 未配置"})
    if self._file_server is None:
        return _json({"ok": False, "error": "file_server 未配置"})
    file_path = str(args.get("path", "")).strip()
    group_id = str(args.get("group_id", "")).strip()
    user_id = str(args.get("user_id", "")).strip()
    chat_flow_id = str(args.get("chat_flow_id", "")).strip() or None
    if not file_path:
        return _json({"ok": False, "error": "缺少 path"})
    path = self._resolve_send_path(file_path, chat_flow_id)
    if not path.exists():
        return _json({"ok": False, "error": f"文件不存在: {file_path}"})
    if not group_id and not user_id:
        return _json({"ok": False, "error": "缺少 group_id 或 user_id"})
    try:
        from neobot_app.utils.media_sender import prepare_image_segment
        from neobot_contracts.models import ConversationRef

        if group_id:
            conv_ref = ConversationRef(kind="group", id=group_id)
        else:
            conv_ref = ConversationRef(kind="private", id=user_id)

        segment = prepare_image_segment(self._file_server, path)
        resp = await self._adapter.send(conv_ref, [segment])

        # 检查 go-cqhttp API 响应状态
        if resp is None:
            return _json({"ok": False, "error": "发送超时，无响应"})
        if hasattr(resp, "status") and hasattr(resp, "retcode"):
            if resp.status == "failed" or (resp.retcode is not None and resp.retcode != 0):
                msg = resp.message or resp.wording or str(resp.retcode)
                return _json({"ok": False, "error": f"发送失败(retcode={resp.retcode}): {msg}"})
        elif isinstance(resp, dict):
            r_status = resp.get("status")
            r_retcode = resp.get("retcode")
            if r_status == "failed" or (r_retcode is not None and r_retcode != 0):
                msg = resp.get("message") or resp.get("wording") or str(r_retcode)
                return _json({"ok": False, "error": f"发送失败(retcode={r_retcode}): {msg}"})
        return _json({"ok": True, "path": str(path)})
    except Exception as e:
        return _json({"ok": False, "error": f"发送失败: {e}"})

async def _handle_send_chat_file(self: SandboxManagerSkill, args: dict) -> str:
    if self._adapter is None:
        return _json({"ok": False, "error": "adapter 未配置"})
    if self._file_server is None:
        return _json({"ok": False, "error": "file_server 未配置"})
    file_path = str(args.get("path", "")).strip()
    group_id = str(args.get("group_id", "")).strip()
    user_id = str(args.get("user_id", "")).strip()
    chat_flow_id = str(args.get("chat_flow_id", "")).strip() or None
    if not file_path:
        return _json({"ok": False, "error": "缺少 path"})
    path = self._resolve_send_path(file_path, chat_flow_id)
    if not path.exists():
        return _json({"ok": False, "error": f"文件不存在: {file_path}"})
    if not group_id and not user_id:
        return _json({"ok": False, "error": "缺少 group_id 或 user_id"})
    try:
        from neobot_app.utils.media_sender import prepare_file_segment
        from neobot_contracts.models import ConversationRef

        if group_id:
            conv_ref = ConversationRef(kind="group", id=group_id)
        else:
            conv_ref = ConversationRef(kind="private", id=user_id)

        segment = prepare_file_segment(self._file_server, path)
        resp = await self._adapter.send(conv_ref, [segment])

        if resp is None:
            return _json({"ok": False, "error": "发送超时，无响应"})
        if hasattr(resp, "status") and hasattr(resp, "retcode"):
            if resp.status == "failed" or (resp.retcode is not None and resp.retcode != 0):
                msg = resp.message or resp.wording or str(resp.retcode)
                return _json({"ok": False, "error": f"发送失败(retcode={resp.retcode}): {msg}"})
        elif isinstance(resp, dict):
            r_status = resp.get("status")
            r_retcode = resp.get("retcode")
            if r_status == "failed" or (r_retcode is not None and r_retcode != 0):
                msg = resp.get("message") or resp.get("wording") or str(r_retcode)
                return _json({"ok": False, "error": f"发送失败(retcode={r_retcode}): {msg}"})
        return _json({"ok": True, "path": str(path)})
    except Exception as e:
        return _json({"ok": False, "error": f"发送失败: {e}"})

async def _handle_hold_temp(self: SandboxManagerSkill, args: dict) -> str:
    chat_flow_id = str(args.get("chat_flow_id", "")).strip()
    minutes = int(args.get("minutes", 120))
    if not chat_flow_id:
        return _json({"ok": False, "error": "缺少 chat_flow_id"})
    if self._sandbox is None:
        return _json({"ok": True, "note": f"模拟：临时目录 {chat_flow_id} 已保活 {minutes} 分钟"})
    self._sandbox.ensure_temp_dir(chat_flow_id)
    return _json({"ok": True, "note": f"临时目录 {chat_flow_id} 已保活 {minutes} 分钟"})


async def _handle_download_file(self: SandboxManagerSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    url = str(args.get("url", "")).strip()
    save_name = str(args.get("save_name", "")).strip()
    chat_flow_id = str(args.get("chat_flow_id", "")).strip()
    if not url or not save_name or not chat_flow_id:
        return _json({"ok": False, "error": "缺少必要参数 url/save_name/chat_flow_id"})
    try:
        import httpx
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.content
        path = self._sandbox.resolve_path(save_name, chat_flow_id)
        await self._sandbox.write_file(path, data)
        return _json({"ok": True, "path": str(path), "size": len(data)})
    except Exception as e:
        return _json({"ok": False, "error": f"下载失败: {e}"})


_HANDLERS = {
    "read_file": _handle_read_file,
    "write_file": _handle_write_file,
    "delete_file": _handle_delete_file,
    "list_files": _handle_list_files,
    "move_file": _handle_move_file,
    "copy_file": _handle_copy_file,
    "send_file": _handle_send_file,
    "send_chat_file": _handle_send_chat_file,
    "hold_temp": _handle_hold_temp,
    "download_file": _handle_download_file,
}
