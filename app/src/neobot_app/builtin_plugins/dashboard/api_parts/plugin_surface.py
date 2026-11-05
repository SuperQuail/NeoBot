"""统一 SDK 的面板入口，身份与权限只从已鉴权的宿主会话获取。"""

from __future__ import annotations

import asyncio

from aiohttp import web

from neobot_modloader.sdk.actions import ActionError, ActionInvocation

from ._common import _json_error, _json_ok

_ERROR_STATUS = {
    "permission_denied": 403,
    "action_not_found": 404,
    "plugin_not_found": 404,
    "plugin_not_ready": 409,
    "plugin_busy": 409,
    "invalid_input": 400,
    "invalid_invocation": 403,
    "contract_invalid": 422,
    "invalid_output": 500,
    "action_failed": 500,
}


def _failure(error: ActionError) -> web.Response:
    return _json_error(error.message, status=_ERROR_STATUS.get(error.code, 400), code=error.code, fields=error.fields)


class PluginSurfaceMixin:
    def _surface_permissions(self, request: web.Request) -> frozenset[str]:
        permissions = {"read", "operate"}
        if self._can_manage(request):
            permissions.add("manage")
        return frozenset(permissions)

    async def plugin_surface_get(self, request: web.Request) -> web.Response:
        control = self._plugin_control()
        getter = getattr(control, "surface", None)
        if not callable(getter):
            return _json_ok(contract=None, available=False, state="unavailable", permissions=[], source="none")
        try:
            result = getter(request.match_info["name"])
        except ActionError as exc:
            return _failure(exc)
        except Exception:
            return _json_error("插件契约读取失败", status=500)
        return _json_ok(result, permissions=sorted(self._surface_permissions(request)))

    async def plugin_action_call(self, request: web.Request) -> web.Response:
        control = self._plugin_control()
        invoke = getattr(control, "invoke_action", None)
        if not callable(invoke):
            return _json_error("插件运行时不可用", status=503)
        try:
            payload = await self._read_json(request)
        except ValueError:
            return _json_error("动作请求必须是有效 JSON 对象", status=400)
        invocation = ActionInvocation("dashboard", self._surface_permissions(request))
        try:
            async with asyncio.timeout(30):
                result = await invoke(
                    request.match_info["name"], request.match_info["action"], payload.get("values", {}), invocation
                )
        except ActionError as exc:
            return _failure(exc)
        except TimeoutError:
            return _json_error("插件动作执行超时", status=504, code="action_timeout")
        except Exception:
            return _json_error("插件动作执行失败", status=500, code="action_failed")
        return _json_ok(result=result)
