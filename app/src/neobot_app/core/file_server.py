"""HTTP 文件服务器 - 提供临时文件访问"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict

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

    _MAX_UPLOAD_BYTES = 30_000_000
    _SUPPORTED_IMAGE_FORMATS = {
        "JPEG": (".jpg", "image/jpeg"),
        "PNG": (".png", "image/png"),
        "GIF": (".gif", "image/gif"),
        "WEBP": (".webp", "image/webp"),
        "BMP": (".bmp", "image/bmp"),
    }

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
        self._site: web.TCPSite | None = None
        self._cleanup_task: asyncio.Task | None = None
        self._running = False
        self._load_metadata()

    async def start(self) -> None:
        """启动文件服务器（端口被占时自动 +1 重试，最多 100 次）"""
        if not self._enabled:
            logging.warning("已跳过 HTTP 文件服务器启动（配置要求走本地路径）")
            return
        if self._running:
            return
        self._app = web.Application(middlewares=[self._cors_middleware])
        self._app.router.add_post("/files", self._handle_upload)
        self._app.router.add_get("/files/{filename}", self._handle_file)
        self._app.router.add_options("/{tail:.*}", self._handle_options)
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        max_attempts = 100
        _first_port = self._port
        last_error = None
        for _ in range(max_attempts):
            try:
                self._site = web.TCPSite(self._runner, self._host, self._port)
                await self._site.start()
                last_error = None
                break
            except OSError as e:
                last_error = e
                self._port += 1

        if last_error is not None:
            raise RuntimeError(
                f"文件服务器端口占用: 尝试 {_first_port}~{_first_port + max_attempts - 1} "
                f"共 {max_attempts} 个端口均被占用"
            ) from last_error

        if self._port == 0 and self._site._server is not None:
            sockets = self._site._server.sockets or []
            if sockets:
                self._port = int(sockets[0].getsockname()[1])
        self._running = True
        logging.info(f"文件服务器已启动: http://{self._host}:{self._port}")
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
        self._site = None
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

    @web.middleware
    async def _cors_middleware(self, request: web.Request, handler):
        response = await handler(request)
        response.headers.setdefault("Access-Control-Allow-Origin", "*")
        response.headers.setdefault("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        response.headers.setdefault("Access-Control-Allow-Headers", "Content-Type,Authorization")
        response.headers.setdefault("Access-Control-Max-Age", "86400")
        return response

    async def _handle_options(self, request: web.Request) -> web.Response:
        return web.Response(status=204)

    async def _handle_upload(self, request: web.Request) -> web.Response:
        """处理浏览器上传的图片文件."""
        if not self._enabled:
            return self._json_error("disabled", "文件服务器未启用", status=503)

        try:
            reader = await request.multipart()
        except Exception as exc:
            return self._json_error("invalid_multipart", f"需要 multipart/form-data: {exc}", status=400)

        field = await reader.next()
        while field is not None and field.name != "file":
            await field.read(decode=False)
            field = await reader.next()

        if field is None:
            return self._json_error("missing_file", "缺少 file 字段", status=400)

        temp_path = self._tmp_dir / f".upload_{secrets.token_hex(16)}.tmp"
        size = 0
        try:
            with temp_path.open("wb") as fh:
                while True:
                    chunk = await field.read_chunk(size=1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > self._MAX_UPLOAD_BYTES:
                        return self._json_error(
                            "file_too_large",
                            f"图片不能超过 {self._MAX_UPLOAD_BYTES} 字节",
                            status=413,
                        )
                    fh.write(chunk)

            if size <= 0:
                return self._json_error("empty_file", "上传文件为空", status=400)

            try:
                image_info = self._inspect_uploaded_image(temp_path)
            except ValueError as exc:
                return self._json_error("invalid_image", str(exc), status=400)

            filename = self._uploaded_filename(image_info["suffix"])
            final_path = self._tmp_dir / filename
            temp_path.replace(final_path)
            url = self.register_file(final_path)
            metadata = self._files[filename]
            return self._json_ok(
                {
                    "filename": filename,
                    "original_filename": Path(field.filename or "").name,
                    "size": size,
                    "content_type": image_info["mime_type"],
                    "width": image_info["width"],
                    "height": image_info["height"],
                    "url": url,
                    "expires_at": metadata.expires_at,
                    "segment": {
                        "type": "image",
                        "data": {
                            "file": url,
                            "url": url,
                        },
                    },
                }
            )
        finally:
            temp_path.unlink(missing_ok=True)

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
            self._unlink_registered_file(meta)
            self._save_metadata()
            return web.Response(status=404, text="文件已过期")

        file_path = Path(meta.path)
        if not file_path.exists():
            return web.Response(status=404, text="文件已被删除")
        suffix = file_path.suffix.lower()
        content_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }.get(suffix, "application/octet-stream")
        return web.FileResponse(file_path, headers={"Content-Type": content_type})

    def _inspect_uploaded_image(self, path: Path) -> dict[str, Any]:
        try:
            from PIL import Image, UnidentifiedImageError
        except Exception as exc:  # pragma: no cover - pillow is an app dependency
            raise ValueError("图片处理依赖不可用") from exc

        try:
            with Image.open(path) as image:
                format_name = str(image.format or "").upper()
                width, height = image.size
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ValueError("上传内容不是有效图片") from exc

        if format_name not in self._SUPPORTED_IMAGE_FORMATS:
            supported = ", ".join(sorted(self._SUPPORTED_IMAGE_FORMATS))
            raise ValueError(f"不支持的图片格式: {format_name or 'unknown'}，支持: {supported}")

        suffix, mime_type = self._SUPPORTED_IMAGE_FORMATS[format_name]
        return {
            "format": format_name,
            "suffix": suffix,
            "mime_type": mime_type,
            "width": width,
            "height": height,
        }

    @staticmethod
    def _uploaded_filename(suffix: str) -> str:
        return f"upload_{secrets.token_hex(16)}{suffix}"

    @staticmethod
    def _json_ok(data: Any) -> web.Response:
        return web.json_response({"ok": True, "data": data, "error": None})

    @staticmethod
    def _json_error(code: str, message: str, *, status: int = 400) -> web.Response:
        return web.json_response(
            {
                "ok": False,
                "data": None,
                "error": {"code": code, "message": message},
            },
            status=status,
        )

    async def _cleanup_loop(self) -> None:
        """清理过期文件（仅删除临时文件，不删除图库/表情包等永久文件）"""
        while self._running:
            await asyncio.sleep(60)
            now = epoch_seconds()
            expired = [name for name, meta in self._files.items() if meta.expires_at <= now]
            for name in expired:
                meta = self._files.pop(name)
                self._unlink_registered_file(meta)
            if expired:
                self._save_metadata()

    def _unlink_registered_file(self, meta: FileMetadata) -> None:
        """删除注册的文件。仅删除 tmp 目录下的临时文件，避免误删表情包等永久文件。"""
        file_path = Path(meta.path)
        try:
            if self._tmp_dir in file_path.parents:
                file_path.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass

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

