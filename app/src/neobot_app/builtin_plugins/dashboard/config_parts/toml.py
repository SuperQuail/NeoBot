"""config.toml 的托管字段树、密钥掩码/还原与 TOML 文档 diff/合并。"""

from __future__ import annotations

import re
from dataclasses import fields, is_dataclass
from typing import Any, Iterator, NamedTuple, get_args, get_origin

import tomlkit

from neobot_app.builtin_plugins.dashboard.security import is_sensitive_key

from .schema import _inner_types


_DELETE = object()
_MISSING = object()

#: 自由映射字段（dict 类型）：键由用户/账号决定，例如分群回复系数，
#: 表单里删掉某个键就是真的要删，不做「未知键保护」。
_FREE_MAPPING = object()


class _ListOfTables(NamedTuple):
    """表数组字段（``List[dataclass]``，如 models.registry / chat.key_word）。

    逐元素 diff：元素里面板不认识的键同样要保留。
    """

    element: Any

_MANAGED_TREES: dict[type, dict[str, Any]] = {}


def _managed_tree(schema: type) -> dict[str, Any]:
    """按 dataclass 声明生成托管字段树，用于判断哪些键允许被表单删除。

    - dataclass 字段 -> 子 dataclass（分区：只有声明过的键才允许删）
    - dict 字段 -> ``_FREE_MAPPING``（键由用户决定，允许删）
    - 其它字段 -> ``None``（标量/数组，整值替换，不涉及删键）
    """
    cached = _MANAGED_TREES.get(schema)
    if cached is not None:
        return cached
    tree: dict[str, Any] = {}
    if is_dataclass(schema):
        for field_obj in fields(schema):
            inner = _inner_types(field_obj.type)
            target = inner[0] if inner else field_obj.type
            if is_dataclass(target):
                tree[field_obj.name] = target
            elif get_origin(target) is list:
                args = get_args(target)
                element = args[0] if args else None
                tree[field_obj.name] = (
                    _ListOfTables(element) if is_dataclass(element) else None
                )
            elif get_origin(target) is dict:
                tree[field_obj.name] = _FREE_MAPPING
            else:
                tree[field_obj.name] = None
    _MANAGED_TREES[schema] = tree
    return tree


def _mask_sensitive_leaves(data: Any, found: dict[str, bool] | None = None, path: tuple[str, ...] = ()) -> Any:
    """把密钥类字段的值替换为空串，并记录「是否已设置」。

    config.toml 里也有机密（``adapter.local_auth_token`` /
    ``adapter.reverse_ws_access_token``）：认证/反向 WS 的 token 落到面板响应里，
    任何已登录会话（含只读、远程）都能拿到并冒充 OneBot 框架注入伪造事件。
    这里与 .env 的处理保持一致：只回「是否已设置」，不回值。
    """
    if isinstance(data, dict):
        masked: dict[str, Any] = {}
        for key, value in data.items():
            child_path = (*path, str(key))
            if is_sensitive_key(key):
                # 只有字符串才是真密钥。max_output_tokens / *_per_mtokens 这类数值
                # 字段名也命中密钥正则，但它们是普通数字，既不能掩码也不能登记，
                # 否则面板读到空串、新增模型行保存必 400。
                if isinstance(value, str):
                    if found is not None:
                        found[".".join(child_path)] = bool(value)
                    masked[key] = ""
                else:
                    if found is not None and value is None:
                        found[".".join(child_path)] = False
                    masked[key] = value
                continue
            masked[key] = _mask_sensitive_leaves(value, found, child_path)
        return masked
    if isinstance(data, list):
        return [_mask_sensitive_leaves(item, found, (*path, str(index))) for index, item in enumerate(data)]
    return data


_SECRET_PLACEHOLDER = "***"
_TOML_SECTION_RE = re.compile(r"^\s*\[(?P<name>[^\]]+)\]\s*(?:#.*)?$")
#: 只匹配「简单键 = 引号字符串/单 token（可带行尾注释）」，复杂值（数组、多行、
#: 时间）原样放过：面板不需要脱敏它们，误改反而是数据损坏。
_TOML_KEY_LINE_RE = re.compile(
    r"^(?P<indent>\s*)(?P<key>[A-Za-z0-9_\-]+)(?P<sep>\s*=\s*)"
    r"(?P<value>\"[^\"]*\"|'[^']*'|[^#\s]+)(?P<tail>\s*(?:#.*)?)$"
)


def _is_quoted(match: re.Match[str]) -> bool:
    """值是否为引号字符串：数值（max_output_tokens = 2048）不是密钥，别掩码。"""
    return match.group("value")[:1] in ('"', "'")


