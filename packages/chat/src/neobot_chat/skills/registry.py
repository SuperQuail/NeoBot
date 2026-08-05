from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import yaml
from yaml.tokens import DocumentStartToken

from neobot_chat.utils.xml import XmlNode

_FRONTMATTER_OPEN_RE = re.compile(r"\A---[ \t]*(?:\r?\n)")
_FRONTMATTER_DELIMITER_RE = re.compile(r"---[ \t]*")
_SKILL_FILENAME = "SKILL.md"
_MAX_MANIFEST_BYTES = 128 * 1024
# 关键词按空白与常见标点（含中文标点）切分，兼容 "weather, forecast"、"菜谱、烹饪" 等写法
_KEYWORD_SPLIT_RE = re.compile(r"[\s,.;:!?()\[\]{}'\"`、，。；：？！]+")
# Agent Skills 标准：name 必须为 kebab-case、包含字母，长度不超过 64
_SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_MAX_SKILL_NAME_LENGTH = 64
_MAX_SKILL_DESCRIPTION_LENGTH = 2048
_MAX_KEYWORDS_LENGTH = 2048
_MAX_KEYWORD_COUNT = 64
# 与 modloader 侧一致：license / compatibility 长度上限 256
_MAX_LICENSE_LENGTH = 256
_MAX_COMPATIBILITY_LENGTH = 256
_FINAL_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_MAX_DISCOVERY_ERROR_LENGTH = 500


def validate_skill_name(name: Any) -> str:
    """校验 Skill 名称：必须为 kebab-case、包含字母且长度不超过 64。

    非法时抛带上下文的 ValueError，供 register_many / _load 复用。
    """
    if (
        not isinstance(name, str)
        or not _SKILL_NAME_RE.fullmatch(name)
        or not any("a" <= char <= "z" for char in name)
        or len(name) > _MAX_SKILL_NAME_LENGTH
    ):
        raise ValueError(
            f"invalid skill name: {name!r} (must be kebab-case, contain a letter, "
            f"<= {_MAX_SKILL_NAME_LENGTH} chars)"
        )
    return name


def normalize_keywords(value: Any) -> str:
    """把 keywords 规范化为空格分隔字符串并限制匹配成本。"""
    if isinstance(value, str):
        normalized = value
    elif isinstance(value, (list, tuple)):
        if len(value) > _MAX_KEYWORD_COUNT:
            raise ValueError(f"keywords 超过 {_MAX_KEYWORD_COUNT} 项限制")
        normalized = " ".join(str(item) for item in value)
    else:
        normalized = ""
    if len(normalized) > _MAX_KEYWORDS_LENGTH:
        raise ValueError(f"keywords 超过 {_MAX_KEYWORDS_LENGTH} 字符限制")
    keyword_count = sum(1 for word in _KEYWORD_SPLIT_RE.split(normalized) if word)
    if keyword_count > _MAX_KEYWORD_COUNT:
        raise ValueError(f"keywords 超过 {_MAX_KEYWORD_COUNT} 项限制")
    return normalized


