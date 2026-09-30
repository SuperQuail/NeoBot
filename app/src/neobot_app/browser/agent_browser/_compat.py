"""DrissionPage 符号的唯一导入点（含版本兼容诊断）。

为什么要有这个模块
------------------
DrissionPage 5.0 是一次破坏性改版：删除了顶层 ChromiumPage（连
DrissionPage/_pages/chromium_page.py 整个文件都没了），改用
Chromium + latest_tab 的模型。而本仓库的依赖声明曾经只写了下界
（drissionpage>=4.1），在「允许预发布」的解析语义下会选中 5.0.0b1 ——
结果是**任何重新解析依赖的环境（例如新部署）一启动就 ImportError**，
连 neobot install-browser 都用不了。

现在做了两件事：

1. pyproject.toml 收紧到 drissionpage>=4.1,<4.2（4.2 的 beta 会连带把
   lxml 拉到 7.0.0b1，同样不适合当默认）；
2. 所有 DrissionPage 符号集中在这里导入，导入失败时给出**可执行的**
   错误信息，而不是把一句 cannot import name 'ChromiumPage' 丢给用户。

上层模块（manager / snapshot / cli）只从这里取值，不要再直接
from DrissionPage import ...。
"""

from __future__ import annotations

#: 出现这个异常说明装的是 DrissionPage 5.x（或其它删掉 ChromiumPage 的版本）。
DRISSIONPAGE_HINT = (
    "当前安装的 DrissionPage 与本项目不兼容（缺少 ChromiumPage）。"
    "本项目使用 DrissionPage 4.1.x 的 API：请执行 "
    'uv pip install "drissionpage<4.2" / pip install "drissionpage>=4.1,<4.2" 后重试；'
    "（5.0 起移除了顶层 ChromiumPage，需要改造 browser 子系统才能支持，尚未适配。）"
)

try:  # pragma: no cover - 依赖存在与否决定分支
    from DrissionPage import ChromiumOptions, ChromiumPage
    from DrissionPage._pages.chromium_base import ChromiumBase
    from DrissionPage.errors import PageDisconnectedError

    DRISSIONPAGE_AVAILABLE = True
    DRISSIONPAGE_IMPORT_ERROR: ImportError | None = None
except ImportError as exc:  # pragma: no cover - 兼容路径
    ChromiumOptions = None  # type: ignore[assignment]
    ChromiumPage = None  # type: ignore[assignment]
    ChromiumBase = None  # type: ignore[assignment]

    class PageDisconnectedError(Exception):  # type: ignore[no-redef]
        """DrissionPage 不可用时的占位异常（永远不会被真正抛出）。"""

    DRISSIONPAGE_AVAILABLE = False
    DRISSIONPAGE_IMPORT_ERROR = exc


def require_drissionpage() -> None:
    """在真正驱动浏览器前调用；不可用时抛出带修复指引的 RuntimeError。"""

    if not DRISSIONPAGE_AVAILABLE:
        raise RuntimeError(f"{DRISSIONPAGE_HINT}（原始错误：{DRISSIONPAGE_IMPORT_ERROR}）")


__all__ = [
    "ChromiumBase",
    "ChromiumOptions",
    "ChromiumPage",
    "DRISSIONPAGE_AVAILABLE",
    "DRISSIONPAGE_HINT",
    "DRISSIONPAGE_IMPORT_ERROR",
    "PageDisconnectedError",
    "require_drissionpage",
]
