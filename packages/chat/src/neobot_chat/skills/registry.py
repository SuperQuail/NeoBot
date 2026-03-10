from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)
_SKILL_FILENAME = "SKILL.md"


@dataclass(frozen=True)
class Skill:
    """一个已加载的 Skill"""

    name: str
    description: str
    content: str
    path: Path
    keywords: str = ""


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

    def __post_init__(self):
        self.root = Path(self.root)

    # ── 公共 API ──

    def discover(self) -> SkillRegistry:
        """扫描 root 下所有 SKILL.md 并加载"""
        self._skills.clear()
        if not self.root.is_dir():
            return self
        for md_path in sorted(self.root.rglob(_SKILL_FILENAME)):
            skill = self._load(md_path)
            if skill:
                self._skills[skill.name] = skill
        return self

    @property
    def skills(self) -> dict[str, Skill]:
        return dict(self._skills)

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def match(self, query: str) -> list[Skill]:
        """根据查询文本匹配相关 skills（基于 description 关键词）"""
        if not self._skills:
            return []
        q = query.lower()
        return [s for s in self._skills.values() if self._is_relevant(s, q)]

    @staticmethod
    def format_skills_xml(skills: list[Skill]) -> str:
        """将 skills 格式化为 XML 片段（仅元数据）"""
        if not skills:
            return ""
        sections = "\n".join(
            f'<skill name="{s.name}" description="{s.description}" skill_dir="{s.path.parent.absolute()}" />'
            for s in skills
        )
        return f"<skills>\n{sections}\n</skills>"

    @staticmethod
    def build_system_prompt(
            instructions: str = "",
            skills: list[Skill] | None = None,
    ) -> str:
        """组装完整的 system prompt（XML 结构）"""
        parts: list[str] = []
        if instructions:
            parts.append(f"<instructions>\n{instructions}\n</instructions>")
        if skills:
            parts.append(
                "当需要使用 skill 时，先用工具读取 skill_dir 下的 SKILL.md 文件获取完整说明。\n"
                "SKILL.md 中的相对路径（如 scripts/analyze.py）相对于 skill_dir。\n\n"
                + SkillRegistry.format_skills_xml(skills)
            )
        if not parts:
            return ""
        return "<system>\n" + "\n\n".join(parts) + "\n</system>"

    # ── 内部方法 ──

    @staticmethod
    def _load(path: Path) -> Skill | None:
        text = path.read_text(encoding="utf-8")
        m = _FRONTMATTER_RE.match(text)
        if not m:
            return None

        metadata: dict[str, str] = {}
        for line in m.group(1).splitlines():
            key, _, value = line.partition(":")
            if value:
                metadata[key.strip()] = value.strip()

        name = metadata.get("name")
        if not name:
            return None

        return Skill(
            name=name,
            description=metadata.get("description", ""),
            content=m.group(2),
            path=path,
            keywords=metadata.get("keywords", ""),
        )

    @staticmethod
    def _is_relevant(skill: Skill, query_lower: str) -> bool:
        """关键词匹配：仅使用 keywords，为空则不匹配"""
        if not skill.keywords:
            return False
        words = [w for w in skill.keywords.lower().split() if len(w) >= 2]
        return any(w in query_lower for w in words)
