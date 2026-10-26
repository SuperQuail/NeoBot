"""部署状态、OneBot 连接与 .env 管理接口。"""

from __future__ import annotations

import secrets
from typing import Any

from aiohttp import web

from ..config_manager import ConfigConflictError, ConfigValidationError
from ._common import (
    _as_text,
    _deploy_field_defaults,
    _detect_lan_host,
    _json_ok,
    _json_error,
    _env_reload_message,
)


class DeployMixin:
    # ── 快捷部署（新手引导）──────────────────────────────────────────

    async def deploy_status(self, request: web.Request) -> web.Response:
        """快捷部署菜单：还差哪几项、以及 OneBot 连接所需的一切（只读）。

        新手只需要配少数几项就能把 Bot 跑起来，这个端点把「必须项」逐条判出
        done/缺失，并把反向 WS 的**生效**监听信息一并给出 —— NapCat 侧要填的
        就是地址与 access token 这两样。

        注：OneBot 反向 WS 的**路径由框架侧自己配**，服务端不限制（见
        `neobot_adapter/onebot/receiver/core.py`），NapCat 常用 `/onebot/v11/ws`。
        """
        denied = self._require_manage(request, action="查看部署状态")
        if denied is not None:
            return denied
        try:
            config_obj = self._config_proxy()
        except Exception as exc:
            return _json_error(f"读取配置失败: {exc}", status=500)

        bot = getattr(config_obj, "bot", None)
        chat = getattr(config_obj, "chat", None)
        account = _as_text(getattr(bot, "account", ""))
        nick_name = _as_text(getattr(bot, "nick_name", ""))
        persona = _as_text(getattr(bot, "bot_data", ""))
        aliases = [
            str(item).strip()
            for item in (getattr(bot, "alias_name", None) or [])
            if str(item).strip()
        ]
        admins = [
            str(item).strip()
            for item in (getattr(chat, "admin_accounts", None) or [])
            if str(item).strip()
        ]
        try:
            group_chat_chance = float(getattr(chat, "group_chat_chance", 0.3) or 0.0)
        except (TypeError, ValueError):
            group_chat_chance = 0.3
        # 出厂占位不算「配好了」：`account` 默认是 '0'、昵称与人设都是示例文案。
        # 用 schema 默认值现算而不是写死字面量 —— 默认值以后改了这里自动跟上。
        defaults = _deploy_field_defaults()
        account_ready = bool(account) and account.casefold() != defaults["bot_account"].casefold()
        nick_ready = bool(nick_name) and nick_name.casefold() != defaults["bot_nick_name"].casefold()
        persona_ready = bool(persona) and persona.casefold() != defaults["bot_data"].casefold()

        env_revision = None
        deepseek_ready = False
        try:
            env_document = self._env_manager().read(mask=True)
            env_revision = env_document.get("revision")
            for item in env_document.get("items") or []:
                key = str(item.get("key") or "")
                if key.casefold().startswith("deepseek_") and key.casefold().endswith("apikey"):
                    deepseek_ready = bool(item.get("has_value"))
        except Exception as exc:
            self.logger.warning(f"读取 .env 失败: {exc}")

        onebot = self._onebot_connection()
        steps = [
            {
                "key": "bot_identity",
                "label": "机器人身份",
                "required": True,
                "done": bool(account_ready and nick_ready),
                "hint": "机器人 QQ 号与昵称都是必填：面板「机器人」页、命令与落盘都用它",
                "action": "identity",
            },
            {
                "key": "persona",
                "label": "人设",
                "required": True,
                "done": persona_ready,
                "hint": "写清「你是谁、怎么说话、有什么规矩」——它插进系统提示词（{bot_data}）",
                "action": "persona",
            },
            {
                "key": "platform_key",
                "label": "平台密钥",
                "required": True,
                "done": deepseek_ready,
                "hint": "至少填 DeepSeek_APIKey —— 默认模型库全部走 DeepSeek",
                "action": "platform_key",
            },
            {
                "key": "onebot",
                "label": "OneBot 连接",
                "required": True,
                "done": bool(onebot["port"]) and bool(onebot["token"]),
                "hint": "配好监听端口与 access token，再把下面两样填进 NapCat",
                "action": "onebot",
            },
            {
                "key": "admin",
                "label": "超级管理员（选填）",
                "required": False,
                "done": bool(admins),
                "hint": "填一个 QQ 号用于接收余额不足等系统通知；留空也能正常跑，只是收不到通知",
                "action": "admin",
            },
        ]
        return _json_ok(
            {
                "steps": steps,
                "onebot": onebot,
                "values": {
                    "bot_account": account,
                    "bot_nick_name": nick_name,
                    "bot_data": persona,
                    "alias_name": aliases,
                    "admin_accounts": admins,
                    "group_chat_chance": group_chat_chance,
                },
                "defaults": defaults,
                "revision": self._config_manager().revision(),
                "env_revision": env_revision,
                "ready": all(step["done"] for step in steps if step["required"]),
            }
        )

    def _onebot_connection(self) -> dict[str, Any]:
        """反向 WS 的生效监听信息（配置 > 环境变量 > 默认值）。

        复用 adapter 包的 `ReverseWsSettings.resolve`，不在这里重写一套解析规则 ——
        面板显示的必须是**真正会监听的**地址与 token，否则 NapCat 那边连不上。
        """
        from neobot_adapter.onebot.receiver.settings import ReverseWsSettings

        config_obj = self._config_proxy()
        adapter = getattr(config_obj, "adapter", None)
        raw_port = int(getattr(adapter, "reverse_ws_port", 0) or 0)
        settings = ReverseWsSettings.resolve(
            host=str(getattr(adapter, "reverse_ws_host", "") or "") or None,
            port=raw_port or None,
            access_token=str(getattr(adapter, "reverse_ws_access_token", "") or ""),
        )
        port = int(settings.port)
        # 监听 0.0.0.0 时「连哪个地址」要分开给：NapCat 与本程序同机用回环，
        # 不同机用局域网地址 —— 直接给 0.0.0.0 是连不上的。
        bind_all = settings.host in {"0.0.0.0", "::", ""}
        return {
            "host": settings.host,
            "port": port,
            "token": settings.access_token,
            "token_enabled": settings.token_enabled,
            "bind_all": bind_all,
            "url_local": f"ws://127.0.0.1:{port}",
            "url_lan": f"ws://{_detect_lan_host()}:{port}",
            # 路径由框架侧自己配、服务端不校验；这里给仓库文档（08-部署说明 §4.2）用的惯例写法
            "path_hint": "/onebot",
            "warning": settings.security_warning(),
            "from_config": raw_port > 0,
            # 预留：装了 NapCat Desktop 之后由它直接创建连接（端口与 token 自动生成并回填）。
            # 现在只报「不可用 + 原因」，前端据此显示「自动连接（待支持）」而不是假装能用。
            "auto_connect": {
                "available": False,
                "reason": (
                    "自动创建连接需要 NapCat Desktop 支持（后续版本提供）；"
                    "在此之前请手动把下面的地址与 token 填进 NapCat 的反向 WS"
                ),
            },
        }

    async def deploy_generate_token(self, request: web.Request) -> web.Response:
        """生成一个 OneBot access token 并写入 `[adapter]`（NapCat 侧填同一个值）。"""
        denied = self._require_manage(request, action="生成 OneBot token")
        if denied is not None:
            return denied
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))

        token = secrets.token_urlsafe(24)
        manager = self._config_manager()
        try:
            document = manager.save(
                config={"adapter": {"reverse_ws_access_token": token}},
                expected_revision=payload.get("revision"),
            )
        except ConfigConflictError as exc:
            return _json_error(str(exc), status=409)
        except ConfigValidationError as exc:
            return _json_error(str(exc), status=400, errors=exc.errors)
        except Exception as exc:
            return _json_error(f"保存 access token 失败: {exc}", status=500)

        # adapter 是 AdapterSupervisor 的热重载路径：这一步会让它按新 token 重连，
        # 不需要重启进程（失败也不回滚配置，只是提示需要重启）。
        reload_result = await self._reload_config(extra_changed_paths=("adapter",))
        applied = bool(reload_result.get("ok"))
        document["token"] = token
        document["applied"] = applied
        document["message"] = (
            "已生成并写入 access token；请把它填进 NapCat 的反向 WS 配置"
            if applied
            else "access token 已写入配置，但适配器重载失败，需重启 NeoBot 后生效"
        )
        document["can_manage"] = self.console.manage_plugins
        return _json_ok(document)


    async def env_get(self, request: web.Request) -> web.Response:
        try:
            document = self._env_manager().read(mask=True)
        except Exception as exc:
            return _json_error(f"读取 .env 失败: {exc}", status=500)
        document["can_manage"] = self.console.manage_plugins
        return _json_ok(document)

    async def env_platform_add(self, request: web.Request) -> web.Response:
        """一键添加 API 供应商：写入 <平台名>_URL / <平台名>_APIKey（Key 只写不读）。"""
        denied = self._require_manage(request, action="添加 API 供应商")
        if denied is not None:
            return denied
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        manager = self._env_manager()
        try:
            document = manager.add_platform(
                name=str(payload.get("name") or ""),
                url=str(payload.get("url") or ""),
                api_key=str(payload.get("api_key") or payload.get("apiKey") or ""),
                expected_revision=payload.get("revision"),
            )
        except ConfigConflictError as exc:
            return _json_error(str(exc), status=409)
        except ConfigValidationError as exc:
            return _json_error(str(exc), status=400, errors=exc.errors)
        except Exception as exc:
            return _json_error(f"添加供应商失败: {exc}", status=500)
        self.logger.info(
            f"面板添加 API 供应商 ip={self.console.request_ip(request)} name={payload.get('name')}"
        )
        document["can_manage"] = self.console.manage_plugins
        document["message"] = "供应商已写入 .env（API Key 只写不读，可在模型库中引用该平台）"
        if payload.get("reload"):
            reload_result = await self._reload_config()
            document["applied"] = bool(reload_result.get("ok"))
            document["message"] = str(reload_result.get("message") or document["message"])
        return _json_ok(document)

    async def env_save(self, request: web.Request) -> web.Response:
        denied = self._require_manage(request)
        if denied is not None:
            return denied
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        manager = self._env_manager()
        try:
            document = manager.save(
                updates=payload.get("updates") or {},
                deletes=payload.get("deletes") or [],
                expected_revision=payload.get("revision"),
            )
        except ConfigConflictError as exc:
            return _json_error(str(exc), status=409)
        except ConfigValidationError as exc:
            return _json_error(str(exc), status=400, errors=exc.errors)
        except Exception as exc:
            return _json_error(f"保存 .env 失败: {exc}", status=500)
        document["can_manage"] = self.console.manage_plugins
        env_written = bool(payload.get("updates") or payload.get("deletes"))
        document["message"] = "环境变量已保存；模型注册表需重载后生效"
        if payload.get("reload"):
            reload_result = await self._reload_config(
                # 显式声明 env 变更：.env 不进 config.toml 的配置快照，不带这条路径
                # 的话 provider 消费者不会被触发，新凭据要等重启才生效（issue #74）。
                extra_changed_paths=("env",) if env_written else (),
            )
            document["applied"] = bool(reload_result.get("ok"))
            message, needs_restart = _env_reload_message(reload_result, env_written)
            document["message"] = message
            document["needs_restart"] = needs_restart
            if reload_result.get("hot_reload"):
                document["hot_reload"] = reload_result["hot_reload"]
        return _json_ok(document)
