"""提示词历史的纯函数层：图片脱敏 + 逐份 JSON diff/patch。

两件事都为了同一个目标——把「完整提示词历史」从磁盘搬回内存之后依然便宜：

- **图片脱敏**：image_url 里的 data:image/...;base64,... 正文换成 sha256 哈希。
  面板审查提示词时 base64 没有任何信息量，却让单份体积从几 KB 涨到数 MB；
  哈希与图库去重同口径（sha256(图片字节)），拿着它就能在图库里定位到原图。
- **逐份 diff**：第一份存完整快照，之后每份只存相对上一份的补丁（类似 git）。
  回复管线的 messages 是逐轮追加的，因此补丁极小：
  100 份历史合计约 1~2 MB（落盘实现是 100 × 0.5~1.2 MB）。

补丁格式（不对外暴露，仅本模块内自洽）：:

    {"op": "replace", "path": ["messages", 3, "content"], "value": "..."}
    {"op": "add",     "path": ["messages", 9], "value": {...}}   # 仅列表插入
    {"op": "remove",  "path": ["usage", "detail"]}

path 是 **token 列表**（dict 的键 + list 的索引），不是 JSON Pointer 字符串，
省掉 ~0/~1 转义，键里带 "/" 也不会串味。
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
from typing import Any

#: 脱敏后图片引用的前缀（值形如 sha256:<64 位十六进制>）
IMAGE_HASH_PREFIX = "sha256:"
#: 只认图片类 data URL（data:image/png;base64,... 等）
_IMAGE_DATA_PREFIX = "data:image/"
_BASE64_MARKER = ";base64,"
#: 明文 base64 字段名（image_context 工具的入参形态）
_RAW_BASE64_KEYS = frozenset({"image_base64"})
#: 明文 base64 至少这么长才当图片处理（避免把短字符串误判）
_RAW_BASE64_MIN_CHARS = 256


# ── 图片脱敏 ────────────────────────────────────────────────────


def sanitize_images(value: Any) -> tuple[Any, int, int]:
    """把对象图里的图片 base64 换成 sha256 哈希。

    返回 (脱敏后的对象, 替换处数, 释放的 base64 字符数)。
    未发生替换的分支 **原样返回**（结构共享），因此不会改动调用方仍在使用的
    messages；被替换的分支才复制。
    """
    if isinstance(value, str):
        replaced = _sanitize_image_string(value)
        if replaced is None:
            return value, 0, 0
        return replaced, 1, len(value)
    if isinstance(value, dict):
        result: dict[Any, Any] = {}
        changed = False
        count = 0
        freed = 0
        for key, item in value.items():
            if (
                isinstance(item, str)
                and isinstance(key, str)
                and key in _RAW_BASE64_KEYS
                and len(item) >= _RAW_BASE64_MIN_CHARS
            ):
                digest = _sha256_of_base64(item)
                new_item: Any = (
                    IMAGE_HASH_PREFIX + digest if digest is not None else item
                )
                if digest is not None:
                    count += 1
                    freed += len(item)
            else:
                new_item, sub_count, sub_freed = sanitize_images(item)
                count += sub_count
                freed += sub_freed
            if new_item is not item:
                changed = True
            result[key] = new_item
        return (result if changed else value), count, freed
    if isinstance(value, list):
        result_list: list[Any] = []
        changed = False
        count = 0
        freed = 0
        for item in value:
            new_item, sub_count, sub_freed = sanitize_images(item)
            count += sub_count
            freed += sub_freed
            if new_item is not item:
                changed = True
            result_list.append(new_item)
        return (result_list if changed else value), count, freed
    if isinstance(value, tuple):
        new_items, count, freed = sanitize_images(list(value))
        return new_items, count, freed
    return value, 0, 0


def _sanitize_image_string(text: str) -> str | None:
    """图片 data URL → sha256:<hex>；不是图片 data URL 或解不出来则返回 None。"""
    if not text.startswith(_IMAGE_DATA_PREFIX) or _BASE64_MARKER not in text:
        return None
    digest = _sha256_of_base64(text.partition(_BASE64_MARKER)[2])
    if digest is None:
        return None
    return IMAGE_HASH_PREFIX + digest


def _sha256_of_base64(payload: str) -> str | None:
    """对 base64 正文解码后取 sha256（与图库去重口径一致）；解不出来返回 None。"""
    try:
        raw = base64.b64decode(payload + "=" * (-len(payload) % 4), validate=False)
    except Exception:
        return None
    if not raw:
        return None
    return hashlib.sha256(raw).hexdigest()


def count_image_refs(value: Any) -> int:
    """统计对象图里已脱敏的图片引用数（sha256: 形态的字符串）。"""
    if isinstance(value, str):
        return 1 if value.startswith(IMAGE_HASH_PREFIX) else 0
    if isinstance(value, dict):
        return sum(count_image_refs(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return sum(count_image_refs(item) for item in value)
    return 0


# ── 逐份 diff / patch ───────────────────────────────────────────


def diff_payload(old: Any, new: Any) -> list[dict[str, Any]]:
    """求 old → new 的补丁（列表按「公共前缀 + 公共后缀」切分）。

    列表不做 LCS：本场景的消息列表是逐轮追加的，公共前后缀足以把补丁压到最小，
    而 LCS 会引入 O(n²) 的最坏复杂度与不必要的实现风险。
    顺序无关（每条 op 都带绝对路径）。
    """
    ops: list[dict[str, Any]] = []
    _diff(old, new, [], ops)
    return ops


def apply_patch(base: Any, patch: list[dict[str, Any]]) -> Any:
    """把补丁应用到 base 上并返回同一个对象。

    **会原地修改 base**：调用方必须先自行复制（见 apply_patch_copy）。
    """
    if not patch:
        return base
    current = base
    for op in patch:
        path = op.get("path") or []
        kind = op.get("op")
        if not path:
            current = op.get("value")
            continue
        parent = _resolve(current, path[:-1])
        if parent is None:
            continue
        key = path[-1]
        if kind == "remove":
            if isinstance(parent, list):
                if isinstance(key, int) and 0 <= key < len(parent):
                    del parent[key]
            elif isinstance(parent, dict):
                parent.pop(key, None)
            continue
        value = op.get("value")
        if kind == "add" and isinstance(parent, list):
            insert_at = key if isinstance(key, int) else len(parent)
            parent.insert(insert_at, value)
        elif isinstance(parent, list):
            parent[key] = value
        elif isinstance(parent, dict):
            parent[key] = value
    return current


def apply_patch_copy(base: Any, patch: list[dict[str, Any]]) -> Any:
    """复制 base 后应用补丁（纯函数版本）。"""
    return apply_patch(copy.deepcopy(base), patch)


def _diff(old: Any, new: Any, path: list[Any], ops: list[dict[str, Any]]) -> None:
    if old is new or old == new:
        return
    if isinstance(old, dict) and isinstance(new, dict):
        for key in old.keys() - new.keys():
            ops.append({"op": "remove", "path": path + [key]})
        for key in new.keys() - old.keys():
            ops.append({"op": "replace", "path": path + [key], "value": new[key]})
        for key in old.keys() & new.keys():
            _diff(old[key], new[key], path + [key], ops)
        return
    if isinstance(old, list) and isinstance(new, list):
        _diff_list(old, new, path, ops)
        return
    ops.append({"op": "replace", "path": path, "value": new})


def _diff_list(
    old: list[Any], new: list[Any], path: list[Any], ops: list[dict[str, Any]]
) -> None:
    """公共前缀 + 公共后缀以外的部分整体替换（逐元素相等检测）。"""
    limit = min(len(old), len(new))
    prefix = 0
    while prefix < limit and old[prefix] == new[prefix]:
        prefix += 1
    suffix = 0
    while (
        suffix < limit - prefix
        and old[len(old) - 1 - suffix] == new[len(new) - 1 - suffix]
    ):
        suffix += 1
    # 先删（倒序，保持索引有效），再插
    for index in range(len(old) - suffix - 1, prefix - 1, -1):
        ops.append({"op": "remove", "path": path + [index]})
    middle = new[prefix : len(new) - suffix]
    for offset, item in enumerate(middle):
        ops.append({"op": "add", "path": path + [prefix + offset], "value": item})


def _resolve(value: Any, tokens: list[Any]) -> Any:
    current = value
    for token in tokens:
        if isinstance(current, dict):
            current = current.get(token)
        elif isinstance(current, list) and isinstance(token, int):
            if not 0 <= token < len(current):
                return None
            current = current[token]
        else:
            return None
        if current is None:
            return None
    return current


# ── 体积度量 ────────────────────────────────────────────────────


def json_safe(value: Any) -> Any:
    """转成纯 JSON 结构（深拷贝 + 非 JSON 值走 str），与旧落盘实现的语义一致。"""
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def payload_bytes(payload: Any) -> int:
    """一份 payload 的 JSON 体积（UTF-8 字节）。"""
    return len(json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"))


def patch_bytes(patch: list[dict[str, Any]]) -> int:
    """一份补丁的 JSON 体积（UTF-8 字节）。"""
    return len(json.dumps(patch, ensure_ascii=False, default=str).encode("utf-8"))


__all__ = [
    "IMAGE_HASH_PREFIX",
    "apply_patch",
    "apply_patch_copy",
    "count_image_refs",
    "diff_payload",
    "json_safe",
    "patch_bytes",
    "payload_bytes",
    "sanitize_images",
]
