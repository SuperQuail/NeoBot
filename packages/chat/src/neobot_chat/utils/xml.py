from __future__ import annotations

from dataclasses import dataclass, field
from xml.sax.saxutils import escape, quoteattr


@dataclass
class XmlNode:
    tag_name: str
    attributes: dict[str, str] = field(default_factory=dict)
    text: str | None = None
    children: list["XmlNode"] = field(default_factory=list)
    self_closing: bool = False

    def __post_init__(self) -> None:
        if not self.tag_name:
            raise ValueError("tag_name must not be empty")
        self.attributes = {
            str(name): str(value)
            for name, value in self.attributes.items()
            if value is not None
        }
        if self.self_closing and (self.text or self.children):
            raise ValueError("self_closing nodes cannot have text or children")

    def add_child(self, child: "XmlNode") -> "XmlNode":
        self.children.append(child)
        return self

    def extend_children(self, children: list["XmlNode"]) -> "XmlNode":
        self.children.extend(children)
        return self

    def set_attribute(self, name: str, value: str) -> "XmlNode":
        self.attributes[str(name)] = str(value)
        return self

    def to_xml(self, indent: int = 0, indent_step: int = 2) -> str:
        prefix = " " * indent
        attrs = "".join(
            f" {name}={quoteattr(value)}" for name, value in self.attributes.items()
        )
        if self.self_closing:
            return f"{prefix}<{self.tag_name}{attrs} />"
        if self.children:
            open_tag = f"{prefix}<{self.tag_name}{attrs}>"
            child_xml = "\n".join(
                child.to_xml(indent + indent_step, indent_step) for child in self.children
            )
            close_tag = f"{prefix}</{self.tag_name}>"
            return f"{open_tag}\n{child_xml}\n{close_tag}"
        if self.text is not None:
            return f"{prefix}<{self.tag_name}{attrs}>{escape(self.text)}</{self.tag_name}>"
        return f"{prefix}<{self.tag_name}{attrs}></{self.tag_name}>"
