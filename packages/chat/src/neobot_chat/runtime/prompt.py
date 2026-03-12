from __future__ import annotations

from dataclasses import dataclass

from neobot_chat.schema.exceptions import ValidationError
from neobot_chat.skills.registry import Skill
from neobot_chat.utils.xml import XmlNode

_TOOL_POLICY_ITEMS = [
    "When the user asks you to perform actions (file operations, running commands, etc.), you MUST use the provided tool functions.",
    "Do NOT write code or commands in your text response.",
]

_SKILL_POLICY_ITEMS = [
    "当需要使用 skill 时，先用工具读取 skill_dir 下的 SKILL.md 文件获取完整说明。",
    "SKILL.md 中的相对路径（如 scripts/analyze.py）相对于 skill_dir。",
]

_SECTION_ORDER = {
    "description": 0,
    "instructions": 1,
    "tool_policy": 2,
    "tools": 3,
    "skill_policy": 4,
    "skills": 5,
    "runtime": 6,
}


@dataclass
class SystemPromptState:
    root: XmlNode

    @classmethod
    def empty(cls) -> "SystemPromptState":
        return cls(root=XmlNode("system"))

    @classmethod
    def from_messages(cls, system_messages: list[str]) -> "SystemPromptState":
        state = cls.empty()
        for message in system_messages:
            stripped = message.strip()
            if not stripped:
                continue
            if stripped.startswith("<system"):
                try:
                    state.merge_system_xml(stripped)
                    continue
                except Exception:
                    pass
            state.add_instruction(stripped)
        return state

    def merge_system_xml(self, text: str) -> None:
        incoming = XmlNode.from_xml(text)
        if incoming.tag_name != "system":
            raise ValidationError("system xml root tag must be <system>")
        for child in incoming.children:
            if child.tag_name == "instructions":
                for item in child.children:
                    if item.tag_name == "item" and (item.text or "").strip():
                        self.add_instruction(item.text or "")
                continue
            if self.root.find_child(child.tag_name) is None:
                self.root.add_child(child)

    def add_instruction(self, text: str | None) -> None:
        value = (text or "").strip()
        if not value:
            return
        instructions = self.root.ensure_child("instructions")
        for item in instructions.children:
            if item.tag_name == "item" and (item.text or "").strip() == value:
                return
        instructions.add_child(XmlNode("item", text=value))

    def set_description(self, text: str | None) -> None:
        value = (text or "").strip()
        if not value:
            return
        self.root.replace_child(XmlNode("description", text=value))

    def set_tools(self, tool_names: list[str] | None) -> None:
        if not tool_names:
            return
        self.root.replace_child(
            XmlNode(
                "tool_policy",
                children=[XmlNode("item", text=item) for item in _TOOL_POLICY_ITEMS],
            )
        )
        self.root.replace_child(
            XmlNode(
                "tools",
                children=[
                    XmlNode("tool", attributes={"name": name}, self_closing=True)
                    for name in tool_names
                ],
            )
        )

    def set_runtime(
        self,
        *,
        cwd: str | None = None,
        max_iterations: int | None = None,
        command_timeout: int | None = None,
        allowed_commands: list[str] | None = None,
    ) -> None:
        if (
            cwd is None
            and max_iterations is None
            and command_timeout is None
            and not allowed_commands
        ):
            return
        children: list[XmlNode] = []
        if cwd:
            children.append(XmlNode("cwd", text=cwd))
        if max_iterations is not None:
            children.append(XmlNode("max_iterations", text=str(max_iterations)))
        if command_timeout is not None:
            children.append(XmlNode("command_timeout", text=str(command_timeout)))
        if allowed_commands:
            children.append(
                XmlNode(
                    "allowed_commands",
                    children=[XmlNode("command", text=command) for command in allowed_commands],
                )
            )
        self.root.replace_child(XmlNode("runtime", children=children))

    def set_skills(self, skills: list[Skill] | None) -> None:
        if not skills:
            return
        self.root.replace_child(
            XmlNode(
                "skill_policy",
                children=[XmlNode("item", text=item) for item in _SKILL_POLICY_ITEMS],
            )
        )
        self.root.replace_child(
            XmlNode(
                "skills",
                children=[
                    XmlNode(
                        "skill",
                        attributes={
                            "name": skill.name,
                            "description": skill.description,
                            "skill_dir": str(skill.path.parent.absolute()),
                        },
                        self_closing=True,
                    )
                    for skill in skills
                ],
            )
        )

    def render(self) -> str:
        if not self.root.children:
            return ""
        self.root.children.sort(key=lambda node: _SECTION_ORDER.get(node.tag_name, 999))
        return self.root.to_xml()
