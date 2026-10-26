"""三个 B站工具 Skill 共用的依赖解析与错误处理。"""

from __future__ import annotations

from typing import Any

from neobot_app.bilibili._compat import call_client
from neobot_app.skills.base import SkillModule
from neobot_app.skills.bilibili_tool_parts.common import (
    _CONFIRM_REQUIRED,
    _WRITE_TOOLS,
    _Unavailable,
    _dormant_reason,
    _flag,
    _json,
    logger,
)
from neobot_app.skills.bilibili_tool_parts.dispatch import _HANDLERS


class _BilibiliToolBase(SkillModule):
    """三个 B站工具 Skill 共用的依赖解析与错误处理。"""

    def __init__(
        self,
        service: Any = None,
        client: Any = None,
        video_service: Any = None,
        archive_service: Any = None,
        uow_factory: Any = None,
        task_manager: Any = None,
        read_api: Any = None,
    ) -> None:
        self._service = service
        self._client = client
        self._video_service = video_service
        self._archive = archive_service
        self._uow_factory = uow_factory
        self._video_tasks = task_manager
        self._read_api = read_api

    def reset(self) -> None:
        pass

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown tool: {tool_name}"})
        if tool_name in _WRITE_TOOLS and not _flag((args or {}).get("confirm"), False):
            return _json(
                {"ok": False, "code": "CONFIRM_REQUIRED", "error": _CONFIRM_REQUIRED}
            )
        try:
            await self._ensure_login()
            return await handler(self, args)
        except _Unavailable as exc:
            return _json({"ok": False, "error": str(exc)})
        except Exception as exc:
            logger.warning(f"B站工具执行失败：{tool_name}：{type(exc).__name__}: {exc}")
            return _json(
                {"ok": False, "error": f"B站工具执行失败：{type(exc).__name__}: {exc}"}
            )

    async def _ensure_login(self) -> None:
        """登录门禁：先让 service 自愈（refresh），仍不可用才报未登录并带原因。"""
        service = self._service
        if service is None:
            return
        refresh = getattr(service, "refresh", None)
        if callable(refresh):
            try:
                await call_client(refresh)
            except Exception as exc:
                logger.warning(f"B站登录态刷新失败：{type(exc).__name__}: {exc}")
        if getattr(service, "available", None) is False:
            raise _Unavailable(_dormant_reason(service))

    def _has_client_source(self) -> bool:
        return self._service is not None or self._client is not None

    def _require_client(self, *methods: str) -> Any:
        target = self._client
        if target is None:
            service = self._service
            if service is None:
                raise _Unavailable("B站服务未配置，无法访问B站")
            if getattr(service, "available", None) is False:
                raise _Unavailable(_dormant_reason(service))
            target = getattr(service, "client", None) or service
        for method in methods:
            if not callable(getattr(target, method, None)):
                raise _Unavailable(f"B站客户端缺少 {method} 能力（客户端未更新或未配置）")
        return target

    def _require_video_service(self) -> Any:
        if self._video_service is None:
            raise _Unavailable("视频解析服务未配置，暂时不能看视频")
        return self._video_service

    def _read(self) -> Any:
        """只读扩展：优先用注入实例，否则按当前客户端懒加载。"""
        if self._read_api is not None:
            return self._read_api
        # 延迟导入：skills 与 bilibili 包在模块级互相依赖。
        from neobot_app.bilibili.read_api import BilibiliReadApi

        return BilibiliReadApi(self._require_client())
