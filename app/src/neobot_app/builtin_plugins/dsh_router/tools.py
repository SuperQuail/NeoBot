"""dsh_router 的 LLM 工具（最终名 ``dsh_router__*``，不拆 package）。

设计要点：

- 参数 schema 全部显式声明（``parameters=``），因此模型看到的参数就是这里列出的；
- ``pipeline_key`` / ``_requester_id`` 由宿主回复分派注入（见 reply/tool_parts/dispatch.py），
  不写进 schema，模型既看不到也无法伪造；
- 工具默认走 deferred 技能：主 Agent 需要先 ``skills__load_tools`` 才会看到它们，
  这是本体的既有机制，插件不额外处理；
- 网关 / Router 模式缺失时返回中文提示，不抛异常（插件加载失败比功能缺失更糟）。

注册采用「模块级函数 + register(plugin)」，避免 ``tools`` 与插件入口互相 import。
"""

from __future__ import annotations

from typing import Any

from .service import DshRouterService

#: 运行时绑定的服务（on_load 时注入；热重载会换成新对象）。
_service: DshRouterService | None = None

NOT_READY_TEXT = "dsh_router 尚未加载完成（插件正在启动或已停用），稍后再试。"
NO_CHAT_TEXT = "无法确定当前会话（缺少 pipeline_key）：请在聊天里直接使用本工具。"
OWNER_DENIED_TEXT = "这个任务不是你发起的，只有发起人或系统后台可以操作。"


def bind_service(service: DshRouterService | None) -> None:
    global _service
    _service = service


def get_service() -> DshRouterService | None:
    return _service


def _ready() -> tuple[DshRouterService | None, str]:
    if _service is None:
        return None, NOT_READY_TEXT
    return _service, ""


def _chat(pipeline_key: str) -> tuple[str, str]:
    key = str(pipeline_key or "").strip()
    if not key:
        return "", NO_CHAT_TEXT
    return key, ""


def _owner_denied(owner_user_id: int | None, requester_id: int | None) -> bool:
    """后台触发（requester 为空）一律放行；否则只允许 owner 本人。"""
    if requester_id is None:
        return False
    return owner_user_id is not None and int(owner_user_id) != int(requester_id)


