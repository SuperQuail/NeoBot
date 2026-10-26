"""发送文件到聊天的处理函数。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .common import _json

if TYPE_CHECKING:
    from ..sandbox_manager_skill import SandboxManagerSkill

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
        # 不等 echo：发送几乎不会失败，等待回执只会阻塞 agent 继续执行。
        resp = await self._adapter.send(conv_ref, [segment], wait_response=False)

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
        resp = await self._adapter.send(conv_ref, [segment], wait_response=False)

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
