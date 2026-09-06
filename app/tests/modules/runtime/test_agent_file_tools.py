"""Dedicated shared file-tool isolation, loss-prevention and budget regressions."""
from __future__ import annotations

import asyncio
import json

import pytest

from neobot_app.runtime import agent_file_tools as module
from neobot_app.runtime.agent_file_tools import AgentFileTools
from neobot_app.runtime.sandbox_service import MAX_TEXT_READ_BYTES, SandboxService
from neobot_app.skills.sandbox_manager_skill import SandboxManagerSkill


@pytest.fixture
def env(tmp_path):
    service = SandboxService(tmp_path / "sandbox")
    directory = service.ensure_temp_dir("group:1")
    return service, AgentFileTools(service), directory


async def call(tools, name, args, owner="alice", flow="group:1"):
    return await tools.execute(name, args, owner=owner, chat_flow_id=flow)


async def test_edit_tail_over_64k_and_preserve_mixed_newlines(env):
    service, tools, directory = env
    original = ("你好 mixed\r\n" * 9000 + "TAIL old\rfinal\n").encode()
    path = directory / "large.txt"
    path.write_bytes(original)
    assert len(original) > MAX_TEXT_READ_BYTES
    read = await call(tools, "read", {"file_path": "large.txt"})
    assert read["ok"] and read["truncated"] and read["size"] == len(original)
    denied = await call(tools, "write", {"file_path": "large.txt", "content": read["content"]})
    assert denied["code"] == "incomplete_read"
    result = await call(tools, "edit", {"file_path": "large.txt", "old_string": "TAIL old", "new_string": "TAIL new"})
    assert result["ok"], result
    assert path.read_bytes() == original.replace(b"TAIL old", b"TAIL new")


async def test_legacy_edit_without_read_never_overwrites_preview(env):
    service, _, directory = env
    path = directory / "legacy.txt"
    original = b"header old\r\n" + b"x" * 100000 + b"tail old\r\n"
    path.write_bytes(original)
    skill = SandboxManagerSkill(service)
    result = json.loads(await skill.execute("edit_file", {"path": "legacy.txt", "chat_flow_id": "group:1",
                                                        "old_string": "tail old", "new_string": "tail new"}))
    assert result["ok"] and "compatibility_note" in result
    assert path.read_bytes() == original.replace(b"tail old", b"tail new")
    assert len(skill.get_tools()) == 14


async def test_utf8_long_line_pagination_and_complete_write(env):
    _, tools, directory = env
    original = "汉" * 40000 + "\r\n第二行\n结尾"
    path = directory / "utf8.txt"
    path.write_bytes(original.encode())
    args = {"file_path": "utf8.txt", "limit": 1}
    pages = []
    while True:
        result = await call(tools, "read", args)
        assert result["ok"], result
        assert len(result["content"].encode()) <= MAX_TEXT_READ_BYTES
        pages.append(result["content"])
        if result["next_offset"] is None:
            break
        args.update(offset=result["next_offset"], column=result["next_column"])
    assert "".join(pages) == original
    assert result["totalLines"] == 3 and result["complete_observation"]
    empty = await call(tools, "write", {"file_path": "utf8.txt", "content": "", "expected_version": result["version"]})
    assert empty["ok"] and path.read_bytes() == b""
    read = await call(tools, "read", {"file_path": "utf8.txt"})
    assert read["content"] == "" and read["lines"] == [] and read["totalLines"] == 0


async def test_new_empty_file_and_strict_argument_types(env):
    _, tools, directory = env
    assert (await call(tools, "write", {"file_path": "empty", "content": ""}))["ok"]
    assert (directory / "empty").read_bytes() == b""
    assert not (await call(tools, "write", {"file_path": "bad", "content": None}))["ok"]
    assert (await call(tools, "read", {"file_path": "empty", "offset": 0}))["code"] == "invalid_argument"
    assert (await call(tools, "read", {"file_path": "empty", "limit": True}))["code"] == "invalid_argument"


