"""面板接口共用的模块级辅助函数与常量。"""

from __future__ import annotations

import json
import socket
from typing import Any, Mapping

from aiohttp import web


def _pydantic_errors(exc: Any, *, include_messages: bool = True, model: Any = None) -> list[dict[str, str]]:
    """把 pydantic 校验错误转换为面板统一的 {path, message} 列表。"""
    if not include_messages:
        from neobot_modloader.sdk.actions import validation_error_fields

        return [
            {"path": ".".join(str(part) for part in item["path"]) or "config", "message": "字段值不符合配置要求"}
            for item in validation_error_fields(exc, model)
        ] or [{"path": "config", "message": "配置校验失败"}]
    errors: list[dict[str, str]] = []
    raw = getattr(exc, "errors", None)
    if callable(raw):
        try:
            for item in raw():
                location = item.get("loc") or ()
                errors.append(
                    {
                        "path": ".".join(str(part) for part in location) or "config",
                        "message": str(item.get("msg") or "取值非法"),
                    }
                )
        except Exception:
            errors = []
    if not errors:
        errors.append({"path": "config", "message": str(exc)})
    return errors


def _as_text(value: Any) -> str:
    """把配置值转成可比较的文本。

    不能写成 `x or ""` —— `bot.account` 是 **int**，默认值 `0` 是假值，
    一 `or` 就变成空串，「出厂占位 0」与「未填」就分不出来了。
    """
    return "" if value is None else str(value).strip()


def _append_model_reload_hint(message: str, changes: Mapping[str, Any]) -> tuple[str, list[str]]:
    """模型 / 凭据变更后追加「仍需重启」提示；返回 (文案, 未覆盖部分)。

    为什么必须补这一句：`models` / `env` 在热重载分类表里被**整体**标成可热重载
    （provider 消费者登记的规则），于是 `diff_snapshot` 的 `needs_restart_count` 恒为 0 ——
    面板只会说「0 项需重启」，而实际仍有组件在用启动期的 provider（issue #75）。
    缺口清单在 `runtime/provider_reload.MODEL_RELOAD_GAPS`：补一个删一条。
    """
    from neobot_app.runtime.provider_reload import (
        MODEL_RELOAD_GAPS,
        model_reload_restart_hint,
    )

    if not MODEL_RELOAD_GAPS:
        return message, []
    groups = {str(path).split(".", 1)[0] for path in changes}
    if not groups & {"models", "env"}:
        return message, []
    return message + model_reload_restart_hint(), list(MODEL_RELOAD_GAPS)


def _deploy_field_defaults() -> dict[str, str]:
    """快捷部署判定用的**出厂默认值**（现算，不写死字面量）。

    出厂配置里 `bot.account` 是 `'0'`、昵称与人设都是示例文案 —— 这些「假数据」
    让「没配」和「配了」在配置值上长得一样。向导据此把它们判成未配置；
    默认值以后改了这里自动跟上（不写死字面量就是为了这个）。
    """
    try:
        from neobot_app.config.schemas.bot import BotConfig as _BotConfigSchema

        bot = _BotConfigSchema().bot
        return {
            "bot_account": _as_text(getattr(bot, "account", "")),
            "bot_nick_name": _as_text(getattr(bot, "nick_name", "")),
            "bot_data": _as_text(getattr(bot, "bot_data", "")),
        }
    except Exception:
        return {"bot_account": "", "bot_nick_name": "", "bot_data": ""}


def _detect_lan_host() -> str:
    """猜一个「局域网内其他机器连得上本机」的地址（拿不到就回环）。

    做法是向一个公网地址开 UDP socket、看内核选了哪张网卡 —— **不实际发包**，
    也不需要外网可达。失败时回落到 127.0.0.1：宁可让用户自己改，
    也不要给他一个连不上的地址（NapCat 那边只会看到「连接失败」）。
    """
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.2)
        sock.connect(("223.5.5.5", 80))
        return str(sock.getsockname()[0]) or "127.0.0.1"
    except Exception:
        return "127.0.0.1"
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass


def _json_ok(data: Any = None, **extra: Any) -> web.Response:
    payload: dict[str, Any] = {"ok": True}
    if isinstance(data, dict):
        payload.update(data)
    elif data is not None:
        payload["data"] = data
    payload.update(extra)
    return web.json_response(payload)


def _json_error(message: str, *, status: int = 400, **extra: Any) -> web.Response:
    payload = {"ok": False, "error": str(message)}
    payload.update(extra)
    return web.json_response(payload, status=status)


#: 保存 .env 后仍然必须重启才能生效的部分：这些模块在启动时构建并持有 provider，
#: 没有注册热重载消费者（ProviderReloadConsumer 只覆盖 reply / image_parse / archive）。
ENV_RESTART_HINT = "在启动时读取环境变量的其它模块（TTS、生图、联网搜索等）需重启进程后生效"


