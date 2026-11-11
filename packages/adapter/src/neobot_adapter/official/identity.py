"""官方通道合成号的历史迁移表（运行时不再分配合成号）。

官方适配器改为「openid 直通」：事件/发送/查询里的用户、群 ID 直接就是 openid
字符串（见 events.py / send.py / actions.py）。本模块只保留旧的
<DATA_DIR>/qqbot/identities.json（合成号 ↔ openid）作为**只读**迁移表：
旧数据库、队列、定时任务里残留的 13 位合成号仍可反查成 openid。

不提供分配/写盘 API，也不参与新 ID 生成；identities.json 缺失或损坏时表为空。

MessageIdMap 是运行时真实使用的映射（官方 msg_id ↔ OneBot 合成 int），与身份
映射无关，继续保留。
"""

from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path
from typing import Any

_IDENTITIES_DIR_NAME = "qqbot"
_IDENTITIES_FILE_NAME = "identities.json"
#: 旧合成号的最小位数：真实 QQ 号最多 11 位、群号最多 12 位。
_LEGACY_ID_MIN_DIGITS = 13


class IdentityMap:
    """旧 identities.json 的只读视图（合成号 → openid）；不分配、不写盘。"""

    #: 迁移期标记：调用方据此知道这类 ID 只是历史数据。
    legacy = True

    def __init__(
        self,
        data_dir: str | Path,
        *,
        namespace: str = "",
        logger: Any | None = None,
    ) -> None:
        # namespace/logger 只为兼容旧构造签名；只读迁移表不使用命名空间分配。
        del namespace
        self._logger = logger
        self._path = Path(data_dir) / _IDENTITIES_DIR_NAME / _IDENTITIES_FILE_NAME
        self._user_openids: dict[int, str] = {}
        self._group_openids: dict[int, str] = {}
        self._load()

    def openid(self, synthetic: Any, kind: str = "user") -> str | None:
        """合成号 → openid；kind="group" 走群表，其余走用户表。"""
        try:
            value = int(synthetic)
        except (TypeError, ValueError):
            return None
        table = self._group_openids if str(kind or "").strip().casefold() == "group" else self._user_openids
        return table.get(value)

    def decode(self, synthetic: Any, *, kind: str = "user") -> str | None:
        """openid() 的旧命名别名（迁移期保留）。"""
        return self.openid(synthetic, kind)

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(raw, dict):
            return
        self._user_openids = _invert(raw.get("users"))
        self._group_openids = _invert(raw.get("groups"))


def _invert(value: Any) -> dict[int, str]:
    if not isinstance(value, dict):
        return {}
    result: dict[int, str] = {}
    for openid, synthetic in value.items():
        if isinstance(synthetic, bool) or not isinstance(synthetic, int) or synthetic <= 0:
            continue
        key = str(openid or "").strip()
        if key:
            result[synthetic] = key
    return result


def is_legacy_synthetic_id(value: Any) -> bool:
    """13 位及以上纯数字视为旧合成号（真实 QQ/群号最多 12 位，openid 一般非纯数字）。"""
    text = str(value or "").strip()
    return text.isdigit() and len(text) >= _LEGACY_ID_MIN_DIGITS


def resolve_openid(identity: "IdentityMap | None", local_id: Any, kind: str) -> str | None:
    """本地 ID → 官方 openid（迁移期兼容旧合成号）。

    - 非纯数字字符串：就是 openid，原样返回；
    - int / 纯数字：先按旧合成号查只读迁移表；查不到时把字符串原样当 openid
      （官方 openid 理论上也可能是纯数字）；int 没有可透传的字符串形态，查不到返回 None。
    """
    if local_id is None or isinstance(local_id, bool):
        return None
    if isinstance(local_id, int):
        return identity.openid(local_id, kind) if identity is not None else None
    text = str(local_id).strip()
    if not text:
        return None
    if not text.isdigit():
        return text
    legacy = identity.openid(int(text), kind) if identity is not None else None
    return legacy or text


class MessageIdMap:
    """官方 msg_id ↔ 合成 int 的 LRU（附带撤回上下文与引用索引）。

    官方事件里的 message_id 是字符串，而 OneBot 形状的响应/工具参数用 int；
    只保留最近一段映射，避免长跑进程无限吃内存。引用发送需要 REFIDX 索引
    （事件里的 msg_idx / 发送响应里的 ext_info.ref_idx），撤回需要「群/单聊 +
    openid + 时间」定位端点，因此都挂在同一个 LRU 上一起淘汰。
    """

    def __init__(self, max_size: int = 2000) -> None:
        self._by_official: OrderedDict[str, int] = OrderedDict()
        self._by_synthetic: dict[int, str] = {}
        #: 合成号 -> {"kind": "group"/"private", "openid": str, "at": epoch 秒}
        self._contexts: dict[int, dict[str, Any]] = {}
        #: 合成号 -> 引用索引（REFIDX_...）
        self._references: dict[int, str] = {}
        self._max_size = max(1, int(max_size))
        self._next_synthetic = 1

    def next(self, official_id: str, *, context: dict[str, Any] | None = None) -> int:
        """官方 msg_id -> 合成 int；同一官方 id 稳定返回同一个合成号。"""
        key = str(official_id or "").strip()
        if not key:
            raise ValueError("官方消息缺少 message_id")
        known = self._by_official.get(key)
        if known is not None:
            self._by_official.move_to_end(key)
            if context:
                self._contexts[known] = dict(context)
            return known
        synthetic = self._next_synthetic
        self._next_synthetic += 1
        self._by_official[key] = synthetic
        self._by_synthetic[synthetic] = key
        if context:
            self._contexts[synthetic] = dict(context)
        while len(self._by_official) > self._max_size:
            _, evicted = self._by_official.popitem(last=False)
            self._by_synthetic.pop(evicted, None)
            self._contexts.pop(evicted, None)
            self._references.pop(evicted, None)
        return synthetic

    def official(self, synthetic: int) -> str | None:
        """合成 int -> 官方 msg_id；已被 LRU 淘汰时返回 None。"""
        official_id = self._by_synthetic.get(int(synthetic))
        if official_id is not None:
            self._by_official.move_to_end(official_id)
        return official_id

    def context(self, synthetic: int) -> dict[str, Any] | None:
        """合成 int -> 发送/接收上下文；用于撤回定位。"""
        return self._contexts.get(int(synthetic))

    def remember_reference(self, synthetic: int, ref_idx: str) -> None:
        """记录该消息的引用索引，供之后 message_reference 使用。"""
        text = str(ref_idx or "").strip()
        if text:
            self._references[int(synthetic)] = text

    def reference(self, synthetic: int) -> str | None:
        """合成 int -> 引用索引（REFIDX_...）；没有则返回 None。"""
        return self._references.get(int(synthetic))
