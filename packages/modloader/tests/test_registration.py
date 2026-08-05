from __future__ import annotations

import unittest

from neobot_modloader.plugins.registration import validate_plugin_name


class PluginNameValidationTest(unittest.TestCase):
    def test_rejects_path_components_and_escape_names(self) -> None:
        for name in (".", "..", "../escape", "..\\escape", "/escape", "C:\\escape"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_plugin_name(name)

    def test_allows_dots_inside_a_safe_name(self) -> None:
        self.assertEqual(validate_plugin_name("vendor.plugin-v1"), "vendor.plugin-v1")


if __name__ == "__main__":
    unittest.main()
