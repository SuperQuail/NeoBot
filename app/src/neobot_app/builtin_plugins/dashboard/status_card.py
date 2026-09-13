"""status 图片命令的数据采集与卡片渲染（spec(4) Part D / 4.11.3）。

四个块（**硬编码白名单，不可配置**，spec(4) 4.9 明确不做）：

- 概况：在线状态 / 延迟 / 运行时长 / 今日消息 / 累计消息 / 协议端名与版本
- 用量：近 24h 与近 7d 的金额 CNY、输入 / 输出 / 缓存命中 Token、调用次数
- 插件：名称 / 版本 / 状态
- 错误：近 24h ERROR 条数 + 最近一次异常的时间与模块名

明确排除：QQ 号、昵称、头像、群名好友名、配置值、.env、API Key、提示词、
日志正文、档案与聊天内容、按模型 / 模块 / 会话排行、堆栈、安装路径、repo 地址。

数据来自**进程内服务**（面板插件与本体同进程），不走 HTTP、不需要面板登录；
面板未启动也能出图（spec(4) A59）。
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import time
from collections.abc import Mapping, Sequence
from typing import Any

from neobot_app.runtime.html_card import render_card_html, render_card_image
from neobot_app.utils.logger import get_module_logger

logger = get_module_logger("dashboard.status_card")

#: 四个块的固定顺序与名称（白名单；顺序即缺省渲染顺序）
BLOCK_NAMES: tuple[str, ...] = ("概况", "用量", "插件", "错误")

#: 卡片标题
CARD_TITLE = "NeoBot 运行状态"

#: 渲染不可用时的启用提示（R28 / D25）
FALLBACK_HINT = "安装 playwright 与 chromium 后可发图片"

#: 截图自身的超时（ScreenshotOptions.timeout）
SCREENSHOT_TIMEOUT_SECONDS = 20.0

#: 命令内兜底超时（在截图超时之上再加一层）
COMMAND_TIMEOUT_SECONDS = 25.0

#: 错误块统计窗口
ERROR_WINDOW_SECONDS = 24 * 60 * 60

_PLUGIN_STATE_LABELS = {
    "running": "运行中",
    "loaded": "运行中",
    "error": "异常",
    "disabled": "已停用",
    "stopped": "已停用",
    "unloaded": "未加载",
}


def normalize_blocks(blocks: Sequence[str] | None) -> tuple[str, ...]:
    """规范化块名参数：缺省 = 四块全渲染；去重且保持固定顺序。"""
    if not blocks:
        return BLOCK_NAMES
    requested = {str(block).strip() for block in blocks if str(block).strip()}
    return tuple(name for name in BLOCK_NAMES if name in requested)


def unknown_blocks(blocks: Sequence[str] | None) -> list[str]:
    """返回既不在白名单、也不是空串的块名（用于回明确错误且不截图）。"""
    if not blocks:
        return []
    return [
        str(block).strip()
        for block in blocks
        if str(block).strip() and str(block).strip() not in BLOCK_NAMES
    ]


# ----------------------------------------------------------------------
# 取数基础设施
# ----------------------------------------------------------------------


def _service(ctx: Any, name: str, default: Any = None) -> Any:
    """从进程内宿主服务注册表取服务（插件与面板同进程）。"""
    host = getattr(ctx, "plugin_host", None)
    services = getattr(host, "services", None)
    getter = getattr(services, "get", None)
    if not callable(getter):
        return default
    try:
        value = getter(name, default)
    except Exception:
        return default
    return default if value is None else value


def _plugin_control(ctx: Any) -> Any:
    control = getattr(ctx, "plugin_control", None)
    if control is not None:
        return control
    runtime = _service(ctx, "plugin_runtime")
    return getattr(runtime, "control", None)


def _metrics(console: Any) -> Any:
    return getattr(console, "metrics", None)


def format_duration(seconds: Any) -> str:
    """把秒数格式化为「N 天 N 小时 N 分」；非法输入返回「未知」。"""
    try:
        total = int(float(seconds))
    except (TypeError, ValueError):
        return "未知"
    if total < 0:
        return "未知"
    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    if days:
        return f"{days} 天 {hours} 小时 {minutes} 分"
    if hours:
        return f"{hours} 小时 {minutes} 分"
    return f"{minutes} 分"


def _format_amount(value: Any) -> str:
    try:
        return f"¥{float(value):.6f}"
    except (TypeError, ValueError):
        return "—"


def _format_int(value: Any) -> str:
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return "—"


def _kv(title: str, rows: Sequence[tuple[str, str]]) -> dict[str, Any]:
    return {"kind": "kv", "title": title, "rows": [list(row) for row in rows]}


def _table(title: str, columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> dict[str, Any]:
    return {
        "kind": "table",
        "title": title,
        "columns": [str(column) for column in columns],
        "rows": [[str(cell) for cell in row] for row in rows],
    }


# ----------------------------------------------------------------------
# 各块取数
# ----------------------------------------------------------------------


async def _collect_overview(ctx: Any, console: Any) -> list[dict[str, Any]]:
    online = "未知"
    app_name = "—"
    app_version = "—"
    if console is not None:
        try:
            bot = await console.bot_info()
        except Exception as exc:
            logger.warning(f"读取协议端信息失败: {exc}")
            bot = {}
        if isinstance(bot, dict):
            online = "在线" if bot.get("online") else "离线"
            app_name = str(bot.get("app_name") or "—")
            app_version = str(bot.get("app_version") or "")

    latency = "—"
    today = "—"
    total = "—"
    metrics = _metrics(console)
    if metrics is not None:
        try:
            current = metrics.latency_series().get("current_ms")
            latency = f"{current} ms" if current is not None else "无样本"
        except Exception as exc:
            logger.warning(f"读取延迟失败: {exc}")
        try:
            stats = metrics.message_stats()
            today = _format_int(stats.get("today"))
            total = _format_int(stats.get("total"))
        except Exception as exc:
            logger.warning(f"读取消息统计失败: {exc}")

    uptime = format_duration(getattr(console, "uptime_seconds", None))
    protocol = app_name if not app_version else f"{app_name} {app_version}"
    return [
        _kv(
            "",
            [
                ("在线状态", online),
                ("延迟", latency),
                ("运行时长", uptime),
                ("今日消息", today),
                ("累计消息", total),
                ("协议端", protocol),
            ],
        )
    ]


async def _collect_usage(ctx: Any, console: Any) -> list[dict[str, Any]]:
    session_factory = _service(ctx, "usage_session_factory")
    if session_factory is None:
        return [_kv("", [("用量数据", "不可用")])]
    from neobot_storage.repositories.usage import SqlAlchemyUsageRepository

    parts: list[dict[str, Any]] = []
    for hours, title, bucket in ((24, "近 24 小时", "hour"), (24 * 7, "近 7 天", "day")):
        try:
            cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=hours)
            async with session_factory() as session:
                repo = SqlAlchemyUsageRepository(session)
                points = await repo.series_since(cutoff, bucket=bucket)
        except Exception as exc:
            logger.warning(f"读取用量失败 ({title}): {exc}")
            parts.append(_kv(title, [("用量数据", "不可用")]))
            continue
        calls = sum(int(point.get("calls") or 0) for point in points)
        input_tokens = sum(int(point.get("input_tokens") or 0) for point in points)
        output_tokens = sum(int(point.get("output_tokens") or 0) for point in points)
        cache_tokens = sum(int(point.get("cache_hit_tokens") or 0) for point in points)
        cost = sum(float(point.get("cost_cny") or 0.0) for point in points)
        parts.append(
            _kv(
                title,
                [
                    ("金额", _format_amount(cost)),
                    ("输入 Token", _format_int(input_tokens)),
                    ("输出 Token", _format_int(output_tokens)),
                    ("缓存命中 Token", _format_int(cache_tokens)),
                    ("调用次数", _format_int(calls)),
                ],
            )
        )
    return parts


async def _collect_plugins(ctx: Any, console: Any) -> list[dict[str, Any]]:
    control = _plugin_control(ctx)
    if control is None:
        return [_table("", ("名称", "版本", "状态"), [])]
    try:
        snapshots = list(control.snapshot())
    except Exception as exc:
        logger.warning(f"读取插件清单失败: {exc}")
        return [_table("", ("名称", "版本", "状态"), [])]
    rows = []
    for snapshot in sorted(snapshots, key=lambda item: str(getattr(item, "name", ""))):
        state = str(getattr(snapshot, "state", "") or "")
        if not getattr(snapshot, "enabled", True):
            label = _PLUGIN_STATE_LABELS["disabled"]
        else:
            label = _PLUGIN_STATE_LABELS.get(state, "未加载")
        rows.append(
            [
                str(getattr(snapshot, "name", "") or "—"),
                str(getattr(snapshot, "version", "") or "—"),
                label,
            ]
        )
    return [_table("", ("名称", "版本", "状态"), rows)]


async def _collect_errors(ctx: Any, console: Any) -> list[dict[str, Any]]:
    metrics = _metrics(console)
    if metrics is None:
        return [_kv("", [("近 24 小时 ERROR", "—"), ("最近一次异常", "—")])]
    try:
        payload = metrics.logs(since=0, limit=0)
    except Exception as exc:
        logger.warning(f"读取错误摘要失败: {exc}")
        return [_kv("", [("近 24 小时 ERROR", "—"), ("最近一次异常", "—")])]
    cutoff = time.time() - ERROR_WINDOW_SECONDS
    errors = [
        item
        for item in (payload.get("items") or [])
        if str(item.get("level") or "").lower() == "error"
        and float(item.get("ts") or 0) >= cutoff
    ]
    latest = errors[-1] if errors else None
    latest_text = "无"
    if latest is not None:
        latest_text = (
            f"{latest.get('datetime') or latest.get('time') or '—'}"
            f" · {latest.get('module') or '—'}"
        )
    return [
        _kv(
            "",
            [
                ("近 24 小时 ERROR", _format_int(len(errors))),
                ("最近一次异常", latest_text),
            ],
        )
    ]


_COLLECTORS = {
    "概况": _collect_overview,
    "用量": _collect_usage,
    "插件": _collect_plugins,
    "错误": _collect_errors,
}


async def collect_status_blocks(
    ctx: Any,
    blocks: Sequence[str] | None = None,
    *,
    console: Any = None,
) -> dict[str, list[dict[str, Any]]]:
    """按白名单取数，返回 {块名: [部分, ...]}（缺省 = 四块全渲染）。

    ctx 是 modloader 插件上下文（读宿主服务与插件控制面）；
    console 是面板服务对象（提供 metrics / uptime / bot_info）。
    两者都缺失时仍返回结构完整的块，只是字段为占位符——命令绝不抛错。
    """
    collected: dict[str, list[dict[str, Any]]] = {}
    for name in normalize_blocks(blocks):
        collector = _COLLECTORS[name]
        try:
            collected[name] = await collector(ctx, console)
        except Exception as exc:  # 单块失败不影响其它块
            logger.warning(f"采集 status 块失败 ({name}): {exc}")
            collected[name] = [_kv("", [("数据", "不可用")])]
    return collected


# ----------------------------------------------------------------------
# 渲染
# ----------------------------------------------------------------------


def build_status_payload(
    blocks: dict[str, list[dict[str, Any]]],
    *,
    subtitle: str = "",
    footer: str = "",
    theme: str = "default",
) -> dict[str, Any]:
    """把取数结果整理成渲染载荷（HTML 与纯文本共用同一份）。"""
    ordered = [name for name in BLOCK_NAMES if name in blocks]
    return {
        "title": CARD_TITLE,
        "subtitle": subtitle,
        "footer": footer,
        "theme": theme,
        "blocks": [{"name": name, "parts": blocks[name]} for name in ordered],
    }


#: 插件状态 -> 单元格色调（运行中绿、异常红、已停用灰、未加载黄）
_PLUGIN_STATE_TONES = {
    "运行中": "ok",
    "异常": "danger",
    "已停用": "muted",
    "未加载": "warn",
}

#: 值 -> 指标卡片色调（在线绿、离线/异常红、未知灰）
_VALUE_TONES = {
    "在线": "ok",
    "运行中": "ok",
    "正常": "ok",
    "离线": "danger",
    "异常": "danger",
    "不可用": "danger",
    "未知": "muted",
    "无样本": "muted",
    "无": "muted",
    "—": "muted",
}


def value_tone(value: Any) -> str:
    """按取值给出色调（不认识的值不加色，保持中性）。"""
    return _VALUE_TONES.get(str(value or "").strip(), "")


def _state_cell(label: str) -> dict[str, Any]:
    return {"text": label, "tone": _PLUGIN_STATE_TONES.get(label.strip(), "")}


def _kv_items(part: Mapping[str, Any]) -> list[tuple[str, Any]]:
    items: list[tuple[str, Any]] = []
    for row in part.get("rows") or ():
        if isinstance(row, Sequence) and not isinstance(row, (str, bytes)) and len(row) >= 2:
            items.append((str(row[0]), row[1]))
    return items


def _stat_items(part: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    """概况块的键值 -> 指标卡片（值带状态色）。"""
    tiles: list[tuple[str, str, str]] = []
    for label, value in _kv_items(part):
        text = str(value)
        tiles.append((label, text, value_tone(text)))
    return tiles


def _part_block(part: Mapping[str, Any], *, tone: str = "") -> dict[str, Any]:
    """把采集到的单个部分转成卡片块（表格 / 键值面板）。"""
    if part.get("kind") == "table":
        columns = [str(column) for column in (part.get("columns") or ())]
        is_plugin_table = bool(columns) and columns[0] == "名称"
        rows: list[list[Any]] = []
        for row in part.get("rows") or ():
            cells = list(row) if isinstance(row, Sequence) and not isinstance(row, (str, bytes)) else []
            if is_plugin_table and len(cells) == len(columns):
                cells = [*cells[:-1], _state_cell(str(cells[-1]))]
            rows.append(cells)
        block: dict[str, Any] = {
            "kind": "rows",
            "title": part.get("title") or "",
            "columns": columns,
            "rows": rows,
        }
    else:
        block = {"kind": "kv", "title": part.get("title") or "", "items": _kv_items(part)}
    if tone:
        block["tone"] = tone
    return block


def _error_part_tone(part: Mapping[str, Any]) -> str:
    """错误块：近 24 小时 ERROR 条数 > 0 时整块用告警色强调。"""
    for label, value in _kv_items(part):
        if label.endswith("ERROR"):
            try:
                return "danger" if int(str(value).strip()) > 0 else ""
            except (TypeError, ValueError):
                return ""
    return ""


def build_status_html(payload: dict[str, Any]) -> str:
    """用公共卡片渲染器生成自包含 HTML（内联 CSS、无 JS、无外链）。

    呈现上做了分块卡片化：概况用指标卡片墙、用量多窗口并排成两栏、
    错误块在有条目时整体转成告警配色，块间距收紧以免整张图过高。
    """
    card_blocks: list[dict[str, Any]] = []
    for block in payload.get("blocks") or ():
        name = str(block.get("name") or "")
        parts = [part for part in (block.get("parts") or ()) if isinstance(part, Mapping)]
        tone = ""
        if name == "错误":
            tone = "danger" if any(_error_part_tone(part) == "danger" for part in parts) else ""
        card_blocks.append({"kind": "heading", "text": name, "tone": tone})

        # 概况：单个无标题键值块 -> 指标卡片墙（值带状态色）
        if (
            name == "概况"
            and len(parts) == 1
            and parts[0].get("kind") != "table"
            and not parts[0].get("title")
        ):
            card_blocks.append({"kind": "stats", "cols": 3, "items": _stat_items(parts[0])})
            continue

        panels = [_part_block(part, tone=tone) for part in parts]
        if len(panels) == 2 and all(
            panel["kind"] == "kv" and panel.get("title") for panel in panels
        ):
            # 用量：近 24 小时 / 近 7 天并排成两栏，省一半高度
            card_blocks.append(
                {"kind": "grid", "cols": 2, "cells": [[panel] for panel in panels]}
            )
        else:
            card_blocks.extend(panels)

    return render_card_html(
        title=str(payload.get("title") or CARD_TITLE),
        subtitle=str(payload.get("subtitle") or ""),
        blocks=card_blocks,
        footer=str(payload.get("footer") or ""),
        theme=str(payload.get("theme") or "default"),
        width=720,
    )


def build_status_text(payload: dict[str, Any], *, hint: str = "") -> str:
    """与图片版**信息等价**的纯文本卡片（同样的四块、同样的字段）。"""
    lines = [str(payload.get("title") or CARD_TITLE)]
    subtitle = str(payload.get("subtitle") or "")
    if subtitle:
        lines.append(subtitle)
    for block in payload.get("blocks") or ():
        lines.append(f"【{block.get('name') or ''}】")
        for part in block.get("parts") or ():
            title = str(part.get("title") or "")
            if title:
                lines.append(f"  {title}")
            indent = "    " if title else "  "
            rows = part.get("rows") or ()
            if part.get("kind") == "table":
                columns = [str(column) for column in (part.get("columns") or ())]
                if not rows:
                    lines.append(f"{indent}（暂无数据）")
                    continue
                lines.append(f"{indent}{' | '.join(columns)}")
                for row in rows:
                    lines.append(f"{indent}{' | '.join(str(cell) for cell in row)}")
            else:
                for label, value in rows:
                    lines.append(f"{indent}{label}: {value}")
    footer = str(payload.get("footer") or "")
    if footer:
        lines.append(footer)
    if hint:
        lines.append(hint)
    return "\n".join(lines)


async def render_status_image(
    html: str,
    *,
    screenshots: Any = None,
    timeout: float = SCREENSHOT_TIMEOUT_SECONDS,
) -> bytes | None:
    """渲染 PNG 字节；不可用 / 失败 / 超时返回 None（调用方降级为文本）。"""
    return await render_card_image(html, timeout=timeout, screenshots=screenshots)


async def render_status_png(
    payload: dict[str, Any],
    *,
    screenshots: Any = None,
    timeout: float = SCREENSHOT_TIMEOUT_SECONDS,
) -> bytes | None:
    """一次到位：payload -> PNG（失败返回 None）。"""
    return await render_status_image(
        build_status_html(payload), screenshots=screenshots, timeout=timeout
    )


async def render_status_with_fallback(
    payload: dict[str, Any],
    *,
    screenshots: Any = None,
    timeout: float | None = None,
) -> tuple[bytes | None, str]:
    """渲染图片；不可用 / 失败 / 超时 -> (None, 等价纯文本)。

    命令内 25s 兜底超时（在截图 20s 之上），命令**绝不**因渲染失败而报错。
    timeout 缺省取 COMMAND_TIMEOUT_SECONDS（调用时解析，便于测试与调参）。
    """
    budget = COMMAND_TIMEOUT_SECONDS if timeout is None else float(timeout)
    try:
        png = await asyncio.wait_for(
            render_status_png(payload, screenshots=screenshots), timeout=budget
        )
    except (asyncio.TimeoutError, TimeoutError):
        logger.warning("status 卡片渲染超时，降级为纯文本")
        png = None
    if png:
        return png, ""
    return None, build_status_text(payload, hint=FALLBACK_HINT)


__all__ = [
    "BLOCK_NAMES",
    "CARD_TITLE",
    "COMMAND_TIMEOUT_SECONDS",
    "FALLBACK_HINT",
    "SCREENSHOT_TIMEOUT_SECONDS",
    "build_status_html",
    "build_status_payload",
    "build_status_text",
    "collect_status_blocks",
    "format_duration",
    "normalize_blocks",
    "render_status_image",
    "render_status_png",
    "render_status_with_fallback",
    "unknown_blocks",
]
