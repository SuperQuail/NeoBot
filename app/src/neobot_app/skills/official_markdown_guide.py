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
只有需要标题、列表、引用、链接、内嵌 @、@全体成员或指令按钮时，才调用
send_official_markdown（仅官方通道可见，发送的是官方 Markdown 卡片）。
它和我们自己的 Markdown 图片（send_long_reply 把 Markdown 渲染成图片）不是一回事。

## content 写法（只放行内嵌 @）

- 支持：## 标题、**加粗**、_斜体_、~~删除线~~、> 引用、- 列表、1. 有序、
  [文字](https://...)、*** 分割线；
- 不支持：表格、代码块、HTML；需要就改 send_long_reply（转图片）。
- @ 用户：<qqbot-at-user id="openid" />，openid 是群友资料里的完整用户 ID
  （提示词/资料中 openid 后面那串），不要编；单聊不支持 @，直接写昵称。
- 不要手写 <qqbot-at-everyone /> 或 <qqbot-cmd-*>：这类标签会被工具转义成普通文字。
  @全体成员用 at_everyone=true（仅群聊，每群每天 1 次，机器人必须是群管理员）；
  指令按钮用 commands 数组（工具会生成 qqbot-cmd-enter/qqbot-cmd-input 标签）。

## commands 示例

[{"text": "/签到", "show": "去签到"}]：text 必填、text/show 各 ≤100 字符；
单聊可加 "enter": true（点一下直接发送），群聊不支持 enter。
reference 只对参数指令生效（是否带引用，默认 false）。

## 限制

- 单条 ≤4000 字，一次回复里最多 1 条；
- 被动回复额度：群 5 分钟内 5 次、单聊 60 分钟内 4 次，不要用它刷屏；
- 链接只允许 http(s)；javascript:/data:/file: 与回环/内网地址会被拒绝；
- @全体需要机器人是群管理员，当天已用过就不要再试；单聊不支持 @。

失败怎么办：发送失败是真实失败，不会自动降级成纯文本；按错误修正参数，
或告诉用户暂时无法发送。
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
