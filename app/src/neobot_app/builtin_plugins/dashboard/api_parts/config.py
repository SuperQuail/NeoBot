"""插件配置与机器人配置读写接口。"""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import web

from ..config_manager import (
    BotConfigManager,
    ConfigConflictError,
    ConfigValidationError,
    EnvFileManager,
    describe_pydantic_model,
)
from ..plugin_config import PluginConfigConflictError, PluginConfigError
from ..config_parts.normalize import normalize_config_values
from ._common import _pydantic_errors, _append_model_reload_hint, _json_ok, _json_error


class ConfigMixin:
    async def plugin_config_get(self, request: web.Request) -> web.Response:
        """插件配置：读取插件数据目录下的 config.toml（官方/第三方同一路径）。"""
        control = self._plugin_control()
        if control is None:
            return _json_error("插件运行时不可用", status=503)
        name = request.match_info["name"]
        snapshot = self._find_snapshot(control, name)
        try:
            editor = self._plugin_config_editor(control, name)
            if editor is None:
                return _json_error(f"插件不存在或没有独立数据目录: {name}", status=404)
            document = editor.read()
        except PluginConfigError as exc:
            return _json_error(str(exc), status=400)
        model = control.config_model(name)
        schema = describe_pydantic_model(model, document.get("config") or {})
        if schema:
            # 插件声明了 pydantic 模型时以模型为准（带范围/标题/说明）；
            # 模型没写 description 的字段用 plugin.toml 的注释兜底
            document["schema"] = self._with_field_comments(schema, self._plugin_field_comments(control, name))
            document["form_supported"] = True
        return _json_ok(self._plugin_config_meta(snapshot, name, document))

    async def plugin_config_save(self, request: web.Request) -> web.Response:
        """插件配置：写入插件数据目录下的 config.toml，可选立即重载插件。"""
        denied = self._require_manage(request)
        if denied is not None:
            return denied
        control = self._plugin_control()
        if control is None:
            return _json_error("插件运行时不可用", status=503)
        name = request.match_info["name"]
        snapshot = self._find_snapshot(control, name)
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        try:
            editor = self._plugin_config_editor(control, name)
        except PluginConfigError as exc:
            return _json_error(str(exc), status=400)
        if editor is None:
            return _json_error(f"插件不存在或没有独立数据目录: {name}", status=404)
        values = payload.get("config")
        if not isinstance(values, dict):
            values = payload.get("values")
        model = control.config_model(name)
        if model is not None and isinstance(values, dict):
            values = editor.prepare_values(values)
            defaults: dict[str, Any] = {}
            getter = getattr(control, "plugin_config_defaults", None)
            if callable(getter):
                try:
                    defaults = dict(getter(name))
                except Exception:
                    defaults = {}
            try:
                validated = model.model_validate({**defaults, **values})
            except Exception as exc:
                # 已恢复的只写字段可能出现在作者校验器错误中，只返回位置，不能回显异常正文。
                return _json_error(
                    "插件配置校验失败", status=400, errors=_pydantic_errors(exc, include_messages=False, model=model)
                )
            # 校验通过的值按模型声明的类型回填（"9981" -> 9981，list 也不再是字符串），
            # 提交里有的键才回填：未知键原样保留。否则 TOML 里会落下字符串，
            # 插件读到的类型与声明的对不上（静默漂移）。
            values = normalize_config_values(values, validated)
        # 保存前的生效配置：用于判断哪些改动可以在运行期原地生效（不重载插件）
        before_values = self._plugin_config_values(control, name)
        try:
            document = editor.save(
                config=values if isinstance(values, dict) else None,
                source=payload.get("source"),
                expected_revision=payload.get("revision"),
            )
        except PluginConfigConflictError as exc:
            return _json_error(str(exc), status=409)
        except PluginConfigError as exc:
            return _json_error(str(exc), status=400)
        schema = describe_pydantic_model(model, document.get("config") or {})
        if schema:
            document["schema"] = self._with_field_comments(schema, self._plugin_field_comments(control, name))
        applied = False
        message = "配置已保存到插件数据目录"
        reload_requested = bool(payload.get("reload"))
        consumer = self._plugin_config_consumer(control, name)
        if reload_requested and consumer is not None:
            # ① 原地生效（bugfixes/feat(2) §6）：把运行期安全的字段直接喂给插件，
            #    不重载插件本体 —— HTTP 服务不中断、当前保存请求正常返回、内存指标不重置。
            applied, message, changes = await self._apply_plugin_config_in_place(
                name, consumer, before=before_values, control=control
            )
            if changes is not None:
                document["changes"] = changes
        elif reload_requested:
            if bool(getattr(snapshot, "config_hot_reload", True)):
                outcome = await control.reload(name)
                applied = outcome.ok
                message = (
                    f"配置已保存并重载 {name}"
                    if outcome.ok
                    else f"配置已保存，但重载失败: {outcome.error or outcome.state}"
                )
            else:
                message += "；该插件配置需要重启 NeoBot 才能生效"
        # 注意顺序：_plugin_config_meta 会写入一条**通用**说明，必须先在它之后再覆盖
        # applied / message，否则插件配置保存后的「已生效 / 需重启」提示会被通用文案吞掉。
        payload = self._plugin_config_meta(snapshot, name, document)
        payload["applied"] = applied
        payload["message"] = message
        return _json_ok(payload)

    @staticmethod
    def _plugin_config_values(control: Any, name: str) -> dict[str, Any]:
        """插件当前生效的原始配置（打包默认值 + 数据目录里保存的值）。"""
        getter = getattr(control, "plugin_config_values", None)
        if not callable(getter):
            return {}
        try:
            values = getter(name)
        except Exception:
            return {}
        return dict(values) if isinstance(values, dict) else {}

    @staticmethod
    def _plugin_config_consumer(control: Any, name: str) -> Any | None:
        """插件声明的「配置原地生效」消费者；未声明时返回 None（维持原有重启语义）。"""
        getter = getattr(control, "config_consumer", None)
        if not callable(getter):
            return None
        try:
            return getter(name)
        except Exception:
            return None

    async def _apply_plugin_config_in_place(
        self,
        name: str,
        consumer: Any,
        *,
        before: dict[str, Any],
        control: Any,
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """把插件配置里「运行期安全」的改动原地生效，返回 (是否已生效, 提示文案, 改动明细)。"""
        from neobot_app.runtime.plugin_config_reload import (
            apply_plugin_config_change,
            diff_summary,
        )

        after = self._plugin_config_values(control, name)
        try:
            result = await apply_plugin_config_change(consumer, plugin_name=name, before=before, after=after)
        except Exception as exc:
            self.logger.error(f"插件配置原地生效失败: {name}", error=str(exc))
            return False, f"配置已保存，但立即生效失败（已保留原配置）: {exc}", None

        changes = diff_summary(result.changes) if result.changes else None
        restart_note = f"；另有 {len(result.needs_restart)} 项需重启 NeoBot 才能生效" if result.needs_restart else ""
        if result.error:
            self.logger.error(f"插件配置原地生效失败: {name}", error=result.error)
            return (
                False,
                f"配置已保存，但立即生效失败（已保留原配置）: {result.error}{restart_note}",
                changes,
            )
        if result.ok:
            self.logger.info(
                f"插件配置已原地生效: {name}",
                applied=list(result.applied),
                needs_restart=list(result.needs_restart),
            )
            return (
                True,
                f"配置已保存并已生效（{len(result.applied)} 项立即生效，无需重启）{restart_note}",
                changes,
            )
        if result.needs_restart:
            return False, f"配置已保存；该插件配置需要重启 NeoBot 才能生效{restart_note}", changes
        return False, "配置已保存（本次没有检测到配置项变化）", changes

    # ------------------------------------------------------------------
    # 本体配置 / .env
    # ------------------------------------------------------------------

    def _config_manager(self) -> BotConfigManager:
        return self.console.config_manager

    def _env_manager(self) -> EnvFileManager:
        return self.console.env_manager

    async def config_get(self, request: web.Request) -> web.Response:
        try:
            document = self._config_manager().read()
        except ConfigValidationError as exc:
            return _json_error(str(exc), status=400, errors=exc.errors)
        except Exception as exc:
            return _json_error(f"读取配置失败: {exc}", status=500)
        document["can_manage"] = self.console.manage_plugins
        if not self._can_manage(request):
            # config.toml 里也有机密（adapter.local_auth_token /
            # adapter.reverse_ws_access_token）。结构化 config/schema 已按字段掩码，
            # 但原文与 raw 副本同样带明文，只读会话不得获取——与 .env 侧
            # 「密钥只回是否已设置」的约定保持一致。
            document["source"] = ""
            document["raw"] = {}
            document["secrets_hidden"] = True
        return _json_ok(document)

    async def config_save(self, request: web.Request) -> web.Response:
        denied = self._require_manage(request)
        if denied is not None:
            return denied
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        manager = self._config_manager()
        try:
            document = manager.save(
                source=payload.get("source"),
                config=payload.get("config"),
                expected_revision=payload.get("revision"),
            )
        except ConfigConflictError as exc:
            return _json_error(str(exc), status=409)
        except ConfigValidationError as exc:
            return _json_error(str(exc), status=400, errors=exc.errors)
        except Exception as exc:
            return _json_error(f"保存配置失败: {exc}", status=500)
        applied = False
        message = "配置已保存"
        if payload.get("reload"):
            reload_result = await self._reload_config(with_changes=True)
            applied = bool(reload_result.get("ok"))
            message = str(reload_result.get("message") or message)
            if reload_result.get("changes"):
                document["changes"] = reload_result["changes"]
        document["can_manage"] = self.console.manage_plugins
        document["applied"] = applied
        document["message"] = message
        return _json_ok(document)

    async def config_validate(self, request: web.Request) -> web.Response:
        try:
            payload = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        errors = self._config_manager().validate(source=payload.get("source"), config=payload.get("config"))
        if errors:
            return _json_error("配置校验未通过", status=400, errors=errors)
        return _json_ok({"message": "配置校验通过", "errors": []})

    async def config_reload(self, request: web.Request) -> web.Response:
        """不重启进程的热重载：重载配置并返回「已生效 / 需重启」明细。"""
        denied = self._require_manage(request)
        if denied is not None:
            return denied
        result = await self._reload_config(with_changes=True)
        if result.get("ok"):
            return _json_ok(result)
        return _json_error(str(result.get("message") or "重载失败"), status=500)

    async def _reload_config(
        self, *, with_changes: bool = False, extra_changed_paths: tuple[str, ...] = ()
    ) -> dict[str, Any]:
        """重载配置并返回结果。

        `extra_changed_paths`：**配置快照之外**的改动路径（目前只有 `.env`）。
        `.env` 的值不进 config.toml，配置 diff 里永远看不到它，所以要由调用方
        显式声明，否则热重载消费者一个都不会被触发（issue #74）。
        """
        from neobot_app.config.hot_reload import diff_snapshot, snapshot, summarize_changes

        extra_paths = tuple(str(item) for item in extra_changed_paths if str(item))
        before: dict[str, Any] | None = None
        if with_changes:
            config_obj = self._models_config()
            if config_obj is not None:
                try:
                    before = snapshot(config_obj)
                except Exception:
                    before = None

        commands = self._service("host_commands")
        caller = getattr(commands, "call", None) if commands is not None else None
        if not callable(caller):
            return {"ok": False, "message": "配置重载入口不可用，请重启 NeoBot"}
        try:
            # 只在真的要声明时带参：宿主命令注册表的**实现**未必接受 `**kwargs`
            # （协议上允许，但既有实现是 `call(self, name)`）。不为一个只在 env 场景用到的
            # 参数去改外部调用契约 —— 保持 `config.reload` 的调用形态不变。
            if extra_paths:
                result = caller("config.reload", extra_changed_paths=extra_paths)
            else:
                result = caller("config.reload")
            if asyncio.iscoroutine(result):
                result = await result
        except Exception as exc:
            return {"ok": False, "message": f"配置重载失败: {exc}"}
        if not isinstance(result, dict):
            return {"ok": False, "message": "配置重载返回异常"}
        ok = str(result.get("status") or "").lower() == "ok"
        payload: dict[str, Any] = {"ok": ok, "message": str(result.get("message") or "")}
        # 透传热重载报告：env 保存要据此说明「哪些组件已按新凭据重建」
        if isinstance(result.get("hot_reload"), dict):
            payload["hot_reload"] = result["hot_reload"]
        if ok and before is not None:
            after = self._models_config()
            if after is not None:
                try:
                    changes = diff_snapshot(before, after)
                    payload["changes"] = summarize_changes(changes)
                    if changes:
                        message, restart_parts = _append_model_reload_hint(
                            f"配置已热重载：{payload['changes']['hot_reload_count']} 项已生效，"
                            f"{payload['changes']['needs_restart_count']} 项需重启",
                            changes,
                        )
                        payload["message"] = message
                        if restart_parts:
                            payload["needs_restart_parts"] = restart_parts
                    elif not extra_paths:
                        # 只有「配置快照里也确实没有变化」时才这么说。改了 .env 的场景
                        # 走不到这里 —— 那句「没有检测到配置项变化」会让用户以为没保存成功。
                        payload["message"] = "配置已重载，本次没有检测到配置项变化"
                except Exception as exc:
                    self.logger.warning(f"配置差异计算失败: {exc}")
        return payload
