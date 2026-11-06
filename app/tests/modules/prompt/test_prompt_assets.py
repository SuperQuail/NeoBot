"""全局提示词统一入口（prompt/assets.py）的契约测试。

- 所有 TOML 分区都在注册表里、都能经 assets 读取（store 有/无两条路径）；
- custom 覆盖与 enabled 对所有资产统一生效（主模板保留安全例外）；
- 数据只在唯一文件里，不依赖 labels.toml / bilibili prompts.toml 等旁路。
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from neobot_app.prompt.assets import (
    asset_enabled,
    asset_ids,
    asset_keys,
    asset_section,
    raw_text,
    text,
)
from neobot_app.prompt.blocks import BLOCKS, Stage, validate_blocks
from neobot_app.prompt.store import DEFAULT_TEMPLATE_FILE, KNOWN_SECTIONS

_TEMPLATE_SECTIONS = {
    key: value
    for key, value in tomllib.loads(DEFAULT_TEMPLATE_FILE.read_text("utf-8")).items()
    if key != "version"
}


def test_registry_covers_every_prompt_section():
    registered = set(asset_ids())
    assert registered == set(_TEMPLATE_SECTIONS)
    assert set(KNOWN_SECTIONS) == registered
    assert validate_blocks() == []


def test_asset_ids_and_sections_are_unique():
    ids = asset_ids()
    assert len(ids) == len(set(ids))
    for asset_id in ids:
        assert asset_section(asset_id) in _TEMPLATE_SECTIONS


@pytest.mark.parametrize("asset_id", asset_ids())
def test_every_declared_key_resolves_with_and_without_store(
    asset_id, prompt_store
):
    for key in asset_keys(asset_id):
        assert raw_text(asset_id, key), f"{asset_id}.{key} 无内置文本"
        assert raw_text(asset_id, key, store=prompt_store)


def test_custom_override_applies_to_labels_and_bilibili(custom_store):
    store = custom_store(
        '[label_message_meta]\nline = "自定义消息行"\n'
        '[bili_human_feel]\ntemplate = "自定义B站风格"\n'
    )

    assert text("label_message_meta", "line", store=store) == "自定义消息行"
    assert text("bili_human_feel", store=store) == "自定义B站风格"


def test_enabled_false_uniformly_empties_catalog_assets(custom_store):
    store = custom_store("[bili_scene]\nenabled = false\n")

    assert asset_enabled("bili_scene", store=store) is False
    assert text("bili_scene", store=store) == ""


def test_main_template_keeps_safety_exception_when_disabled(custom_store):
    """主模板禁用会让机器人失去提示词，assets 保留安全例外（文档已写明）。"""
    store = custom_store("[group_chat]\nenabled = false\n")

    block = next(item for item in BLOCKS if item.id == "group_chat")
    assert block.stage is Stage.SYSTEM_MAIN
    assert asset_enabled("group_chat", store=store) is True
    assert text("group_chat", store=store)


def test_unknown_asset_is_a_loud_error():
    with pytest.raises(KeyError):
        raw_text("不存在的资产")


# ── 统一性守卫：除资产层/管理面板外，不允许绕过 assets 直读提示词 ──────────────

_APP_ROOT = Path(__file__).resolve().parents[3] / "app" / "src" / "neobot_app"
_DIRECT_READ_ALLOWED = {
    "prompt/assets.py",  # 资产层本身
    "prompt/store.py",  # 存储/合并/兜底实现
    "prompt/context.py",  # 组合器取值（内部已转 assets）
    "prompt/builder.py",  # 未注册分区的兼容回退
    "builtin_plugins/dashboard/prompt_admin.py",  # 面板展示/编辑
    "builtin_plugins/dashboard/api_parts/prompts.py",
    "builtin_plugins/dashboard/api_parts/_common.py",
}
_DIRECT_READ_PATTERN = re.compile(
    r"get_template_value\(|packaged_template\(|prompt_store\.get\(|store\.get\(|\.template\(|_FALLBACK_SECTIONS|parse_prompt_file\("
)


def test_no_direct_prompt_reads_outside_assets():
    offenders: list[str] = []
    for path in sorted(_APP_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(_APP_ROOT).as_posix()
        if relative in _DIRECT_READ_ALLOWED:
            continue
        for line_no, line in enumerate(path.read_text("utf-8", errors="ignore").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if _DIRECT_READ_PATTERN.search(line):
                offenders.append(f"{relative}:{line_no}: {line.strip()}")
    assert not offenders, "以下位置绕过 assets 直读提示词：\n" + "\n".join(offenders)