def normalize_allowed_tools(value: Any) -> tuple[str, ...]:
    """把 allowed-tools 规范化为经过最终工具名校验的元组。

    与 modloader 侧规则一致：字符串先按逗号切分，再对每段按空白二次切分；
    列表/元组分支逐项 trim、去空（不按空白二次切分）。
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


def normalize_compatibility(value: Any) -> str:
    """把 compatibility 字段规范化为字符串（兼容字符串与列表）。"""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value)
    return ""


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
    if len(detail) > _MAX_DISCOVERY_ERROR_LENGTH:
        return f"{detail[: _MAX_DISCOVERY_ERROR_LENGTH - 3]}..."
    return detail or type(exc).__name__


def _format_discovery_error(path: Path, exc: BaseException) -> str:
    return f"{path}: {type(exc).__name__}: {_exception_detail(exc)}"


@dataclass(frozen=True)
class Skill:
    """一个已加载的 Skill（遵循 Agent Skills 标准字段）"""

    name: str
    description: str
    content: str
    path: Path
    keywords: str = ""
    owner: str = ""
    license: str = ""
    compatibility: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    allowed_tools: tuple[str, ...] = ()

    @property
    def qualified_name(self) -> str:
        return f"{self.owner}:{self.name}" if self.owner else self.name


@dataclass
class SkillRegistry:
    """从目录中发现并管理 SKILL.md 文件

    目录结构::

        skills/
        ├── weather-analysis/
        │   └── SKILL.md
        └── code-review/
            └── SKILL.md
    """

    root: Path
    _skills: dict[str, Skill] = field(default_factory=dict, init=False, repr=False)
    _errors: list[str] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self):
        self.root = Path(self.root)

    def discover(self) -> SkillRegistry:
        """扫描 root 下所有 SKILL.md，跳过并记录单文件错误。"""
        staged: dict[str, Skill] = {}
        source_paths: dict[str, Path] = {}
        errors: list[str] = []
        if not self.root.is_dir():
            self._skills = staged
            self._errors = errors
            return self
        for md_path in sorted(self.root.rglob(_SKILL_FILENAME)):
            # 跳过 __pycache__ 等构建产物目录里的文件（与 modloader 扫描一致）
            if "__pycache__" in md_path.parts:
                continue
            try:
                skill = self._load(md_path)
            except Exception as exc:
                errors.append(_format_discovery_error(md_path, exc))
                continue
            if skill.name in staged:
                errors.append(
                    f"{md_path}: duplicate skill name {skill.name!r}; "
                    f"keeping {source_paths[skill.name]}"
                )
                continue
            staged[skill.name] = skill
            source_paths[skill.name] = md_path
        self._skills = staged
        self._errors = errors
        return self

    @property
    def skills(self) -> dict[str, Skill]:
        return dict(self._skills)

    @property
    def errors(self) -> tuple[str, ...]:
        """最近一次 discover() 中被跳过文件的有界诊断。"""
        return tuple(self._errors)

    def get(self, name: str) -> Skill | None:
        """按全局名或裸名查找 Skill。

        兼容两种 key 来源：discover() 以裸 name 为 key，
        register_many() 以 ``owner:name`` 为 key。
        """
        skill = self._skills.get(name)
        if skill is not None:
            return skill
        for candidate in self._skills.values():
            if candidate.qualified_name == name:
                return candidate
        if ":" not in name:
            for candidate in self._skills.values():
                if candidate.name == name:
                    return candidate
        return None

    def register_many(self, owner: str, skills: Sequence[Any]) -> None:
        """以 ``owner`` 名义批量注册 Skill，全局名为 ``{owner}:{name}``。

        接受任意鸭子类型对象（含 name/description/content/path 等属性），
        内部统一构建标准 ``Skill``。任何一项冲突（owner 非法、name 非法、
        全局名已存在）都会整体失败，不会留下半成品状态。
        """
        if not owner or ":" in owner:
            raise ValueError(f"invalid skill owner: {owner!r}")
        staged: dict[str, Skill] = {}
        for skill in skills:
            converted = _to_skill(skill, owner=owner)
            qualified = converted.qualified_name
            if qualified in self._skills or qualified in staged:
                raise ValueError(f"Skill 已注册: {qualified}")
            staged[qualified] = converted
        self._skills.update(staged)

    def unregister_owner(self, owner: str) -> list[str]:
        """注销某个 owner 的全部 Skill，返回被移除的全局名。"""
        prefix = f"{owner}:"
        removed = [name for name in self._skills if name.startswith(prefix)]
        for name in removed:
            self._skills.pop(name, None)
        return removed

    def match(self, query: str, limit: int | None = None) -> list[Skill]:
        """根据查询文本匹配相关 skills（基于 keywords 关键词）。

        按命中关键词数降序排序后再截取 limit，保证 limit 命中时优先返回
        最相关的技能；同分技能保持注册顺序（排序稳定）。
        """
        if not self._skills:
            return []
        q = query.lower()
        matched = sorted(
            (s for s in self._skills.values() if self._is_relevant(s, q)),
            key=lambda s: self._match_score(s, q),
            reverse=True,
        )
        if limit is not None:
            return matched[:limit]
        return matched

    @staticmethod
    def format_skills_xml(skills: list[Skill]) -> str:
        """将 skills 格式化为 XML 片段（仅元数据）"""
        if not skills:
            return ""
        node = XmlNode(
            "skills",
            children=[
                XmlNode(
                    "skill",
                    attributes={
                        "name": s.name,
                        "description": s.description,
                        "skill_dir": str(s.path.parent.absolute()),
                    },
                    self_closing=True,
                )
                for s in skills
            ],
        )
        return node.to_xml()

    @staticmethod
    def parse_frontmatter(text: str) -> tuple[dict[str, Any] | None, str]:
        """解析 SKILL.md 的 YAML frontmatter。

        返回 (metadata, body)。没有合法 frontmatter 时 metadata 为 None。
        """
        try:
            return _parse_frontmatter(text)
        except Exception:
            return None, text

    @staticmethod
    def _load(path: Path) -> Skill:
        if path.stat().st_size > _MAX_MANIFEST_BYTES:
            raise ValueError(f"文件超过 {_MAX_MANIFEST_BYTES} 字节限制")
        # utf-8-sig 兼容带 BOM 的 SKILL.md（Windows 编辑器常见）
        text = path.read_text(encoding="utf-8-sig")
        metadata, body = _parse_frontmatter(text)

        raw_name = metadata.get("name")
        name = validate_skill_name(raw_name)
        # Agent Skills 标准：name 必须与 SKILL.md 所在目录同名
        if path.parent.name != name:
            raise ValueError(f"name {name!r} 与父目录名 {path.parent.name!r} 不一致")

        description = metadata.get("description")
        if not isinstance(description, str) or not description.strip():
            raise ValueError("description 必填且必须是非空字符串")
        if len(description) > _MAX_SKILL_DESCRIPTION_LENGTH:
            raise ValueError(
                f"description 超过 {_MAX_SKILL_DESCRIPTION_LENGTH} 字符限制"
            )

        # metadata 必须是 dict 且所有键必须为字符串，否则拒绝
        raw_metadata = metadata.get("metadata")
        if raw_metadata is not None:
            if not isinstance(raw_metadata, dict):
                raise ValueError("metadata 必须是 dict")
            if not all(isinstance(key, str) for key in raw_metadata):
                raise ValueError("metadata 的键必须均为字符串")

        # 与 modloader 侧一致：license / compatibility 超过 256 字符拒绝
        license_value = str(metadata.get("license", "") or "")
        if len(license_value) > _MAX_LICENSE_LENGTH:
            raise ValueError(f"license 超过 {_MAX_LICENSE_LENGTH} 字符限制")
        compatibility_value = normalize_compatibility(metadata.get("compatibility", ""))
        if len(compatibility_value) > _MAX_COMPATIBILITY_LENGTH:
            raise ValueError(f"compatibility 超过 {_MAX_COMPATIBILITY_LENGTH} 字符限制")
        keywords = normalize_keywords(metadata.get("keywords", ""))
        allowed_tools = normalize_allowed_tools(metadata.get("allowed-tools", ()))

        return Skill(
            name=name,
            description=description,
            content=body,
            path=path,
            keywords=keywords,
            license=license_value,
            compatibility=compatibility_value,
            metadata=dict(raw_metadata) if isinstance(raw_metadata, dict) else {},
            allowed_tools=allowed_tools,
        )

    @staticmethod
    def _is_relevant(skill: Skill, query_lower: str) -> bool:
        """关键词匹配：仅使用 keywords，为空则不匹配"""
        return SkillRegistry._match_score(skill, query_lower) > 0

    @staticmethod
    def _match_score(skill: Skill, query_lower: str) -> int:
        """查询命中该 skill 的关键词数（用于相关度排序）。"""
        if not skill.keywords:
            return 0
        words = [
            w for w in _KEYWORD_SPLIT_RE.split(skill.keywords.lower()) if len(w) >= 2
        ]
        return sum(1 for w in words if w in query_lower)


def _to_skill(skill: Any, *, owner: str) -> Skill:
    """把协议对象转换为标准 Skill（校验规则与 _load 保持一致）。"""
    name = validate_skill_name(getattr(skill, "name", None))
    raw_path = getattr(skill, "path", None)
    if raw_path is None or (isinstance(raw_path, str) and not raw_path.strip()):
        raise ValueError(f"Skill 缺少有效的 path 字段: {skill!r}")
    try:
        path = Path(raw_path)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Skill path 非法: {raw_path!r}") from exc
    description = getattr(skill, "description", None)
    if not isinstance(description, str) or not description.strip():
        raise ValueError(f"Skill description 不能为空: {skill!r}")
    if len(description) > _MAX_SKILL_DESCRIPTION_LENGTH:
        raise ValueError(
            f"Skill description 超过 {_MAX_SKILL_DESCRIPTION_LENGTH} 字符限制: {skill!r}"
        )
    raw_metadata = getattr(skill, "metadata", None)
    if raw_metadata is None:
        raw_metadata = {}
    if not isinstance(raw_metadata, dict):
        raise ValueError(f"Skill metadata 必须是 dict: {skill!r}")
    if not all(isinstance(key, str) for key in raw_metadata):
        raise ValueError(f"Skill metadata 键必须均为字符串: {skill!r}")
    metadata = dict(raw_metadata)
    license_value = str(getattr(skill, "license", "") or "")
    if len(license_value) > _MAX_LICENSE_LENGTH:
        raise ValueError(
            f"Skill license 超过 {_MAX_LICENSE_LENGTH} 字符限制: {skill!r}"
        )
    compatibility_value = normalize_compatibility(getattr(skill, "compatibility", ""))
    if len(compatibility_value) > _MAX_COMPATIBILITY_LENGTH:
        raise ValueError(
            f"Skill compatibility 超过 {_MAX_COMPATIBILITY_LENGTH} 字符限制: {skill!r}"
        )
    keywords = normalize_keywords(getattr(skill, "keywords", ""))
    allowed_tools = normalize_allowed_tools(getattr(skill, "allowed_tools", ()))
    return Skill(
        name=name,
        description=description,
        content=str(getattr(skill, "content", "") or ""),
        path=path,
        keywords=keywords,
        owner=owner,
        license=license_value,
        compatibility=compatibility_value,
        metadata=metadata,
        allowed_tools=allowed_tools,
    )
