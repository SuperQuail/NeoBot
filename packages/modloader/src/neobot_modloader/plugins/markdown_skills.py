"""插件目录 SKILL.md 的扫描、解析与注册。

约定：插件目录下的 ``skills/**/SKILL.md`` 会被视为插件的 Markdown 技能，
以 ``{plugin_name}:{local_name}`` 的全局名注册进共享的 Markdown Skill 注册表，
供主聊天在构建提示词时匹配注入。

frontmatter 遵循 Agent Skills 开放标准（agentskills.org）：
必填 ``name`` / ``description``，可选 ``license`` / ``compatibility`` /
``metadata`` / ``allowed-tools``；``keywords`` 为 NeoBot 扩展字段，用于关键词匹配。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from yaml.tokens import DocumentStartToken

_FRONTMATTER_OPEN_RE = re.compile(r"\A---[ \t]*(?:\r?\n)")
_FRONTMATTER_DELIMITER_RE = re.compile(r"---[ \t]*")
_SKILL_FILENAME = "SKILL.md"
_MAX_MANIFEST_BYTES = 128 * 1024
# Agent Skills 标准：name 必须为 kebab-case 且至少包含一个小写字母
_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_MAX_NAME_CHARS = 64
_MAX_DESCRIPTION_CHARS = 2048
_KEYWORD_SPLIT_RE = re.compile(r"[\s,.;:!?()\[\]{}'\"`、，。；：？！]+")
_MAX_KEYWORDS_CHARS = 2048
_MAX_KEYWORD_COUNT = 64
_MAX_LICENSE_CHARS = 256
_MAX_COMPATIBILITY_CHARS = 256
_FINAL_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_MAX_ERROR_CHARS = 500


@dataclass(frozen=True)
class PluginSkill:
    name: str
    description: str
    keywords: str
    content: str
    path: Path
    license: str = ""
    compatibility: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    allowed_tools: tuple[str, ...] = ()


def scan_plugin_skills(plugin_dir: Path) -> tuple[list[PluginSkill], list[str]]:
    """扫描 ``<plugin_dir>/skills/**/SKILL.md``。

    返回 (skills, errors)；解析失败或格式非法的文件只会进入 errors，
    不会中止其他文件的扫描。
    """
    skills_root = Path(plugin_dir) / "skills"
    skills: list[PluginSkill] = []
    source_paths: dict[str, Path] = {}
    errors: list[str] = []
    if not skills_root.is_dir():
        return skills, errors
    for md_path in sorted(skills_root.rglob(_SKILL_FILENAME)):
        # 只匹配 SKILL.md 文件名；__pycache__ 等构建产物目录里的文件一律跳过
        if "__pycache__" in md_path.parts:
            continue
        try:
            skill = _load_skill_file(md_path)
        except Exception as exc:
            errors.append(_format_scan_error(md_path, exc))
            continue
        if skill.name in source_paths:
            errors.append(
                f"{md_path}: duplicate skill name {skill.name!r}; "
                f"keeping {source_paths[skill.name]}"
            )
            continue
        skills.append(skill)
        source_paths[skill.name] = md_path
    return skills, errors


def _load_skill_file(path: Path) -> PluginSkill:
    size = path.stat().st_size
    if size > _MAX_MANIFEST_BYTES:
        raise ValueError(f"文件超过 {_MAX_MANIFEST_BYTES} 字节限制")
    # utf-8-sig 兼容带 BOM 的 SKILL.md（Windows 编辑器常见）
    text = path.read_text(encoding="utf-8-sig")
    metadata, body = _parse_frontmatter(text)
    name = metadata.get("name")
    if (
        not isinstance(name, str)
        or not _NAME_RE.fullmatch(name)
        or not any("a" <= char <= "z" for char in name)
        or len(name) > _MAX_NAME_CHARS
    ):
        raise ValueError(
            f"name 必须为 kebab-case（小写字母/数字/连字符）、至少包含一个字母"
            f"且不超过 {_MAX_NAME_CHARS} 字符: {name!r}"
        )
    if name != path.parent.name:
        raise ValueError(f"name {name!r} 与父目录名 {path.parent.name!r} 不一致")
    description = metadata.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ValueError("description 必填且不能为空")
    if len(description) > _MAX_DESCRIPTION_CHARS:
        raise ValueError(f"description 超过 {_MAX_DESCRIPTION_CHARS} 字符限制")
    raw_metadata = metadata.get("metadata")
    if raw_metadata is not None and (
        not isinstance(raw_metadata, dict)
        or not all(isinstance(key, str) for key in raw_metadata)
    ):
        raise ValueError("metadata 必须是 dict 且所有键均为字符串")
    license_value = str(metadata.get("license", "") or "")
    if len(license_value) > _MAX_LICENSE_CHARS:
        raise ValueError(f"license 超过 {_MAX_LICENSE_CHARS} 字符限制")
    compatibility_value = _normalize_compatibility(metadata.get("compatibility", ""))
    if len(compatibility_value) > _MAX_COMPATIBILITY_CHARS:
        raise ValueError(f"compatibility 超过 {_MAX_COMPATIBILITY_CHARS} 字符限制")
    keywords = _normalize_keywords(metadata.get("keywords", ""))
    allowed_tools = _normalize_allowed_tools(metadata.get("allowed-tools", ()))
    return PluginSkill(
        name=name,
        description=description,
        keywords=keywords,
        content=body,
        path=path,
        license=license_value,
        compatibility=compatibility_value,
        metadata=(
            dict(metadata["metadata"])
            if isinstance(metadata.get("metadata"), dict)
            else {}
        ),
        allowed_tools=allowed_tools,
    )


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """用 YAML token 定位关闭分隔符，避免把标量内容当作 frontmatter 结尾。"""
    if text.startswith("\ufeff"):
        text = text[1:]
    opening = _FRONTMATTER_OPEN_RE.match(text)
    if opening is None:
        raise ValueError("缺少 frontmatter 开始分隔符")

    closing_start: int | None = None
    document_count = 0
    try:
        for token in yaml.scan(text, Loader=yaml.SafeLoader):
            if not isinstance(token, DocumentStartToken):
                continue
            document_count += 1
            if document_count == 2:
                closing_start = token.start_mark.index
                break
    except yaml.YAMLError as exc:
        raise ValueError(
            f"frontmatter YAML 扫描失败: {_exception_detail(exc)}"
        ) from exc
    if closing_start is None:
        raise ValueError("缺少 frontmatter 结束分隔符")

    newline_index = text.find("\n", closing_start)
    delimiter_end = len(text) if newline_index < 0 else newline_index
    delimiter = text[closing_start:delimiter_end].removesuffix("\r")
    if not _FRONTMATTER_DELIMITER_RE.fullmatch(delimiter):
        raise ValueError("frontmatter 结束分隔符必须独占一行")

    frontmatter = text[opening.end() : closing_start]
    try:
        metadata: Any = yaml.safe_load(frontmatter)
    except yaml.YAMLError as exc:
        raise ValueError(
            f"frontmatter YAML 解析失败: {_exception_detail(exc)}"
        ) from exc
    if not isinstance(metadata, dict):
        raise ValueError("frontmatter 必须是 YAML 键值映射（dict）")
    body_start = len(text) if newline_index < 0 else newline_index + 1
    return metadata, text[body_start:]


def _exception_detail(exc: BaseException) -> str:
    try:
        detail = " ".join(str(exc).split())
    except Exception:
        detail = type(exc).__name__
    if len(detail) > _MAX_ERROR_CHARS:
        return f"{detail[: _MAX_ERROR_CHARS - 3]}..."
    return detail or type(exc).__name__


def _format_scan_error(path: Path, exc: BaseException) -> str:
    return f"{path}: {type(exc).__name__}: {_exception_detail(exc)}"


def _normalize_keywords(value: Any) -> str:
    if isinstance(value, str):
        normalized = value
    elif isinstance(value, (list, tuple)):
        if len(value) > _MAX_KEYWORD_COUNT:
            raise ValueError(f"keywords 超过 {_MAX_KEYWORD_COUNT} 项限制")
        normalized = " ".join(str(item) for item in value)
    else:
        normalized = ""
    if len(normalized) > _MAX_KEYWORDS_CHARS:
        raise ValueError(f"keywords 超过 {_MAX_KEYWORDS_CHARS} 字符限制")
    keyword_count = sum(1 for word in _KEYWORD_SPLIT_RE.split(normalized) if word)
    if keyword_count > _MAX_KEYWORD_COUNT:
        raise ValueError(f"keywords 超过 {_MAX_KEYWORD_COUNT} 项限制")
    return normalized


def _normalize_allowed_tools(value: Any) -> tuple[str, ...]:
    """把 allowed-tools 规范化为经过最终工具名校验的元组。

    兼容 Agent Skills 标准的三种写法：空白分隔字符串、逗号分隔字符串、
    YAML 列表。字符串先按逗号切分，再对每段按空白二次切分。
    """
    if value is None:
        return ()
    if isinstance(value, str):
        parts = [part for chunk in value.split(",") for part in chunk.split()]
    elif isinstance(value, (list, tuple)):
        if not all(isinstance(item, str) for item in value):
            raise ValueError("allowed-tools 的每一项都必须是字符串")
        parts = list(value)
    else:
        raise ValueError("allowed-tools 必须是字符串或字符串列表")
    result: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if not _FINAL_TOOL_NAME_RE.fullmatch(part):
            display = part if len(part) <= 80 else f"{part[:77]}..."
            raise ValueError(
                f"invalid allowed-tools entry: {display!r} "
                "(must match ^[A-Za-z0-9_-]{1,64}$)"
            )
        if part not in result:
            result.append(part)
    return tuple(result)


def _normalize_compatibility(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value)
    return ""


async def bind_markdown_skills(plugin: Any, context: Any) -> None:
    """扫描插件目录中的 SKILL.md 并注册进共享注册表。"""
    registrar = getattr(context, "markdown_skills", None)
    if registrar is None or not hasattr(registrar, "register"):
        return
    if not getattr(registrar, "available", True):
        # 宿主未注入共享 Skill 注册表时跳过，插件不因技能功能缺失而加载失败
        return
    plugin_dir = getattr(context, "plugin_dir", None)
    if plugin_dir is None:
        return
    skills, errors = scan_plugin_skills(plugin_dir)
    logger = getattr(context, "logger", None)
    for error in errors:
        if logger is not None:
            logger.warning(f"插件 {plugin.name} 的 SKILL.md 跳过: {error}")
    if not skills:
        return
    # 注册失败直接抛出（与 bind_tools / bind_agents 一致），由 manager
    # 统一清理已绑定的工具与 Agent，避免留下没有技能说明的半成品插件。
    registrar.register(skills)
