"""创建可运行工程，显式导入作者代码导出公开契约。"""

from __future__ import annotations

import contextlib
import json
import shutil
import sys
import tempfile
from importlib.resources import files
from pathlib import Path

from neobot_modloader.loader import FilesystemPluginLoader, LoadedPlugin, PluginLoadError
from neobot_modloader.loading.manifest import read_manifest
from neobot_modloader.plugins.registration import validate_plugin_name

from .models import ToolingError, ToolReport
from .validation import contract_path, read_contract

_STARTER_FILES = {
    "plugin.py.txt": "__init__.py",
    "test_plugin.py.txt": "tests/test_plugin.py",
    "README.md": "README.md",
    "AGENTS.md.txt": "AGENTS.md",
    "GUIDE.md": "GUIDE.md",
}


def export_contract(path: Path, *, check: bool = False) -> ToolReport:
    """此操作会执行插件入口，必须在可信开发环境或隔离 CI 中运行。"""
    root = Path(path).resolve()
    loader = FilesystemPluginLoader(namespace="neobot_sdk_export", enabled_resolver=lambda _name, _default: True)
    loaded = None
    try:
        metadata = read_manifest(root / "plugin.toml")
        target = contract_path(root, metadata, must_exist=False)
        with contextlib.redirect_stdout(sys.stderr):
            loaded = loader.load_one(root)
            if isinstance(loaded, PluginLoadError):
                raise ToolingError(f"插件导入失败: {loaded.error}")
            if not isinstance(loaded, LoadedPlugin):
                raise ToolingError("插件导入失败: 没有可加载入口")
            document = loaded.plugin.surface.describe(loaded.plugin)
        from neobot_modloader.sdk.contract import validate_contract

        errors = validate_contract(document)
        if errors:
            return ToolReport("export", False, errors=tuple(errors), path=str(target), executes_plugin=True)
        if check:
            if not target.is_file() or read_contract(target) != document:
                raise ToolingError("静态契约已过期，请重新执行 export 并检查差异")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            content = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
            target.write_text(content, encoding="utf-8", newline="\n")
        return ToolReport("export", True, ("contract",), path=str(target), executes_plugin=True)
    except SystemExit as exc:
        return ToolReport(
            "export", False, errors=(f"插件入口请求退出: {exc.code!r}",), path=str(root), executes_plugin=True
        )
    except Exception as exc:
        return ToolReport("export", False, errors=(str(exc),), path=str(root), executes_plugin=True)
    finally:
        if isinstance(loaded, LoadedPlugin):
            loader.clear_module_cache(loaded.module_names)


def init_project(path: Path, name: str, *, template: Path | None = None) -> ToolReport:
    """先在暂存目录生成和导出，目标已存在时保持原样。"""
    destination = Path(path).absolute()
    try:
        validate_plugin_name(name)
        if destination.exists() or destination.is_symlink():
            raise ToolingError("目标已存在，请选择一个新的插件目录")
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Windows 读取句柄可能暂时阻止删除私有暂存文件，不影响已验证目标的创建结果。
        with tempfile.TemporaryDirectory(
            prefix=".neobot-init-", dir=destination.parent, ignore_cleanup_errors=True
        ) as temporary:
            staging = Path(temporary) / name
            staging.mkdir()
            if template is not None:
                from .templates import instantiate_template

                instantiate_template(template, staging, name)
            else:
                _write_minimal_template(staging, name)
            report = export_contract(staging)
            if not report.ok:
                raise ToolingError("; ".join(report.errors))
            if template is not None:
                from .validation import check_project

                checked = check_project(staging)
                if not checked.ok:
                    raise ToolingError("; ".join(checked.errors))
            destination.mkdir()
            try:
                shutil.copytree(staging, destination, dirs_exist_ok=True)
            except BaseException:
                shutil.rmtree(destination)
                raise
        return ToolReport("init", True, ("template", "contract"), path=str(destination))
    except (OSError, ValueError) as exc:
        return ToolReport("init", False, errors=(str(exc),), path=str(destination))


def _write_minimal_template(staging: Path, name: str) -> None:
    """离线创建与独立仓库相同形状的唯一入门工程。"""
    assets = files(__package__).joinpath("starter")
    for source, relative in _STARTER_FILES.items():
        target = staging / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        content = assets.joinpath(source).read_text(encoding="utf-8").replace("__PLUGIN_NAME__", name)
        target.write_text(content, encoding="utf-8", newline="\n")
    (staging / "plugin.toml").write_text(
        f'name = "{name}"\nversion = "0.1.0"\npython_dependencies = ["pydantic>=2,<3"]\n'
        '[sdk]\nversion = 1\ncontract = "plugin.contract.json"\n',
        encoding="utf-8",
    )
    (staging / "pyproject.toml").write_text('[tool.pytest.ini_options]\nasyncio_mode = "auto"\n', encoding="utf-8")
