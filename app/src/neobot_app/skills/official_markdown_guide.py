"""官方 Markdown 卡片技能文档：静态内置，启动/重载时写入 data/skills。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

SKILL_DIR_NAME = "qq-official-markdown"
SKILL_OWNER = "official_markdown"
_DESCRIPTION = "官方 QQ 机器人 Markdown 卡片与内嵌 @/指令按钮的写法（仅 official 通道，按需读取）"
_KEYWORDS = "markdown 卡片 官方机器人 标题 列表 引用 按钮 指令 @ 群通知"

_DOCUMENT = """# 官方 QQ 机器人 Markdown 卡片

官方 QQ 机器人 Markdown 卡片与内嵌 @/指令按钮的写法（仅 official 通道，按需读取）。

普通 send_reply 只发送纯文本，不会渲染 Markdown，也不能真正 @ 用户。
只有需要标题、列表、引用、链接、图片、内嵌 @ 或指令按钮时，才调用
send_official_markdown（仅官方通道可见，发送的是官方 Markdown 卡片）。
它和我们自己的 Markdown 图片（send_long_reply 把 Markdown 渲染成图片）不是一回事。

## 支持的内嵌语法

- 群 @ 用户：<qqbot-at-user id="合成ID" />，合成 ID 是群友资料里的 900 开头 13 位 QQ ID。
- @全体成员：<qqbot-at-everyone />；机器人必须是群管理员，且每个群每个自然日只能发一次。
- 回车指令：<qqbot-cmd-enter text="..." />；群聊不支持。
- 参数指令：<qqbot-cmd-input text="..." show="..." reference="false" />；
  text 必填，text/show 各 ≤100 字符，值需要 URL 编码。

其余 <...> 标签会被工具拒绝。表格、代码块官方不支持，改用 send_long_reply。

发送失败是真实的失败：不要改写成普通文本重发，读取错误修正参数，或告诉用户暂时无法发送。
"""


def _frontmatter() -> str:
    return "\n".join(
        [
            "---",
            f"name: {SKILL_DIR_NAME}",
            f"description: {_DESCRIPTION}",
            f"keywords: {_KEYWORDS}",
            "---",
        ]
    ) + "\n\n"


def sync_official_markdown_skill(*, registry: Any, data_dir: Path, logger: Any = None) -> bool:
    skill_dir = Path(data_dir) / "skills" / SKILL_DIR_NAME
    skill_path = skill_dir / "SKILL.md"
    body = _DOCUMENT
    try:
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(_frontmatter() + body, encoding="utf-8")
    except OSError as exc:
        if logger is not None:
            logger.warning(f"写入官方 Markdown 卡片技能失败: {exc}")
        return False
    if registry is None:
        return False
    try:
        unregister = getattr(registry, "unregister_owner", None)
        if callable(unregister):
            unregister(SKILL_OWNER)
        register_many = getattr(registry, "register_many", None)
        if not callable(register_many):
            return False
        register_many(
            SKILL_OWNER,
            [
                SimpleNamespace(
                    name=SKILL_DIR_NAME,
                    description=_DESCRIPTION,
                    content=body,
                    path=skill_path,
                    keywords=_KEYWORDS,
                    metadata={},
                )
            ],
        )
    except Exception as exc:
        if logger is not None:
            logger.warning(f"注册官方 Markdown 卡片技能失败: {exc}")
        return False
    if logger is not None:
        logger.info("官方 Markdown 卡片技能已就绪")
    return True