async def test_unique_replace_all_and_no_match(env):
    _, tools, directory = env
    path = directory / "edit"
    path.write_bytes(b"a\r\na\nb")
    assert (await call(tools, "edit", {"file_path": "edit", "old_string": "a", "new_string": "z"}))["code"] == "read_required"
    await call(tools, "read", {"file_path": "edit"})
    for old, code in [("a", "ambiguous_match"), ("missing", "no_match"), ("", "invalid_argument")]:
        result = await call(tools, "edit", {"file_path": "edit", "old_string": old, "new_string": ""})
        assert result["code"] == code
        assert path.read_bytes() == b"a\r\na\nb"
    result = await call(tools, "edit", {"file_path": "edit", "old_string": "a", "new_string": "", "replace_all": True})
    assert result["replacements"] == 2
    assert path.read_bytes() == b"\r\n\nb"


async def test_concurrent_same_owner_explicit_version_one_wins(env):
    service, tools, directory = env
    path = directory / "concurrent"
    path.write_bytes(b"a b")
    observed = await call(tools, "read", {"file_path": "concurrent"})
    # Two facades must share locks AND observations.
    other = AgentFileTools(service)
    results = await asyncio.gather(
        call(tools, "edit", {"file_path": "concurrent", "old_string": "a", "new_string": "A", "expected_version": observed["version"]}),
        call(other, "edit", {"file_path": "concurrent", "old_string": "b", "new_string": "B", "expected_version": observed["version"]}),
    )
    assert sum(r["ok"] for r in results) == 1, results
    assert [r["code"] for r in results if not r["ok"]] == ["stale_version"]


async def test_owner_observations_cannot_be_forged_and_external_staleness(env):
    _, tools, directory = env
    path = directory / "version"
    path.write_bytes(b"old")
    observed = await call(tools, "read", {"file_path": "version"})
    forged = await call(tools, "write", {"file_path": "version", "content": "evil", "expected_version": observed["version"]}, owner="bob")
    assert not forged["ok"] and path.read_bytes() == b"old"
    assert (await call(tools, "write", {"file_path": "version", "content": "evil"}, owner="bob"))["code"] == "read_required"
    path.write_bytes(b"external")
    stale = await call(tools, "write", {"file_path": "version", "content": "lost"})
    assert stale["code"] == "stale_version" and path.read_bytes() == b"external"


@pytest.mark.parametrize("operation", ["read", "write", "edit", "glob", "grep"])
async def test_no_parent_traversal_other_flow_absolute_or_argument_identity(env, operation):
    service, tools, directory = env
    other = service.ensure_temp_dir("group:2") / "secret.txt"
    other.write_text("secret", encoding="utf-8")
    base = {"content": "bad", "old_string": "secret", "new_string": "bad", "pattern": "*"}
    for value in ("../group_2/secret.txt", str(other), "../../docs/private"):
        result = await call(tools, operation, {**base, "path": value})
        assert result["code"] == "permission_denied", result
    result = await call(tools, operation, {**base, "path": "x", "owner": "victim"})
    assert result["code"] == "untrusted_context"
    result = await call(tools, operation, {**base, "path": "x"}, owner="")
    assert result["code"] == "permission_denied"
    assert other.read_text() == "secret"


async def test_explicit_shared_policy_and_readonly_resource(env, tmp_path):
    service, tools, _ = env
    assert (await call(tools, "write", {"file_path": "shared:docs/index.md", "content": "shared"}))["ok"]
    assert (await call(tools, "read", {"file_path": "shared:docs/index.md"}, owner="bob", flow="group:2"))["content"] == "shared"
    assert not (await call(tools, "write", {"file_path": "shared:temp/secret", "content": "bad"}))["ok"]
    assert AgentFileTools.is_shared_write("write", {"file_path": "shared:docs/a"})
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    (gallery / "a.txt").write_text("readonly")
    readonly = AgentFileTools(SandboxService(service._root, allowed_read_dirs=[gallery]))
    assert (await call(readonly, "read", {"file_path": "shared:gallery/a.txt"}))["content"] == "readonly"
    assert (await call(readonly, "write", {"file_path": "shared:gallery/a.txt", "content": "bad"}))["code"] == "permission_denied"


