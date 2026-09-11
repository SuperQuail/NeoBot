"""Isolated tests: python -B -m unittest discover -s scripts -p test_prepare_release.py."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from http.client import IncompleteRead
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from packaging.version import Version

# Also works as a directly executed file, independent of cwd or package installation.
_SPEC = importlib.util.spec_from_file_location("prepare_release", Path(__file__).with_name("prepare_release.py"))
release = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = release
_SPEC.loader.exec_module(release)


class Response(io.BytesIO):
    status = 200


def response(versions=()):
    return Response(json.dumps({"releases": {version: [] for version in versions}}).encode())


class PrepareReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.add_project("pyproject.toml", "root", build=False)
        self.add_project("packages/one/pyproject.toml", "one")
        self.add_project("packages/two/pyproject.toml", "two")
        self.add_project("app/pyproject.toml", "app")
        # All test cases block real network by default.
        self.network = patch.object(release, "urlopen", side_effect=lambda *a, **kw: response())
        self.urlopen = self.network.start()
        self.addCleanup(self.network.stop)

    def add_project(self, relative, name, version="1.0.0-alpha.22", build=True):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        text = f'[project]\nname = "{name}"\nversion = "{version}" # keep comment\n'
        text += 'dependencies = ["other==1.0.0-alpha.22"]\n'
        text += '[tool.example]\nversion = "1.0.0-alpha.22"\n'
        if build:
            text += '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
        path.write_bytes(text.encode())
        return path

    def snapshot(self):
        return {path: path.read_bytes() for path in self.root.rglob("pyproject.toml")}

    def assert_unchanged_failure(self):
        before = self.snapshot()
        with self.assertRaises(release.ReleaseError):
            release.prepare_release(self.root)
        self.assertEqual(self.snapshot(), before)

    def assert_versions(self, expected):
        for path in self.snapshot():
            self.assertEqual(tomllib.loads(path.read_text())["project"]["version"], expected)

    def test_first_release_404_syncs_root_without_querying_it(self):
        self.urlopen.side_effect = HTTPError("url", 404, "Not Found", None, None)
        self.assertEqual(release.prepare_release(self.root), "1.0.0a22")
        self.assert_versions("1.0.0a22")
        urls = [call.args[0] for call in self.urlopen.call_args_list]
        self.assertEqual(urls, [f"https://pypi.org/pypi/{name}/json" for name in ("one", "two", "app")])
        self.assertTrue(all(call.kwargs["timeout"] == 30 for call in self.urlopen.call_args_list))

    def test_buildable_root_is_queried(self):
        self.add_project("pyproject.toml", "root", build=True)
        release.prepare_release(self.root)
        self.assertEqual(self.urlopen.call_count, 4)
        self.assertIn("/root/json", self.urlopen.call_args_list[0].args[0])

    def test_all_histories_include_pre_releases_not_info_version(self):
        self.urlopen.side_effect = [
            Response(b'{"info":{"version":"0.9"},"releases":{"1.0.0a25":[]}}'),
            response(["1.0.0b3", "1.0.0rc2"]),
            response(["1.0.0rc10", "1.0.0rc9"]),
        ]
        self.assertEqual(release.prepare_release(self.root), "1.0.0rc11")
        self.assert_versions("1.0.0rc11")

    def test_local_ahead_is_kept(self):
        self.urlopen.side_effect = lambda *a, **kw: response(["0.9", "1.0.0a21"])
        self.assertEqual(release.prepare_release(self.root), "1.0.0a22")

    def test_version_increment_cases(self):
        cases = [
            ("1.0.0-alpha.22", ["1.0.0a22"], "1.0.0a23"),
            ("1.0.0", ["1.2.3-beta.9"], "1.2.3b10"),
            ("1.0.0", ["1.2.3rc9"], "1.2.3rc10"),
            ("1.2.3", ["1.2.3"], "1.2.4"),
            ("1.0.0a22", ["1.0.0"], "1.0.1"),
            ("1.0.0", ["2.4"], "2.4.1"),
            ("1!1.0", ["1!1.0"], "1!1.0.1"),
            ("1.0.0", [], "1.0.0"),
        ]
        for local, published, expected in cases:
            with self.subTest(local=local, published=published):
                self.assertEqual(str(release.choose_version(Version(local), list(map(Version, published)))), expected)

    def test_semantically_equal_local_versions_allowed(self):
        self.add_project("packages/two/pyproject.toml", "two", "1.0.0a22")
        self.assertEqual(release.prepare_release(self.root), "1.0.0a22")

    def test_out_of_sync_rejected_before_network(self):
        self.add_project("packages/two/pyproject.toml", "two", "1.0.0a23")
        self.assert_unchanged_failure()
        self.urlopen.assert_not_called()

    def test_local_unsupported_or_invalid_versions_rejected(self):
        for version in ("1.0.dev1", "1.0.post1", "1.0+local", "not-version"):
            with self.subTest(version=version):
                self.add_project("packages/two/pyproject.toml", "two", version)
                self.assert_unchanged_failure()
        self.urlopen.assert_not_called()

    def test_published_unsupported_or_invalid_versions_rejected(self):
        for version in ("1.0.dev1", "1.0.post1", "1.0+local", "not-version"):
            with self.subTest(version=version):
                self.urlopen.side_effect = lambda *a, **kw: response([version])
                self.assert_unchanged_failure()

    def test_late_http_network_and_json_failures_do_not_write(self):
        failures = [
            HTTPError("url", 403, "Forbidden", None, None),
            HTTPError("url", 500, "Server error", None, None),
            URLError("connection failed"),
            TimeoutError("timeout"),
            IncompleteRead(b"partial"),
        ]
        for failure in failures:
            with self.subTest(failure=failure):
                self.urlopen.side_effect = [response(["2.0"]), response(), failure]
                self.assert_unchanged_failure()
        for payload in (b"not json", b"\xff", b"[]", b"{}", b'{"releases":[]}', b'{"releases":{"1.0":null}}'):
            with self.subTest(payload=payload):
                self.urlopen.side_effect = [response(["2.0"]), response(), Response(payload)]
                self.assert_unchanged_failure()

    def test_unexpected_response_status_fails_closed(self):
        bad_response = response()
        bad_response.status = 503
        self.urlopen.side_effect = [bad_response]
        self.assert_unchanged_failure()

    def test_precise_edit_preserves_dependencies_comments_crlf_and_fake_keys(self):
        path = self.root / "pyproject.toml"
        text = (
            '[project]\r\nname = "root"\r\n'
            "'version'  = '1.0.0-alpha.22' # untouched comment\r\n"
            'description = """\r\n[project]\r\nversion = "1.0.0-alpha.22"\r\n"""\r\n'
            'dependencies = ["other==1.0.0-alpha.22"]\r\n'
            '[tool.example]\r\nversion = "1.0.0-alpha.22"\r\n'
        )
        path.write_bytes(text.encode())
        self.urlopen.side_effect = lambda *a, **kw: response(["1.0.0a22"])
        release.prepare_release(self.root)
        expected = text.replace("'version'  = '1.0.0-alpha.22'", "'version'  = '1.0.0a23'")
        self.assertEqual(path.read_bytes(), expected.encode())

    def test_uneditable_last_file_fails_before_any_write(self):
        path = self.root / "app/pyproject.toml"
        path.write_text('project = { name = "app", version = "1.0.0a22" }\n', encoding="utf-8")
        self.assert_unchanged_failure()

    def test_cli_appends_github_output(self):
        output = self.root / "github-output"
        output.write_text("existing=value\n", encoding="utf-8")
        with patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}), redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(release.main(["--repo-root", str(self.root)]), 0)
        self.assertEqual(stdout.getvalue(), "1.0.0a22\n")
        self.assertEqual(output.read_text(), "existing=value\nversion=1.0.0a22\n")

    def test_cli_default_root_uses_script_path_not_cwd(self):
        fake_script = self.root / "scripts" / "prepare_release.py"
        with patch.object(release, "__file__", str(fake_script)), patch.dict(os.environ, {}, clear=True):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(release.main([]), 0)
        self.assert_versions("1.0.0a22")

    def test_cli_failure_emits_no_github_output(self):
        output = self.root / "github-output"
        self.urlopen.side_effect = URLError("offline")
        with patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}), redirect_stderr(io.StringIO()):
            self.assertEqual(release.main(["--repo-root", str(self.root)]), 1)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
