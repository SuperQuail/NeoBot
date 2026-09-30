"""依赖边界策略：上界必须存在、预发布必须被关掉、版本号必须是正式版。

背景：1.0.0 在新环境部署启动即崩 —— drissionpage>=4.1 没有上界，
而部署侧以「允许预发布」的语义解析，选中了删掉 ChromiumPage 的 5.0.0b1。
一次事故三处教训，各自用一条用例钉住：

1. 直接依赖必须有上界（否则下一次大版本破坏性改版会重演）；
2. [tool.uv].prerelease 必须是 disallow（否则换台机器/换个环境变量就解出 beta）；
3. 版本号必须是正式版（预发布版发出去，用户装到的就是未验证的东西）。
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

#: 工作区内部包：由 uv workspace 管理，不加版本上界
_WORKSPACE_PACKAGES = {
    "neobot",
    "neobot-app",
    "neobot-adapter",
    "neobot-chat",
    "neobot-contracts",
    "neobot-memory",
    "neobot-modloader",
    "neobot-storage",
}

_MANIFESTS = [
    "pyproject.toml",
    "app/pyproject.toml",
    "packages/adapter/pyproject.toml",
    "packages/chat/pyproject.toml",
    "packages/contracts/pyproject.toml",
    "packages/memory/pyproject.toml",
    "packages/modloader/pyproject.toml",
    "packages/storage/pyproject.toml",
]


def _load(rel: str) -> dict:
    return tomllib.loads((REPO_ROOT / rel).read_text(encoding="utf-8"))


def _requirements(data: dict) -> list[tuple[str, list[str]]]:
    """收集所有依赖清单：(组名, 条目列表)。"""

    groups: list[tuple[str, list[str]]] = []
    project = data.get("project") or {}
    groups.append(("project.dependencies", project.get("dependencies") or []))
    for name, entries in (project.get("optional-dependencies") or {}).items():
        groups.append((f"project.optional-dependencies.{name}", entries))
    for name, entries in (data.get("dependency-groups") or {}).items():
        groups.append((f"dependency-groups.{name}", entries))
    return groups


@pytest.mark.parametrize("rel", _MANIFESTS)
def test_direct_dependencies_have_upper_bounds(rel: str) -> None:
    """每个直接依赖都必须写上界。

    没有上界 = 把「下一个大版本会不会破坏我们」交给运气。DrissionPage 5.0 已经
    演示过一次代价：新装环境直接起不来。
    """

    missing: list[str] = []
    for group_name, entries in _requirements(_load(rel)):
        for entry in entries:
            package = entry.strip().split(";")[0].strip()
            match = re.match(r"^([A-Za-z0-9_.\-]+)", package)
            if not match:
                continue
            if match.group(1).lower().replace("_", "-") in _WORKSPACE_PACKAGES:
                continue
            if "<" not in package and "==" not in package and "~=" not in package:
                missing.append(f"{group_name}: {package}")

    assert not missing, f"{rel} 里这些依赖没有上界（大版本破坏性改版会直接被装进来）：{missing}"


def test_prerelease_is_disallowed() -> None:
    """必须显式 disallow：否则换个解析语义就会选中 beta（本次事故的引子）。"""

    data = _load("pyproject.toml")
    uv_config = (data.get("tool") or {}).get("uv") or {}
    assert uv_config.get("prerelease") == "disallow", (
        "pyproject.toml 的 [tool.uv].prerelease 必须是 disallow："
        "allow / if-necessary 在换机器或换环境变量时会解出预发布版本"
    )


@pytest.mark.parametrize("rel", _MANIFESTS)
def test_versions_are_stable_releases(rel: str) -> None:
    """版本号必须是正式版：带 a/b/rc 的预发布不应出现在 main 上。"""

    version = (_load(rel).get("project") or {}).get("version")
    assert version, f"{rel} 缺少 version"
    assert re.fullmatch(r"\d+\.\d+\.\d+", version), (
        f"{rel} 的版本 {version!r} 不是正式版（形如 X.Y.Z，不带 a1/b1/rc1）"
    )
