"""官方 openid 与 OneBot 合成数字 ID 的映射。

官方事件只给 openid，而本体的会话键、存储与工具参数都沿用了 OneBot 的 int
用户/群号；这里把 openid 换成不会与真实 QQ 号碰撞的 13 位合成号，并持久化，
保证重启后同一 openid 仍是同一个会话对象。
"""

from __future__ import annotations

import json
import os
import tempfile
from collections import OrderedDict
from pathlib import Path
from typing import Any

#: 官方合成号的两段起点。真实 QQ 号最多 10 位，13 位段既不会碰撞，
#: 用户/群两段（9.0T / 9.5T）也互不重叠，从 id 一眼能看出来源。
_USER_BASE = 9_000_000_000_000
_GROUP_BASE = 9_500_000_000_000
_IDENTITIES_DIR_NAME = "qqbot"
_IDENTITIES_FILE_NAME = "identities.json"


class IdentityMap:
    """openid ↔ 13 位合成号；落盘到 <data_dir>/qqbot/identities.json。"""

    def __init__(self, data_dir: str | Path) -> None:
        self._path = Path(data_dir) / _IDENTITIES_DIR_NAME / _IDENTITIES_FILE_NAME
        self._users: dict[str, int] = {}
        self._groups: dict[str, int] = {}
        self._user_openids: dict[int, str] = {}
        self._group_openids: dict[int, str] = {}
        self._next_user = _USER_BASE
        self._next_group = _GROUP_BASE
        self._load()

    # ── 读取/分配 ────────────────────────────────────────────────────

    def user_id(self, openid: str) -> int:
        """openid -> 合成用户号；未知 openid 分配并落盘。"""
        return self._resolve(openid, "用户", self._users, self._user_openids, is_group=False)

    def group_id(self, openid: str) -> int:
        """openid -> 合成群号；未知 openid 分配并落盘。"""
        return self._resolve(openid, "群", self._groups, self._group_openids, is_group=True)

    def openid(self, synthetic: int, kind: str) -> str | None:
        """合成号 -> openid；kind 为 "group" 走群映射，其余（private/friend）走用户映射。"""
        table = self._group_openids if str(kind or "").strip().casefold() == "group" else self._user_openids
        return table.get(int(synthetic))

    # ── 内部 ────────────────────────────────────────────────────────

    def _resolve(
        self,
        openid: str,
        label: str,
        by_openid: dict[str, int],
        by_synthetic: dict[int, str],
        *,
        is_group: bool,
    ) -> int:
        key = str(openid or "").strip()
        if not key:
            raise ValueError(f"官方事件缺少{label} openid")
        known = by_openid.get(key)
        if known is not None:
            return known
        if is_group:
            synthetic = self._next_group
            self._next_group += 1
        else:
            synthetic = self._next_user
            self._next_user += 1
        by_openid[key] = synthetic
        by_synthetic[synthetic] = key
        self._persist()
        return synthetic

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError):
            # 文件损坏时先留副本再重建：直接覆盖会永久丢掉用户/群的历史映射，
            # 而映射一变，旧会话与档案就全部对不上了。
            try:
                self._path.replace(self._path.with_name(self._path.name + ".corrupt"))
            except OSError:
                pass
            return
        if not isinstance(raw, dict):
            return
        self._users = _int_map(raw.get("users"))
        self._groups = _int_map(raw.get("groups"))
        self._user_openids = {value: key for key, value in self._users.items()}
        self._group_openids = {value: key for key, value in self._groups.items()}
        # 合成号只增不减：以现存最大值为准，删除的映射不会被重新分配；
        # 夹到段起点以上，手改过的旧文件也不会把新号分到段外。
        self._next_user = max(_USER_BASE, max(self._users.values(), default=_USER_BASE - 1) + 1)
        self._next_group = max(_GROUP_BASE, max(self._groups.values(), default=_GROUP_BASE - 1) + 1)

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"users": self._users, "groups": self._groups},
            ensure_ascii=False,
        )
        _atomic_write(self._path, payload)


def _int_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, synthetic in value.items():
        if isinstance(synthetic, bool) or not isinstance(synthetic, int) or synthetic <= 0:
            continue
        result[str(key)] = synthetic
    return result


def _atomic_write(path: Path, text: str) -> None:
    fd, temp_path = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


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
