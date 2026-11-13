"""通道本地 ID（官方 openid）↔ 真实 QQ 号/群号的人工映射。

官方通道只给 openid（字母数字串），NeoBot 以它作为本地身份 key；它和真实
QQ 号/群号没有 API 可以互转（官方「唯一身份机制」：不同 AppID 的 openid 都不同）。
这里只做**人工绑定**：

- 管理员命令 /linkqq（@用户 + QQ号）、/linkgroup（当前群 + 群号）；
- agent 工具 user_identity__link_user_qq / link_group_number（只做展示映射，
  **不能**用来获得管理员权限；管理员映射必须由管理员命令写入 trusted 记录）。

生效范围：
- 提示词/资料/历史里用户显示为 QQ:<真实号>、群显示为 群号:<真实群号>；未映射的
  openid 原样显示为 openid:<完整值>，不再折叠成合成数字；
- 管理员名单/权限、好友/群黑白名单、回复黑名单只认管理员命令写入的 trusted
  映射；agent 工具写入的映射只影响展示与身份提示（trusted=False）；
- 不改资料存储主键，映射只影响展示与身份解析。

存储：<DATA_DIR>/user_qq_map.json，原子写。
格式 v3：aliases["kind:channel:local_id"] = {"qq": int, "trusted": bool}
local_id 是 openid（官方通道）或 QQ 号；旧 v2 的 13 位合成号 key 会借
<DATA_DIR>/qqbot/identities.json（适配器持久化的 openid↔合成号）反查成 openid
后重写；兼容旧格式 aliases["channel:id"] = int（视为 user、非 trusted）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from neobot_app.bot_accounts import (
    display_group_id as _bot_display_group_id,
)
from neobot_app.bot_accounts import (
    display_user_id as _bot_display_user_id,
)
from neobot_app.bot_accounts import group_label as _bot_group_label
from neobot_app.bot_accounts import id_label as _bot_id_label
from neobot_app.bot_accounts import identity_text
from neobot_app.bot_accounts import infer_channel
from neobot_app.bot_accounts import looks_like_real_group_number
from neobot_app.bot_accounts import looks_like_real_qq
from neobot_app.utils.atomic import atomic_write_text

_DATA_FILE = "user_qq_map.json"
#: 适配器持久化的 openid↔合成号映射（相对 DATA_DIR，见 official/identity.py）。
_IDENTITIES_FILE = Path("qqbot") / "identities.json"
_VERSION = 3
_USER = "user"
_GROUP = "group"


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _is_valid_qq(value: Any) -> bool:
    """真实 QQ 号输入校验：5~11 位纯数字（openid/旧合成号都不是 QQ）。"""
    return looks_like_real_qq(value, min_digits=5)


def _is_valid_group_number(value: Any) -> bool:
    """真实 QQ 群号输入校验：5~12 位纯数字（openid/旧合成号都不是群号）。"""
    return looks_like_real_group_number(value, min_digits=5)


def _load_identity_index(data_dir: Path) -> dict[str, dict[str, str]]:
    """读适配器的 identities.json，返回 synthetic_id -> openid（按 user/group 分段）。

    文件缺失/损坏时返回空表：旧映射保持原样，等适配器下次运行生成文件后再迁移。
    """
    try:
        raw = json.loads((data_dir / _IDENTITIES_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    index: dict[str, dict[str, str]] = {}
    for field, kind in (("users", _USER), ("groups", _GROUP)):
        table = raw.get(field)
        if not isinstance(table, dict):
            continue
        mapping: dict[str, str] = {}
        for openid, synthetic in table.items():
            text = str(openid or "").strip()
            number = _to_int(synthetic)
            if text and number:
                mapping[str(number)] = text
        index[kind] = mapping
    return index


def _parse_alias_key(key: str) -> tuple[str, str, str] | None:
    """解析别名 key：v3 kind:channel:local；旧格式 channel:local（视为 user）。"""
    parts = str(key or "").split(":", 2)
    if len(parts) == 3 and parts[0] in (_USER, _GROUP):
        return parts[0], parts[1], parts[2]
    parts = str(key or "").split(":", 1)
    if len(parts) == 2 and parts[0] and parts[1]:
        return _USER, parts[0], parts[1]
    return None


class UserIdentityMap:
    def __init__(self) -> None:
        self._path: Path | None = None
        self._aliases: dict[str, dict[str, Any]] = {}
        #: 旧合成号 -> openid（适配器 identities.json），用于读旧数据与迁移
        self._synthetic_to_openid: dict[str, dict[str, str]] = {_USER: {}, _GROUP: {}}

    # ── 持久化 ──────────────────────────────────────────────

    def bind(self, data_dir: Path | str | None) -> None:
        self._aliases = {}
        self._path = None
        self._synthetic_to_openid = {_USER: {}, _GROUP: {}}
        if data_dir is None:
            return
        root = Path(data_dir)
        self._path = root / _DATA_FILE
        self._synthetic_to_openid = _load_identity_index(root)
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        aliases = raw.get("aliases") if isinstance(raw, dict) else None
        if not isinstance(aliases, dict):
            return
        changed = bool(raw.get("version") != _VERSION) if isinstance(raw, dict) else False
        for key, value in aliases.items():
            parsed = _parse_alias_key(str(key))
            entry = self._parse_entry(value)
            if parsed is None or entry is None:
                changed = True
                continue
            kind, channel, local = parsed
            migrated = self._openid_for(kind, local)
            new_key = f"{kind}:{channel}:{migrated}"
            if new_key != str(key):
                changed = True
            self._aliases[new_key] = entry
        if changed:
            try:
                self._save()
            except OSError:
                # 迁移写盘失败不阻塞启动：内存里已按新 key 生效，覆盖文件由下次 bind 重试
                pass

    @staticmethod
    def _parse_entry(value: Any) -> dict[str, Any] | None:
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
        payload = {"version": _VERSION, "aliases": self._aliases}
        atomic_write_text(
            self._path,
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )

    # ── ID/key 解析 ─────────────────────────────────────────

    def _openid_for(self, kind: str, value: Any) -> str:
        """把旧合成号换成 openid；openid/QQ 号原样返回。"""
        text = identity_text(value)
        if not text:
            return ""
        mapping = self._synthetic_to_openid.get(kind) or {}
        return mapping.get(text, text)

    def openid_for_legacy_id(self, kind: str, value: Any) -> str | None:
        """旧合成号 → openid；不是合成号或没有映射时返回 None。"""
        text = identity_text(value)
        if not text or not text.isdigit():
            return None
        return (self._synthetic_to_openid.get(kind) or {}).get(text)

    def _local_candidates(self, kind: str, value: Any) -> list[str]:
        """查询候选 ID：原始值 + 由旧合成号反查出的 openid（去重、保序）。"""
        text = identity_text(value)
        if not text:
            return []
        candidates = [text]
        migrated = self._openid_for(kind, text)
        if migrated and migrated not in candidates:
            candidates.append(migrated)
        return candidates

    @staticmethod
    def _channel_order(channel: str | None, local: str, kind: str) -> list[str]:
        channels: list[str] = []
        if channel:
            channels.append(str(channel))
        channels.append(infer_channel(local, kind=kind))
        for fallback in ("onebot", "official"):
            if fallback not in channels:
                channels.append(fallback)
        return channels

    def _keys(self, kind: str, local_id: Any, channel: str | None) -> list[str]:
        keys: list[str] = []
        for local in self._local_candidates(kind, local_id):
            for name in self._channel_order(channel, local, kind):
                keys.append(f"{kind}:{name}:{local}")
            # 旧格式兼容 key（无 kind）
            for name in self._channel_order(channel, local, kind):
                keys.append(f"{name}:{local}")
        return list(dict.fromkeys(keys))

    def _entry(
        self, kind: str, local_id: Any, channel: str | None
    ) -> dict[str, Any] | None:
        for key in self._keys(kind, local_id, channel):
            entry = self._aliases.get(key)
            if entry:
                return entry
        return None

    def _trusted_entry(
        self, kind: str, local_id: Any, channel: str | None
    ) -> dict[str, Any] | None:
        """只找管理员命令写入的映射。

        同一 ID 可能有多条通道 key，任一 trusted 命中即可：若按展示优先级取第一条，
        agent 在另一条通道 key 写一条非 trusted 映射就能把 ACL 用的 trusted 映射遮住。
        """
        for key in self._keys(kind, local_id, channel):
            entry = self._aliases.get(key)
            if entry and entry.get("trusted"):
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
        entry = (
            self._trusted_entry(_USER, user_id, channel)
            if trusted_only
            else self._entry(_USER, user_id, channel)
        )
        return _to_int(entry.get("qq")) if entry else None

    def trusted_qq_for(self, user_id: Any, channel: str | None = None) -> int | None:
        """只返回管理员命令写入的映射；agent 工具写入的只影响展示。"""
        return self.qq_for(user_id, channel, trusted_only=True)

    def openid_for_qq(self, qq: Any, channel: str | None = None) -> str | None:
        """真实 QQ 号反查本地用户 ID（openid 优先，旧合成号原样兼容）。"""
        return self._local_for_number(_USER, qq, channel)

    def link(
        self,
        user_id: Any,
        qq: Any,
        channel: str | None = None,
        *,
        trusted: bool = False,
    ) -> tuple[bool, str]:
        local = self._openid_for(_USER, user_id)
        qq_number = _to_int(qq)
        if not local:
            return False, "用户 ID 不能为空"
        if not _is_valid_qq(qq_number):
            return False, "QQ 号必须是 5~11 位纯数字"
        if looks_like_real_qq(local) and _to_int(local) == qq_number:
            return True, f"用户 {local} 本身就是 QQ 号，无需映射"
        channel_name = str(channel or "").strip() or infer_channel(local, kind=_USER)
        key = f"{_USER}:{channel_name}:{local}"
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
        return True, f"已映射 {local} → QQ:{qq_number}"

    def unlink(self, user_id: Any, channel: str | None = None, *, force: bool = False) -> tuple[bool, str]:
        keys = self._keys(_USER, user_id, channel)
        if not force and any((self._aliases.get(key) or {}).get("trusted") for key in keys):
            return False, "该用户的映射由管理员命令建立，agent 不能移除；请联系管理员处理"
        local = self._openid_for(_USER, user_id)
        removed = False
        for key in keys:
            if self._aliases.pop(key, None) is not None:
                removed = True
        if not removed:
            return False, f"用户 {local or identity_text(user_id)} 没有映射"
        try:
            self._save()
        except OSError as exc:
            return False, f"保存映射失败: {exc}"
        return True, f"已移除用户 {local} 的 QQ 映射"

    # ── 群映射 ──────────────────────────────────────────────

    def _local_for_number(self, kind: str, number: Any, channel: str | None) -> str | None:
        """真实 QQ 号/群号反查本地 ID；同号多条映射时优先指定通道。"""
        target = _to_int(number)
        if not target:
            return None
        candidates: list[tuple[str, str]] = []
        for key, entry in self._aliases.items():
            if _to_int(entry.get("qq")) != target:
                continue
            parsed = _parse_alias_key(key)
            if parsed is None or parsed[0] != kind:
                continue
            _kind, local_channel, local = parsed
            if local:
                candidates.append((local_channel, local))
        if not candidates:
            return None
        if channel:
            for local_channel, local in candidates:
                if local_channel == str(channel):
                    return self._openid_for(kind, local)
            return None
        return self._openid_for(kind, candidates[0][1])

    def openid_for_group(self, group_number: Any, channel: str | None = None) -> str | None:
        """真实群号反查本地群 ID（openid 优先，旧合成号原样兼容）。"""
        return self._local_for_number(_GROUP, group_number, channel)

    def group_number_for(
        self, group_id: Any, channel: str | None = None
    ) -> int | None:
        entry = self._entry(_GROUP, group_id, channel)
        return _to_int(entry.get("qq")) if entry else None

    def trusted_group_number_for(
        self, group_id: Any, channel: str | None = None
    ) -> int | None:
        """只返回管理员命令写入的群映射；agent 写入的只影响展示。"""
        entry = self._trusted_entry(_GROUP, group_id, channel)
        return _to_int(entry.get("qq")) if entry else None

    def link_group(
        self,
        group_id: Any,
        group_number: Any,
        channel: str | None = None,
        *,
        trusted: bool = False,
    ) -> tuple[bool, str]:
        local = self._openid_for(_GROUP, group_id)
        number = _to_int(group_number)
        if not local:
            return False, "群 ID 不能为空"
        if not _is_valid_group_number(number):
            return False, "群号必须是 5~12 位纯数字"
        if looks_like_real_group_number(local) and _to_int(local) == number:
            return True, f"群 {local} 本身就是群号，无需映射"
        channel_name = str(channel or "").strip() or infer_channel(local, kind=_GROUP)
        key = f"{_GROUP}:{channel_name}:{local}"
        previous = self._aliases.get(key)
        if previous and previous.get("trusted") and not trusted:
            return False, "该群的映射由管理员命令建立，agent 不能修改；请联系管理员用 /linkgroup 处理"
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
        return True, f"已映射群 {local} → 群号:{number}"

    def unlink_group(self, group_id: Any, channel: str | None = None, *, force: bool = False) -> tuple[bool, str]:
        keys = self._keys(_GROUP, group_id, channel)
        if not force and any((self._aliases.get(key) or {}).get("trusted") for key in keys):
            return False, "该群的映射由管理员命令建立，agent 不能移除；请联系管理员处理"
        local = self._openid_for(_GROUP, group_id)
        removed = False
        for key in keys:
            if self._aliases.pop(key, None) is not None:
                removed = True
        if not removed:
            return False, f"群 {local or identity_text(group_id)} 没有映射"
        try:
            self._save()
        except OSError as exc:
            return False, f"保存映射失败: {exc}"
        return True, f"已移除群 {local} 的群号映射"

    # ── 展示 ────────────────────────────────────────────────

    def display_user_id(self, user_id: Any, channel: str | None = None) -> str:
        qq = self.qq_for(user_id, channel)
        if qq:
            return f"QQ:{qq}"
        return _bot_display_user_id(self._openid_for(_USER, user_id))

    def id_label(self, user_id: Any, channel: str | None = None) -> str:
        return "QQ" if self.qq_for(user_id, channel) else _bot_id_label(self._openid_for(_USER, user_id))

    def display_group_id(self, group_id: Any, channel: str | None = None) -> str:
        number = self.group_number_for(group_id, channel)
        if number:
            return f"群号:{number}"
        return _bot_display_group_id(self._openid_for(_GROUP, group_id))

    def group_label(self, group_id: Any, channel: str | None = None) -> str:
        if self.group_number_for(group_id, channel):
            return "群号"
        return _bot_group_label(self._openid_for(_GROUP, group_id))

    def _trusted_local_for_number(
        self, kind: str, number: Any, channel: str | None
    ) -> str | None:
        """真实 QQ/群号 -> 本地 ID，只认管理员命令写入的 trusted 映射。

        agent 工具写入的映射只影响展示；拿它做 profile/archive 主键会让模型把
        数据路由到任意 openid（审计发现），因此 canonical 归一必须排除。
        """
        target = _to_int(number)
        if not target:
            return None
        candidates: list[tuple[str, str]] = []
        for key, entry in self._aliases.items():
            if not isinstance(entry, dict) or not entry.get("trusted"):
                continue
            if _to_int(entry.get("qq")) != target:
                continue
            parsed = _parse_alias_key(key)
            if parsed is None or parsed[0] != kind:
                continue
            _kind, local_channel, local = parsed
            if local:
                candidates.append((local_channel, local))
        if not candidates:
            return None
        if channel:
            for local_channel, local in candidates:
                if local_channel == str(channel):
                    return self._openid_for(kind, local)
            return None
        return self._openid_for(kind, candidates[0][1])

    def canonical_user_id(self, user_id: Any, channel: str | None = None) -> str:
        """把任意本地用户 ID 归一成主键：优先 openid，其次是旧合成号迁移值。

        QQ 号有 /linkqq 映射时返回对应 openid；openid 原样返回；旧 13 位合成号走
        identities.json 迁移；无映射的 QQ 号保持原样（还没 link 的用户）。
        """
        text = identity_text(user_id)
        if not text:
            return ""
        migrated = self.openid_for_legacy_id(_USER, text)
        if migrated:
            return migrated
        if text.isdigit():
            mapped = self._trusted_local_for_number(_USER, text, channel)
            if mapped:
                return mapped
        return text

    def canonical_group_id(self, group_id: Any, channel: str | None = None) -> str:
        """把任意本地群 ID 归一成主键（openid 优先，兼容旧合成号/真实群号）。"""
        text = identity_text(group_id)
        if not text:
            return ""
        migrated = self.openid_for_legacy_id(_GROUP, text)
        if migrated:
            return migrated
        if text.isdigit():
            mapped = self._trusted_local_for_number(_GROUP, text, channel)
            if mapped:
                return mapped
        return text

    def profile_identity(self, user_id: Any, channel: str | None = None) -> str:
        """用户档案里的身份展示：映射后同时给真实 QQ 号和完整 openid。"""
        text = identity_text(user_id)
        if not text:
            return ""
        local = self._openid_for(_USER, text)
        mapped = self.qq_for(text, channel)
        if mapped:
            return f"QQ:{mapped}（openid:{local}）"
        if looks_like_real_qq(text):
            return f"QQ号:{text}"
        return f"openid:{local}"


_singleton = UserIdentityMap()


def bind_user_identity(data_dir: Path | str | None) -> None:
    """bootstrap 每次构建调用；软重启会重新读取映射文件并完成旧合成号迁移。"""
    _singleton.bind(data_dir)


def get_user_identity() -> UserIdentityMap:
    return _singleton


def qq_for_user(user_id: Any, channel: str | None = None) -> int | None:
    return _singleton.qq_for(user_id, channel)


def trusted_qq_for_user(user_id: Any, channel: str | None = None) -> int | None:
    return _singleton.trusted_qq_for(user_id, channel)


def openid_for_qq(qq: Any, channel: str | None = None) -> str | None:
    return _singleton.openid_for_qq(qq, channel)


def openid_for_group(group_number: Any, channel: str | None = None) -> str | None:
    return _singleton.openid_for_group(group_number, channel)


def openid_for_legacy_id(kind: str, value: Any) -> str | None:
    return _singleton.openid_for_legacy_id(kind, value)


def link_user_qq(
    user_id: Any,
    qq: Any,
    channel: str | None = None,
    *,
    trusted: bool = False,
) -> tuple[bool, str]:
    return _singleton.link(user_id, qq, channel, trusted=trusted)


def unlink_user_qq(
    user_id: Any, channel: str | None = None, *, force: bool = False
) -> tuple[bool, str]:
    return _singleton.unlink(user_id, channel, force=force)


def canonical_user_id(user_id: Any, channel: str | None = None) -> str:
    return _singleton.canonical_user_id(user_id, channel)


def canonical_group_id(group_id: Any, channel: str | None = None) -> str:
    return _singleton.canonical_group_id(group_id, channel)


#: 档案表 -> 主键类型；这两个函数给 ArchiveMemoryService 做统一 key 归一。
_USER_ARCHIVE_TABLES = frozenset({"user_profile", "user_summary"})
_GROUP_ARCHIVE_TABLES = frozenset({"group_profile", "group_summary"})


def canonical_archive_key(table_name: str, key: str) -> str:
    """档案 key 归一：用户表按用户主键、群表按群主键，其它表原样返回。"""
    if table_name in _USER_ARCHIVE_TABLES:
        return canonical_user_id(key)
    if table_name in _GROUP_ARCHIVE_TABLES:
        return canonical_group_id(key)
    return key


def display_user_id(user_id: Any, channel: str | None = None) -> str:
    return _singleton.display_user_id(user_id, channel)


def profile_identity(user_id: Any, channel: str | None = None) -> str:
    return _singleton.profile_identity(user_id, channel)


def id_label(user_id: Any, channel: str | None = None) -> str:
    return _singleton.id_label(user_id, channel)


def group_number_for(group_id: Any, channel: str | None = None) -> int | None:
    return _singleton.group_number_for(group_id, channel)


def trusted_group_number_for(group_id: Any, channel: str | None = None) -> int | None:
    return _singleton.trusted_group_number_for(group_id, channel)


def link_group_number(
    group_id: Any,
    group_number: Any,
    channel: str | None = None,
    *,
    trusted: bool = False,
) -> tuple[bool, str]:
    return _singleton.link_group(group_id, group_number, channel, trusted=trusted)


def unlink_group_number(
    group_id: Any, channel: str | None = None, *, force: bool = False
) -> tuple[bool, str]:
    return _singleton.unlink_group(group_id, channel, force=force)


def display_group_id(group_id: Any, channel: str | None = None) -> str:
    return _singleton.display_group_id(group_id, channel)


def group_label(group_id: Any, channel: str | None = None) -> str:
    return _singleton.group_label(group_id, channel)


__all__ = [
    "UserIdentityMap",
    "bind_user_identity",
    "canonical_archive_key",
    "canonical_group_id",
    "canonical_user_id",
    "display_group_id",
    "display_user_id",
    "get_user_identity",
    "group_label",
    "group_number_for",
    "id_label",
    "link_group_number",
    "link_user_qq",
    "openid_for_group",
    "openid_for_legacy_id",
    "openid_for_qq",
    "profile_identity",
    "qq_for_user",
    "trusted_group_number_for",
    "trusted_qq_for_user",
    "unlink_group_number",
    "unlink_user_qq",
]
