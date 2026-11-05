"""``/dsh`` 命令：status / tasks / pending / approve / cancel / exit / help。

命令走宿主命令表（``ctx.app_commands``），因此出现在 /help 列表里，
权限档位来自插件配置 ``command_permission``（默认 2=超级管理员）。
权限校验由宿主命令服务统一完成，这里只做子命令解析。
"""

from __future__ import annotations

from typing import Any

from .service import DshRouterService

USAGE = "status | tasks | pending | approve <request_id> allow|deny | cancel <task_id> [原因] | exit | help"


def _pipeline_key(command_ctx: Any) -> str:
    kind = "group" if str(getattr(command_ctx, "kind", "") or "") == "group" else "private"
    conv_id = str(getattr(command_ctx, "conv_id", "") or "").strip()
    if not conv_id:
        return ""
    return f"{kind}:{conv_id}"


async def run_command(service: DshRouterService, command_ctx: Any) -> str:
    args = [str(item) for item in (getattr(command_ctx, "args", None) or [])]
    sub = args[0].strip().lower() if args else "status"
    pipeline_key = _pipeline_key(command_ctx)

    if sub in {"help", "帮助", "-h", "--help"}:
        return f"用法：/dsh {USAGE}\n权限：需要超级管理员" if not pipeline_key else USAGE

    if sub == "status":
        return service.overview(pipeline_key)
    if sub == "tasks":
        return service.tasks(pipeline_key)
    if sub == "pending":
        return service.pending_text(pipeline_key)
    if sub == "approve":
        if len(args) < 3:
            return f"用法：/dsh approve <request_id> allow|deny\n提示：{USAGE}"
        verdict = args[2].strip().lower()
        if verdict not in {"allow", "deny", "yes", "no", "允许", "拒绝"}:
            return "审批结果只能是 allow 或 deny。"
        allow = verdict in {"allow", "yes", "允许"}
        return service.approve(args[1], allow)
    if sub == "cancel":
        if len(args) < 2:
            return "用法：/dsh cancel <task_id> [原因]"
        reason = " ".join(args[2:]).strip()
        return service.cancel(args[1], reason=reason)
    if sub == "exit":
        active = service.store.active(pipeline_key)
        if active:
            return f"还有 {len(active)} 个未结束任务，先等它们结束或 /dsh cancel 再退出。"
        return service.exit_mode(pipeline_key)
    return f"未知子命令 {sub}。用法：/dsh {USAGE}"


def register_commands(ctx: Any, service: DshRouterService) -> int:
    """把 /dsh 注册进宿主命令表；宿主没有命令表时静默跳过。"""
    registrar = getattr(ctx, "app_commands", None)
    if registrar is None or not getattr(registrar, "available", False):
        return 0
    permission = int(service.config.command_permission)

    @registrar.register(
        "dsh",
        description="DSH 任务路由：查看 / 审批 / 取消派给 worker 的开发任务",
        usage=USAGE,
        permission=permission,
    )
    async def _dsh_command(command_ctx: Any) -> str:
        return await run_command(service, command_ctx)

    return 1


__all__ = ["USAGE", "register_commands", "run_command"]