async def test_glob_files_only_anchor_basename_and_truncation(env):
    _, tools, directory = env
    (directory / "nested").mkdir()
    for p in (directory / "a.txt", directory / "nested" / "b.txt", directory / ".hidden.txt"):
        p.write_text("match")
    result = await call(tools, "glob", {"pattern": "*.txt", "limit": 1})
    assert result["ok"] and len(result["paths"]) == 1 and result["truncated"]
    all_files = await call(tools, "glob", {"pattern": "**/*.txt"})
    assert len(all_files["paths"]) == 3 and not all_files["truncated"]
    anchored = await call(tools, "glob", {"pattern": "nested/*.txt"})
    assert anchored["paths"] == [str(directory / "nested" / "b.txt")]
    assert not (await call(tools, "glob", {"pattern": "../*"}))["ok"]


async def test_search_truncation_invalid_regex_and_budget(env, monkeypatch):
    _, tools, directory = env
    (directory / "search.txt").write_text("match\n" * 10)
    result = await call(tools, "grep", {"pattern": "match", "include": "*.txt", "limit": 2})
    assert result["ok"] and len(result["matches"]) == 2 and result["truncated"]
    assert result["matches"][0]["lineNumber"] == 1
    assert not result["total_is_exact"]
    assert (await call(tools, "grep", {"pattern": "["}))["code"] == "invalid_pattern"
    monkeypatch.setattr(module, "MAX_SEARCH_BYTES", 5)
    limited = await call(tools, "grep", {"pattern": "match"})
    assert limited["truncated"] and "byte_limit" in limited["truncation_reasons"]


async def test_catastrophic_regex_is_killed_without_blocking_event_loop(env, monkeypatch):
    _, tools, directory = env
    (directory / "evil.txt").write_text("a" * 10000 + "!")
    monkeypatch.setattr(module, "REGEX_TIMEOUT_SECONDS", 0.3)
    task = asyncio.create_task(call(tools, "grep", {"pattern": "(a+)+$"}))
    await asyncio.sleep(0.05)
    assert not task.done()  # event loop ran while isolated regex worked
    result = await asyncio.wait_for(task, 3)
    assert result["code"] == "search_timeout"


async def test_atomic_failure_keeps_original_and_cleans_temporary(env, monkeypatch):
    service, tools, directory = env
    path = directory / "atomic"
    path.write_bytes(b"original")
    await call(tools, "read", {"file_path": "atomic"})
    def fail(*args):
        raise OSError("simulated replace failure")
    monkeypatch.setattr("neobot_app.runtime.sandbox_service.os.replace", fail)
    result = await call(tools, "write", {"file_path": "atomic", "content": "replacement"})
    assert not result["ok"] and path.read_bytes() == b"original"
    assert not list(directory.glob(".neobot-write-*"))
    assert not service._file_locks


async def test_legacy_partial_write_rejected_empty_write_accepted(env):
    service, _, directory = env
    path = directory / "legacy"
    path.write_bytes(b"x" * 100000)
    skill = SandboxManagerSkill(service)
    args = {"path": "legacy", "chat_flow_id": "group:1"}
    read = json.loads(await skill.execute("read_file", args))
    assert read["truncated"] and read["size"] == 100000
    write = json.loads(await skill.execute("write_file", {**args, "content": read["content"]}))
    assert write["code"] == "incomplete_read" and path.stat().st_size == 100000
    empty = json.loads(await skill.execute("write_file", {"path": "new-empty", "chat_flow_id": "group:1", "content": ""}))
    assert empty["ok"]


