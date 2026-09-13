"""四个玩法模块的公共基类与注册表（spec(5) §4.4）。

每个玩法都**同时**提供两条入口（R15）：

1. 命令入口（/mg <游戏> ...），由 :mod:`.minigame` 统一注册；
2. agent 入口：:meth:`Game.describe` 的说明文本 + `minigame__<tool>` 可调用工具。

玩法只做「程序必须做的事」（随机、上限、计分、落库、渲染）；
「这算不算成语 / 接不接得上」一律交 AI 判定（D14）。
"""

from __future__ import annotations

import html as html_module
import re
from dataclasses import dataclass, field
from typing import Any

#: 卡片里承载 Markdown 正文的占位符（渲染后被替换成可信 HTML 片段）
CONTENT_MARKER = "@@MG_CONTENT@@"

#: Markdown 正文片段的内联样式
MARKDOWN_CSS = """\
.mg-md { margin: 0; }
.mg-md p { margin: 0 0 8px; }
.mg-md p:last-child { margin-bottom: 0; }
.mg-md pre { background: rgba(0, 0, 0, 0.28); padding: 10px 12px; border-radius: 8px; overflow-x: auto; }
.mg-md code { font-family: var(--card-font); }
.mg-md ul, .mg-md ol { margin: 0 0 8px 20px; }
.mg-md blockquote { margin: 0 0 8px; padding-left: 10px; border-left: 3px solid var(--accent); }
"""

#: Markdown 允许的扩展（与卡片能力匹配：无外链、无 JS）
_MARKDOWN_EXTENSIONS = ("fenced_code", "sane_lists", "nl2br")

#: 只在属性位置清理危险 URL（data: 用于头像，但头像片段在清洗之后才注入）
_UNSAFE_URL_RE = re.compile(r"""(?i)\b(href|src)\s*=\s*"([^"]*)"\s*""")
_UNSAFE_SCHEME_RE = re.compile(r"(?i)^\s*(javascript|vbscript|data|file)\s*:")

#: 纯链接判定：分隔后每一段都长得像 URL
_URL_TOKEN_RE = re.compile(r"(?i)^(?:https?://|www\.)\S+$")


def is_pure_link(text: str) -> bool:
    """正文是否「纯链接」（分隔后每段都是 URL 形态）。"""
    tokens = [token for token in str(text or "").split() if token]
    if not tokens:
        return False
    return all(_URL_TOKEN_RE.match(token) for token in tokens)


def sanitize_fragment(fragment_html: str) -> str:
    """清掉片段里指向 javascript:/data:/file: 的 href/src（属性级清洗）。"""

    def _replace(match: re.Match[str]) -> str:
        attr = match.group(1)
        value = html_module.unescape(match.group(2))
        if _UNSAFE_SCHEME_RE.match(value):
            return f'{attr}="#"'
        return match.group(0)

    return _UNSAFE_URL_RE.sub(_replace, fragment_html)


def render_markdown_fragment(text: str) -> str:
    """把用户正文变成可信 HTML 片段：**先 HTML 转义，再交 Markdown**。

    - 原始 HTML（<script> / <img onerror=...>）因此变成字面文本；
    - 语法（粗体 / 列表 / 代码块 / 引用）照常生效；
    - 最后再做一次属性级 URL 清洗，堵掉 [x](javascript:...) 这类链接。
    """
    import markdown

    escaped = html_module.escape(str(text or ""), quote=True)
    rendered = markdown.markdown(escaped, extensions=list(_MARKDOWN_EXTENSIONS))
    return sanitize_fragment(rendered)


#: 属性位置的危险 URL：javascript / vbscript / file 一律禁止；data: 只允许内联图片
#: （卡片头像由 avatars 模块注入为 data:image/png，属于可信片段）
def _unsafe_attr_value(value: str) -> bool:
    decoded = html_module.unescape(str(value or "")).strip().lower()
    if decoded.startswith(("javascript:", "vbscript:", "file:")):
        return True
    return decoded.startswith("data:") and not decoded.startswith("data:image/")


def error_html_scan(fragment_html: str) -> bool:
    """片段里是否含有标签级的事件属性 / 危险 URL（测试与自检用）。"""
    for tag in re.findall(r"<[^>]*>", fragment_html):
        if re.search(r"(?i)\son[a-z]+\s*=", tag):
            return True
        for value in re.findall(r"""(?i)\b(?:href|src)\s*=\s*"([^"]*)\"""", tag):
            if _unsafe_attr_value(value):
                return True
    return False


@dataclass
class GameRequest:
    """一次玩法执行请求（命令通道或工具通道共用）。"""

    runtime: Any
    service: Any
    config: Any
    command_ctx: Any = None
    args: list[str] = field(default_factory=list)
    raw_args: str = ""
    user_id: int = 0
    user_name: str = ""
    kind: str = "group"
    conversation_id: str = ""

    def want_sync_reply(self) -> None:
        """把本次结果交主管线（与 /sleep 同一机制，不新造管线）。"""
        ctx = self.command_ctx
        if ctx is not None:
            try:
                ctx.sync_reply = True
            except Exception:  # pragma: no cover - 只读上下文时忽略
                pass


class Game:
    """玩法基类。"""

    #: 玩法 id（与 enabled_games / mg_record.game_id 一致）
    id: str = ""
    #: 菜单展示名
    name: str = ""
    #: 命令别名（/mg <别名>）
    aliases: tuple[str, ...] = ()
    #: 菜单里的一行说明
    summary: str = ""

    #: 该玩法对 agent 暴露的工具（本地名，最终名自动加 {plugin}__ 前缀）
    tool_names: tuple[str, ...] = ()

    # ── R15：给 agent 看的说明文本 ─────────────────────────────

    def describe(self) -> str:
        """agent 入口的说明文本（工具与提示词里引用）。"""
        raise NotImplementedError

    def help_text(self, *, mode: str = "") -> str:
        """面向用户的规则文本（/mg help <游戏> 与 /mg <游戏> 帮助）。"""
        raise NotImplementedError

    def matches(self, token: str) -> bool:
        value = str(token or "").strip().casefold()
        if not value:
            return False
        candidates = {self.id.casefold(), self.name.casefold()}
        candidates.update(alias.casefold() for alias in self.aliases)
        return value in candidates

    async def run(self, request: GameRequest) -> str | None:
        """执行玩法；返回 None 表示已自行发送回复（图片）。"""
        raise NotImplementedError


def build_games() -> list[Game]:
    """构造四个玩法实例（按菜单顺序）。"""
    from .bottle import BottleGame
    from .checkin import CheckinGame
    from .chengyu import ChengyuGame
    from .fortune import FortuneGame

    return [BottleGame(), ChengyuGame(), CheckinGame(), FortuneGame()]


def find_game(games: Any, token: str) -> Game | None:
    for game in games or ():
        if game.matches(token):
            return game
    return None


__all__ = [
    "CONTENT_MARKER",
    "Game",
    "GameRequest",
    "MARKDOWN_CSS",
    "build_games",
    "error_html_scan",
    "find_game",
    "is_pure_link",
    "render_markdown_fragment",
    "sanitize_fragment",
]
