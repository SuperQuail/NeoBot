"""提示词模板渲染的公共工具。

集中放置占位符扫描、空区块清理与安全渲染,避免 builder / orchestrator /
子 Agent 各自实现一份而出现行为分叉。转义与占位符规则见
templates/prompts.toml 顶部说明。
"""

from __future__ import annotations

import re
from typing import Any

from neobot_app.utils.formater import safe_format

# 只含空白的 XML 风格区块(如 <群友信息> 与 </群友信息> 之间只有换行)。
# 渲染后统一删除,使可选区块可以放心写在模板里。
_EMPTY_TAG_BLOCK_RE = re.compile(r"[ \t]*<([^<>\s/]+)>\s*</\1>[ \t]*\n?")

# 占位符扫描:先屏蔽转义写法 {{ / }},避免把字面量花括号当成占位符
_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_ESCAPED_BRACE_SENTINEL = "\x00"


def template_placeholders(template: str) -> set[str]:
    """返回模板中真实占位符的名字集合(排除转义写法与字面量花括号)。"""
    cleaned = template.replace("{{", _ESCAPED_BRACE_SENTINEL).replace(
        "}}", _ESCAPED_BRACE_SENTINEL
    )
    return set(_PLACEHOLDER_RE.findall(cleaned))


def strip_empty_tag_blocks(text: str) -> str:
    """删除只含空白的 XML 风格区块,并压缩多余空行。"""
    previous = None
    current = text
    while current != previous:
        previous = current
        current = _EMPTY_TAG_BLOCK_RE.sub("\n", current)
    current = re.sub(r"\n{3,}", "\n\n", current)
    return current.strip()


def render_template(template: str, values: dict[str, Any]) -> str:
    """渲染模板并清理空区块;模板为空白时返回空字符串。"""
    if not template or not template.strip():
        return ""
    return strip_empty_tag_blocks(safe_format(template, **values))
