"""仅本机可用的版本化开发控制接口；控制现有运行时，不承担插件下载。"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import os
import secrets
import tempfile
from pathlib import Path
from typing import Any, Callable

from aiohttp import web

from neobot_modloader.development import DevelopmentError
from neobot_modloader.plugins.registration import validate_plugin_name

SCHEMA_VERSION = 1
CAPABILITIES = ("plugin.list", "plugin.dev", "plugin.reload", "runtime.stop")


def _success(data: dict[str, Any]) -> web.Response:
    return web.json_response({"schema_version": SCHEMA_VERSION, "ok": True, "data": data})


def _error(code: str, message: str, *, status: int = 400) -> web.Response:
    return web.json_response(
        {"schema_version": SCHEMA_VERSION, "ok": False, "error": {"code": code, "message": message}},
        status=status,
    )


class LocalControlServer:
    def __init__(
        self,
        runtime: Any,
        *,
        data_dir: Path,
        version: str,
        request_stop: Callable[[], None],
    ) -> None:
        self.runtime = runtime
        self.data_dir = Path(data_dir).resolve()
        self.version = version
        self.request_stop = request_stop
        self.instance_id = secrets.token_hex(16)
        self._token = secrets.token_urlsafe(32)
        self.discovery = self.data_dir / ".neobot" / "control.json"
        self._runner: web.AppRunner | None = None
        self.url = ""
        self._mutations = asyncio.Lock()
        self._closing = False

    @web.middleware
    async def _guard(self, request: web.Request, handler: Any) -> web.StreamResponse:
        # 不接受浏览器、反代或 DNS rebinding；原始 TCP 客户端也必须持有随机凭证。
        if request.remote != "127.0.0.1" or request.headers.get("Origin") is not None:
            return _error("forbidden_origin", "只接受本机控制客户端", status=403)
        if request.host != self.url.removeprefix("http://"):
            return _error("forbidden_host", "控制接口主机名无效", status=403)
        supplied = request.headers.get("Authorization", "")
        if not hmac.compare_digest(supplied.encode("utf-8"), f"Bearer {self._token}".encode("ascii")):
            return _error("unauthorized", "控制凭证无效", status=401)
        try:
            return await handler(request)
        except DevelopmentError as error:
            return _error(error.code, str(error), status=409)
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            return _error("invalid_request", str(error))
        except web.HTTPException as error:
            return _error("invalid_request", "控制请求无效", status=error.status)
        except Exception:
            # 不把插件异常、环境或凭据原文返回控制客户端。
            return _error("operation_failed", "控制操作失败，请查看宿主日志", status=500)

    def snapshot(self) -> dict[str, Any]:
        plugins = []
        for item in self.runtime.snapshot_plugins():
            plugins.append(
                {
                    "name": item.name,
                    "state": item.state,
                    "version": item.version,
                    "path": str(item.path) if item.path else None,
                    "enabled": item.enabled,
                    "error": item.error,
                    **self.runtime.development.status(item.name),
                }
            )
        return {
            "instance_id": self.instance_id,
            "pid": os.getpid(),
            "data_dir": str(self.data_dir),
            "plugin_dir": str(self.runtime.plugin_dir),
            "version": self.version,
            "stopping": self._closing,
            "capabilities": list(CAPABILITIES),
            "plugins": plugins,
        }

    async def _status(self, _request: web.Request) -> web.Response:
        return _success(self.snapshot())

    async def _body(self, request: web.Request, *, keys: set[str]) -> dict[str, Any]:
        if self._closing:
            raise DevelopmentError("shutting_down", "宿主正在关闭")
        if request.content_type != "application/json":
            raise ValueError("请求必须使用 JSON")
        body = await request.json()
        if not isinstance(body, dict) or set(body) != keys:
            raise ValueError("请求字段不匹配")
        return body

    async def _dev(self, request: web.Request) -> web.Response:
        body = await self._body(request, keys={"name", "enabled"})
        if not isinstance(body["name"], str) or type(body["enabled"]) is not bool:
            raise ValueError("name 必须是字符串，enabled 必须是布尔值")
        async with self._mutations:
            if self._closing:
                raise DevelopmentError("shutting_down", "宿主正在关闭")
            await self.runtime.development.set_enabled(body["name"], body["enabled"])
            return _success(self.snapshot())

    async def _reload(self, request: web.Request) -> web.Response:
        body = await self._body(request, keys={"name"})
        name = body["name"]
        if not isinstance(name, str):
            raise ValueError("name 必须是字符串")
        validate_plugin_name(name)
        async with self._mutations:
            if self._closing:
                raise DevelopmentError("shutting_down", "宿主正在关闭")
            snapshot = self.runtime.control.get(name)
            record = self.runtime.manager.get_record(name)
            if snapshot is None or snapshot.path is None or record is None:
                raise DevelopmentError("plugin_not_found", "插件未加载")
            if not snapshot.enabled or snapshot.state not in {"running", "loaded"}:
                raise DevelopmentError("plugin_not_running", "插件未运行，请先显式启动")
            if not snapshot.hot_reloadable:
                raise DevelopmentError("restart_required", "此插件不支持热重载")
            result = await self.runtime.reload_plugin_result(
                name,
                start=snapshot.state == "running",
                auto_install_dependencies=False,
                _expected=(record, record.state),
            )
            if not result.ok:
                raise DevelopmentError("reload_failed", result.error or "插件重载失败")
            return _success(self.snapshot())

    async def _stop(self, request: web.Request) -> web.Response:
        await self._body(request, keys=set())
        self._closing = True
        asyncio.get_running_loop().call_soon(self.request_stop)
        return _success({"instance_id": self.instance_id, "stopping": True})

    async def start(self) -> None:
        if self._runner is not None:
            return
        if self.discovery.parent.is_symlink():
            raise ValueError("实例控制目录不能是符号链接")
        self.discovery.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        app = web.Application(middlewares=[self._guard], client_max_size=8192)
        app.add_routes(
            [
                web.get("/v1/status", self._status),
                web.post("/v1/plugins/dev", self._dev),
                web.post("/v1/plugins/reload", self._reload),
                web.post("/v1/stop", self._stop),
            ]
        )
        runner = web.AppRunner(app, access_log=None)
        self._runner = runner
        try:
            await runner.setup()
            site = web.TCPSite(runner, "127.0.0.1", 0)
            await site.start()
            port = runner.addresses[0][1]
            self.url = f"http://127.0.0.1:{port}"
            document = {
                "schema_version": SCHEMA_VERSION,
                "url": self.url,
                "token": self._token,
                "pid": os.getpid(),
                "instance_id": self.instance_id,
                "data_dir": str(self.data_dir),
            }
            descriptor, temporary = tempfile.mkstemp(prefix=".control-", dir=self.discovery.parent)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    json.dump(document, stream)
                    stream.write("\n")
                os.replace(temporary, self.discovery)
            finally:
                with contextlib.suppress(FileNotFoundError):
                    Path(temporary).unlink()
        except BaseException:
            await self.close()
            raise

    async def begin_shutdown(self) -> None:
        self._closing = True
        async with self._mutations:
            pass

    async def close(self) -> None:
        await self.begin_shutdown()
        runner, self._runner = self._runner, None
        if runner is not None:
            await runner.cleanup()
        with contextlib.suppress(OSError, ValueError):
            document = json.loads(self.discovery.read_text(encoding="utf-8"))
            if document.get("instance_id") == self.instance_id:
                self.discovery.unlink()