def _env_reload_message(reload_result: dict[str, Any], env_written: bool) -> tuple[str, bool]:
    """组合「保存 .env 并重载」后的提示文案；返回 (文案, 是否仍需重启)。

    为什么要单独写文案：环境变量不进 config.toml 的配置快照，重载自身的分支是
    「配置已重载，本次没有检测到配置项变化」—— 对刚改完 Key 的用户来说，
    这句话既像成功又像什么都没发生，正是 issue #74 的误导来源。
    """
    if not env_written:
        return "未检测到环境变量改动；已重载配置。", False

    report = reload_result.get("hot_reload") or {}
    applied = [str(item.get("name") or "") for item in report.get("applied") or []]
    failed = list(report.get("failed") or [])

    if failed:
        reasons = "；".join(str(item.get("error") or item.get("name") or "未知原因") for item in failed)
        head = f"环境变量已保存并重载，但部分组件重建失败（{reasons}），仍在用旧凭据。"
    elif "provider" in applied:
        head = "环境变量已保存并重载：平台凭据变更已重建 provider（覆盖 主对话 / 视觉 / 档案总结）。"
    else:
        head = "环境变量已保存并重载。"

    return f"{head}{ENV_RESTART_HINT}。", True


def _parse_cost_detail(raw: Any) -> dict[str, Any] | None:
    """把 cost_detail 的单行 JSON 解析回 {components, note}（解析失败返回原始文本）。"""
    if raw is None:
        return None
    text = str(raw)
    if not text.strip():
        return None
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return {"raw": text}
    return parsed if isinstance(parsed, dict) else {"raw": text}


def _redact_prompt_report(report: dict[str, Any]) -> dict[str, Any]:
    """非管理会话只保留统计：系统提示词原文与工具 schema 不整段外发。"""
    redacted = dict(report)
    agents: list[dict[str, Any]] = []
    for entry in report.get("agents", []):
        if not isinstance(entry, dict):
            continue
        item = dict(entry)
        parts: list[dict[str, Any]] = []
        for part in item.get("parts", []):
            if isinstance(part, dict):
                parts.append({**part, "text": "", "redacted": True})
        item["parts"] = parts
        item["text_redacted"] = True
        agents.append(item)
    redacted["agents"] = agents
    return redacted


_SCHEDULED_ACTION_MESSAGES = {
    "create": "定时任务已创建",
    "update": "定时任务已更新",
    "set_state": "定时任务状态已更新",
    "set_notification_policy": "通知策略已更新",
    "delete": "定时任务已删除",
}


def _prompt_value(store: Any, section: str, path: str) -> str | None:
    """按「分区.键」或「分区.子表.键」读取提示词当前取值。"""
    if not section:
        return None
    parts = [part for part in str(path or "").split(".") if part]
    if len(parts) == 1:
        return store.get(section, parts[0], default="") or None
    if len(parts) == 2:
        sub = store.sub_section(section, parts[0])
        value = sub.get(parts[1])
        return value if isinstance(value, str) and value.strip() else None
    return None


def _status_text(snapshot: Any) -> str:
    if not getattr(snapshot, "enabled", True):
        return "disabled"
    state = str(getattr(snapshot, "state", "") or "")
    if state == "error":
        return "error"
    if state == "running":
        return "loaded"
    if state in {"stopped", "unloaded"}:
        return "unloaded" if getattr(snapshot, "enabled", True) else "disabled"
    return state or "unloaded"


def installed_name(result: Any) -> str:
    return str(getattr(result, "name", "") or "")


def _operation_response(result: Any, success_message: str) -> web.Response:
    conflict = getattr(result, "conflict", None)
    if getattr(result, "ok", False):
        payload: dict[str, Any] = {
            "message": success_message,
            "name": getattr(result, "name", ""),
            "state": getattr(result, "state", None),
            "requires_restart": bool(getattr(result, "requires_restart", False)),
        }
        version = getattr(result, "version", "")
        if version:
            payload["version"] = version
        backup_path = getattr(result, "backup_path", None)
        if backup_path is not None:
            payload["backup_path"] = str(backup_path)
            payload["message"] = f"{success_message}（旧版本已备份到 {backup_path}）"
        if conflict:
            payload["conflict"] = conflict
        return _json_ok(payload)
    # 冲突是「可二选一」的显式状态，用 409 区分于普通参数错误
    return _json_error(
        str(getattr(result, "error", "") or "操作失败"),
        status=409 if conflict else 400,
        name=getattr(result, "name", ""),
        state=getattr(result, "state", None),
        conflict=conflict,
    )
