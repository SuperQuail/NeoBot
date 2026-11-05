"""说明书有限步骤元数据的共用校验；不执行命令或保存配置。"""

from __future__ import annotations

from typing import Any


FORM_PHASES = frozenset({"start", "edit", "validate", "save", "saved"})


def guide_form_errors(step: Any, location: str) -> list[str]:
    """表单流程只用于配置目标，诊断固定到字段位置且不回显输入。"""
    if "form" not in step:
        return []
    errors = []
    phase = step["form"]
    if not isinstance(phase, str) or phase not in FORM_PHASES:
        errors.append(f"{location}.form 必须是 start、edit、validate、save 或 saved")
    target = step.get("target")
    if not isinstance(target, str) or not (target == "config" or target.startswith("config.")) or "command" in step:
        errors.append(f"{location}.form 只能用于无 command 的配置步骤")
    return errors


def guide_command_errors(value: Any, location: str) -> list[str]:
    """声明与静态契约共用相同字段规则，诊断不回显作者填写的内容。"""
    if not isinstance(value, dict):
        return [f"{location} 必须是对象"]
    errors = []
    if set(value) - {"text", "context", "reply"}:
        errors.append(f"{location} 只支持 text、context 和 reply")
    for key in ("text", "context", "reply"):
        if key == "reply" and key not in value:
            continue
        text = value.get(key)
        if not isinstance(text, str) or not text.strip():
            errors.append(f"{location}.{key} 必须是非空字符串")
    return errors
