"""本体级用户头像存储与惰性刷新（spec(5) §4.9 / R33–R37 / D13）。

职责：为**聊过天的用户**维护一份本地头像 —— 图片落盘（<DATA_DIR>/avatars/
<user_id>.png）+ 信息落表（user_data 新增的三列）。调用方（卡片、面板、插件）
一律用 get_path / get_data_uri 取值，**不自行联网**。

设计要点（与文档 §4.9 一一对应）：

- **惰性、事件驱动**：唯一触发点是「用户再次出现在聊天流」。无头像则获取；
  已有头像且 now - avatar_fetched_at > refresh_days（默认 7 天）才更新；
  未过期**零网络开销、零写库**。不做定时全量扫描。
- **失败不更新**：avatar_path / avatar_fetched_at 原样保留（宁可旧头像，
  不要空头像），只把 avatar_fail_count +1 并记 debug 日志；失败后进入
  fail_cooldown_seconds（默认 600）冷却，冷却期内再频繁发言也不重试。
  失败过程不落半截文件：先写同目录临时文件，落库成功后再 os.replace 原子替换。
- **不阻塞消息处理**：maybe_refresh 只做一次 DB 读 + 一次时间比较（外加见下），
  真正的下载在 asyncio.create_task 里跑，异常全部吞掉。
- **单飞与限速**：同一 user_id 同时只允许一个下载（进程内集合）；全局在途数
  不超过 max_concurrent（默认 2），超限**丢弃本次触发**（该用户下次出现时
  自然重试，不做排队）。
- **容量治理**：单图字节上限 max_bytes（默认 512 KiB），超限不落盘并按失败处理；
  keep_days（默认 90）清理长期未活跃用户的头像（文件 + 列清空）。清理随头像
  刷新流量触发且最多每 24 小时一次，不做定时全量扫描。
- **对外接口**：get_path / get_data_uri / maybe_refresh / stats；get_data_uri 内部
  维护进程内 LRU（128 条，640px PNG 约 40 KB，合计约 5 MB）。

为什么与用户资料同表：**有 user_data 行 = 认识该用户**，天然覆盖「聊过天的人」，
也避免「资料有行、头像没行」的两处数据不一致（见 models.UserData 注释）。
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import os
import re
import tempfile
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable

from neobot_contracts.ports.logging import Logger
from neobot_contracts.time_context import to_utc

from neobot_app.core.constants import AVATAR_DIR
from neobot_app.time_context import monotonic_seconds, now_utc
from neobot_app.utils.logger import get_module_logger

#: 头像取源（既有约定，与面板现算 URL 同源）
QQ_AVATAR_URL_TEMPLATE = "https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640"

#: 单次下载超时（秒）
FETCH_TIMEOUT_SECONDS = 20.0

#: get_data_uri 的进程内 LRU 条数（防止长跑进程把 base64 串全留在内存）
DATA_URI_CACHE_SIZE = 128

#: 容量清理的最小触发间隔（秒）。清理是**事件驱动**的（随聊天流触发），
#: 进程启动后至少间隔该时长才会执行第一次清理，因此「未过期再次发言零写库」
#: 不会被清理写库打破。
CLEANUP_INTERVAL_SECONDS = 86400.0

DEFAULT_REFRESH_DAYS = 7
DEFAULT_FAIL_COOLDOWN_SECONDS = 600
DEFAULT_MAX_CONCURRENT = 2
DEFAULT_MAX_BYTES = 524288
DEFAULT_KEEP_DAYS = 90

_SAFE_ID_RE = re.compile(r"[^0-9A-Za-z_-]+")

#: 图片魔数（用于挡掉错误页 / JSON 之类的假响应；不强制 PNG，QQ 偶尔改格式时
#: 不至于把所有头像永久判失败）
_IMAGE_MAGIC = (
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",
    b"GIF87a",
    b"GIF89a",
)


def _pick(value: Any, section: Any, name: str, default: Any) -> Any:
    """取值优先级：显式参数 > 配置段字段 > 默认值。"""
    if value is not None:
        return value
    return getattr(section, name, default)


def _as_int(value: Any, default: int, *, minimum: int = 0) -> int:
    """把配置读成整数；None / 非法值 / 小于下限一律回落默认值。"""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= minimum else default


def _as_float(value: Any, default: float, *, minimum: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= minimum else default


def _as_datetime(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return to_utc(value)


def safe_user_key(user_id: Any) -> str:
    """把 user_id 变成可安全用作文件名的键（QQ 号为纯数字，原样保留）。"""
    raw = str(user_id or "").strip()
    if not raw:
        return ""
    return _SAFE_ID_RE.sub("_", raw)


def _looks_like_image(data: bytes) -> bool:
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return True
    return any(data.startswith(magic) for magic in _IMAGE_MAGIC)


class AvatarStore:
    """头像的本地存储、惰性刷新与容量治理。"""

    def __init__(
        self,
        *,
        uow_factory: Any = None,
        config: Any = None,
        logger: Logger | None = None,
        directory: Any = None,
        fetcher: Callable[[str], Awaitable[bytes]] | None = None,
        clock: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] | None = None,
        enabled: bool | None = None,
        refresh_days: Any = None,
        fail_cooldown_seconds: Any = None,
        max_concurrent: Any = None,
        max_bytes: Any = None,
        keep_days: Any = None,
    ) -> None:
        section = getattr(config, "avatars", None)
        self._uow_factory = uow_factory
        self._logger = logger or get_module_logger("runtime.avatar_store")
        self._directory = Path(directory) if directory is not None else Path(AVATAR_DIR)
        self._fetcher = fetcher
        self._clock = clock or now_utc
        self._monotonic = monotonic or monotonic_seconds

        self._enabled = bool(_pick(enabled, section, "enabled", True))
        self._refresh_days = _as_int(
            _pick(refresh_days, section, "refresh_days", DEFAULT_REFRESH_DAYS),
            DEFAULT_REFRESH_DAYS,
        )
        self._fail_cooldown_seconds = _as_float(
            _pick(
                fail_cooldown_seconds,
                section,
                "fail_cooldown_seconds",
                DEFAULT_FAIL_COOLDOWN_SECONDS,
            ),
            float(DEFAULT_FAIL_COOLDOWN_SECONDS),
        )
        self._max_concurrent = _as_int(
            _pick(max_concurrent, section, "max_concurrent", DEFAULT_MAX_CONCURRENT),
            DEFAULT_MAX_CONCURRENT,
            minimum=1,
        )
        # max_bytes <= 0 视为「不限制」；正常配置不会用到。
        self._max_bytes = _as_int(
            _pick(max_bytes, section, "max_bytes", DEFAULT_MAX_BYTES),
            DEFAULT_MAX_BYTES,
        )
        self._keep_days = _as_int(
            _pick(keep_days, section, "keep_days", DEFAULT_KEEP_DAYS),
            DEFAULT_KEEP_DAYS,
        )

        #: 同一 user_id 的在途下载（单飞）
        self._inflight: set[str] = set()
        #: 持有任务强引用，避免被 GC 提前回收
        self._tasks: set[asyncio.Task[None]] = set()
        self._active = 0
        #: user_id -> 冷却到期时刻（单调时钟秒）
        self._cooldown_until: dict[str, float] = {}
        self._data_uri_cache: OrderedDict[str, str] = OrderedDict()
        self._last_cleanup_monotonic = self._monotonic()
        self._cleanup_inflight = False
        self._counters: dict[str, int] = {
            "started": 0,
            "succeeded": 0,
            "refreshed": 0,
            "failed": 0,
            "skipped_fresh": 0,
            "skipped_cooldown": 0,
            "skipped_inflight": 0,
            "dropped_concurrency": 0,
            "cleaned": 0,
        }
        self._dir_ready = False
        self._ensure_dir()

    # ── 只读接口（卡片 / 面板 / 插件）────────────────────────────

    @property
    def directory(self) -> Path:
        """头像目录 <DATA_DIR>/avatars。"""
        return self._directory

    @property
    def enabled(self) -> bool:
        return self._enabled

    def path_for(self, user_id: Any) -> Path:
        """该用户头像的**约定路径**（不判断是否存在）。"""
        return self._directory / (safe_user_key(user_id) + ".png")

    def get_path(self, user_id: Any) -> Path | None:
        """本地头像路径；未就绪（没取过 / 已被清理）返回 None。

        路径是**确定性**的（<目录>/<user_id>.png），所以这里以「文件是否存在」
        为准：等价于查表（表里的 avatar_path 只是同一路径的镜像，用于容量清理
        与一致性诊断），但卡片渲染路径不必再打一次 DB。**不联网**，这是 R33
        「调用方一律查表取值、不自行联网」的落点。
        """
        key = safe_user_key(user_id)
        if not key:
            return None
        path = self.path_for(key)
        try:
            return path if path.is_file() else None
        except OSError:
            return None

    def get_data_uri(self, user_id: Any) -> str | None:
        """头像的 data:image/png;base64,... 串；未就绪返回 None。

        进程内 LRU（DATA_URI_CACHE_SIZE 条）：同一张头像在卡片渲染中被反复
        取用时不重复读盘 / 编码，也不会随用户数无限增长。
        """
        key = safe_user_key(user_id)
        if not key:
            return None
        cached = self._data_uri_cache.get(key)
        if cached is not None:
            self._data_uri_cache.move_to_end(key)
            return cached
        path = self.get_path(key)
        if path is None:
            return None
        try:
            raw = path.read_bytes()
        except OSError as exc:
            self._logger.debug("头像读取失败", user_id=key, error=str(exc))
            return None
        uri = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
        self._data_uri_cache[key] = uri
        self._data_uri_cache.move_to_end(key)
        while len(self._data_uri_cache) > DATA_URI_CACHE_SIZE:
            self._data_uri_cache.popitem(last=False)
        return uri

    def stats(self) -> dict[str, Any]:
        """运行态计数与容量快照（面板 / 诊断 / 测试用）。"""
        snapshot: dict[str, Any] = {
            "enabled": self._enabled,
            "refresh_days": self._refresh_days,
            "keep_days": self._keep_days,
            "max_concurrent": self._max_concurrent,
            "max_bytes": self._max_bytes,
            "directory": str(self._directory),
            "dir_ready": self._dir_ready,
            "active": self._active,
            "inflight": len(self._inflight),
            "cooldowns": len(self._cooldown_until),
            "data_uri_cached": len(self._data_uri_cache),
            "tasks": len(self._tasks),
        }
        snapshot.update(self._counters)
        return snapshot

    # ── 惰性刷新（消息路径唯一入口）──────────────────────────────

    async def maybe_refresh(self, user_id: Any) -> bool:
        """用户再次出现在聊天流时的判定；返回是否派发了一次下载。

        **永不抛异常**：判定失败、配置未接线、DB 读失败都只是「这次不刷新」，
        绝不能把消息处理路径带崩。
        """
        try:
            return await self._maybe_refresh(user_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._logger.debug(
                "头像刷新判定异常", user_id=safe_user_key(user_id), error=str(exc)
            )
            return False

    async def _maybe_refresh(self, user_id: Any) -> bool:
        if not self._enabled or self._uow_factory is None:
            return False
        key = safe_user_key(user_id)
        if not key:
            return False
        # 单飞：同一用户同时只允许一个下载（他可能在多个群里同时发言）。
        if key in self._inflight:
            self._counters["skipped_inflight"] += 1
            return False

        row = await self._load_row(key)  # 一次 DB 读
        now = self._clock()
        path = self.path_for(key)
        has_avatar = bool(getattr(row, "avatar_path", None)) and path.is_file()
        fetched_at = _as_datetime(getattr(row, "avatar_fetched_at", None))
        if has_avatar and fetched_at is not None:
            if now - fetched_at <= timedelta(days=self._refresh_days):
                # 未过期：到此为止 —— 零网络开销、零写库。
                self._counters["skipped_fresh"] += 1
                return False
        if self._in_cooldown(key):
            self._counters["skipped_cooldown"] += 1
            return False
        if self._active >= self._max_concurrent:
            # 超限丢弃本次触发：下一次该用户出现时自然重试，不排队、不等待。
            self._counters["dropped_concurrency"] += 1
            self._logger.debug(
                "头像下载并发已满，丢弃本次触发",
                user_id=key,
                max_concurrent=self._max_concurrent,
            )
            return False

        self._start_download(key, is_refresh=has_avatar)
        self._maybe_schedule_cleanup()
        return True

    def _start_download(self, key: str, *, is_refresh: bool) -> None:
        self._inflight.add(key)
        self._active += 1
        self._counters["started"] += 1
        if is_refresh:
            self._counters["refreshed"] += 1
        task = asyncio.create_task(self._download(key))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _download(self, key: str) -> None:
        try:
            data = await self._fetch(key)
            problem = self._validate(data)
            if problem is not None:
                await self._record_failure(key, reason=problem)
                return
            path = self.path_for(key)
            temp_path = self._write_temp(path, data)
            try:
                # 先落库再原子替换：落库失败就删掉临时文件，旧头像原样保留。
                await self._record_success(key, path)
            except BaseException:
                self._discard_temp(temp_path)
                raise
            try:
                os.replace(temp_path, path)
            except OSError as exc:
                # 极罕见（例如目录被删）：库里已改成新时间戳但盘上还是旧文件，
                # 仍是一张可用头像，不当作失败处理。
                self._discard_temp(temp_path)
                self._logger.warning(
                    "头像文件替换失败", user_id=key, error=str(exc)
                )
                return
            self._counters["succeeded"] += 1
            self._data_uri_cache.pop(key, None)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._record_failure(key, reason=str(exc))
        finally:
            self._inflight.discard(key)
            self._active = max(0, self._active - 1)

    async def _fetch(self, key: str) -> bytes:
        if self._fetcher is not None:
            return await self._fetcher(key)
        return await self._fetch_from_qq(key)

    async def _fetch_from_qq(self, key: str) -> bytes:
        """按既有约定从 qlogo 取 640px 头像（唯一的联网点）。"""
        from neobot_app.utils.http import image_http_client

        url = QQ_AVATAR_URL_TEMPLATE.format(user_id=key)
        async with image_http_client(
            timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=True, url=url
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            content_type = str(response.headers.get("content-type", "") or "")
            if content_type and not content_type.lower().startswith("image/"):
                raise ValueError(f"响应不是图片: {content_type}")
            return bytes(response.content)

    def _validate(self, data: bytes) -> str | None:
        """返回失败原因；None 表示可以落盘。"""
        if not data:
            return "空响应"
        if self._max_bytes > 0 and len(data) > self._max_bytes:
            return f"超过单图上限 {len(data)} > {self._max_bytes}"
        if not _looks_like_image(data):
            return "响应不是已知图片格式"
        return None

    async def _record_success(self, key: str, path: Path) -> None:
        async with self._uow_factory() as uow:
            await uow.profiles.upsert_user(
                key,
                avatar_path=str(path),
                avatar_fetched_at=self._clock(),
                avatar_fail_count=0,
            )
            await uow.commit()
        self._cooldown_until.pop(key, None)
        self._logger.debug("头像已更新", user_id=key, path=str(path))

    async def _record_failure(self, key: str, *, reason: str) -> None:
        """失败不更新：只累加 fail_count + 进入冷却，旧头像与旧时间戳原样保留。"""
        self._counters["failed"] += 1
        self._cooldown_until[key] = self._monotonic() + self._fail_cooldown_seconds
        self._logger.debug("头像获取失败，保留旧头像", user_id=key, reason=reason)
        try:
            async with self._uow_factory() as uow:
                await uow.profiles.bump_avatar_fail_count(key)
                await uow.commit()
        except Exception as exc:
            self._logger.debug("头像失败计数落库失败", user_id=key, error=str(exc))

    async def _load_row(self, key: str) -> Any:
        async with self._uow_factory() as uow:
            return await uow.profiles.get_user(key)

    def _in_cooldown(self, key: str) -> bool:
        deadline = self._cooldown_until.get(key)
        if deadline is None:
            return False
        if self._monotonic() >= deadline:
            self._cooldown_until.pop(key, None)
            return False
        return True

    # ── 容量治理 ─────────────────────────────────────────────────

    async def cleanup_expired(self) -> int:
        """清理长期未活跃用户的头像（文件 + 列清空）；返回清理条数。

        判定依据见 SqlAlchemyProfileRepository.list_stale_avatars：avatar_fetched_at
        同时充当「最后活跃时间的代理」。永不抛异常。
        """
        try:
            if not self._enabled or self._uow_factory is None or self._keep_days <= 0:
                return 0
            cutoff = self._clock() - timedelta(days=self._keep_days)
            async with self._uow_factory() as uow:
                rows = await uow.profiles.list_stale_avatars(cutoff)
            keys = [safe_user_key(getattr(row, "user_id", "")) for row in rows]
            keys = [key for key in keys if key]
            if not keys:
                return 0
            for key in keys:
                self._remove_file(key)
            async with self._uow_factory() as uow:
                for key in keys:
                    await uow.profiles.clear_avatar(key)
                await uow.commit()
            self._counters["cleaned"] += len(keys)
            self._logger.info(
                "头像容量清理完成", removed=len(keys), keep_days=self._keep_days
            )
            return len(keys)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._logger.debug("头像容量清理失败", error=str(exc))
            return 0

    def _maybe_schedule_cleanup(self) -> None:
        if not self._enabled or self._uow_factory is None or self._keep_days <= 0:
            return
        if self._cleanup_inflight:
            return
        now = self._monotonic()
        if now - self._last_cleanup_monotonic < CLEANUP_INTERVAL_SECONDS:
            return
        self._last_cleanup_monotonic = now
        self._cleanup_inflight = True
        task = asyncio.create_task(self._run_cleanup())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run_cleanup(self) -> None:
        try:
            await self.cleanup_expired()
        finally:
            self._cleanup_inflight = False

    # ── 关闭 / 测试辅助 ──────────────────────────────────────────

    async def drain(self, timeout: float = 5.0) -> None:
        """等待在途下载 / 清理任务结束（shutdown 与测试用）。超时不取消任务。"""
        pending = [task for task in self._tasks if not task.done()]
        if not pending:
            return
        await asyncio.wait(pending, timeout=timeout)

    # ── 内部工具 ─────────────────────────────────────────────────

    def _ensure_dir(self) -> None:
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            self._dir_ready = True
        except OSError as exc:
            self._dir_ready = False
            self._logger.warning(
                "头像目录创建失败", directory=str(self._directory), error=str(exc)
            )

    def _write_temp(self, path: Path, data: bytes) -> Path:
        """把字节写入同目录临时文件；返回临时文件路径（调用方负责原子替换）。"""
        self._ensure_dir()
        handle_fd, temp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=".tmp-avatar-", suffix=".png"
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(handle_fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            self._discard_temp(temp_path)
            raise
        return temp_path

    @staticmethod
    def _discard_temp(temp_path: Path) -> None:
        with contextlib.suppress(OSError):
            temp_path.unlink()

    def _remove_file(self, key: str) -> None:
        path = self.path_for(key)
        with contextlib.suppress(OSError):
            path.unlink()
        self._data_uri_cache.pop(key, None)
