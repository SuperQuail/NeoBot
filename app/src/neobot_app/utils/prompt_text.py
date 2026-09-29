"""提示词文本转义（用户可控字段进提示词前必须过这里）。

提示词模板是 XML 风格区块（`<群友信息>...</群友信息>`），而模板里注入的值来自
群昵称、群名、备注、档案等**任何人都能改**的字段。若值里出现 `</群友信息>` 这类
闭合标签，区块结构会被破坏，注入文本会落到区块之外——详见 fix(12) §4.9。

放在 utils 而不是 app.prompt.render：后者被 builder 导入，而 builder 又导入
user_profiles，转义函数放在 prompt.render 会形成循环导入。
"""

from __future__ import annotations

from typing import Any

#: 会被替换成全角等价字符的 XML/模板元字符。用全角（而不是 html.escape 的
#: `&lt;`）是因为这些值最终是给模型读的自然语言：`＜昵称＞` 与 `<昵称>` 语义
#: 等价，但不会闭合模板标签、也不会触发 strip_empty_tag_blocks。
_XML_META_CHARS = {"<": "＜", ">": "＞", "&": "＆"}


def escape_prompt_text(value: Any) -> str:
    """把用户可控文本转义成"只能当文本"的形式（None → 空串）。"""
    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)
    for char, replacement in _XML_META_CHARS.items():
        text = text.replace(char, replacement)
    return text
