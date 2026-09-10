"""min_neobot_version 比较规则。"""

from __future__ import annotations

import unittest

from neobot_modloader.version import (
    incompatible_version_error,
    parse_version,
    version_at_least,
)


class ParseVersionTest(unittest.TestCase):
    def test_parses_numeric_components(self) -> None:
        self.assertEqual(parse_version("1.2.3"), (1, 2, 3))
        self.assertEqual(parse_version("v0.6"), (0, 6))
        self.assertEqual(parse_version(" 2 "), (2,))
        self.assertEqual(parse_version("1.2.3-beta.1"), (1, 2, 3))

    def test_unparsable_returns_none(self) -> None:
        for value in ("", None, "latest", "abc"):
            self.assertIsNone(parse_version(value))


class VersionAtLeastTest(unittest.TestCase):
    def test_compares_by_padded_components(self) -> None:
        self.assertTrue(version_at_least("0.6.0", "0.6"))
        self.assertTrue(version_at_least("1.0", "0.9.9"))
        self.assertFalse(version_at_least("0.5.9", "0.6.0"))
        # 10 必须大于 9（不能按字符串比较）
        self.assertTrue(version_at_least("0.10.0", "0.9.0"))

    def test_equal_versions_satisfy(self) -> None:
        self.assertTrue(version_at_least("0.6.0", "0.6.0"))

    def test_uncomparable_returns_none(self) -> None:
        self.assertIsNone(version_at_least("latest", "0.6.0"))
        self.assertIsNone(version_at_least("0.6.0", "latest"))

    def test_all_zero_host_treated_as_unknown(self) -> None:
        """源码运行取不到发行版本时会回落 0.0.0，不能因此把所有插件判成过旧。"""
        self.assertIsNone(version_at_least("0.0.0", "0.6.0"))


class IncompatibleVersionErrorTest(unittest.TestCase):
    def test_reports_too_old_host(self) -> None:
        message = incompatible_version_error(
            name="demo", host="0.5.0", minimum="0.6.0"
        )

        self.assertIsNotNone(message)
        assert message is not None
        self.assertIn("demo", message)
        self.assertIn("0.6.0", message)
        self.assertIn("0.5.0", message)

    def test_satisfied_or_absent_minimum_is_ok(self) -> None:
        self.assertIsNone(
            incompatible_version_error(name="demo", host="0.6.0", minimum="0.6.0")
        )
        self.assertIsNone(
            incompatible_version_error(name="demo", host="0.6.0", minimum=None)
        )
        self.assertIsNone(
            incompatible_version_error(
                name="demo", host="0.0.0", minimum="0.6.0"
            )
        )


if __name__ == "__main__":
    unittest.main()
