"""面板鉴权与 B 站扫码登录接口。"""

from __future__ import annotations

from aiohttp import web

from ..bilibili_login import LOGIN_PAGE, LOGIN_SCRIPT
from neobot_app.panel_auth import (
    PasswordPolicyError,
    PasswordRevisionError,
    PasswordVerificationError,
)
from ..security import is_loopback
from ._common import _json_ok, _json_error


class AuthMixin:
    # ------------------------------------------------------------------
    # 鉴权
    # ------------------------------------------------------------------

    async def auth_status(self, request: web.Request) -> web.Response:
        ip = self.console.request_ip(request)
        loopback = is_loopback(ip)
        configured = self.console.passwords.configured
        return _json_ok(
            {
                "authenticated": False,
                "configured": configured,
                "setup_required": not configured,
                "setup_allowed": (not configured) and loopback,
                "loopback": loopback,
                "can_manage": configured
                and self.console.manage_plugins
                and (self.console.allow_remote_manage or loopback),
                "base_path": self.console.base_path,
                "version": self.console.version,
            }
        )

    async def auth_setup(self, request: web.Request) -> web.Response:
        """本机首次设置面板密码（未设置密码时仅回环地址可用）。"""
        ip = self.console.request_ip(request)
        if self.console.passwords.configured:
            return _json_error("面板密码已设置，请直接登录", status=400)
        if not is_loopback(ip):
            return _json_error(
                "只能在本机设置面板密码；外网访问请由超级管理员在 QQ 私聊发送 /set_password 设置",
                status=403,
            )
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        password = str(payload.get("password") or "")
        confirm = str(payload.get("confirm") or "")
        if confirm and confirm != password:
            return _json_error("两次输入的密码不一致")
        try:
            self.console.passwords.set_password(password)
        except PasswordPolicyError as exc:
            return _json_error(str(exc))
        session = self.console.create_session(request)
        response = _json_ok(
            {
                "token": session.token,
                "csrf_token": session.csrf_token,
                "message": "面板密码已设置，登录成功",
                "session": session.to_payload(
                    timeout_seconds=self.console.sessions.timeout_seconds
                ),
            }
        )
        self.console.set_session_cookie(response, session.token)
        self.logger.warning(f"面板密码已设置 ip={ip}")
        return response

    async def auth_me(self, request: web.Request) -> web.Response:
        session = request.get("dashboard_session")
        ip = self.console.request_ip(request)
        return _json_ok(
            {
                "authenticated": True,
                "configured": self.console.passwords.configured,
                "session": session.to_payload(timeout_seconds=self.console.sessions.timeout_seconds)
                if session is not None
                else {},
                "csrf_token": session.csrf_token if session is not None else "",
                "loopback": is_loopback(ip),
                "can_manage": self.console.manage_plugins
                and (self.console.allow_remote_manage or is_loopback(ip)),
                "manage_plugins": self.console.manage_plugins,
                "allow_remote_manage": self.console.allow_remote_manage,
                "base_path": self.console.base_path,
                "version": self.console.version,
            }
        )

    async def auth_login(self, request: web.Request) -> web.Response:
        ip = self.console.request_ip(request)
        locked, remaining = self.console.limiter.is_locked(ip)
        if locked:
            return _json_error(
                f"登录失败次数过多，请在 {remaining} 秒后重试", status=429
            )
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        supplied = str(payload.get("password") or "")
        if not self.console.passwords.configured:
            return _json_error(
                "面板尚未设置密码，请在本机设置或由超级管理员在 QQ 私聊发送 /set_password",
                status=403,
                setup_required=True,
            )
        if not self.console.verify_password(supplied):
            self.console.limiter.record_failure(ip)
            self.logger.warning(f"面板登录失败 ip={ip}")
            return _json_error("密码不正确", status=401)
        self.console.limiter.reset(ip)
        session = self.console.create_session(request)
        response = _json_ok(
            {
                "token": session.token,
                "csrf_token": session.csrf_token,
                "session": session.to_payload(
                    timeout_seconds=self.console.sessions.timeout_seconds
                ),
            }
        )
        self.console.set_session_cookie(response, session.token)
        self.logger.info(f"面板登录成功 ip={ip}")
        return response

    async def auth_logout(self, request: web.Request) -> web.Response:
        session = request.get("dashboard_session")
        if session is not None:
            self.console.sessions.revoke(session.token)
        response = _json_ok({"message": "已退出登录"})
        self.console.clear_session_cookie(response)
        return response

    async def auth_password(self, request: web.Request) -> web.Response:
        """已登录管理员改密；成功后不签发替代会话。"""
        denied = self._require_manage(request, action="修改面板密码")
        if denied is not None:
            return denied
        session = request.get("dashboard_session")
        if session is None:
            return _json_error("需要登录", status=401)
        ip = self.console.request_ip(request)
        locked, remaining = self.console.limiter.is_locked(ip)
        if locked:
            return _json_error(f"密码校验失败次数过多，请在 {remaining} 秒后重试", status=429)
        try:
            payload = await self._read_json(request)
        except ValueError:
            return _json_error("请求体必须是有效 JSON 对象")
        current = payload.get("current_password")
        new = payload.get("new_password")
        confirm = payload.get("confirm")
        if not all(isinstance(value, str) for value in (current, new, confirm)):
            return _json_error("当前密码、新密码和确认密码均须为字符串")
        if new != confirm:
            return _json_error("两次输入的新密码不一致")
        try:
            self.console.passwords.change_password(current, new, expected_revision=session.password_revision)
        except PasswordPolicyError as exc:
            return _json_error(str(exc))
        except PasswordVerificationError:
            self.console.limiter.record_failure(ip)
            self.logger.warning(f"面板改密校验失败 ip={ip}")
            return _json_error("当前密码不正确", status=403)
        except PasswordRevisionError:
            self.console.sessions.revoke(session.token)
            response = _json_error("登录已失效，请重新登录", status=401)
            self.console.clear_session_cookie(response)
            return response
        except OSError:
            self.logger.error(f"面板密码写入失败 ip={ip}")
            return _json_error("密码保存失败，请稍后重试", status=500)
        self.console.sessions.revoke_all()
        self.console.limiter.reset(ip)
        response = _json_ok({"reauthenticate": True, "message": "密码已修改，请重新登录"})
        self.console.clear_session_cookie(response)
        self.logger.warning(f"面板密码已修改，全部会话已撤销 ip={ip}")
        return response

    # ------------------------------------------------------------------
    # B站扫码登录
    # ------------------------------------------------------------------

    def _require_bilibili_login(self, request: web.Request) -> web.Response | None:
        if not self.console.allow_remote_manage and not is_loopback(
            self.console.request_ip(request)
        ):
            return _json_error(
                "B站扫码登录默认只允许本机操作"
                "（dashboard.allow_remote_manage=false）",
                status=403,
            )
        return None

    async def bilibili_login_page(self, request: web.Request) -> web.Response:
        return web.Response(
            text=LOGIN_PAGE,
            content_type="text/html",
            headers={"Cache-Control": "no-store"},
        )

    async def bilibili_login_script(self, request: web.Request) -> web.Response:
        return web.Response(
            text=LOGIN_SCRIPT,
            content_type="application/javascript",
            headers={"Cache-Control": "no-store"},
        )

    async def bilibili_login_status(self, request: web.Request) -> web.Response:
        blocked = self._require_bilibili_login(request)
        if blocked is not None:
            return blocked
        service = self._service("bilibili_service")
        refresh = getattr(service, "refresh", None)
        if callable(refresh):
            try:
                await refresh()
            except Exception as exc:
                # 自愈失败不挡读状态：snapshot 里仍有上次结论与 error 文案。
                self.logger.warning(f"B站登录态自愈刷新失败: {exc}")
        return _json_ok(self.console.bilibili_login.snapshot())

    async def bilibili_login_start(self, request: web.Request) -> web.Response:
        blocked = self._require_bilibili_login(request)
        if blocked is not None:
            return blocked
        try:
            snapshot = await self.console.bilibili_login.start()
        except RuntimeError as exc:
            return _json_error(str(exc), status=503)
        return _json_ok(snapshot)
