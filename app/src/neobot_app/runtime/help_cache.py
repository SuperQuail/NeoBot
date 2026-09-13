"""/help 预渲染缓存（spec(5) §4.2 / R9 / D7 / D8）。

设计要点：

- 目录：<DATA_DIR>/cache/help/，删掉即回退到即时渲染（回滚手段）；
- 缓存键按**权限维度**分份：help-{perm}-p{page}-s{size}-{fingerprint}.png，
  详情 detail-{cmd}-{perm}-{fingerprint}.png；
- 指纹 = sha256(sorted([(name, usage, description, permission)]))[:16]，
  命令集（插件加载 / 卸载 / 热重载）任何变化即换指纹；
- index.json 记录当前指纹 / 各维度页数 / 生成时间 / 渲染器版本，版本或指纹
  变化即整体失效；
- 只预渲染**列表**（3 个权限维度 × 页），详情按需渲染并写回；
- 容量上限 HELP_CACHE_MAX_FILES，超出按生成时间（mtime）淘汰；
- 预渲染全程 try/except，失败只记 warning，绝不影响启动 / 软重启。

安全：读取按当前用户的权限维度取文件，低权限用户拿不到高权限维度的图片
（spec(5) §6 列为最关键的安全点）。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from neobot_app.core.constants import HELP_CACHE_DIR
from neobot_app.runtime import help_card
from neobot_app.runtime.html_card import render_card_image
from neobot_app.utils.logger import get_module_logger

logger = get_module_logger("runtime.help_cache")

#: 列表卡片每页条数
HELP_PAGE_SIZE = help_card.PAGE_SIZE

#: 缓存目录内的图片文件上限（超出按 mtime 从旧到新淘汰）
HELP_CACHE_MAX_FILES = 60

#: 缓存子目录名（<DATA_DIR>/cache/help）
HELP_CACHE_DIR_NAME = "help"

#: 索引文件名
INDEX_FILE_NAME = "index.json"

#: 渲染器版本：布局 / 主题 / 字段变化时递增，旧缓存整体失效。
#: "2"：卡片渲染器重写（多主题美术 / 三列命令表 / 翻页条 / 指标卡片），
#: 旧指纹命中的缓存必须整体失效，否则 /help 会继续发美化前的图。
RENDERER_VERSION = "2"

#: 预渲染的权限维度（所有人 / 次级管理员 / 超级管理员）
PERMISSION_DIMENSIONS: tuple[int, ...] = (0, 1, 2)

#: 单张卡片的渲染超时
RENDER_TIMEOUT_SECONDS = 20.0


def default_cache_dir() -> Path:
    """默认缓存目录 <DATA_DIR>/cache/help。"""
    return Path(HELP_CACHE_DIR)


def cache_dir(data_dir: Any = None) -> Path:
    """缓存目录：给了 data_dir 就用 <data_dir>/cache/help，否则用 DATA_DIR。"""
    if data_dir is None:
        return default_cache_dir()
    return Path(data_dir) / "cache" / HELP_CACHE_DIR_NAME


def command_fingerprint(commands: Any) -> str:
    """命令集指纹：命令名 / 用法 / 描述 / 权限 任一变化即换指纹。"""
    rows = sorted(
        (
            str(getattr(command, "name", "") or ""),
            str(getattr(command, "usage", "") or ""),
            str(getattr(command, "description", "") or ""),
            int(getattr(command, "permission", 0) or 0),
        )
        for command in commands or ()
    )
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _safe_component(value: Any) -> str:
    """把命令名转成安全的文件名片段（只留字母数字与 -_）。"""
    text = str(value or "")
    cleaned = "".join(char if (char.isalnum() or char in "-_") else "_" for char in text)
    return cleaned or "cmd"


def list_cache_path(
    *,
    fingerprint: str,
    perm: int,
    page: int,
    size: int = HELP_PAGE_SIZE,
    directory: Any = None,
    data_dir: Any = None,
) -> Path:
    """列表卡片缓存路径。"""
    base = Path(directory) if directory is not None else cache_dir(data_dir)
    return base / f"help-{int(perm)}-p{int(page)}-s{int(size)}-{fingerprint}.png"


def detail_cache_path(
    *,
    command: Any,
    fingerprint: str,
    perm: int,
    directory: Any = None,
    data_dir: Any = None,
) -> Path:
    """详情卡片缓存路径。"""
    base = Path(directory) if directory is not None else cache_dir(data_dir)
    name = getattr(command, "name", command)
    return base / f"detail-{_safe_component(name)}-{int(perm)}-{fingerprint}.png"

class HelpCache:
    """列表 / 详情卡片在 <DATA_DIR>/cache/help/ 下的落盘缓存。"""

    def __init__(
        self,
        *,
        directory: Any = None,
        data_dir: Any = None,
        size: int = HELP_PAGE_SIZE,
        max_files: int = HELP_CACHE_MAX_FILES,
        log: Any = None,
    ) -> None:
        self._directory = (
            Path(directory) if directory is not None else cache_dir(data_dir)
        )
        self._size = max(1, int(size or HELP_PAGE_SIZE))
        self._max_files = max(1, int(max_files or HELP_CACHE_MAX_FILES))
        self._logger = log or logger

    @property
    def directory(self) -> Path:
        return self._directory

    @property
    def size(self) -> int:
        return self._size

    @property
    def max_files(self) -> int:
        return self._max_files

    def ensure_dir(self) -> Path:
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:  # pragma: no cover - 磁盘异常只记 warning
            self._logger.warning(f"help 缓存目录创建失败: {exc}")
        return self._directory

    # ── 索引 ──

    def read_index(self) -> dict[str, Any]:
        path = self._directory / INDEX_FILE_NAME
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def write_index(self, index: dict[str, Any]) -> None:
        self.ensure_dir()
        path = self._directory / INDEX_FILE_NAME
        tmp = path.with_name(path.name + ".tmp")
        try:
            tmp.write_text(
                json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            tmp.replace(path)
        except OSError as exc:  # pragma: no cover - 写索引失败不影响发图
            self._logger.warning(f"help 缓存索引写入失败: {exc}")
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass

    def is_fresh(self, fingerprint: str, index: dict[str, Any] | None = None) -> bool:
        """索引是否对当前指纹有效（指纹 / 渲染器版本 / 页大小三者都对）。"""
        data = self.read_index() if index is None else index
        if str(data.get("fingerprint") or "") != str(fingerprint):
            return False
        if str(data.get("renderer_version") or "") != RENDERER_VERSION:
            return False
        try:
            return int(data.get("size") or 0) == self._size
        except (TypeError, ValueError):
            return False

    def new_index(self, fingerprint: str) -> dict[str, Any]:
        """新指纹对应的空索引骨架。"""
        return {
            "fingerprint": str(fingerprint),
            "renderer_version": RENDERER_VERSION,
            "size": self._size,
            "generated_at": time.time(),
            "pages": {},
        }

    def touch_index(self, index: dict[str, Any]) -> dict[str, Any]:
        index["fingerprint"] = str(index.get("fingerprint") or "")
        index["renderer_version"] = RENDERER_VERSION
        index["size"] = self._size
        index["generated_at"] = time.time()
        pages = index.get("pages")
        if not isinstance(pages, dict):
            pages = {}
        index["pages"] = pages
        return index

    # ── 图片读写 ──

    def _write_bytes(self, path: Path, data: bytes) -> None:
        self.ensure_dir()
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)

    def load_list_image(self, commands: Any, *, perm: int, page: int) -> bytes | None:
        """命中即返回 PNG 字节；未命中 / 索引过期 / 文件缺失返回 None。"""
        try:
            fingerprint = command_fingerprint(commands)
            if not self.is_fresh(fingerprint):
                return None
            path = list_cache_path(
                fingerprint=fingerprint,
                perm=perm,
                page=page,
                size=self._size,
                directory=self._directory,
            )
            if not path.is_file():
                return None
            return path.read_bytes()
        except Exception as exc:
            self._logger.warning(f"读取 help 列表缓存失败，改为即时渲染: {exc}")
            return None

    def store_list_image(
        self, data: bytes, *, fingerprint: str, perm: int, page: int, pages: int
    ) -> Path | None:
        """写回列表卡片并更新索引页数；失败返回 None（不影响本次发图）。"""
        try:
            index = self.read_index()
            if str(index.get("fingerprint") or "") != str(fingerprint):
                index = self.new_index(fingerprint)
            path = list_cache_path(
                fingerprint=fingerprint,
                perm=perm,
                page=page,
                size=self._size,
                directory=self._directory,
            )
            self._write_bytes(path, data)
            pages_map = index.setdefault("pages", {})
            key = str(int(perm))
            pages_map[key] = max(int(pages_map.get(key, 0) or 0), int(pages))
            self.write_index(self.touch_index(index))
            self.prune()
            return path
        except Exception as exc:
            self._logger.warning(f"写回 help 列表缓存失败: {exc}")
            return None

    def load_detail_image(
        self, command: Any, *, perm: int, fingerprint: str
    ) -> bytes | None:
        """详情卡片缓存读取（按需渲染，命中即复用）。"""
        try:
            if not self.is_fresh(fingerprint):
                return None
            path = detail_cache_path(
                command=command,
                fingerprint=fingerprint,
                perm=perm,
                directory=self._directory,
            )
            if not path.is_file():
                return None
            return path.read_bytes()
        except Exception as exc:
            self._logger.warning(f"读取 help 详情缓存失败，改为即时渲染: {exc}")
            return None

    def store_detail_image(
        self, data: bytes, *, command: Any, perm: int, fingerprint: str
    ) -> Path | None:
        """写回详情卡片缓存（索引指纹不匹配时顺手重建索引骨架）。"""
        try:
            index = self.read_index()
            if str(index.get("fingerprint") or "") != str(fingerprint):
                self.write_index(self.new_index(fingerprint))
            path = detail_cache_path(
                command=command,
                fingerprint=fingerprint,
                perm=perm,
                directory=self._directory,
            )
            self._write_bytes(path, data)
            self.prune()
            return path
        except Exception as exc:
            self._logger.warning(f"写回 help 详情缓存失败: {exc}")
            return None

    # ── 容量与旧指纹清理 ──

    def _iter_images(self) -> list[Path]:
        try:
            return [path for path in self._directory.glob("*.png") if path.is_file()]
        except OSError:  # pragma: no cover - 目录不可读时按空处理
            return []

    @staticmethod
    def _mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:  # pragma: no cover
            return 0.0

    def cleanup_stale(self, fingerprint: str) -> int:
        """删除不属于当前指纹的缓存图片，返回删除数量。"""
        removed = 0
        for path in self._iter_images():
            if str(fingerprint) in path.name:
                continue
            try:
                path.unlink()
                removed += 1
            except OSError:  # pragma: no cover
                continue
        return removed

    def prune(self) -> int:
        """按生成时间淘汰超出上限的图片，返回删除数量。"""
        images = sorted(self._iter_images(), key=self._mtime)
        removed = 0
        while len(images) > self._max_files:
            path = images.pop(0)
            try:
                path.unlink()
                removed += 1
            except OSError:  # pragma: no cover
                continue
        return removed


async def prerender_help_menu(
    *,
    commands: Any,
    screenshots: Any = None,
    directory: Any = None,
    data_dir: Any = None,
    size: int = HELP_PAGE_SIZE,
    max_files: int = HELP_CACHE_MAX_FILES,
    timeout: float = RENDER_TIMEOUT_SECONDS,
    perm_dimensions: Any = PERMISSION_DIMENSIONS,
    log: Any = None,
) -> dict[str, int]:
    """预渲染三个权限维度的列表卡片并落盘；全程不抛异常。

    返回统计（pages / rendered / failed / pruned / stale_removed），失败只记 warning，
    因此可以安全地挂在启动 / 软重启的后台任务上（spec(5) R9 / D8 / A14）。
    """
    stats = {"pages": 0, "rendered": 0, "failed": 0, "pruned": 0, "stale_removed": 0}
    reporter = log or logger
    cache = HelpCache(
        directory=directory,
        data_dir=data_dir,
        size=size,
        max_files=max_files,
        log=reporter,
    )
    try:
        command_list = list(commands or ())
        fingerprint = command_fingerprint(command_list)
        # 先清理旧指纹文件并落下新索引骨架，避免半新半旧的缓存被当成命中
        stats["stale_removed"] = cache.cleanup_stale(fingerprint)
        cache.write_index(cache.new_index(fingerprint))
        for perm in perm_dimensions:
            visible = sorted(
                (
                    command
                    for command in command_list
                    if int(getattr(command, "permission", 0) or 0) <= int(perm)
                ),
                key=lambda item: str(item.name),
            )
            pages = help_card.total_pages(len(visible), cache.size)
            stats["pages"] += pages
            for page in range(1, pages + 1):
                payload = help_card.build_list_payload(
                    visible, page=page, size=cache.size
                )
                html = help_card.render_payload_html(payload)
                png = await render_card_image(
                    html, timeout=timeout, screenshots=screenshots
                )
                if not png:
                    stats["failed"] += 1
                    continue
                stored = cache.store_list_image(
                    png, fingerprint=fingerprint, perm=perm, page=page, pages=pages
                )
                if stored is None:
                    stats["failed"] += 1
                else:
                    stats["rendered"] += 1
        stats["pruned"] = cache.prune()
    except Exception as exc:
        stats["failed"] += 1
        reporter.warning(f"/help 预渲染失败（不影响启动 / 软重启）: {exc}")
    return stats


def make_prerender_coro(
    *,
    commands: Any,
    screenshots: Any = None,
    directory: Any = None,
    data_dir: Any = None,
    size: int = HELP_PAGE_SIZE,
    max_files: int = HELP_CACHE_MAX_FILES,
    timeout: float = RENDER_TIMEOUT_SECONDS,
    perm_dimensions: Any = PERMISSION_DIMENSIONS,
    delay: float = 0.0,
    log: Any = None,
) -> Any:
    """构造后台预渲染协程（挂 NeoBotApplication.background_coros）。

    commands 可以是命令列表，也可以是「返回命令列表的可调用对象」——后者在协程
    真正运行时才读取命令表，因此插件命令注册完成后再预渲染即可拿到完整命令集。
    """
    reporter = log or logger

    async def _run() -> None:
        try:
            if delay and delay > 0:
                await asyncio.sleep(float(delay))
            command_list = list(commands() if callable(commands) else commands)
            await prerender_help_menu(
                commands=command_list,
                screenshots=screenshots,
                directory=directory,
                data_dir=data_dir,
                size=size,
                max_files=max_files,
                timeout=timeout,
                perm_dimensions=perm_dimensions,
                log=reporter,
            )
        except Exception as exc:  # noqa: BLE001 - 预渲染绝不影响启动 / 软重启
            reporter.warning(f"/help 预渲染任务异常（已忽略）: {exc}")

    return _run()


__all__ = [
    "HELP_CACHE_DIR_NAME",
    "HELP_CACHE_MAX_FILES",
    "HELP_PAGE_SIZE",
    "INDEX_FILE_NAME",
    "PERMISSION_DIMENSIONS",
    "RENDER_TIMEOUT_SECONDS",
    "RENDERER_VERSION",
    "HelpCache",
    "cache_dir",
    "command_fingerprint",
    "default_cache_dir",
    "detail_cache_path",
    "list_cache_path",
    "make_prerender_coro",
    "prerender_help_menu",
]


