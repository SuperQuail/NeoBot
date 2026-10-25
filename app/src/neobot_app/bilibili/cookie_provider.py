"""B 站登录 Cookie 的本地持久化（默认 <DATA_DIR>/bilibili/cookies.json）。

文件格式是一个扁平的 JSON 对象：cookie 名 → 值，另带两个元数据字段：

refresh_token
    二维码登录成功后返回的 refresh_token（用于以后续期）。
saved_at
    保存时刻的秒级时间戳（字符串），服务用它展示「登录时间」。
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from pathlib import Path

from neobot_app.utils.atomic import atomic_write_text

#: 需要落盘的关键 cookie。buvid3 是 B 站风控常用设备标识，登录后尽量补齐。
COOKIE_NAMES = ("SESSDATA", "bili_jct", "DedeUserID", "buvid3")


class BilibiliCookieStore:
    """读写 B 站 cookie 文件；文件缺失/损坏/缺关键项一律按「未登录」处理。"""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> dict[str, str] | None:
        """读取 cookie；无有效登录信息时返回 None。"""
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(raw, dict):
            return None
        cookies = {
            name: str(raw[name])
            for name in (*COOKIE_NAMES, "refresh_token", "saved_at")
            if raw.get(name) not in (None, "")
        }
        if not cookies.get("SESSDATA") or not cookies.get("bili_jct"):
            return None
        return cookies

    def save(
        self,
        cookies: Mapping[str, str],
        *,
        refresh_token: str = "",
    ) -> None:
        """原子写入 cookie；缺 SESSDATA / bili_jct 时抛 ValueError。"""
        sessdata = str(cookies.get("SESSDATA") or "")
        bili_jct = str(cookies.get("bili_jct") or "")
        if not sessdata or not bili_jct:
            raise ValueError("保存 B 站 cookie 需要 SESSDATA 与 bili_jct")
        payload: dict[str, str] = {}
        for name in COOKIE_NAMES:
            value = str(cookies.get(name) or "")
            if value:
                payload[name] = value
        if refresh_token:
            payload["refresh_token"] = refresh_token
        elif cookies.get("refresh_token"):
            payload["refresh_token"] = str(cookies["refresh_token"])
        payload["saved_at"] = str(int(time.time()))
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        # atomic_write_text 自身已对 Windows 文件占用（os.replace 被拒）做短退避重试；
        # 这里不再套第二层重试或直写兜底：直写牺牲原子性，写坏反而丢掉唯一一份凭证。
        # 失败直接抛，异常带真实路径——调用方只把摘要给用户，路径进日志。
        try:
            atomic_write_text(self._path, text)
        except OSError as exc:
            raise OSError(f"写入 {self._path} 失败: {exc}") from exc

    def clear(self) -> None:
        """删除 cookie 文件（已不存在时忽略）。"""
        try:
            self._path.unlink()
        except FileNotFoundError:
            pass
