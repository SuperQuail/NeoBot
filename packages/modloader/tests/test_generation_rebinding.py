"""代际绑定契约：软重启后插件注册必须落在新一代对象上。

组合根每次软重启都会重建 agent/skill 注册表与截图端口，而插件运行时是核心
对象。这里守住 PluginRuntime.bind_generation 的行为：
- 已注册的插件 Agent / Markdown Skill 迁入新注册表；
- 旧注册表不得被排空或关闭（插件 Agent 要在新代际继续服役）；
- 截图端口等读时解析的依赖自动指向新对象；
- 新代际绑定后加载的插件直接注册进当前代际。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from neobot_modloader.runtime import PluginRuntime


class FakeLogger:
    def info(self, *args: Any, **kwargs: Any) -> None:
        pass

    def error(self, *args: Any, **kwargs: Any) -> None:
        pass

    def exception(self, *args: Any, **kwargs: Any) -> None:
        pass

    def warning(self, *args: Any, **kwargs: Any) -> None:
        pass


class FakeLoggerFactory:
    def get_logger(self, name: str) -> Any:
        return FakeLogger()


class FakeAgentRegistry:
    def __init__(self) -> None:
        self.agents: dict[str, Any] = {}
        self.unregistered: list[str] = []

    @property
    def names(self) -> list[str]:
        return list(self.agents)

    def register(self, name: str, agent: Any) -> None:
        if name in self.agents:
            raise ValueError(f"Agent already registered: {name}")
        self.agents[name] = agent

    def unregister(self, name: str) -> Any | None:
        self.unregistered.append(name)
        return self.agents.pop(name, None)


class FakeSkillRegistry:
    def __init__(self) -> None:
        self.owners: dict[str, list[Any]] = {}

    def register_many(self, owner: str, skills: list[Any]) -> None:
        registered = self.owners.setdefault(owner, [])
        for skill in skills:
            if any(existing.name == skill.name for existing in registered):
                raise ValueError(f"Skill 已注册: {owner}:{skill.name}")
            registered.append(skill)

    def unregister_owner(self, owner: str) -> list[str]:
        removed = self.owners.pop(owner, [])
        return [f"{owner}:{skill.name}" for skill in removed]


PLUGIN_SOURCE = '''
from neobot_modloader import Plugin


class _Agent:
    description = "probe"
    tool_definitions = []

    async def invoke(self, state):
        return {"ok": True}

    async def stream_invoke(self, state):
        yield "ok"

    async def close(self):
        pass


class _Skill:
    name = "probe-skill"
    description = "probe"


plugin = Plugin("genprobe")


@plugin.on_load
async def load(ctx):
    ctx.agents.register("probe", _Agent())
    ctx.markdown_skills.register([_Skill()])
'''


class GenerationRebindingTest(unittest.IsolatedAsyncioTestCase):
    def make_runtime(
        self,
        root: Path,
        *,
        agents: FakeAgentRegistry,
        skills: FakeSkillRegistry,
        screenshots: Any,
    ) -> PluginRuntime:
        plugin_dir = root / "plugins"
        plugin_dir.mkdir()
        (plugin_dir / "genprobe.py").write_text(PLUGIN_SOURCE, encoding="utf-8")
        return PluginRuntime(
            plugin_dir=plugin_dir,
            data_dir=root / "data",
            adapter=object(),
            logger_factory=FakeLoggerFactory(),
            agent_registry=agents,
            skills_registry=skills,
            screenshots=screenshots,
        )

    async def test_bind_generation_moves_registrations(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first_agents, second_agents = FakeAgentRegistry(), FakeAgentRegistry()
            first_skills, second_skills = FakeSkillRegistry(), FakeSkillRegistry()
            first_shots, second_shots = object(), object()
            runtime = self.make_runtime(
                root,
                agents=first_agents,
                skills=first_skills,
                screenshots=first_shots,
            )
            runtime.load_all()
            await runtime.load_registered()

            self.assertIn("genprobe.probe", first_agents.agents)
            self.assertEqual(len(first_skills.owners["genprobe"]), 1)
            record = runtime.manager.get_record("genprobe")
            self.assertIs(record.context.screenshots, first_shots)

            runtime.bind_generation(
                agent_registry=second_agents,
                skills_registry=second_skills,
                screenshots=second_shots,
            )

            self.assertIn("genprobe.probe", second_agents.agents)
            self.assertEqual(len(second_skills.owners["genprobe"]), 1)
            self.assertIs(record.context.screenshots, second_shots)
            # 旧注册表必须保持完整：不得排空（排空最终会 close 插件 Agent）
            self.assertEqual(first_agents.unregistered, [])
            self.assertNotIn("genprobe", first_skills.owners)
            # 运行时对外暴露的当前代际也必须是新对象
            self.assertIs(runtime.agent_registry, second_agents)
            self.assertIs(runtime.skills_registry, second_skills)

    async def test_bind_generation_same_objects_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            agents, skills = FakeAgentRegistry(), FakeSkillRegistry()
            shots = object()
            runtime = self.make_runtime(root, agents=agents, skills=skills, screenshots=shots)
            runtime.load_all()
            await runtime.load_registered()

            previous = runtime.generation
            current = runtime.bind_generation(
                agent_registry=agents, skills_registry=skills, screenshots=shots
            )

            self.assertIs(current, previous)
            self.assertEqual(len(agents.agents), 1)

    async def test_plugin_loaded_after_bind_uses_current_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first_agents, second_agents = FakeAgentRegistry(), FakeAgentRegistry()
            first_skills, second_skills = FakeSkillRegistry(), FakeSkillRegistry()
            runtime = self.make_runtime(
                root,
                agents=first_agents,
                skills=first_skills,
                screenshots=object(),
            )
            # 先绑定新代际，再加载插件：注册必须直接落在新注册表
            runtime.bind_generation(
                agent_registry=second_agents,
                skills_registry=second_skills,
                screenshots=object(),
            )
            runtime.load_all()
            await runtime.load_registered()

            self.assertIn("genprobe.probe", second_agents.agents)
            self.assertNotIn("genprobe.probe", first_agents.agents)
            self.assertIn("genprobe", second_skills.owners)
            self.assertNotIn("genprobe", first_skills.owners)


CONFIG_PLUGIN_SOURCE = '''
from pydantic import BaseModel, Field

from neobot_modloader import Plugin


class _Cfg(BaseModel):
    port: int = Field(default=9981, ge=1, le=65535)


plugin = Plugin("cfgprobe", config=_Cfg)


@plugin.on_load
async def load(ctx):
    pass
'''


class PluginConfigValidationTest(unittest.IsolatedAsyncioTestCase):
    def make_runtime(self, root: Path, *, manifest_config: str = "") -> PluginRuntime:
        plugin_dir = root / "plugins"
        package = plugin_dir / "cfgprobe"
        package.mkdir(parents=True)
        (package / "plugin.toml").write_text(
            'name = "cfgprobe"\n' + manifest_config, encoding="utf-8"
        )
        (package / "__init__.py").write_text(CONFIG_PLUGIN_SOURCE, encoding="utf-8")
        return PluginRuntime(
            plugin_dir=plugin_dir,
            data_dir=root / "data",
            adapter=object(),
            logger_factory=FakeLoggerFactory(),
        )

    def write_stored(self, root: Path, text: str) -> None:
        data_dir = root / "data" / "cfgprobe"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "config.toml").write_text(text, encoding="utf-8")

    async def test_invalid_stored_value_falls_back_to_packaged_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root)
            self.write_stored(root, "port = 70000\n")

            runtime.load_all()
            await runtime.load_registered()

            record = runtime.manager.get_record("cfgprobe")
            self.assertEqual(record.context.config["port"], 9981)
            self.assertIn("port", runtime.plugin_config_error("cfgprobe") or "")
            snapshot = [
                item for item in runtime.snapshot_plugins() if item.name == "cfgprobe"
            ][0]
            self.assertTrue(snapshot.config_error)

    async def test_valid_stored_value_passes_through(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root)
            self.write_stored(root, "port = 1234\n")

            runtime.load_all()
            await runtime.load_registered()

            record = runtime.manager.get_record("cfgprobe")
            self.assertEqual(record.context.config["port"], 1234)
            self.assertIsNone(runtime.plugin_config_error("cfgprobe"))
            snapshot = [
                item for item in runtime.snapshot_plugins() if item.name == "cfgprobe"
            ][0]
            self.assertIsNone(snapshot.config_error)

    async def test_invalid_packaged_default_falls_back_to_model_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root, manifest_config="[config]\nport = 99999\n")

            runtime.load_all()
            await runtime.load_registered()

            record = runtime.manager.get_record("cfgprobe")
            self.assertEqual(record.context.config["port"], 9981)
            self.assertTrue(runtime.plugin_config_error("cfgprobe"))
