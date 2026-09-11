"""运行时代际：软重启时被重建的对象集合，供插件运行时显式绑定。

插件运行时是进程寿命对象，而 Agent/Skill 注册表、截图端口由组合根在每次
软重启时重建。开发期把它们放进构造函数的做法会让运行期永久捕获上一代对象：
插件注册进旧注册表、面板插件拿到已关闭的截图端口，且没有任何报错。

把这三者收进一份可整体替换的绑定后：

- 组合根每次构建完运行时对象，调用 PluginRuntime.bind_generation(...)；
- 插件侧通过稳定的解析器读取当前代际，而不是在构造期捕获实例；
- 代际切换时插件已注册的资源（Agent / Markdown Skill）被重放到新对象上。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: "未提供该字段"哨兵：与显式传入 None（表示该代际确实没有该能力）区分。
UNSET: Any = object()


@dataclass(frozen=True, slots=True, eq=False)
class RuntimeGeneration:
    """一份可整体替换的代际绑定。"""

    agent_registry: Any | None = None
    skills_registry: Any | None = None
    screenshots: Any | None = None

    def merged(
        self,
        *,
        agent_registry: Any = UNSET,
        skills_registry: Any = UNSET,
        screenshots: Any = UNSET,
    ) -> "RuntimeGeneration":
        """以当前绑定为底，替换显式传入的字段。"""
        return RuntimeGeneration(
            agent_registry=(
                self.agent_registry if agent_registry is UNSET else agent_registry
            ),
            skills_registry=(
                self.skills_registry if skills_registry is UNSET else skills_registry
            ),
            screenshots=self.screenshots if screenshots is UNSET else screenshots,
        )

    def differs_from(self, other: "RuntimeGeneration") -> bool:
        """按身份比较三个字段：内容相等但对象不同也必须视为新代际。"""
        return (
            self.agent_registry is not other.agent_registry
            or self.skills_registry is not other.skills_registry
            or self.screenshots is not other.screenshots
        )
