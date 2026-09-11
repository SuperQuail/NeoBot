"""插件配置的宿主侧校验：把已存配置校验/回落成插件可安全消费的值。

面板插件这类"配置坏掉就再也没有修复入口"的场景不能硬失败：这里对插件声明的
config_model 做一次校验，非法的已存字段回落到打包默认值（仍非法时回落模型
默认值），并把告警交回调用方记录/展示。插件收到的配置保证可通过自身校验。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def validate_plugin_config(
    model: type | None,
    merged: Mapping[str, Any],
    stored: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], str | None]:
    """校验「打包默认值 + 已存配置」。

    返回 (可注入插件的配置, 告警文本)。告警非空表示部分已存值非法、已回落
    默认值；返回值保证能被 model 校验通过。model 未声明或不是 pydantic
    模型时原样返回。
    """
    values = {str(key): value for key, value in (merged or {}).items()}
    if not isinstance(model, type) or not callable(getattr(model, "model_validate", None)):
        return values, None

    warning: str | None = None
    invalid_keys: set[str] = set()
    try:
        return _dump(model.model_validate(values)), None
    except Exception as exc:  # noqa: BLE001 - 校验失败是预期路径，要转成告警
        warning = _format_error(exc)
        invalid_keys = _invalid_top_level_keys(exc)

    # 只回落"用户存下来的字段"：打包默认值本身非法属于插件作者问题，
    # 删掉它也不会让模型变合法，最终走模型默认值并同样告警。
    drop = invalid_keys & {str(key) for key in (stored or {})}
    if drop:
        repaired = {key: value for key, value in values.items() if key not in drop}
        try:
            return _dump(model.model_validate(repaired)), warning
        except Exception:
            pass

    try:
        return _dump(model()), warning
    except Exception:
        return values, warning


def _invalid_top_level_keys(error: BaseException) -> set[str]:
    """从 pydantic ValidationError 中提取出错的顶层字段名。"""
    errors = getattr(error, "errors", None)
    if not callable(errors):
        return set()
    try:
        items = errors()
    except Exception:
        return set()
    keys: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            continue
        loc = item.get("loc") or ()
        if loc and isinstance(loc[0], str):
            keys.add(str(loc[0]))
    return keys


def _format_error(error: BaseException) -> str:
    errors = getattr(error, "errors", None)
    if callable(errors):
        try:
            details = []
            for item in errors():
                if not isinstance(item, Mapping):
                    continue
                loc = ".".join(str(part) for part in (item.get("loc") or ())) or "<root>"
                details.append(f"{loc}: {item.get('msg')}")
            if details:
                return "; ".join(details[:5])
        except Exception:
            pass
    return str(error) or type(error).__name__


def _dump(model: Any) -> dict[str, Any]:
    dump = getattr(model, "model_dump", None)
    if callable(dump):
        data = dump()
        if isinstance(data, Mapping):
            return {str(key): value for key, value in data.items()}
    return dict(model)
