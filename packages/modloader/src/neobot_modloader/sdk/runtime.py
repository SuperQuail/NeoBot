"""把统一契约绑定到当前插件代，并提供不执行代码的离线读取。"""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from neobot_modloader.loading.manifest import read_manifest

from .actions import ActionError, ActionInvocation
from .contract import validate_contract

if TYPE_CHECKING:
    from neobot_modloader.runtime import PluginRuntime

_MAX_CONTRACT_BYTES = 1024 * 1024
_READY = {"loaded", "running"}


def _static_contract(directory: Path, name: str, version: str) -> dict | None:
    try:
        manifest = read_manifest(directory / "plugin.toml")
        declaration = manifest.get("sdk")
        if declaration is None:
            return None
        if not isinstance(declaration, dict) or type(declaration.get("version")) is not int:
            raise ValueError("SDK 声明无效")
        if declaration["version"] != 1:
            raise ValueError("SDK 版本不支持")
        filename = declaration.get("contract", "plugin.contract.json")
        if not isinstance(filename, str) or not filename or Path(filename).is_absolute():
            raise ValueError("契约路径无效")
        root = directory.resolve()
        path = (root / filename).resolve()
        path.relative_to(root)
        with path.open("rb") as stream:
            raw = stream.read(_MAX_CONTRACT_BYTES + 1)
        if len(raw) > _MAX_CONTRACT_BYTES:
            raise ValueError("契约过大")
        document = json.loads(raw.decode("utf-8-sig"))
        if validate_contract(document):
            raise ValueError("契约结构无效")
        identity = document["plugin"]
        if identity["name"] != name or identity["version"] != version:
            raise ValueError("契约身份与插件不匹配")
        return document
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise ActionError("contract_invalid", "插件随包契约无效，请重新导出并检查") from None


def describe_runtime_surface(runtime: PluginRuntime, name: str) -> dict[str, Any]:
    """运行中读取当前代，停用或失败时只读取经过校验的静态产物。"""
    record = runtime.manager.get_record(name)
    if record is not None and record.state.value in _READY and record.error is None:
        try:
            contract = record.plugin.surface.describe(record.plugin)
            if validate_contract(contract):
                raise ValueError("契约结构无效")
        except Exception:
            raise ActionError("contract_invalid", "插件运行契约无效") from None
        return {"contract": contract, "available": True, "state": record.state.value, "source": "runtime"}
    snapshot = next((item for item in runtime.snapshot_plugins() if item.name == name), None)
    if snapshot is None:
        raise ActionError("plugin_not_found", "插件不存在")
    path = snapshot.path
    contract = None
    if path is not None and Path(path).is_dir():
        contract = _static_contract(Path(path), name, snapshot.version)
    return {
        "contract": contract,
        "available": False,
        "state": snapshot.state,
        "source": "package" if contract else "none",
    }


async def invoke_runtime_action(
    runtime: PluginRuntime, name: str, action_id: str, payload: Any, invocation: ActionInvocation
) -> Any:
    """调用占用运行时代锁，避免热重载后继续使用旧处理器和已关闭资源。"""
    from neobot_modloader.runtime import OperationBusy

    if not isinstance(invocation, ActionInvocation):
        raise ActionError("invalid_invocation", "缺少可信调用身份")
    try:
        async with runtime._named_operation(name):
            record = runtime.manager.get_record(name)
            if record is None or record.state.value not in _READY or record.error is not None:
                raise ActionError("plugin_not_ready", "插件尚未就绪，请先启用并检查运行状态")
            current = replace(invocation, context=record.context)
            return await record.plugin.surface.invoke(record.plugin, action_id, payload, current)
    except OperationBusy:
        raise ActionError("plugin_busy", "插件正在执行其他操作，请稍后重试") from None
