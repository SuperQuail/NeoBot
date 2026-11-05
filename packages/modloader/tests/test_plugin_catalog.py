"""元信息不能伪装来源或以作者自报通过代替固定包验收。"""

import copy
import hashlib
import json
import platform

from neobot_modloader.sdk.catalog import load_catalog, source_digest, validate_entry
from neobot_modloader.sdk.tooling import build_package, init_project
from scripts.plugin_registry import accept_entry


def _candidate(tmp_path):
    source = tmp_path / "source" / "example"
    created = init_project(source, "example")
    assert created.ok, created.errors
    archive = tmp_path / "example.zip"
    package = build_package(source, archive)
    assert package.ok, package.errors
    entry = {
        "schema_version": 1,
        "id": "neobot/example",
        "name": "example",
        "version": "0.1.0",
        "sdk_api": 1,
        "status": "local",
        "source": {"tree_sha256": source_digest(source)},
        "artifact": {"sha256": package.sha256},
        "compatibility": {
            "neobot": ">=2.0.2a11,<3",
            "python": ">=3.13,<3.15",
            "platforms": ["windows", "linux", "macos"],
        },
    }
    return source, archive, entry


def test_local_candidate_has_real_digest_but_does_not_need_invented_release_urls(tmp_path):
    _, _, entry = _candidate(tmp_path)
    assert validate_entry(entry) == []
    published = copy.deepcopy(entry)
    published["status"] = "published"
    assert any("正式" in error for error in validate_entry(published))
    published["source"] = {"repository": "https://github.com/neobot/example", "commit": "dev"}
    assert any("40" in error for error in validate_entry(published))


def test_local_candidate_does_not_enter_published_catalog(tmp_path):
    _, _, entry = _candidate(tmp_path)
    catalog = tmp_path / "catalog"
    local = catalog / "local-candidates"
    local.mkdir(parents=True)
    (local / "example.json").write_text(json.dumps(entry), encoding="utf-8")
    assert load_catalog(catalog) == []
    assert load_catalog(catalog, include_local=True) == [entry]


async def test_controlled_acceptance_retests_and_smokes_exact_final_package(tmp_path):
    _, archive, entry = _candidate(tmp_path)
    report = await accept_entry(entry, archive, tmp_path / "report", timeout=60)
    assert report["ok"], report["errors"]
    expected = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert report["artifact"]["sha256"] == expected
    assert report["controlled"]["artifact"]["sha256"] == expected
    assert report["input_package_smoke"]["sha256"] == expected
    assert report["controlled"]["business_tests"]["passed"] == 1


async def test_wrong_artifact_is_rejected_before_plugin_execution(tmp_path):
    _, archive, entry = _candidate(tmp_path)
    entry["artifact"]["sha256"] = "0" * 64
    report = await accept_entry(entry, archive, tmp_path / "report")
    assert not report["ok"]
    assert report["checks"] == []
    assert "controlled" not in report


async def test_actual_host_python_and_platform_must_satisfy_declared_compatibility(tmp_path):
    _, archive, original = _candidate(tmp_path)
    excluded = "macos" if platform.system() != "Darwin" else "windows"
    for name, value in (("neobot", ">=999"), ("python", "<1"), ("platforms", [excluded])):
        entry = copy.deepcopy(original)
        entry["compatibility"][name] = value
        report = await accept_entry(entry, archive, tmp_path / name)
        assert not report["ok"], name
        assert report["checks"] == ["artifact_identity"]
        assert "controlled" not in report


async def test_author_report_cannot_hide_a_required_skipped_business_test(tmp_path):
    source, archive, entry = _candidate(tmp_path)
    (source / "author-report.json").write_text('{"ok":true}', encoding="utf-8")
    test = source / "tests/test_plugin.py"
    test.write_text('import pytest\ndef test_business():\n    pytest.skip("合成未完成业务")\n', encoding="utf-8")
    package = build_package(source, archive)
    entry["artifact"]["sha256"] = package.sha256
    entry["source"]["tree_sha256"] = source_digest(source)
    report = await accept_entry(entry, archive, tmp_path / "report", timeout=60)
    assert not report["ok"]
    assert report["controlled"]["business_tests"]["skipped"] == 1