def _params(properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    return {"properties": dict(properties or {}), "required": list(required or [])}


_PROPOSAL_PROPERTIES = {
    "task": {
        "type": "string",
        "description": "要交给 worker 完成的完整任务描述（说清目标、约束与验收方式）",
    },
    "cwd": {
        "type": "string",
        "description": "工作目录；必须落在 config.workspaces 之内，留空表示用唯一工作区",
    },
    "mode": {
        "type": "string",
        "enum": ["read", "write"],
        "description": "read=只读分析，write=允许改代码；默认 write",
    },
}


async def propose(
    task: str,
    cwd: str = "",
    mode: str = "write",
    pipeline_key: str = "",
    _requester_id: int | None = None,
) -> str:
    service, error = _ready()
    if error:
        return error
    key, error = _chat(pipeline_key)
    if error:
        return error
    return service.propose(key, _requester_id, task, cwd=cwd, mode=mode)


async def dispatch(
    task: str = "",
    cwd: str = "",
    mode: str = "",
    pipeline_key: str = "",
    _requester_id: int | None = None,
) -> str:
    service, error = _ready()
    if error:
        return error
    key, error = _chat(pipeline_key)
    if error:
        return error
    return service.dispatch(key, _requester_id, task=task, cwd=cwd, mode=mode)


async def tasks(pipeline_key: str = "", _requester_id: int | None = None) -> str:
    service, error = _ready()
    if error:
        return error
    key, error = _chat(pipeline_key)
    if error:
        return error
    return service.tasks(key)


async def status(task_id: str, pipeline_key: str = "", _requester_id: int | None = None) -> str:
    service, error = _ready()
    if error:
        return error
    return service.status(task_id)


async def send(
    task_id: str,
    text: str,
    mode: str = "steer",
    pipeline_key: str = "",
    _requester_id: int | None = None,
) -> str:
    service, error = _ready()
    if error:
        return error
    record = service.store.get(task_id)
    if record is not None and _owner_denied(record.owner_user_id, _requester_id):
        return OWNER_DENIED_TEXT
    return service.send(task_id, text, mode=mode)


async def cancel(
    task_id: str,
    reason: str = "",
    pipeline_key: str = "",
    _requester_id: int | None = None,
) -> str:
    service, error = _ready()
    if error:
        return error
    record = service.store.get(task_id)
    if record is not None and _owner_denied(record.owner_user_id, _requester_id):
        return OWNER_DENIED_TEXT
    return service.cancel(task_id, reason=reason)


async def approve(
    request_id: str,
    allow: bool,
    pipeline_key: str = "",
    _requester_id: int | None = None,
) -> str:
    service, error = _ready()
    if error:
        return error
    record = service.find_by_request(request_id)
    if record is not None and _owner_denied(record.owner_user_id, _requester_id):
        return OWNER_DENIED_TEXT
    return service.approve(request_id, bool(allow))


async def exit(pipeline_key: str = "", _requester_id: int | None = None) -> str:
    service, error = _ready()
    if error:
        return error
    key, error = _chat(pipeline_key)
    if error:
        return error
    if _owner_denied(service.mode_owner(key), _requester_id):
        return OWNER_DENIED_TEXT
    active = service.store.active(key)
    if active:
        ids = "、".join(record.task_id for record in active[:3])
        more = " 等" if len(active) > 3 else ""
        return f"还有 {len(active)} 个未结束任务（{ids}{more}），先等它们结束或 cancel 再退出。"
    return service.exit_mode(key)


#: 工具名 -> (处理器, 描述, 参数 schema)。最终全局名是 ``dsh_router__<name>``。
TOOL_SPECS: tuple[tuple[str, Any, str, dict[str, Any]], ...] = (
    (
        "propose",
        propose,
        "为当前会话起草一份 DSH 派发提案（任务 + 工作区 + 模式），把结果原样给用户确认。"
        "必须先 propose 并等用户明确同意，才能调用 dispatch；提案 10 分钟后过期。",
        _params(_PROPOSAL_PROPERTIES, ["task"]),
    ),
    (
        "dispatch",
        dispatch,
        "把已确认的提案派发给本机 DSH worker。只有用户确认过 propose 的结果后才能调用；"
        "派发后本会话进入 Router 模式，进度与卡点会主动通知。",
        _params(_PROPOSAL_PROPERTIES, []),
    ),
    (
        "tasks",
        tasks,
        "列出当前会话的 DSH 任务（状态 / 最近摘要）。",
        _params(),
    ),
    (
        "status",
        status,
        "查看某个 DSH 任务的详情：状态、工作区、最近摘要、产物与待审批卡点。",
        _params({"task_id": {"type": "string", "description": "任务 id（形如 dsh-abcd1234）"}}, ["task_id"]),
    ),
    (
        "send",
        send,
        "给正在运行的 DSH 任务补一句话。mode=steer 立刻插话，mode=queue 排到当前轮之后。"
        "只有任务发起人或后台流程可以调用。",
        _params(
            {
                "task_id": {"type": "string", "description": "任务 id"},
                "text": {"type": "string", "description": "要告诉 worker 的内容"},
                "mode": {
                    "type": "string",
                    "enum": ["steer", "queue"],
                    "description": "steer=立刻插话（默认），queue=本轮之后",
                },
            },
            ["task_id", "text"],
        ),
    ),
    (
        "cancel",
        cancel,
        "取消一个正在运行的 DSH 任务（说明原因更利于 worker 收尾）。",
        _params(
            {
                "task_id": {"type": "string", "description": "任务 id"},
                "reason": {"type": "string", "description": "取消原因（可选）"},
            },
            ["task_id"],
        ),
    ),
    (
        "approve",
        approve,
        "审批 worker 的卡点请求：allow=true 放行，false 拒绝。request_id 来自通知或 /dsh pending。",
        _params(
            {
                "request_id": {"type": "string", "description": "待审批请求的 id"},
                "allow": {"type": "boolean", "description": "true=允许，false=拒绝"},
            },
            ["request_id", "allow"],
        ),
    ),
    (
        "exit",
        exit,
        "退出 Router 模式，让当前会话恢复常规工具面。没有活跃任务时才能退出。",
        _params(),
    ),
)


def register(plugin_obj: Any) -> None:
    """把本模块的工具挂到插件对象上（由插件入口在 import 时调用一次）。"""
    for name, handler, description, parameters in TOOL_SPECS:
        plugin_obj.tool(name, description=description, parameters=parameters)(handler)


__all__ = [
    "NOT_READY_TEXT",
    "NO_CHAT_TEXT",
    "OWNER_DENIED_TEXT",
    "TOOL_SPECS",
    "approve",
    "bind_service",
    "cancel",
    "dispatch",
    "exit",
    "get_service",
    "propose",
    "register",
    "send",
    "status",
    "tasks",
]
