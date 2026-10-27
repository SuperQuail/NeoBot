"""技能读取与按需加载工具（由 reply/tools.py 拆分）。"""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path
from typing import Any

from neobot_chat.schema.exceptions import ToolError
from neobot_chat.schema.types import ToolDefinition

from neobot_app.reply.tool_parts.common import (
    _MAX_SKILL_RESOURCE_BYTES,
    _opened_file_path,
    _path_is_within,
    _same_open_file,
    _tool_def,
)


class _SkillToolsMixin:
    def _resolve_skill(self, skill_id: str) -> Any:
        if self._skills_registry is None:
            raise ToolError("Markdown 技能注册表不可用")
        skill = self._skills_registry.skills.get(str(skill_id))
        if skill is None:
            raise ToolError(f"技能不存在或已卸载: {skill_id}")
        return skill

    def _read_skill_manifest(self, args: dict) -> str:
        skill_id = str(args.get("skill_id") or "").strip()
        if not skill_id:
            return "Error: 缺少 skill_id 参数"
        try:
            skill = self._resolve_skill(skill_id)
        except ToolError as exc:
            return f"Error: {exc}"
        return skill.content

    def _view_skill_instructions(self, args: dict) -> str:
        """返回指定内置技能的完整操作说明(按需查看)。"""
        if self._skill_manager is None:
            return "Error: SkillManager 不可用"
        skill_name = str(args.get("skill") or "").strip()
        if not skill_name:
            return "Error: 缺少 skill 参数"
        return self._skill_manager.get_skill_instructions(skill_name)

    def _deferred_skill_names(self) -> list[str]:
        """仍处于「未加载」状态的技能名；已加载的技能不再出现在下拉里。"""
        if self._activation is None:
            return []
        return self._activation.candidates()

    def _load_skill_tools(self, args: dict) -> str:
        """把一个或多个技能的工具定义加入本管线后续的模型调用。

        工具 schema 会随每次模型调用一起发送，全部常驻时开销极大；
        因此在模型明确需要某个技能时再加载，加载后本轮即可直接调用。
        """
        if self._activation is None:
            return "Error: SkillManager 不可用"
        return self._activation.load(args)

    def activated_skill_names(self) -> list[str]:
        """本管线已按需加载的技能名（用于日志/调试）。"""
        return self._activation.activated_names() if self._activation else []

    def consume_tools_dirty(self) -> bool:
        """取出并清除「工具列表已变化」标记，供调用方重建 tools。"""
        return self._activation.consume_dirty() if self._activation else False

    @staticmethod
    def _inspect_skill_resource_path(
        base: Path, target: Path
    ) -> tuple[os.stat_result | None, str | None]:
        try:
            relative = target.relative_to(base)
        except ValueError:
            return None, "outside"

        current = base
        target_stat: os.stat_result | None = None
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        try:
            for component in relative.parts:
                current /= component
                target_stat = current.lstat()
                file_attributes = getattr(target_stat, "st_file_attributes", 0)
                if stat.S_ISLNK(target_stat.st_mode) or file_attributes & reparse_flag:
                    return None, "reparse"
        except FileNotFoundError:
            return None, "missing"
        except OSError:
            return None, "read_failed"

        if target_stat is None or not stat.S_ISREG(target_stat.st_mode):
            return None, "missing"
        return target_stat, None

    @classmethod
    def _validate_open_skill_resource(
        cls, file_obj: Any, base: Path, target: Path
    ) -> tuple[os.stat_result | None, str | None]:
        try:
            opened_stat = os.fstat(file_obj.fileno())
        except (AttributeError, OSError, ValueError):
            return None, "unverifiable"
        if not stat.S_ISREG(opened_stat.st_mode):
            return None, "missing"
        link_count = getattr(opened_stat, "st_nlink", None)
        if isinstance(link_count, int) and link_count > 1:
            return None, "hard_link"

        path_stat, error = cls._inspect_skill_resource_path(base, target)
        if error is not None or path_stat is None:
            return None, error or "unverifiable"
        try:
            resolved_target = target.resolve(strict=True)
        except (OSError, RuntimeError):
            return None, "changed"
        if not _path_is_within(resolved_target, base):
            return None, "outside"

        opened_path = _opened_file_path(file_obj)
        if os.name == "nt" and opened_path is None:
            return None, "unverifiable"
        if opened_path is not None and not _path_is_within(opened_path, base):
            return None, "outside"

        if not _same_open_file(opened_stat, path_stat):
            same_resolved_path = opened_path is not None and os.path.normcase(
                os.path.abspath(opened_path)
            ) == os.path.normcase(os.path.abspath(resolved_target))
            if not same_resolved_path:
                return None, "changed"
        return opened_stat, None

    @staticmethod
    def _skill_resource_error(error: str, rel: str) -> str:
        if error == "outside":
            return f"Error: 路径越界，拒绝读取: {rel}"
        if error == "reparse":
            return f"Error: 拒绝读取 symlink/junction 路径: {rel}"
        if error == "hard_link":
            return f"Error: 拒绝读取硬链接文件: {rel}"
        if error == "missing":
            return f"Error: 文件不存在: {rel}"
        if error == "changed":
            return f"Error: 路径在读取期间发生变化，拒绝读取: {rel}"
        if error == "unverifiable":
            return f"Error: 无法安全验证文件路径，拒绝读取: {rel}"
        return f"Error: 读取失败: {rel}"

    def _read_skill_resource(self, args: dict) -> str:
        skill_id = str(args.get("skill_id") or "").strip()
        rel = str(args.get("path") or "").strip()
        if not skill_id or not rel:
            return "Error: 缺少 skill_id 或 path 参数"
        if (
            rel.startswith("/")
            or rel.startswith("\\")
            or re.match(r"^[A-Za-z]:", rel)
            or ".." in rel.replace("\\", "/").split("/")
        ):
            return "Error: 非法路径（仅允许技能目录内的相对路径）"
        try:
            skill = self._resolve_skill(skill_id)
        except ToolError as exc:
            return f"Error: {exc}"
        try:
            base = Path(skill.path.parent).resolve(strict=True)
        except (OSError, RuntimeError):
            return "Error: 技能目录不可用"
        relative_parts = [
            part for part in rel.replace("\\", "/").split("/") if part not in {"", "."}
        ]
        target = base.joinpath(*relative_parts)

        _, error = self._inspect_skill_resource_path(base, target)
        if error is not None:
            return self._skill_resource_error(error, rel)
        try:
            if not _path_is_within(target.resolve(strict=True), base):
                return self._skill_resource_error("outside", rel)
        except (OSError, RuntimeError):
            return self._skill_resource_error("read_failed", rel)

        try:
            with target.open("rb", buffering=0) as file_obj:
                opened_stat, error = self._validate_open_skill_resource(
                    file_obj, base, target
                )
                if error is not None or opened_stat is None:
                    return self._skill_resource_error(error or "unverifiable", rel)
                if opened_stat.st_size > _MAX_SKILL_RESOURCE_BYTES:
                    return f"Error: 文件超过 1MB 限制: {rel}"

                content = file_obj.read(_MAX_SKILL_RESOURCE_BYTES + 1)
                final_stat, error = self._validate_open_skill_resource(
                    file_obj, base, target
                )
                if error is not None or final_stat is None:
                    return self._skill_resource_error(error or "unverifiable", rel)
                if (
                    len(content) > _MAX_SKILL_RESOURCE_BYTES
                    or final_stat.st_size > _MAX_SKILL_RESOURCE_BYTES
                ):
                    return f"Error: 文件超过 1MB 限制: {rel}"
        except FileNotFoundError:
            return self._skill_resource_error("missing", rel)
        except (OSError, ValueError):
            return self._skill_resource_error("read_failed", rel)
        return content.decode("utf-8", errors="replace")

    def _define_skill_tools(self, tools: list[ToolDefinition]) -> None:
        if self._skills_registry is not None and getattr(
            self._skills_registry, "skills", None
        ):
            tools.append(
                _tool_def(
                    "skills__read_manifest",
                    "读取一个技能的完整说明文档（SKILL.md 正文）。"
                    "技能 id 格式为 owner:name，由提示词中的 <可用技能> 列表提供。"
                    "执行技能任务前必须先调用本工具获取说明。",
                    {
                        "properties": {
                            "skill_id": {
                                "type": "string",
                                "description": "技能 id（格式 owner:name）。",
                            },
                        },
                        "required": ["skill_id"],
                    },
                )
            )
            tools.append(
                _tool_def(
                    "skills__read_resource",
                    "读取技能目录内的参考资料（相对路径）。"
                    "仅允许技能目录内的文件，禁止绝对路径或 .. 越界。",
                    {
                        "properties": {
                            "skill_id": {
                                "type": "string",
                                "description": "技能 id（格式 owner:name）。",
                            },
                            "path": {
                                "type": "string",
                                "description": "技能目录内的相对路径，如 references/cities.md。",
                            },
                        },
                        "required": ["skill_id", "path"],
                    },
                )
            )
        if self._skill_manager is not None:
            skill_names = getattr(self._skill_manager, "skill_names", None) or []
            if skill_names:
                tools.append(
                    _tool_def(
                        "skills__view_instructions",
                        "查看某个内置技能的完整操作说明（默认只显示一行摘要）。"
                        "需要深入了解某技能的使用规则、参数细节或注意事项时调用本工具；"
                        "技能名从提示词的 <Skill 操作说明> 摘要列表中选择。",
                        {
                            "properties": {
                                "skill": {
                                    "type": "string",
                                    "enum": skill_names,
                                    "description": "技能名（如 vision_detect、image_parse）。",
                                },
                            },
                            "required": ["skill"],
                        },
                    )
                )
            loader = (
                self._activation.loader_definition()
                if self._activation is not None
                else None
            )
            if loader:
                tools.append(loader)

    def _merge_skill_tool_defs(self, tools: list[ToolDefinition]) -> None:
        # 合并 Skill 系统的工具定义：常驻技能 + 本管线已按需加载的技能。
        if self._skill_manager is not None:
            skill_tools = (
                self._activation.tools() if self._activation is not None else []
            )
            tools.extend(skill_tools)
            capture = getattr(self._skill_manager, "capture_execution_token", None)
            if callable(capture):
                tokens = dict(self._skill_tokens)
                for definition in skill_tools:
                    token = capture(definition["function"]["name"])
                    if token is not None:
                        tokens[definition["function"]["name"]] = token
                self._skill_tokens = tokens
