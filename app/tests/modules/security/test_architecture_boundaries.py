"""架构约束测试：依赖方向与分层边界。

本次改动引入了「核心 / 面板 / 热重载」三方协作，最容易退化成的形态是**反向
依赖**：核心为了照顾面板或在启动路径里特判插件，于是核心反过来依赖插件层；
或者 runtime 反过来 import bootstrap，形成环。这类问题不会让测试变红，只会让
架构慢慢烂掉，因此用机械扫描把它钉住。

规则（对应 docs/06-开发指南.md 的分层约定）：
1. 核心（runtime / bootstrap 之外的领域层）不得 import 内置插件实现；
2. runtime 不得 import bootstrap（组合根单向依赖 runtime，不能成环）；
3. 配置判定（config.availability）与连接探针（connection_readiness）
   只依赖抽象，不依赖具体适配器/Provider 实现。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
APP_SRC = ROOT / "app" / "src" / "neobot_app"

#: 内置插件（面板等）：必须是可选、可移除的，核心不得依赖它们的实现。
#: 允许依赖 ``neobot_app.builtin_plugins`` 包本身 —— 它只提供官方插件扫描目录
#: （``builtin_plugin_dirs()``），属于「列举插件位置」而非「依赖某个插件」。
#: 但 ``builtin_plugins.<name>.*`` 是具体插件实现，核心一律不得 import。
_PLUGIN_PACKAGE = "neobot_app.builtin_plugins"


def _is_plugin_implementation(module: str) -> bool:
    return module.startswith(f"{_PLUGIN_PACKAGE}.")


def _iter_modules(*roots: Path):
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            yield path


def _imported_modules(path: Path) -> set[str]:
    """收集一个文件里所有静态 import 的模块名（含 from ... import）。"""
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # 相对导入：用所在包路径还原成绝对模块名。
                package = path.relative_to(APP_SRC).parent.parts
                base = package[: len(package) - (node.level - 1)] if node.level > 1 else package
                prefix = "neobot_app." + ".".join(base)
                modules.add(f"{prefix}.{node.module}" if node.module else prefix)
            elif node.module:
                modules.add(node.module)
    return modules


def test_core_does_not_import_builtin_plugin_implementations() -> None:
    """核心层（runtime / bootstrap）不得 import 具体内置插件的实现。

    面板是可选插件：核心一旦依赖它，「禁用面板」就不再是真正的可选，
    「移除面板」更是直接起不来。面板需要的数据通过宿主服务注册表获取。
    """
    offenders: list[str] = []
    for path in _iter_modules(APP_SRC / "runtime", APP_SRC / "bootstrap"):
        for module in _imported_modules(path):
            if _is_plugin_implementation(module):
                offenders.append(f"{path.relative_to(ROOT)} -> {module}")

    assert offenders == [], "核心层出现对内置插件实现的反向依赖: " + "; ".join(offenders)


def test_runtime_does_not_import_bootstrap() -> None:
    """runtime 不得 import bootstrap：组合根单向依赖 runtime，反向即成环。"""
    offenders: list[str] = []
    for path in _iter_modules(APP_SRC / "runtime"):
        for module in _imported_modules(path):
            if module == "neobot_app.bootstrap" or module.startswith(
                "neobot_app.bootstrap."
            ):
                offenders.append(f"{path.relative_to(ROOT)} -> {module}")

    assert offenders == [], "runtime 反向依赖组合根: " + "; ".join(offenders)


@pytest.mark.parametrize(
    "module_path",
    [
        APP_SRC / "config" / "availability.py",
        APP_SRC / "runtime" / "connection_readiness.py",
        APP_SRC / "runtime" / "hot_reload_registry.py",
        APP_SRC / "runtime" / "provider_reload.py",
    ],
)
def test_policy_and_orchestration_modules_depend_on_abstractions(
    module_path: Path,
) -> None:
    """判定与编排模块只依赖抽象：不得 import 具体适配器/Provider 实现。"""
    forbidden_prefixes = (
        "neobot_adapter.onebot",
        "neobot_adapter.local",
        "neobot_chat.providers",
        "neobot_app.bootstrap",
        f"{_PLUGIN_PACKAGE}.",
    )
    offenders = [
        module
        for module in _imported_modules(module_path)
        if module.startswith(forbidden_prefixes)
    ]

    assert offenders == [], (
        f"{module_path.relative_to(ROOT)} 依赖了具体实现: " + ", ".join(sorted(offenders))
    )
