"""网页面板「提示词」页的后端逻辑。

职责：
- 读取 data/prompts 的默认/自定义提示词并给出可编辑视图；
- 用模拟取值渲染模板,提供「转义后内容」实时预览；
- 把用户的修改写进 data/prompts/custom/prompts.toml（只动自定义文件）。

写盘与预览都不依赖面板进程状态:预览是纯函数,写盘只碰自定义提示词文件,
因此可以直接被单元测试覆盖。
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import tomlkit

from neobot_app.prompt.render import render_template, template_placeholders
from neobot_app.prompt.store import parse_prompt_file
from neobot_app.time_context import get_current_time_values

#: 会被当作模板渲染的键（其余键按纯文本处理,不提供预览）
RENDERABLE_KEYS = frozenset({"template", "system_prompt"})
#: 分区内的子表键（[problem_solver.runtime] 这类）
_SUB_TABLE_KEYS = ("runtime",)


def sample_values(config: Any = None) -> dict[str, str]:
    """模拟转义用的占位符取值:优先真实配置,其余用固定样例。

    面板的「预览」不连接真实聊天流,因此这里给出一份可读的样例数据,
    让使用者能看到模板最终长什么样。
    """
    values: dict[str, str] = {
        "bot_name": "小助手",
        "bot_account": "999888",
        "other_name": ",也有人叫你Neo、铸币bot",
        "bot_data": "你是一个可爱的机器人,如果你对别人有备注,你会倾向于叫你备注对方的名字",
        "group_name": "示例群聊",
        "group_id": "123456789",
        "group_description": "这是一个示例群聊",
        "group_admin": "群主:小明(123456)",
        "bot_group_admin_status": "你是本群管理员",
        "group_info": "示例群聊的档案:群友主要讨论编程与日常。",
        "member_list": "小明(123456)、小红(789012)",
        "friend_name": "小明",
        "remark": "大学同学",
        "profile": "小明是一个喜欢打游戏的大学生,性格开朗",
        "friend_info": "QQ: 123456\n性别: 男",
        "key_word_reaction_list": "<追加信息_1>对方提到妈妈,可以反问是不是叫夏亚</追加信息_1>",
        "memory_list": "小明生日是明天",
        "numbering_guide": (
            "消息格式说明:每条消息以「[msg_id=真实message_id] 编号: 用户名: 消息内容」"
            "的格式呈现。\n例如:[msg_id=1425980020] 1: 小明: 你好"
        ),
        "new_member_profiles": "[新出现的群友档案]\n小红:新加入的群友",
        "member_profiles": "小红:新加入的群友",
        "tool_name": "send_reply",
        "summary": "已发送 2 条消息",
        "original_chars": "128",
        "peer_descriptions": "- self_heal: 系统自修复诊断",
        "mode_note": "当前任务模式为普通模式,直接调用精简工具。",
        "timeout_seconds": "600",
        "max_iterations": "20",
    }
    values.update(get_current_time_values())
    values.setdefault("current_datetime", values.get("current_time", ""))

    if config is not None:
        bot = getattr(config, "bot", None)
        nick = getattr(bot, "nick_name", None)
        if nick:
            values["bot_name"] = str(nick)
        account = getattr(bot, "account", None)
        if account:
            values["bot_account"] = str(account)
        persona = getattr(bot, "bot_data", None)
        if persona:
            values["bot_data"] = str(persona)
        aliases = [str(item).strip() for item in (getattr(bot, "alias_name", None) or [])]
        aliases = [item for item in aliases if item]
        values["other_name"] = (",也有人叫你" + "、".join(aliases)) if aliases else ""
        chat = getattr(config, "chat", None)
        descriptions = getattr(chat, "group_description", None) or {}
        if isinstance(descriptions, dict) and descriptions:
            group_id, description = next(iter(descriptions.items()))
            values["group_id"] = str(group_id)
            values["group_description"] = str(description)
    return values


def preview_template(
    template: str, values: dict[str, str] | None = None
) -> dict[str, Any]:
    """渲染模板并报告占位符使用情况(纯函数,供实时预览使用)。"""
    merged = sample_values()
    if values:
        for key, value in values.items():
            name = str(key or "").strip()
            if name:
                merged[name] = "" if value is None else str(value)
    rendered = render_template(template or "", merged)
    placeholders = sorted(template_placeholders(template or ""))
    remaining = sorted(template_placeholders(rendered))
    return {
        "rendered": rendered,
        "placeholders": placeholders,
        "unresolved": remaining,
        "values": {name: merged.get(name, "") for name in placeholders},
    }


def _iter_editable_keys(section: dict[str, Any]) -> list[tuple[str, str, str]]:
    """展开分区里可编辑的 (键路径, 显示名, 类型)。

    类型为 "template"(可预览渲染) 或 "text"(纯文本,如子 Agent 的 description)。
    """
    items: list[tuple[str, str, str]] = []
    for key, value in section.items():
        if key == "enabled":
            continue
        if isinstance(value, str):
            kind = "template" if key in RENDERABLE_KEYS else "text"
            items.append((key, key, kind))
        elif isinstance(value, dict) and key in _SUB_TABLE_KEYS:
            for sub_key, sub_value in value.items():
                if not isinstance(sub_value, str):
                    continue
                kind = "template" if sub_key in RENDERABLE_KEYS else "text"
                items.append((f"{key}.{sub_key}", f"{key}.{sub_key}", kind))
    return items


def describe_sections(
    store: Any, *, custom_sections: dict[str, Any] | None = None
) -> dict[str, Any]:
    """把提示词存储展开成面板可编辑的结构。"""
    custom_sections = custom_sections or {}
    merged_sections = store.sections() if store is not None else {}
    default_sections = _default_sections(store)
    sections: list[dict[str, Any]] = []
    for name in sorted(merged_sections):
        merged = merged_sections.get(name) or {}
        default = default_sections.get(name) or {}
        custom = custom_sections.get(name) or {}
        keys: list[dict[str, Any]] = []
        for path, label, kind in _iter_editable_keys(merged):
            default_value = _lookup(default, path)
            custom_value = _lookup(custom, path)
            value = _lookup(merged, path)
            keys.append(
                {
                    "path": path,
                    "label": label,
                    "kind": kind,
                    "value": value,
                    "default": default_value,
                    "custom": custom_value,
                    "overridden": custom_value is not None,
                    "placeholders": sorted(template_placeholders(value or ""))
                    if kind == "template"
                    else [],
                }
            )
        if not keys:
            continue
        sections.append(
            {
                "name": name,
                "keys": keys,
                "enabled": merged.get("enabled"),
                "customized": bool(custom),
            }
        )
    return {
        "sections": sections,
        "default_file": str(getattr(store, "default_file", "")),
        "custom_file": str(getattr(store, "custom_file", "")),
    }


def _default_sections(store: Any) -> dict[str, Any]:
    """内置默认提示词分区(用于「恢复默认」与差异展示)。"""
    from neobot_app.prompt.store import DEFAULT_TEMPLATE_FILE

    if DEFAULT_TEMPLATE_FILE.is_file():
        return parse_prompt_file(DEFAULT_TEMPLATE_FILE)
    # 内置模板文件缺失(异常部署)时退回 store 自己的默认分区读取
    loader = getattr(store, "_load_default_sections", None)
    if callable(loader):
        return loader()
    return {}


def _lookup(section: dict[str, Any], path: str) -> Any:
    current: Any = section
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current if isinstance(current, str) else None


def read_custom_sections(custom_file: Path) -> dict[str, Any]:
    """读取自定义提示词文件的分区(不存在时返回空字典)。"""
    return parse_prompt_file(Path(custom_file))


def write_override(
    custom_file: Path, section: str, path: str, value: str
) -> dict[str, Any]:
    """把某个键写进自定义提示词文件(只动自定义文件,写前备份)。"""
    name = str(section or "").strip()
    key_path = [part for part in str(path or "").split(".") if part]
    if not name or not key_path:
        raise ValueError("分区与键名不能为空")
    if len(key_path) > 2:
        raise ValueError("只支持「分区.键」或「分区.子表.键」两层")
    text = "" if value is None else str(value)

    custom_file = Path(custom_file)
    custom_file.parent.mkdir(parents=True, exist_ok=True)
    if custom_file.is_file():
        original = custom_file.read_text("utf-8-sig")
        doc = tomlkit.parse(original) if original.strip() else tomlkit.document()
    else:
        original = ""
        doc = tomlkit.document()

    if name not in doc:
        doc[name] = tomlkit.table()
    node: Any = doc[name]
    for part in key_path[:-1]:
        if part not in node or not isinstance(node[part], dict):
            node[part] = tomlkit.table()
        node = node[part]
    node[key_path[-1]] = text

    if original:
        _backup(custom_file, original)
    custom_file.write_text(tomlkit.dumps(doc), encoding="utf-8")
    return {
        "section": name,
        "path": ".".join(key_path),
        "value": text,
        "custom_file": str(custom_file),
    }


def remove_override(custom_file: Path, section: str, path: str) -> dict[str, Any]:
    """删除自定义提示词文件里的某个键(恢复默认值)。"""
    name = str(section or "").strip()
    key_path = [part for part in str(path or "").split(".") if part]
    if not name or not key_path:
        raise ValueError("分区与键名不能为空")
    custom_file = Path(custom_file)
    if not custom_file.is_file():
        return {"section": name, "path": ".".join(key_path), "removed": False}

    original = custom_file.read_text("utf-8-sig")
    doc = tomlkit.parse(original) if original.strip() else tomlkit.document()
    removed = False
    section_node = doc.get(name)
    if isinstance(section_node, dict):
        node: Any = section_node
        for part in key_path[:-1]:
            if isinstance(node, dict) and part in node and isinstance(node[part], dict):
                node = node[part]
            else:
                node = None
                break
        if isinstance(node, dict) and key_path[-1] in node:
            del node[key_path[-1]]
            removed = True
        # 分区内已无自定义键时整段移除,保持自定义文件干净
        if isinstance(section_node, dict) and not list(section_node.keys()):
            del doc[name]
            removed = True
    if removed:
        if original:
            _backup(custom_file, original)
        custom_file.write_text(tomlkit.dumps(doc), encoding="utf-8")
    return {"section": name, "path": ".".join(key_path), "removed": removed}


def _backup(custom_file: Path, original: str) -> None:
    """写盘前保留一份 .bak(与 scripts/prompt_builder.py 的约定一致)。"""
    try:
        backup = custom_file.with_suffix(custom_file.suffix + ".bak")
        shutil.copy2(custom_file, backup)
    except OSError:
        pass
