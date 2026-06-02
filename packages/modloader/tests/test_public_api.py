from __future__ import annotations

import unittest

import neobot_modloader


class PublicApiTest(unittest.TestCase):
    def test_only_new_authoring_api_is_exported(self) -> None:
        exported = set(neobot_modloader.__all__)
        self.assertIn("Plugin", exported)
        self.assertIn("AgentRequest", exported)
        self.assertIn("Reply", exported)
        self.assertIn("Message", exported)
        self.assertIn("PluginControlFacade", exported)
        self.assertIn("PluginOperationResult", exported)
        self.assertIn("PluginSnapshot", exported)
        self.assertIn("RuntimePluginContext", exported)
        for old_name in (
            "BasePlugin",
            "PluginContext",
            "CompatLayer",
            "Matcher",
            "on_command",
            "CommandArg",
            "PluginMetadata",
            "get_plugin_config",
        ):
            self.assertNotIn(old_name, exported)
            self.assertFalse(hasattr(neobot_modloader, old_name))


if __name__ == "__main__":
    unittest.main()
