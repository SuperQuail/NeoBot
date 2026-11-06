"""全局提示词资产访问入口：所有提示词文本的唯一读取方式。

注册表在 ``blocks.py``（所有 TOML 分区都登记为 Block）；本模块负责按资产 id
读取文本并渲染：

- 解析顺序：运行时 store（自定义覆盖默认）→ 随包内置模板 → 极简兜底 → default；
- ``enabled`` 统一生效（主模板除外：禁用主模板会让机器人失去提示词，保留安全例外）；
- 支持 ``SECTION.key`` 子键与内容渲染，面板/子 Agent/直播/标签都从这里读取。

数据文件：``prompt/templates/prompts.toml``（含 label_* / bili_* 分区统一注册）。
"""

from __future__ import annotations

from typing import Any

from neobot_app.prompt.blocks import BLOCKS, Block, Stage, block_by_id
from neobot_app.prompt.render import render_template
from neobot_app.prompt.store import fallback_template, packaged_template

#: 禁止关闭的机制性资产：主模板关闭会丢人设；label_message_meta 关闭会让聊天记录渲染成空行进而被整条丢弃
_ALWAYS_ENABLED_ASSETS = frozenset({"group_chat", "friend_chat", "label_message_meta"})

#: 已注册的提示词资产（有 TOML 分区的块）；id 全局唯一
_ASSETS: dict[str, Block] = {
    block.id: block for block in BLOCKS if block.template_section is not None
}


def asset_ids() -> tuple[str, ...]:
    """全部已注册的提示词资产 id（顺序即注册表顺序）。"""
    return tuple(_ASSETS)


def asset_section(asset_id: str) -> str:
    """资产对应的 TOML 分区名。"""
    block = block_by_id(asset_id)
    section = block.template_section
    if section is None:
        raise KeyError(f"提示词资产 {asset_id} 没有 TOML 分区")
    return section


def asset_keys(asset_id: str) -> tuple[str, ...]:
    """资产声明的键（主键 + extra_keys）。"""
    block = block_by_id(asset_id)
    return (block.key, *block.extra_keys)


def asset_enabled(asset_id: str, store: Any = None, default: bool = True) -> bool:
    """资产是否启用；主模板与机制标签永远启用（安全例外），其余按分区 enabled 判定。"""
    block = block_by_id(asset_id)
    if block.id in _ALWAYS_ENABLED_ASSETS:
        return True
    if store is None:
        return default
    section = block.template_section
    if section is None:
        return default
    return store.enabled(section, default=default)


def _lookup_store(store: Any, section: str, key: str) -> str:
    """在 store 的合并分区里按点路径取字符串（store 不可用时返回空串）。"""
    if store is None:
        return ""
    node: Any = store.get_section(section)
    for part in str(key).split("."):
        if not isinstance(node, dict):
            return ""
        node = node.get(part)
    return node if isinstance(node, str) else ""


def raw_text(
    asset_id: str,
    key: str | None = None,
    *,
    store: Any = None,
    strip: bool = True,
) -> str:
    """读取未渲染的提示词模板；资产关闭/缺失时返回空串。"""
    block = block_by_id(asset_id)
    if not asset_enabled(asset_id, store):
        return ""
    section = asset_section(asset_id)
    field = key or block.key
    value = _lookup_store(store, section, field)
    if value.strip():
        return value.strip() if strip else value
    return packaged_template(section, field, strip=strip) or fallback_template(
        section, field, strip=strip
    )


def text(
    asset_id: str,
    key: str | None = None,
    *,
    store: Any = None,
    values: dict[str, Any] | None = None,
    default: str = "",
) -> str:
    """读取并渲染提示词文本；资产关闭/缺失时返回 default。"""
    template = raw_text(asset_id, key, store=store)
    if not template:
        return default
    return render_template(template, values or {})
