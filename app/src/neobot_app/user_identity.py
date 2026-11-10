"""通道本地 ID（官方合成 ID）↔ 真实 QQ 号/群号的人工映射。

官方通道只给 openid，NeoBot 内部映射成 13 位合成 ID；它和真实 QQ 号/群号没有
API 可以互转（官方「唯一身份机制」：不同 AppID 的 openid 都不同）。这里只做
**人工绑定**：

- 管理员命令 /linkqq（@用户 + QQ号）、/linkgroup（当前群 + 群号）；
- agent 工具 user_identity__link_user_qq / link_group_number（只做展示映射，
  **不能**用来获得管理员权限；管理员映射必须由管理员命令写入 trusted 记录）。

生效范围：
- 提示词/资料/历史里用户显示为 QQ:<真实号>、群显示为 群号:<真实群号>；
- 管理员名单/权限只认管理员命令写入的 trusted 映射；
- 好友/群黑白名单、回复黑名单按真实 QQ 号/群号识别；
- 不改资料存储主键，映射只影响展示与身份解析。

存储：<DATA_DIR>/user_qq_map.json，原子写。
格式 v2：aliases["kind:channel:id"] = {"qq": int, "trusted": bool}
兼容旧格式 aliases["channel:id"] = int（视为 user、非 trusted）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from neobot_app.bot_accounts import (
    display_user_id as _bot_display_user_id,
)
from neobot_app.bot_accounts import id_label as _bot_id_label
from neobot_app.bot_accounts import looks_like_real_qq
from neobot_app.utils.atomic import atomic_write_text

_DATA_FILE = "user_qq_map.json"
_USER = "user"
_GROUP = "group"


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _is_valid_qq(value: Any) -> bool:
    """真实 QQ 号：5~11 位纯数字（官方合成号是 13 位，且不是 QQ）。"""
    text = str(value or "").strip()
    return text.isdigit() and 5 <= len(text) <= 11


def _is_valid_group_number(value: Any) -> bool:
    """真实 QQ 群号：5~12 位纯数字（官方合成 group id 是 13 位）。"""
    text = str(value or "").strip()
    return text.isdigit() and 5 <= len(text) <= 12


def _infer_channel(local_id: Any) -> str:
    """真实 QQ 规模数字来自 OneBot；13 位合成号来自官方通道。"""
    return "onebot" if looks_like_real_qq(local_id) else "official"


class UserIdentityMap:
    def __init__(self) -> None:
        self._path: Path | None = None
        self._aliases: dict[str, dict[str, Any]] = {}

    # ── 持久化 ──────────────────────────────────────────────

    def bind(self, data_dir: Path | str | None) -> None:
        self._aliases = {}
        self._path = None
        if data_dir is None:
            return
        self._path = Path(data_dir) / _DATA_FILE
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        aliases = raw.get("aliases") if isinstance(raw, dict) else None
        if not isinstance(aliases, dict):
            return
        for key, value in aliases.items():
            entry = self._parse_entry(str(key), value)
            if entry is not None:
                self._aliases[str(key)] = entry

    @staticmethod
    def _parse_entry(key: str, value: Any) -> dict[str, Any] | None:
        if isinstance(value, dict):
            qq = _to_int(value.get("qq"))
            trusted = bool(value.get("trusted"))
        else:
            # 旧格式：channel:id = qq；视为普通展示映射，不授予权限
            qq = _to_int(value)
            trusted = False
        if not qq:
            return None
        return {"qq": qq, "trusted": trusted}

    def _save(self) -> None:
        if self._path is None:
            return
        payload = {"version": 2, "aliases": self._aliases}
        atomic_write_text(
            self._path,
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )

    # ── key 解析 ────────────────────────────────────────────

    @staticmethod
    def _channel_order(channel: str | None, local_id: Any) -> list[str]:
        channels: list[str] = []
        if channel:
            channels.append(str(channel))
        channels.append(_infer_channel(local_id))
        for fallback in ("onebot", "official"):
            if fallback not in channels:
                channels.append(fallback)
        return channels

    def _keys(self, kind: str, local_id: Any, channel: str | None) -> list[str]:
        uid = _to_int(local_id)
        if not uid:
            return []
        keys: list[str] = []
        for name in self._channel_order(channel, uid):
            keys.append(f"{kind}:{name}:{uid}")
        # 旧格式兼容 key（无 kind）
        for name in self._channel_order(channel, uid):
            keys.append(f"{name}:{uid}")
        return keys

    def _entry(
        self, kind: str, local_id: Any, channel: str | None
    ) -> dict[str, Any] | None:
        for key in self._keys(kind, local_id, channel):
            entry = self._aliases.get(key)
            if entry:
                return entry
        return None

    # ── 用户映射 ────────────────────────────────────────────

    def qq_for(
        self,
        user_id: Any,
        channel: str | None = None,
        *,
        trusted_only: bool = False,
    ) -> int | None:
        entry = self._entry(_USER, user_id, channel)
        if not entry:
            return None
        if trusted_only and not entry.get("trusted"):
            return None
        return _to_int(entry.get("qq"))

    def trusted_qq_for(self, user_id: Any, channel: str | None = None) -> int | None:
        """只返回管理员命令写入的映射；agent 工具写入的只影响展示。"""
        return self.qq_for(user_id, channel, trusted_only=True)

    def link(
        self,
        user_id: Any,
        qq: Any,
        channel: str | None = None,
        *,
        trusted: bool = False,
    ) -> tuple[bool, str]:
        uid = _to_int(user_id)
        qq_number = _to_int(qq)
        if not uid:
            return False, "用户 ID 必须是正整数"
        if not _is_valid_qq(qq_number):
            return False, "QQ 号必须是 5~11 位纯数字"
        if uid == qq_number:
            return True, f"用户 {uid} 本身就是 QQ 号，无需映射"
        key = f"{_USER}:{channel or _infer_channel(uid)}:{uid}"
        previous = self._aliases.get(key)
        if previous and previous.get("trusted") and not trusted:
            return False, "该用户的映射由管理员命令建立，agent 不能修改；请联系管理员用 /linkqq 处理"
        entry = {"qq": qq_number, "trusted": bool(trusted)}
        self._aliases[key] = entry
        try:
            self._save()
        except OSError as exc:
            if previous is None:
                self._aliases.pop(key, None)
            else:
                self._aliases[key] = previous
            return False, f"保存映射失败: {exc}"
        return True, f"已映射 {uid} → QQ:{qq_number}"

    def unlink(self, user_id: Any, channel: str | None = None) -> tuple[bool, str]:
        keys = self._keys(_USER, user_id, channel)
        if any((self._aliases.get(key) or {}).get("trusted") for key in keys):
            return False, "该用户的映射由管理员命令建立，agent 不能移除；请联系管理员处理"
        removed = False
        for key in keys:
            if self._aliases.pop(key, None) is not None:
                removed = True
        if not removed:
            return False, f"用户 {user_id} 没有映射"
        try:
            self._save()
        except OSError as exc:
            return False, f"保存映射失败: {exc}"
        return True, f"已移除用户 {user_id} 的 QQ 映射"

    # ── 群映射 ──────────────────────────────────────────────

    def synthetic_for_qq(self, qq: Any, channel: str | None = None) -> int | None:
        """真实 QQ 号反查通道本地合成 ID（用于官方发送侧拼 @ 标记）。"""
        target = _to_int(qq)
        if not target:
            return None
        candidates: list[tuple[str, int]] = []
        for key, entry in self._aliases.items():
            if _to_int(entry.get("qq")) != target:
                continue
            parts = key.split(":")
            if len(parts) == 3 and parts[0] == _USER:
                local_channel, local_id = parts[1], parts[2]
            elif len(parts) == 2:
                local_channel, local_id = parts[0], parts[1]
            else:
                continue
            local = _to_int(local_id)
            if local:
                candidates.append((local_channel, local))
        if not candidates:
            return None
        if channel:
            for local_channel, local in candidates:
                if local_channel == str(channel):
                    return local
        return candidates[0][1]

    def group_number_for(
        self, group_id: Any, channel: str | None = None
    ) -> int | None:
        entry = self._entry(_GROUP, group_id, channel)
        return _to_int(entry.get("qq")) if entry else None

    def link_group(
        self,
        group_id: Any,
        group_number: Any,
        channel: str | None = None,
        *,
        trusted: bool = False,
    ) -> tuple[bool, str]:
        gid = _to_int(group_id)
        number = _to_int(group_number)
        if not gid:
            return False, "群 ID 必须是正整数"
        if not _is_valid_group_number(number):
            return False, "群号必须是 5~12 位纯数字"
        if gid == number:
            return True, f"群 ID {gid} 本身就是群号，无需映射"
        key = f"{_GROUP}:{channel or _infer_channel(gid)}:{gid}"
        previous = self._aliases.get(key)
        entry = {"qq": number, "trusted": bool(trusted) or bool(previous and previous.get("trusted"))}
        self._aliases[key] = entry
        try:
            self._save()
        except OSError as exc:
            if previous is None:
                self._aliases.pop(key, None)
            else:
                self._aliases[key] = previous
            return False, f"保存映射失败: {exc}"
        return True, f"已映射群 {gid} → 群号:{number}"

    def unlink_group(self, group_id: Any, channel: str | None = None) -> tuple[bool, str]:
        removed = False
        for key in self._keys(_GROUP, group_id, channel):
            if self._aliases.pop(key, None) is not None:
                removed = True
        if not removed:
            return False, f"群 {group_id} 没有映射"
        try:
            self._save()
        except OSError as exc:
            return False, f"保存映射失败: {exc}"
        return True, f"已移除群 {group_id} 的群号映射"

    # ── 展示 ────────────────────────────────────────────────

    def display_user_id(self, user_id: Any, channel: str | None = None) -> str:
        qq = self.qq_for(user_id, channel)
        if qq:
            return f"QQ:{qq}"
        return _bot_display_user_id(user_id)

    def id_label(self, user_id: Any, channel: str | None = None) -> str:
        return "QQ" if self.qq_for(user_id, channel) else _bot_id_label(user_id)

    def display_group_id(self, group_id: Any, channel: str | None = None) -> str:
        number = self.group_number_for(group_id, channel)
        if number:
            return f"群号:{number}"
        text = str(group_id or "").strip()
        if looks_like_real_qq(text):
            return f"群号:{text}"
        return f"群 ID:{text}"

    def group_label(self, group_id: Any, channel: str | None = None) -> str:
        if self.group_number_for(group_id, channel):
            return "群号"
        return "群号" if looks_like_real_qq(group_id) else "群 ID"


_singleton = UserIdentityMap()


def bind_user_identity(data_dir: Path | str | None) -> None:
    """bootstrap 每次构建调用；软重启会重新读取映射文件。"""
    _singleton.bind(data_dir)


def get_user_identity() -> UserIdentityMap:
    return _singleton


def qq_for_user(user_id: Any, channel: str | None = None) -> int | None:
    return _singleton.qq_for(user_id, channel)


def trusted_qq_for_user(user_id: Any, channel: str | None = None) -> int | None:
    return _singleton.trusted_qq_for(user_id, channel)


def link_user_qq(
    user_id: Any,
    qq: Any,
    channel: str | None = None,
    *,
    trusted: bool = False,
) -> tuple[bool, str]:
    return _singleton.link(user_id, qq, channel, trusted=trusted)


def unlink_user_qq(user_id: Any, channel: str | None = None) -> tuple[bool, str]:
    return _singleton.unlink(user_id, channel)


def display_user_id(user_id: Any, channel: str | None = None) -> str:
    return _singleton.display_user_id(user_id, channel)


def id_label(user_id: Any, channel: str | None = None) -> str:
    return _singleton.id_label(user_id, channel)


def group_number_for(group_id: Any, channel: str | None = None) -> int | None:
    return _singleton.group_number_for(group_id, channel)


def link_group_number(
    group_id: Any,
    group_number: Any,
    channel: str | None = None,
    *,
    trusted: bool = False,
) -> tuple[bool, str]:
    return _singleton.link_group(group_id, group_number, channel, trusted=trusted)


def unlink_group_number(group_id: Any, channel: str | None = None) -> tuple[bool, str]:
    return _singleton.unlink_group(group_id, channel)


def synthetic_for_qq(qq: Any, channel: str | None = None) -> int | None:
    return _singleton.synthetic_for_qq(qq, channel)


def display_group_id(group_id: Any, channel: str | None = None) -> str:
    return _singleton.display_group_id(group_id, channel)


def group_label(group_id: Any, channel: str | None = None) -> str:
    return _singleton.group_label(group_id, channel)


__all__ = [
    "UserIdentityMap",
    "bind_user_identity",
    "display_group_id",
    "display_user_id",
    "get_user_identity",
    "group_label",
    "group_number_for",
    "id_label",
    "link_group_number",
    "link_user_qq",
    "qq_for_user",
    "synthetic_for_qq",
    "trusted_qq_for_user",
    "unlink_group_number",
    "unlink_user_qq",
]
