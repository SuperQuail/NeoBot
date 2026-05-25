"""HTTP 文件服务器 - 提供临时文件访问"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict

from aiohttp import web
from neobot_app.time_context import epoch_seconds


@dataclass
class ExpirationConfig:
    """文件过期配置"""
    small_file_seconds: int = 300      # < 1MB: 5 分钟
    medium_file_seconds: int = 900     # 1-10MB: 15 分钟
    large_file_seconds: int = 1800     # 10-30MB: 30 分钟
    xlarge_file_seconds: int = 3600    # > 30MB: 60 分钟


@dataclass
class FileMetadata:
    """文件元数据"""
    path: str
    size: int
    created_at: float
    expires_at: float
    token: str


class FileServer:
    """HTTP 文件服务器"""

    def __init__(
        self,
        data_dir: Path,
        port: int = 8765,
        host: str = "127.0.0.1",
        expiration_config: ExpirationConfig | None = None,
        public_url: str | None = None,
        enabled: bool = True,
    ) -> None:
        self._data_dir = data_dir
        self._tmp_dir = data_dir / "tmp"
        self._enabled = enabled
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        self._port = port
        self._host = host
        self._public_url = public_url
        self._config = expiration_config or ExpirationConfig()
        self._files: Dict[str, FileMetadata] = {}
        self._metadata_file = self._tmp_dir / ".file_metadata.json"
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._cleanup_task: asyncio.Task | None = None
        self._running = False
        self._load_metadata()

    async def start(self) -> None:
        """启动文件服务器"""
        if not self._enabled:
            logging.warning("已跳过 HTTP 文件服务器启动（配置要求走本地路径）")
            return
        if self._running:
            return
        self._app = web.Application()
        self._app.router.add_get("/files/{filename}", self._handle_file)
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self) -> None:
        """停止文件服务器"""
        if not self._running:
            return
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        if self._runner:
            await self._runner.cleanup()
        self._save_metadata()

    def register_file(self, file_path: Path) -> str:
        """注册文件并返回 URL"""
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        size = file_path.stat().st_size
        expires_at = self._calculate_expiration(size)
        filename = file_path.name
        token = secrets.token_urlsafe(32)
        self._files[filename] = FileMetadata(
            path=str(file_path),
            size=size,
            created_at=epoch_seconds(),
            expires_at=expires_at,
            token=token,
        )
        self._save_metadata()
        if self._public_url:
            return f"{self._public_url}/files/{filename}?token={token}"
        return f"http://{self._host}:{self._port}/files/{filename}?token={token}"

    def _calculate_expiration(self, size: int) -> float:
        """根据文件大小计算过期时间"""
        now = epoch_seconds()
        if size < 1_000_000:
            return now + self._config.small_file_seconds
        elif size < 10_000_000:
            return now + self._config.medium_file_seconds
        elif size < 30_000_000:
            return now + self._config.large_file_seconds
        else:
            return now + self._config.xlarge_file_seconds

    async def _handle_file(self, request: web.Request) -> web.Response:
        """处理文件请求"""
        filename = request.match_info["filename"]
        if filename not in self._files:
            return web.Response(status=404, text="文件不存在")
        meta = self._files[filename]
        token = request.query.get("token")
        if token != meta.token:
            return web.Response(status=403, text="无效的访问令牌")
        if epoch_seconds() > meta.expires_at:
            self._files.pop(filename)
            Path(meta.path).unlink(missing_ok=True)
            self._save_metadata()
            return web.Response(status=404, text="文件已过期")
        return web.FileResponse(meta.path)

    async def _cleanup_loop(self) -> None:
        """清理过期文件"""
        while self._running:
            await asyncio.sleep(60)
            now = epoch_seconds()
            expired = [name for name, meta in self._files.items() if meta.expires_at <= now]
            for name in expired:
                meta = self._files.pop(name)
                Path(meta.path).unlink(missing_ok=True)
            if expired:
                self._save_metadata()

    def _load_metadata(self) -> None:
        """加载元数据"""
        if not self._metadata_file.exists():
            return
        try:
            with open(self._metadata_file) as f:
                data = json.load(f)
            self._files = {k: FileMetadata(**v) for k, v in data.items()}
        except Exception:
            pass

    def _save_metadata(self) -> None:
        """保存元数据"""
        try:
            with open(self._metadata_file, "w") as f:
                json.dump({k: asdict(v) for k, v in self._files.items()}, f)
        except Exception:
            pass