async def test_replacement_expansion_rejected_before_allocation(env, monkeypatch):
    _, tools, directory = env
    (directory / "expand").write_bytes(b"a" * 100)
    await call(tools, "read", {"file_path": "expand"})
    monkeypatch.setattr(module, "MAX_FILE_BYTES", 1000)
    result = await call(tools, "edit", {"file_path": "expand", "old_string": "a", "new_string": "b" * 100, "replace_all": True})
    assert result["code"] == "file_too_large"


async def test_sequential_mutations_advance_observation_but_partial_stays_partial(env):
    _, tools, directory = env
    result = await call(tools, "write", {"file_path": "sequence", "content": "one two"})
    assert result["ok"]
    edit = await call(tools, "edit", {"file_path": "sequence", "old_string": "one", "new_string": "ONE"})
    assert edit["ok"]
    again = await call(tools, "edit", {"file_path": "sequence", "old_string": "two", "new_string": "TWO"})
    assert again["ok"]
    assert (directory / "sequence").read_text() == "ONE TWO"
    (directory / "partial").write_bytes(b"x" * 100000 + b"tail")
    await call(tools, "read", {"file_path": "partial"})
    assert (await call(tools, "edit", {"file_path": "partial", "old_string": "tail", "new_string": "end"}))["ok"]
    overwrite = await call(tools, "write", {"file_path": "partial", "content": "x"})
    assert overwrite["code"] == "incomplete_read"


async def test_other_owner_concurrent_implicit_version_one_wins(env):
    _, tools, directory = env
    (directory / "race").write_bytes(b"a b")
    await call(tools, "read", {"file_path": "race"}, owner="alice")
    await call(tools, "read", {"file_path": "race"}, owner="bob")
    results = await asyncio.gather(
        call(tools, "edit", {"file_path": "race", "old_string": "a", "new_string": "A"}, owner="alice"),
        call(tools, "edit", {"file_path": "race", "old_string": "b", "new_string": "B"}, owner="bob"),
    )
    assert sum(r["ok"] for r in results) == 1
    assert [r["code"] for r in results if not r["ok"]] == ["stale_version"]


async def test_aliased_flow_identity_and_public_resolver(env):
    _, tools, directory = env
    (directory / "secret").write_bytes(b"secret")
    assert tools.resolve_path("secret", owner="alice", chat_flow_id="group:1") == directory / "secret"
    for flow in ("group_1", "group/1", "Group:1", "../group:1"):
        result = await call(tools, "read", {"file_path": "secret"}, flow=flow)
        assert result["code"] == "permission_denied", result


async def test_symlink_to_other_flow_denied(env):
    service, tools, directory = env
    other = service.ensure_temp_dir("group:2") / "secret"
    other.write_bytes(b"secret")
    try:
        (directory / "link").symlink_to(other)
    except OSError:
        pytest.skip("host does not grant symlink creation")
    for name in ("read", "write", "edit"):
        result = await call(tools, name, {"file_path": "link", "content": "bad", "old_string": "secret", "new_string": "bad"})
        assert result["code"] == "permission_denied"
    result = await call(tools, "glob", {"pattern": "*"})
    assert str(directory / "link") not in result["paths"]
    assert other.read_bytes() == b"secret"


async def test_recreate_removed_file_requires_confirming_absence(env):
    _, tools, directory = env
    assert (await call(tools, "write", {"file_path": "gone", "content": "old"}))["ok"]
    (directory / "gone").unlink()
    assert (await call(tools, "write", {"file_path": "gone", "content": "new"}))["code"] == "stale_version"
    assert (await call(tools, "read", {"file_path": "gone"}))["code"] == "not_found"
    assert (await call(tools, "write", {"file_path": "gone", "content": "new"}))["ok"]


def test_link_component_policy_without_host_symlink_privilege(env, monkeypatch):
    from pathlib import Path
    _, tools, directory = env
    blocked = directory / "linked"
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == blocked or original(path))
    with pytest.raises(PermissionError, match="symlink"):
        tools.resolve_path("linked/file", owner="alice", chat_flow_id="group:1")
