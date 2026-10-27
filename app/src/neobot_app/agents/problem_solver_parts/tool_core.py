"""执行器生命周期、工具分发与兼容文件工具。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.web_search_package import WebSearchExecutor
from neobot_app.agent_tools.contracts import AgentToolError, ToolContext

from .models import (
    _CHAT_FLOW_ID,
    _SOLUTION_RESULT,
    _SOLVER_CHAT_CONTEXT,
    _TOOL_CONTEXT,
    _json,
)


class ProblemSolverToolCoreMixin:
    """执行器生命周期、工具分发与兼容文件工具。"""

    def __init__(
        self,
        *,
        logger: Logger | None = None,
        web_search_config: dict | None = None,
        sandbox_service: Any = None,
        vision_provider: Any = None,
    ) -> None:
        self._logger = logger or NullLogger()
        ws = web_search_config or {}
        self._search = WebSearchExecutor(
            engines=ws.get("engines"),
            max_rounds=ws.get("max_rounds", 5),
            preview_pages_limit=ws.get("preview_pages_limit", 30),
            variant_result_limit=ws.get("variant_result_limit", 6),
            browser_fallback=ws.get("browser_fallback", True),
            browser_timeout_seconds=ws.get("browser_timeout_seconds", 8.0),
            engine_budgets=ws.get("engine_budgets"),
            deepseek_enabled=ws.get("deepseek_enabled"),
            deepseek_api_key=ws.get("deepseek_api_key", ""),
            deepseek_base_url=ws.get("deepseek_base_url", ""),
            deepseek_timeout_seconds=ws.get("deepseek_timeout_seconds", 20.0),
            deepseek_quota_cooldown_seconds=ws.get("deepseek_quota_cooldown_seconds", 3600.0),
        )
        self._sandbox = sandbox_service
        self._vision_provider = vision_provider
        self._runtime: Any = None

    def reset_search(self) -> None:
        """复位搜索会话计数器，每次解题任务启动时调用。"""
        self._search.reset()

    async def close(self) -> None:
        """释放执行器资源。"""

    async def execute(self, name: str, args: dict) -> str:
        if self._runtime is not None:
            context = _TOOL_CONTEXT.get()
            if not isinstance(context, ToolContext):
                return _json({"ok": False, "code": "CONTEXT_REQUIRED", "error": "缺少可信解题任务身份；不从提示词推断权限"})
            try:
                if name in self._runtime.capability_names() or name == "run_code":
                    value = await self._runtime.execute(name, args, context,
                        external_dispatch=self.execute, external_definitions=self._business_definitions())
                    return _json(value)
                if name not in {"get_chat_context", "submit_solution"}:
                    raise AgentToolError("TOOL_DENIED", "Legacy aliases are not available; use the current canonical tool catalog")
            except AgentToolError as exc:
                return _json({"ok": False, "code": exc.code, "error": str(exc), "details": exc.details})
            except (ValueError, OSError) as exc:
                return _json({"ok": False, "code": "FILE_ERROR", "error": str(exc)})
        if name == "get_chat_context":
            context = _SOLVER_CHAT_CONTEXT.get("")
            chat_flow_id = self._parse_chat_flow_id()
            path_info = ""
            if chat_flow_id and self._sandbox is not None:
                temp_dir = self._sandbox.get_temp_dir(chat_flow_id)
                path_info = (
                    f"\n[文件路径上下文]\n"
                    f"chat_flow_id: {chat_flow_id}\n"
                    f"临时目录: {temp_dir}\n"
                    f"规则：write/run_python 输出的文件默认写入上述临时目录。"
                    f"除非文件是需要长期复用的工具/文档/资源，否则一律放入临时目录。"
                )
            if not context:
                return f"无聊天上下文可用（可能未通过主Agent委托调用）{path_info}"
            return context + path_info
        if name == "search":
            return await self._search.execute("search", args)
        if name == "read_page":
            return await self._search.execute("read", args)
        if name == "search_status":
            return await self._search.execute("status", args)
        if name == "submit_solution":
            solution = str(args.get("solution") or "").strip()
            if not solution:
                return "错误：solution 不能为空"
            _SOLUTION_RESULT.set(solution)
            return "解题结果已提交"
        if name == "run_python":
            return await self._execute_run_python(args)
        if name == "parse_image":
            return await self._execute_parse_image(args)
        if name == "write_file":
            return await self._execute_write_file(args)
        if name == "read_file":
            return await self._execute_read_file(args)
        if name == "list_files":
            return await self._execute_list_files(args)
        return f"未知工具: {name}"

    async def _execute_compatible_file(self, name: str, args: dict, context: ToolContext) -> dict:
        required = {"write_file": "write", "read_file": "read", "list_files": "glob", "parse_image": "read_image"}[name]
        if context.allowed_tools is not None and required not in context.allowed_tools:
            raise AgentToolError("TOOL_DENIED", "Legacy file alias cannot bypass inherited tool permissions")
        if name == "parse_image":
            return await self._runtime.execute("read_image", {"file_path": args.get("image_path", ""),
                "requirement": args.get("requirement", "请分析图片内容。")}, context)
        raw = str(args.get("path") or ".")
        path = self._runtime.files.resolve_path(raw, owner=context.owner, chat_flow_id=context.chat_flow_id,
                                                write=name == "write_file")
        if name == "list_files":
            return {"ok": True, "files": (await self._sandbox.list_files(path))[:200]}
        if name == "read_file":
            return await self._runtime.execute("read", {"file_path": str(path)}, context)
        import base64
        encoded = args.get("content_base64", "")
        if not isinstance(encoded, str) or len(encoded) > 1_048_576:
            raise AgentToolError("INVALID_ARGS", "Expected bounded base64 content")
        data = base64.b64decode(encoded, validate=True)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            if self._runtime.state.is_planning(context):
                raise AgentToolError("PLAN_MODE", "Cannot write files in plan mode")
            if self._runtime.files.is_shared_write("write", {"file_path": raw}):
                await self._runtime.permissions.authorize(
                    context,
                    "agent_shared_write",
                    tool_name="write_file_base64",
                    arguments={"file_path": raw, "content_base64": args.get("content_base64", "")},
                )
            if path.exists():
                raise AgentToolError("FILE_EXISTS", "Binary write requires a new destination; use a new filename")
            await self._sandbox.write_file(path, data)
            return {"ok": True, "path": str(path), "size": len(data)}
        return await self._runtime.execute("write", {"file_path": str(path), "content": text}, context)

    def _get_sandbox_work_dir(self) -> Path | None:
        """返回沙箱工作目录，供 run_python 的 cwd 和 write_file 使用。

        从 _SOLVER_CHAT_CONTEXT 解析 chat_flow_id，优先使用 temp/{chat_flow_id}/，
        回退到沙箱根目录。
        """
        if self._sandbox is None:
            return None
        chat_flow_id = self._parse_chat_flow_id()
        if chat_flow_id:
            return self._sandbox.ensure_temp_dir(chat_flow_id)
        return self._sandbox.resolve_path(".")

    @staticmethod
    def _parse_chat_flow_id() -> str | None:
        """从结构化 ContextVar 获取 chat_flow_id，兼容旧格式上下文。"""
        # 优先：_run_solve 注入的结构化 _CHAT_FLOW_ID
        cfid = _CHAT_FLOW_ID.get("")
        if cfid:
            return cfid
        # 回退：正则解析旧格式 [当前会话] 文本（兼容旧格式）
        import re

        ctx = _SOLVER_CHAT_CONTEXT.get("")
        if not ctx:
            return None
        m = re.search(r"\[当前会话\]\s*\nkind=(\w+)\s*\nid=(\S+)", ctx)
        if m:
            return f"{m.group(1)}_{m.group(2)}"
        return None
