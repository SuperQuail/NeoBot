"""config.toml 的定点写回（聊天段配置、次级管理员列表）。

为什么不能直接在解析出的文档上赋值：tomlkit 的 document.get("chat", {}) 在
[chat] 段不存在时返回一个**游离的 dict**，赋值不会进入文档，于是
tomlkit.dumps(document) 写回去的还是原文件——而调用方收到的是"成功"。
/add_admin 正好会踩中这条路径：命令回复"已添加次级管理员"，文件却没变，
重启 NeoBot 后列表自然就空了（用户看到的现象就是"只写在内存里"）。

本模块把写回收敛成三条保证：

1. 缺段就在**文档里**创建（不是操作游离对象），已有内容与注释保持不动；
2. 值与 schema 类型对齐（次级管理员是 List[str]，就写字符串，避免下次启动
   被当成"类型不匹配的缺失项"整段重置）；
3. 写盘前先校验"这份内容能不能被 BotConfig 加载"，写盘后**回读比对**，
   任何一步不一致都返回失败，绝不谎报成功。
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomlkit

from neobot_app.config.loader.backup import backup_config
from neobot_app.config.loader.converter import dict_to_dataclass
from neobot_app.config.schemas.bot import BotConfig

#: config.toml 里承载聊天/账号配置的表名
CHAT_SECTION = "chat"
#: 次级管理员列表的字段名（schema 里是 List[str]）
SUB_ADMIN_FIELD = "sub_admin_accounts"
#: QQ 号长度上限（防御性校验：不接受明显不是 QQ 号的值）
MAX_ACCOUNT_LENGTH = 20


@dataclass(frozen=True, slots=True)
class ChatConfigWriteResult:
    """一次定点写回的结果。"""

    ok: bool
    #: 写盘后回读到的该键的值（ok=False 时为空）
    values: Mapping[str, Any] = field(default_factory=dict)
    error: str = ""

    def text_value(self, key: str) -> str:
        return str(self.values.get(key, "") or "")


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        Path(temp_name).replace(path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _canonical(value: Any) -> Any:
    """把值归一化成可比较的形态（列表逐项转字符串，标量转字符串）。"""
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return str(value)
    return str(value)


def read_chat_values(config_path: Path, keys: Iterable[str]) -> dict[str, Any]:
    """读取 [chat] 段里指定键的当前值（文件不存在/无该段时返回空字典）。"""
    path = Path(config_path)
    if not path.is_file():
        return {}
    try:
        # utf-8-sig：兼容记事本存的 BOM，否则 tomlkit 会直接抛错
        document = tomlkit.parse(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    chat = document.get(CHAT_SECTION)
    if not isinstance(chat, dict):
        return {}
    result: dict[str, Any] = {}
    for key in keys:
        if key in chat:
            result[str(key)] = chat.get(key)
    return result


def write_chat_values(
    config_path: Path,
    values: Mapping[str, Any],
    *,
    backup_dir: Path | None = None,
    max_backups: int = 15,
) -> ChatConfigWriteResult:
    """把若干键写进 config.toml 的 [chat] 段并回读校验。

    Args:
        config_path: 目标配置文件（通常是 data/config.toml）。
        values: 键 -> 新值；只改这些键，其它内容（含注释与顺序）保持不变。
        backup_dir: 备份目录；缺省为配置文件同级的 config_backup。
        max_backups: 备份保留份数。

    Returns:
        ChatConfigWriteResult：ok=True 时才代表磁盘上确实写成功了。
    """
    path = Path(config_path)
    if not values:
        return ChatConfigWriteResult(ok=False, error="没有需要写入的配置项")

    try:
        text = path.read_text(encoding="utf-8-sig") if path.is_file() else ""
    except OSError as exc:
        return ChatConfigWriteResult(ok=False, error=f"读取配置失败: {exc}")

    try:
        document = tomlkit.parse(text) if text.strip() else tomlkit.document()
    except Exception as exc:
        return ChatConfigWriteResult(ok=False, error=f"配置解析失败: {exc}")

    chat = document.get(CHAT_SECTION)
    if chat is None:
        # 关键修复：在文档里创建 [chat]，而不是往游离 dict 上写
        chat = tomlkit.table()
        document[CHAT_SECTION] = chat
    elif not isinstance(chat, dict):
        return ChatConfigWriteResult(
            ok=False, error=f"配置里的 [{CHAT_SECTION}] 不是表，无法写入"
        )

    for key, value in values.items():
        chat[str(key)] = tomlkit.item(value)

    rendered = tomlkit.dumps(document)

    # 写盘前先确认这份内容能被 schema 加载：写出一份加载不了的配置，
    # 下次启动会被"补全缺失项"整段重写，用户改的东西就没了。
    try:
        validated = dict_to_dataclass(tomlkit.parse(rendered).unwrap(), BotConfig)
    except Exception as exc:
        return ChatConfigWriteResult(ok=False, error=f"配置校验失败，未写入: {exc}")
    if validated is None:  # pragma: no cover - dict_to_dataclass 不会返回 None
        return ChatConfigWriteResult(ok=False, error="配置校验失败，未写入")

    try:
        if path.is_file():
            backup_config(
                path,
                Path(backup_dir) if backup_dir is not None else path.parent / "config_backup",
                max_backups=max_backups,
            )
        _atomic_write(path, rendered if rendered.endswith("\n") else rendered + "\n")
    except Exception as exc:
        return ChatConfigWriteResult(ok=False, error=f"写入配置失败: {exc}")

    persisted = read_chat_values(path, values.keys())
    mismatched = [
        key
        for key, value in values.items()
        if _canonical(persisted.get(key)) != _canonical(value)
    ]
    if mismatched:
        return ChatConfigWriteResult(
            ok=False,
            error="写入后回读不一致: " + "、".join(sorted(mismatched)),
            values=persisted,
        )
    return ChatConfigWriteResult(ok=True, values=persisted)


def normalize_accounts(accounts: Iterable[Any]) -> tuple[tuple[str, ...], str]:
    """归一化 QQ 号列表：去空白、只留数字、去重、按数值排序。

    Returns:
        (规范化后的账号元组, 错误文本)；错误文本非空时元组为空。
    """
    collected: dict[int, str] = {}
    for raw in accounts:
        text = str(raw).strip()
        if not text:
            continue
        if not text.isdigit() or len(text) > MAX_ACCOUNT_LENGTH:
            return (), f"非法的 QQ 号: {raw!r}"
        collected[int(text)] = text
    return tuple(collected[key] for key in sorted(collected)), ""


def save_sub_admin_accounts(
    config_path: Path,
    accounts: Iterable[Any],
    *,
    backup_dir: Path | None = None,
) -> ChatConfigWriteResult:
    """写入次级管理员列表（[chat].sub_admin_accounts）。"""
    normalized, error = normalize_accounts(accounts)
    if error:
        return ChatConfigWriteResult(ok=False, error=error)
    return write_chat_values(
        config_path,
        {SUB_ADMIN_FIELD: list(normalized)},
        backup_dir=backup_dir,
    )


def read_sub_admin_accounts(config_path: Path) -> tuple[str, ...]:
    """读取次级管理员列表（去空白、只留数字、去重、按数值排序）。"""
    stored = read_chat_values(config_path, [SUB_ADMIN_FIELD]).get(SUB_ADMIN_FIELD)
    if not isinstance(stored, list):
        return ()
    normalized, _error = normalize_accounts(stored)
    return normalized


__all__ = [
    "CHAT_SECTION",
    "SUB_ADMIN_FIELD",
    "ChatConfigWriteResult",
    "normalize_accounts",
    "read_chat_values",
    "read_sub_admin_accounts",
    "save_sub_admin_accounts",
    "write_chat_values",
]
