"""工具链统一报告，区分静态检查与会执行作者代码的操作。"""

from __future__ import annotations

from dataclasses import asdict, dataclass


class ToolingError(ValueError):
    """可直接提示开发者的工程或包错误。"""


@dataclass(frozen=True)
class ToolReport:
    command: str
    ok: bool
    checks: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    path: str | None = None
    sha256: str = ""
    executes_plugin: bool = False
    not_applicable: tuple[str, ...] = ()
    unverified: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return asdict(self)