def _iter_secret_lines(source: str) -> Iterator[tuple[str, re.Match[str]]]:
    """逐行产出 (当前分区名, 匹配到的密钥行)。"""
    section = ""
    for line in source.splitlines():
        header = _TOML_SECTION_RE.match(line.strip())
        if header:
            section = header.group("name").strip()
            continue
        match = _TOML_KEY_LINE_RE.match(line)
        if match and is_sensitive_key(match.group("key")) and _is_quoted(match):
            yield section, match


def _mask_toml_source(source: str) -> str:
    """把原文里密钥键的值替换为占位符（面板响应不回明文）。"""
    out: list[str] = []
    for line in source.splitlines():
        match = _TOML_KEY_LINE_RE.match(line)
        if match and is_sensitive_key(match.group("key")) and _is_quoted(match):
            out.append(
                f'{match.group("indent")}{match.group("key")}{match.group("sep")}'
                f'"{_SECRET_PLACEHOLDER}"{match.group("tail")}'
            )
            continue
        out.append(line)
    text = "\n".join(out)
    return text + "\n" if source.endswith("\n") else text


def _restore_masked_source(current_source: str, submitted: str) -> str:
    """提交原文里仍是占位符的密钥键，还原成磁盘上的现有值。

    面板原文是脱敏后返回的：用户没动那一行（提交回来仍是 ``***``）时必须还原，
    否则一次保存就把 token 写成字面量 ``***``。
    """
    originals = {
        (section, match.group("key")): match.group("value")
        for section, match in _iter_secret_lines(current_source)
    }
    if not originals:
        return submitted
    out: list[str] = []
    section = ""
    for line in submitted.splitlines():
        header = _TOML_SECTION_RE.match(line.strip())
        if header:
            section = header.group("name").strip()
            out.append(line)
            continue
        match = _TOML_KEY_LINE_RE.match(line)
        if match and is_sensitive_key(match.group("key")):
            if match.group("value").strip("\"'") == _SECRET_PLACEHOLDER:
                original = originals.get((section, match.group("key")))
                if original is not None:
                    out.append(
                        f'{match.group("indent")}{match.group("key")}'
                        f'{match.group("sep")}{original}{match.group("tail")}'
                    )
                    continue
        out.append(line)
    text = "\n".join(out)
    return text + "\n" if submitted.endswith("\n") else text


def _mask_schema_defaults(
    item: dict[str, Any], found: dict[str, bool], path: tuple[str, ...]
) -> None:
    """schema 描述里的 default/value 同样不能带出密钥明文。"""
    # 只有字符串叶子才可能是密钥（数值字段如 max_output_tokens 只是名字像）。
    if path and is_sensitive_key(path[-1]) and item.get("type") == "str":
        for key in ("default", "value"):
            if item.get(key):
                found[".".join(path)] = True
            item[key] = ""
        return
    # 分区节点自身也带 default/value（整段配置的字典副本），里面的密钥要一并掩码。
    for key in ("default", "value"):
        value = item.get(key)
        if isinstance(value, (dict, list)):
            item[key] = _mask_sensitive_leaves(value, found, path)
    for child in item.get("fields") or []:
        if isinstance(child, dict):
            _mask_schema_defaults(child, found, (*path, str(child.get("name") or "")))
    for child in item.get("item_fields") or []:
        if isinstance(child, dict):
            _mask_schema_defaults(child, found, (*path, str(child.get("name") or "")))


def _restore_masked_secrets(current: Any, submitted: Any, path: tuple[str, ...] = ()) -> Any:
    """把被掩码的密钥字段还原成文件里的现有值。

    掩码后的空串回传时不能当成「用户清空」——否则面板保存会把 token 抹掉。
    想清空请用 TOML 模式直接编辑。
    """
    if isinstance(current, dict) and isinstance(submitted, dict):
        restored: dict[str, Any] = {}
        for key, value in submitted.items():
            child_path = (*path, str(key))
            existing = current.get(key)
            if is_sensitive_key(key) and value == "" and isinstance(existing, str) and existing:
                restored[key] = existing
                continue
            restored[key] = _restore_masked_secrets(existing, value, child_path)
        return restored
    if isinstance(current, list) and isinstance(submitted, list):
        return [
            _restore_masked_secrets(
                current[index] if index < len(current) else None,
                item,
                (*path, str(index)),
            )
            for index, item in enumerate(submitted)
        ]
    return submitted


