"""官方合成用户 ID ↔ 真实 QQ 号的人工映射。

官方通道只给 openid，NeoBot 内部映射成 13 位合成 ID；它和真实 QQ 号没有
API 可以互转（官方「唯一身份机制」：不同 AppID 的 openid 都不同）。这里只做
**人工绑定**：管理员命令 /linkqq、或 agent 工具 user_identity__link_user_qq
把某个通道的本地用户 ID 与真实 QQ 号关联起来，之后：

- 提示词/资料/历史里该用户显示为 QQ:<真实号>（未映射时仍是 ID:<合成号>）；
- 管理员名单/权限按真实 QQ 号识别该用户；
- 不改用户资料的存储主键，映射只影响展示与权限解析。

存储：<DATA_DIR>/user_qq_map.json，原子写。
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


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _is_valid_qq(value: Any) -> bool:
    """真实 QQ 号：5~11 位纯数字（官方合成号是 13 位，且不是 QQ）。"""
    text = str(value or "").strip()
    return text.isdigit() and 5 <= len(text) <= 11


def _infer_channel(user_id: Any) -> str:
    """真实 QQ 号规模的 id 来自 OneBot；13 位合成号来自官方通道。"""
    return "onebot" if looks_like_real_qq(user_id) else "official"


class UserIdentityMap:
    def __init__(self) -> None:
        self._path: Path | None = None
        self._aliases: dict[str, int] = {}

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
            qq = _to_int(value)
            if qq:
                self._aliases[str(key)] = qq

    def _save(self) -> None:
        if self._path is None:
            return
        payload = {"version": 1, "aliases": self._aliases}
        atomic_write_text(
            self._path,
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )

    def _keys(self, user_id: Any, channel: str | None) -> list[str]:
        uid = _to_int(user_id)
        if not uid:
            return []
        channels = []
        if channel:
            channels.append(str(channel))
        channels.append(_infer_channel(uid))
        for fallback in ("onebot", "official"):
            if fallback not in channels:
                channels.append(fallback)
        return [f"{name}:{uid}" for name in channels]

    def qq_for(self, user_id: Any, channel: str | None = None) -> int | None:
        for key in self._keys(user_id, channel):
            qq = self._aliases.get(key)
            if qq:
                return qq
        return None

    def link(
        self, user_id: Any, qq: Any, channel: str | None = None
    ) -> tuple[bool, str]:
        uid = _to_int(user_id)
        qq_number = _to_int(qq)
        if not uid:
            return False, "用户 ID 必须是正整数"
        if not _is_valid_qq(qq_number):
            return False, "QQ 号必须是 5~11 位纯数字"
        if uid == qq_number:
            return True, f"用户 {uid} 本身就是 QQ 号，无需映射"
        key = f"{channel or _infer_channel(uid)}:{uid}"
        self._aliases[key] = qq_number
        try:
            self._save()
        except OSError as exc:
            self._aliases.pop(key, None)
            return False, f"保存映射失败: {exc}"
        return True, f"已映射 {uid} → QQ:{qq_number}"

    def unlink(self, user_id: Any, channel: str | None = None) -> tuple[bool, str]:
        keys = self._keys(user_id, channel)
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

    def display_user_id(self, user_id: Any, channel: str | None = None) -> str:
        qq = self.qq_for(user_id, channel)
        if qq:
            return f"QQ:{qq}"
        return _bot_display_user_id(user_id)

    def id_label(self, user_id: Any, channel: str | None = None) -> str:
        return "QQ" if self.qq_for(user_id, channel) else _bot_id_label(user_id)


_singleton = UserIdentityMap()


def bind_user_identity(data_dir: Path | str | None) -> None:
    """bootstrap 每次构建调用；软重启会重新读取映射文件。"""
    _singleton.bind(data_dir)


def get_user_identity() -> UserIdentityMap:
    return _singleton


def qq_for_user(user_id: Any, channel: str | None = None) -> int | None:
    return _singleton.qq_for(user_id, channel)


def link_user_qq(user_id: Any, qq: Any, channel: str | None = None) -> tuple[bool, str]:
    return _singleton.link(user_id, qq, channel)


def unlink_user_qq(user_id: Any, channel: str | None = None) -> tuple[bool, str]:
    return _singleton.unlink(user_id, channel)


def display_user_id(user_id: Any, channel: str | None = None) -> str:
    return _singleton.display_user_id(user_id, channel)


def id_label(user_id: Any, channel: str | None = None) -> str:
    return _singleton.id_label(user_id, channel)


__all__ = [
    "UserIdentityMap",
    "bind_user_identity",
    "display_user_id",
    "get_user_identity",
    "id_label",
    "link_user_qq",
    "qq_for_user",
    "unlink_user_qq",
]
