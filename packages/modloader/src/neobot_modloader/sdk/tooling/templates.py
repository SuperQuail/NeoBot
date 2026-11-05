"""从独立模板仓库复制唯一工程，不执行仓库内的生成脚本。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .files import project_files, safe_relative_path
from .models import ToolingError

_TEXT_SUFFIXES = {".py", ".toml", ".json", ".js", ".mjs", ".css", ".html", ".md", ".yml", ".yaml"}


def instantiate_template(repository: Path, destination: Path, name: str) -> None:
    """模板以有限文本标记替换名称，文件边界与打包检查一致。"""
    repository = repository.resolve()
    document = json.loads((repository / "template.json").read_text(encoding="utf-8-sig"))
    if not isinstance(document, dict) or document.get("schema_version") != 2:
        raise ToolingError("template.json: 请使用 schema_version = 2 的单模板仓库")
    if "variants" in document or "default" in document:
        raise ToolingError("template.json: 单模板仓库不能再声明 variants 或 default")
    recipe = safe_relative_path(repository, document.get("template"), label="template.path")
    if not recipe.is_dir():
        raise ToolingError("template.path: 模板目录不存在")
    for source in project_files(recipe):
        relative = source.relative_to(recipe)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix.casefold() in _TEXT_SUFFIXES:
            content = source.read_text(encoding="utf-8-sig").replace("__PLUGIN_NAME__", name)
            target.write_text(content, encoding="utf-8", newline="\n")
        else:
            shutil.copyfile(source, target)