def _filter_managed(
    schema: type,
    data: Any,
    *,
    strict: frozenset[tuple[str, ...]] = frozenset(),
    path: tuple[str, ...] = (),
) -> Any:
    """复制一份配置并丢掉声明之外的键（校验用）。

    配置文件里可能本来就有面板不认识的键（自定义分区、插件字段、更新版本
    留下的新字段）。它们既不该让整次保存因「未知配置项」失败，也不该参与
    本次校验。``strict`` 里的路径保持原样：正在编辑的那个分区若出现未知键，
    依然会被校验拦下。
    """
    if not isinstance(data, dict) or not is_dataclass(schema) or path in strict:
        return data
    tree = _managed_tree(schema)
    filtered: dict[str, Any] = {}
    for key, value in data.items():
        if key not in tree:
            continue
        child = tree[key]
        if is_dataclass(child) and isinstance(value, dict):
            filtered[key] = _filter_managed(child, value, strict=strict, path=(*path, key))
        else:
            filtered[key] = value
    return filtered


def _diff_sequence(
    current: Any, new: Any, element_schema: Any
) -> Any:
    """表数组（``[[models.registry]]`` 这类）逐元素 diff。

    数组是「整值替换」的话，元素里面板不认识的键会随一次表单保存被抹掉
    （与分区字段同一类数据丢失）。这里按序号逐元素 diff：下标对得上的元素走
    dict diff（未知键保留），新增的元素整体写入，变短的数组由合并阶段截断。
    返回 None 表示无需改动。
    """
    if not isinstance(current, list) or not isinstance(new, list):
        return new
    diff: list[Any] = []
    for index, item in enumerate(new):
        if (
            index < len(current)
            and isinstance(current[index], dict)
            and isinstance(item, dict)
        ):
            diff.append(_diff_document(current[index], item, element_schema))
        else:
            diff.append(item)
    if diff == current:
        return None
    return diff


def _diff_document(current: Any, new: Any, managed: Any = None) -> Any:
    """只保留相对当前文件真正变化的键，避免整份重写丢掉注释与顺序。

    ``managed`` 是 :func:`_managed_tree` 对应的 dataclass（或 ``_FREE_MAPPING``）。
    表单只认识托管字段，因此文件里那些面板不认识的键（用户自定义分区、插件
    写入的字段、更新版本留下的新字段）一律保留：之前它们会被当成「表单里
    删掉的键」直接删掉，一次面板保存就能把它们从 config.toml 里抹掉。
    """
    if not isinstance(current, dict) or not isinstance(new, dict):
        return new
    tree = _managed_tree(managed) if is_dataclass(managed) else None
    changes: dict[str, Any] = {}
    for key, value in new.items():
        child = tree.get(key) if tree is not None else None
        if isinstance(child, _ListOfTables):
            nested_list = _diff_sequence(current.get(key), value, child.element)
            if nested_list is not None:
                changes[key] = nested_list
        elif isinstance(value, dict) and isinstance(current.get(key), dict):
            nested = _diff_document(current[key], value, child)
            if nested:
                changes[key] = nested
        elif current.get(key, _MISSING) != value:
            changes[key] = value
    for key in current:
        if key in new:
            continue
        if tree is not None and key not in tree:
            continue
        changes[key] = _DELETE
    return changes


def _merge_sequence(document: Any, values: list[Any]) -> None:
    """把元素级 diff 合并回 TOML 表数组（保留未变元素的注释与顺序）。"""
    while len(document) > len(values):
        del document[-1]
    for index, item in enumerate(values):
        if index >= len(document):
            document.append(tomlkit.item(item))
            continue
        target = document[index]
        if isinstance(item, dict) and hasattr(target, "get"):
            _merge_into_document(target, item)
        else:
            document[index] = tomlkit.item(item)


def _merge_into_document(document: Any, data: dict[str, Any], prefix: tuple[str, ...] = ()) -> None:
    """把前端表单回传的字典合并回 TOML 文档，保留原有注释与顺序。"""
    if not isinstance(data, dict):
        return
    for key, value in data.items():
        if value is _DELETE:
            if key in document:
                del document[key]
            continue
        if value is None:
            # 可选字段留空：不写入该键，读取时按默认值（None）处理
            continue
        if isinstance(value, dict):
            existing = document.get(key)
            if existing is None or not hasattr(existing, "get"):
                document[key] = tomlkit.table()
                existing = document[key]
            _merge_into_document(existing, value, (*prefix, str(key)))
        elif isinstance(value, list) and _is_table_array(document.get(key)):
            _merge_sequence(document.get(key), value)
        else:
            document[key] = tomlkit.item(value)


def _is_table_array(node: Any) -> bool:
    return isinstance(node, tomlkit.items.AoT)
