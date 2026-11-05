"""SandboxManagerSkill 的元信息、构造与路径解析。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

class SandboxManagerSkillBase:

    @property
    def name(self) -> str:
        return "sandbox_manager"

    @property
    def description(self) -> str:
        return "沙箱文件管理：读取/写入/编辑/搜索/删除/列表/移动/复制文件，发送文件到聊天"

    @property
    def instructions(self) -> str:
        return (
            "沙箱文件管理 Skill。你可以直接操作沙箱内的文件。\n\n"
            "=== 能力边界 ===\n"
            "你可以自己做（简单、无需代码执行）：\n"
            "  - 写入/编辑纯文本文件（.txt .md .json .yaml .py .html .css .js .csv 等）\n"
            "  - 读取/搜索/列出/移动/复制/删除沙箱中的文件\n"
            "  - 从 URL 下载文件到沙箱\n"
            "  - 将沙箱文件发送到聊天\n\n"
            "你必须委托子 agent 的场景（需要运行代码）：\n"
            "  - 生成 PDF / 图片 / Word / Excel / PPT / 图表\n"
            "  - 数据处理、格式转换\n"
            "  - 任何需要运行 Python/Shell 的操作\n"
            "  委托方式：background_trigger__submit_problem\n\n"
            "=== 委托流程 ===\n"
            "用户要生成文件 → submit_problem(question=\"生成xxx...\")\n"
            "              → 可在合适时 send_reply 告知用户稍候（不强制）\n"
            "              → 收到后台通知（含文件路径）\n"
            "              → send_chat_file(path) 发送给用户\n\n"
            "=== 工具列表 ===\n"
            "  read_file(path, chat_flow_id)  — 读取文件（返回文本或 base64）\n"
            "  write_file(path, content, chat_flow_id) — 写入文本内容到文件\n"
            "  write_file_base64(path, content_base64, chat_flow_id) — 写入 base64 数据\n"
            "  edit_file(path, old_string, new_string, chat_flow_id) — 原地替换文本片段\n"
            "  glob_files(pattern, path, chat_flow_id) — 按 glob 模式搜索文件名\n"
            "  grep_files(pattern, path, glob, chat_flow_id) — 按正则搜索文件内容\n"
            "  list_files(path, pattern, chat_flow_id) — 列出目录\n"
            "  delete_file(path, chat_flow_id) / move_file / copy_file\n"
            "  download_file(url, save_name, chat_flow_id) — 从 URL 下载\n"
            "  send_file(path, chat_flow_id) / send_chat_file(path, chat_flow_id) — 发送到聊天\n"
            "  hold_temp(chat_flow_id, minutes) — 保活临时目录\n\n"
            "## 下载任务（重要）\n"
            "download_file 为会话工具(session模式)：\n"
            "  - 调用后立即返回 session_submitted，实际下载在后台进行\n"
            "  - timeout_seconds 默认为 300 秒（5分钟），agent 可按需设置，最长 1800 秒（30分钟）\n"
            "  - 收到返回后可以继续聊天或处理其他事情；不要轮询或反复提交\n"
            "  - 系统会在下载完成后通过通知自动唤醒你，届时携带文件路径\n\n"
            "## chat_flow_id\n"
            "取 pipeline_key 的值（格式 group:12345 或 private:12345）。\n"
            "生产调用由宿主绑定当前聊天和 owner；参数不能切换聊天，发送也仅允许当前聊天。\n"
            "共享持久目录必须显式使用 shared:docs/... 等路径；共享修改需 agent_shared_write 凭据。\n"
            "覆盖已有 base64 文件需 agent_execute 凭据。已有文本文件修改请先 read_file。\n\n"
            "## 临时目录 vs 沙箱根（重要）\n"
            "路径选择规则：除非文件是长期复用的工具/文档/资源，否则一律写入临时目录。\n"
            "write_file / write_file_base64 写入的文件位于临时目录（sandbox/temp/{chat_flow_id}/）。\n"
            "生产工具的相对路径始终基于宿主绑定的当前聊天临时目录，不能使用 ../ 切换聊天。\n"
            "持久化资源必须显式使用 shared:tools/...、shared:docs/...、shared:assets/... 等白名单路径。\n"
            "无调用上下文的宿主直调保留历史 root/chat_flow_id 路径接口；模型不能选择该模式。\n\n"
            "## 持久化文件操作（tools/docs/assets 目录）\n"
            "  操作前先调用 file_storage__read_storage_doc 查看索引\n"
            "  修改后调用 file_storage__update_storage_doc 更新索引"
        )

    @property
    def session_tools(self) -> set[str]:
        return {"download_file"}

    def __init__(
        self,
        sandbox_service: Any = None,
        adapter: Any = None,
        file_server: Any = None,
        hold_max_minutes: int = 120,
        credential_manager: Any = None,
        reviewer: Any = None,
        auto_review: bool = True,
        review_timeout_seconds: float = 30.0,
        admin_self_authorize: bool = False,
        admin_self_authorize_chats: Any = None,
    ) -> None:
        self._sandbox = sandbox_service
        from neobot_app.runtime.agent_file_tools import AgentFileTools
        self._file_tools = AgentFileTools(sandbox_service) if sandbox_service is not None else None
        self._file_owner = f"legacy-sandbox-skill:{id(self)}"
        self._adapter = adapter
        self._file_server = file_server
        self._hold_max_minutes = hold_max_minutes
        from neobot_app.agent_tools.permissions import ToolPermissions
        self._permissions = ToolPermissions(
            credential_manager,
            reviewer=reviewer,
            auto_review=bool(auto_review),
            review_timeout_seconds=float(review_timeout_seconds or 30.0),
            admin_self_authorize=bool(admin_self_authorize),
            admin_self_authorize_chats=admin_self_authorize_chats,
        )

    def reset(self) -> None:
        pass

    def _resolve_send_path(self, path_str: str, chat_flow_id: str | None = None) -> Path:
        from neobot_app.agent_tools.invocation import CURRENT_INVOCATION
        invocation = CURRENT_INVOCATION.get()
        if invocation is not None:
            if self._file_tools is None:
                raise PermissionError("sandbox_service required for model file delivery")
            return self._file_tools.resolve_path(path_str, owner=invocation.context.owner,
                                                 chat_flow_id=invocation.context.chat_flow_id)
        p = Path(path_str)
        if p.is_absolute() and p.exists():
            return p
        if self._sandbox is not None:
            try:
                resolved = self._sandbox.resolve_read_path(path_str, chat_flow_id)
                if resolved.exists():
                    return resolved
            except Exception:
                pass
        return p

    def _resolve_write_path(self, rel_path: str, chat_flow_id: str) -> Path:
        if self._sandbox is not None:
            return self._sandbox.resolve_path(rel_path, chat_flow_id)
        return Path(rel_path)

    def _get_chat_flow_id(self, args: dict) -> str:
        cid = str(args.get("chat_flow_id", "")).strip()
        if not cid:
            cid = str(args.get("pipeline_key", "")).strip()
        return cid
