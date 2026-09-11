"""插件之间的依赖声明：名字 + 可选版本约束。

plugin.toml 的 dependencies 与 Plugin(dependencies=[...]) 支持：

.. code-block:: toml

    dependencies = ["dashboard>=1.0.0", "metrics>=1.2,<2.0"]

- 只写名字（"dashboard"）= 任意版本；
- 支持 >= <= == != > < ~= ，逗号分隔的多个约束取「与」；
- ~=1.4.2 等价于 >=1.4.2, <1.5.0（兼容发布语义）；
- 版本号只比较数字段（1.0.0-alpha.1 按 1.0.0 处理），与 min_neobot_version
  的既有语义保持一致；
- 任一版本无法比较时返回 None，调用方按「满足」处理并记录告警：
  源码运行、自研版本号等情况不应该把插件直接拦死。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from neobot_modloader.plugins.registration import validate_plugin_name
from neobot_modloader.version import compare_plugin_versions, parse_version

#: 依赖名 + 约束的拆分；名字部分与 validate_plugin_name 的字符集一致
_DEPENDENCY_RE = re.compile(r"^(?P<name>[A-Za-z0-9_.-]{1,64})\s*(?P<specifier>.*)$")
#: 单条约束：可选操作符 + 版本号
_CLAUSE_RE = re.compile(r"^(?P<operator>>=|<=|==|!=|~=|>|<)?\s*(?P<version>[0-9][0-9A-Za-z.\-+]*)$")


class PluginDependencyError(RuntimeError):
    """前置插件缺失、未就绪或版本不满足。"""


@dataclass(frozen=True, slots=True)
class PluginDependency:
    """一条插件依赖声明。"""

    name: str
    specifier: str = ""
    raw: str = ""

    def describe(self) -> str:
        """用于日志与面板展示的文本（dashboard>=1.0.0）。"""
        return self.raw or f"{self.name}{self.specifier}"

    def matches(self, version: str | None) -> bool | None:
        """判断某个版本是否满足本依赖；None 表示无法比较。"""
        return version_satisfies(version, self.specifier)

    def __str__(self) -> str:  # pragma: no cover - 便于调试输出
        return self.describe()


def parse_dependency(value: str) -> PluginDependency:
    """解析一条依赖声明；格式非法时抛 ValueError。"""
    if not isinstance(value, str):
        raise TypeError("插件依赖声明必须是字符串")
    text = value.strip()
    if not text:
        raise ValueError("插件依赖声明不能为空")
    match = _DEPENDENCY_RE.match(text)
    if match is None:
        raise ValueError(f"非法的插件依赖声明: {value!r}")
    name = match.group("name")
    validate_plugin_name(name)
    specifier = match.group("specifier").strip()
    if specifier:
        _validate_specifier(name, specifier)
    return PluginDependency(name=name, specifier=specifier, raw=text)


def parse_dependencies(values: Iterable[str] | None) -> tuple[PluginDependency, ...]:
    """解析依赖列表；按声明顺序返回，同名依赖只允许出现一次。"""
    if values is None:
        return ()
    if isinstance(values, (str, bytes)):
        raise TypeError("插件依赖声明必须是字符串列表，而不是单个字符串")
    parsed: list[PluginDependency] = []
    seen: set[str] = set()
    for item in values:
        dependency = parse_dependency(item)
        if dependency.name in seen:
            raise ValueError(f"重复的插件依赖声明: {dependency.name}")
        seen.add(dependency.name)
        parsed.append(dependency)
    return tuple(parsed)


def format_dependency(name: str, specifier: str = "") -> str:
    """拼回依赖声明文本。"""
    return f"{name}{specifier}"


def _validate_specifier(name: str, specifier: str) -> None:
    clauses = [clause.strip() for clause in specifier.split(",") if clause.strip()]
    if not clauses:
        raise ValueError(f"插件依赖 {name} 的版本约束为空: {specifier!r}")
    for clause in clauses:
        if _CLAUSE_RE.match(clause) is None:
            raise ValueError(f"插件依赖 {name} 的版本约束非法: {clause!r}")


def version_satisfies(version: str | None, specifier: str = "") -> bool | None:
    """判断版本是否满足约束串。

    Returns:
        True / False 表示可比较的结果；None 表示版本或约束无法比较
        （调用方应放行并记录告警）。
    """
    spec = str(specifier or "").strip()
    if not spec:
        return True
    if parse_version(version) is None:
        return None
    verdict: bool | None = True
    for clause in (item.strip() for item in spec.split(",")):
        if not clause:
            continue
        match = _CLAUSE_RE.match(clause)
        if match is None:
            return None
        result = _clause_satisfied(
            version, match.group("operator") or "==", match.group("version")
        )
        if result is False:
            return False
        if result is None:
            verdict = None
    return verdict


def _clause_satisfied(version: str | None, operator: str, target: str) -> bool | None:
    if operator == "~=":
        return _compatible_release_satisfied(version, target)
    comparison = compare_plugin_versions(version, target)
    if comparison is None:
        return None
    if operator == ">=":
        return comparison >= 0
    if operator == "<=":
        return comparison <= 0
    if operator == "==":
        return comparison == 0
    if operator == "!=":
        return comparison != 0
    if operator == ">":
        return comparison > 0
    if operator == "<":
        return comparison < 0
    return None


def _compatible_release_satisfied(version: str | None, target: str) -> bool | None:
    """~=1.4.2 等价于 >=1.4.2, <1.5.0；~=1.4 等价于 >=1.4, <2.0。"""
    target_parts = parse_version(target)
    if target_parts is None or not target_parts:
        return None
    lower = compare_plugin_versions(version, target)
    if lower is None:
        return None
    if lower < 0:
        return False
    prefix = list(target_parts[:-1])
    if not prefix:
        prefix = [0]
    prefix[-1] += 1
    upper = ".".join(str(part) for part in prefix)
    upper_comparison = compare_plugin_versions(version, upper)
    if upper_comparison is None:
        return None
    return upper_comparison < 0


__all__ = [
    "PluginDependency",
    "PluginDependencyError",
    "format_dependency",
    "parse_dependencies",
    "parse_dependency",
    "version_satisfies",
]
