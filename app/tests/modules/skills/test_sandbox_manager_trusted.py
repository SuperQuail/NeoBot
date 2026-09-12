"""Production CURRENT_INVOCATION security for legacy sandbox_manager tools."""
from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import pytest

from neobot_app.agent_tools.contracts import ToolContext
from neobot_app.agent_tools.invocation import CURRENT_INVOCATION, ToolInvocation
from neobot_app.runtime.sandbox_service import SandboxService
from neobot_app.skills.sandbox_manager_skill import SandboxManagerSkill


class Credentials:
    def __init__(self):
        self.calls = []
        self.grants = set()

    def consume(self, *, chat_flow, action, commit):
        self.calls.append((chat_flow, action, commit))
        if (chat_flow, action) in self.grants:
            self.grants.remove((chat_flow, action))
            return object()
        return None


class Adapter:
    def __init__(self):
        self.calls = []

    async def send(self, conversation, segments, wait_response: bool = True):
        self.calls.append((conversation, segments))
        return {"status": "ok", "retcode": 0}


@pytest.fixture
def env(tmp_path):
    service = SandboxService(tmp_path / "sandbox")
    directory = service.ensure_temp_dir("group:1")
    other = service.ensure_temp_dir("group:2")
    (other / "secret.txt").write_bytes(b"secret")
    credentials, adapter = Credentials(), Adapter()
    skill = SandboxManagerSkill(service, adapter=adapter, file_server=SimpleNamespace(_enabled=False),
                                credential_manager=credentials)
    return service, skill, directory, other, credentials, adapter


async def invoke(skill, name, args, *, owner="group:1:main", flow="group:1", allowed=None):
    marker = CURRENT_INVOCATION.set(ToolInvocation(ToolContext(owner=owner, chat_flow_id=flow, allowed_tools=allowed)))
    try:
        return json.loads(await skill.execute(name, args))
    finally:
        CURRENT_INVOCATION.reset(marker)


@pytest.mark.parametrize("name", ["read_file", "write_file", "edit_file", "glob_files", "grep_files",
                                  "delete_file", "list_files", "write_file_base64", "send_file", "send_chat_file"])
async def test_trusted_legacy_rejects_cross_flow_paths_and_identity(env, name):
    _, skill, directory, other, _, adapter = env
    common = {"content": "evil", "content_base64": "ZXZpbA==", "old_string": "secret", "new_string": "evil", "pattern": "*"}
    for path in ("../group_2/secret.txt", str(other / "secret.txt")):
        result = await invoke(skill, name, {**common, "path": path})
        assert not result["ok"] and result["code"] == "permission_denied", result
    forged = await invoke(skill, name, {**common, "path": "x", "chat_flow_id": "group:2"})
    assert forged["code"] == "FLOW_MISMATCH"
    assert (other / "secret.txt").read_bytes() == b"secret"
    assert not adapter.calls
    assert not (directory / "x").exists()


@pytest.mark.parametrize("name", ["move_file", "copy_file"])
async def test_trusted_move_copy_validate_both_paths(env, name):
    _, skill, directory, other, _, _ = env
    (directory / "local").write_bytes(b"local")
    for args in ({"source": str(other / "secret.txt"), "destination": "output"},
                 {"source": "local", "destination": str(other / "output")}):
        result = await invoke(skill, name, args)
        assert result["code"] == "permission_denied"
    assert (directory / "local").read_bytes() == b"local"
    assert not (other / "output").exists()


async def test_trusted_read_edit_share_real_owner_observations(env):
    _, skill, directory, _, _, _ = env
    original = b"x" * 100000 + b"tail"
    (directory / "large").write_bytes(original)
    read = await invoke(skill, "read_file", {"path": "large"})
    assert read["truncated"] and read["size"] == len(original)
    child = await invoke(skill, "edit_file", {"path": "large", "old_string": "tail", "new_string": "child"}, owner="group:1:child")
    assert child["code"] == "read_required"
    overwrite = await invoke(skill, "write_file", {"path": "large", "content": read["content"]})
    assert overwrite["code"] == "incomplete_read"
    edited = await invoke(skill, "edit_file", {"path": "large", "old_string": "tail", "new_string": "done"})
    assert edited["ok"] and "compatibility_note" not in edited
    assert (directory / "large").read_bytes() == original[:-4] + b"done"


@pytest.mark.parametrize("name,args", [
    ("write_file", {"path": "shared:docs/new", "content": "new"}),
    ("edit_file", {"path": "shared:docs/existing", "old_string": "old", "new_string": "new"}),
    ("delete_file", {"path": "shared:docs/existing"}),
    ("move_file", {"source": "shared:docs/existing", "destination": "moved"}),
    ("move_file", {"source": "local", "destination": "shared:docs/moved"}),
    ("copy_file", {"source": "local", "destination": "shared:docs/copied"}),
    ("write_file_base64", {"path": "shared:docs/binary", "content_base64": "bmV3"}),
])
async def test_shared_mutations_consume_chat_bound_credential(env, name, args):
    service, skill, directory, _, credentials, _ = env
    shared = service.resolve_path("docs/existing")
    await service.write_file(shared, b"old")
    (directory / "local").write_bytes(b"local")
    if name == "edit_file":
        assert (await invoke(skill, "read_file", {"path": "shared:docs/existing"}))["ok"]
    result = await invoke(skill, name, args)
    assert result["code"] == "CREDENTIAL_REQUIRED", result
    assert result["details"]["action"] == "agent_shared_write"
    assert shared.read_bytes() == b"old"
    credentials.grants.add(("group:2", "agent_shared_write"))
    assert (await invoke(skill, name, args))["code"] == "CREDENTIAL_REQUIRED"
    credentials.grants.add(("group:1", "agent_shared_write"))
    allowed = await invoke(skill, name, args)
    assert allowed["ok"], allowed
    assert credentials.calls[-1] == ("group:1", "agent_shared_write", True)
    assert ("group:1", "agent_shared_write") not in credentials.grants


async def test_binary_overwrite_requires_execute_but_new_file_does_not(env):
    _, skill, directory, _, credentials, _ = env
    args = {"path": "binary", "content_base64": base64.b64encode(b"original").decode()}
    assert (await invoke(skill, "write_file_base64", args))["ok"]
    assert not credentials.calls
    result = await invoke(skill, "write_file_base64", {"path": "binary", "content_base64": ""})
    assert result["code"] == "CREDENTIAL_REQUIRED" and result["details"]["action"] == "agent_execute"
    assert (directory / "binary").read_bytes() == b"original"
    credentials.grants.add(("group:1", "agent_execute"))
    assert (await invoke(skill, "write_file_base64", {"path": "binary", "content_base64": ""}))["ok"]
    assert (directory / "binary").read_bytes() == b""


@pytest.mark.parametrize("name", ["send_file", "send_chat_file"])
async def test_trusted_send_rejects_any_outside_file_and_binds_recipient(env, tmp_path, name):
    _, skill, directory, _, _, adapter = env
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"private host data")
    assert (await invoke(skill, name, {"path": str(outside)}))["code"] == "permission_denied"
    local = directory / "delivered.txt"
    local.write_bytes(b"deliver")
    denied = await invoke(skill, name, {"path": str(local), "group_id": "2"})
    assert denied["code"] == "FLOW_MISMATCH" and not adapter.calls
    result = await invoke(skill, name, {"path": str(local)})
    assert result["ok"], result
    conversation, segments = adapter.calls[-1]
    assert conversation.kind == "group" and conversation.id == "1"
    assert local.as_posix() in segments[0]["data"]["file"]


async def test_shared_send_and_read_only_copy_remain_available(env):
    service, skill, directory, _, credentials, adapter = env
    await service.write_file(service.resolve_path("docs/shared.txt"), b"shared")
    result = await invoke(skill, "send_chat_file", {"path": "shared:docs/shared.txt"})
    assert result["ok"] and len(adapter.calls) == 1
    copied = await invoke(skill, "copy_file", {"source": "shared:docs/shared.txt", "destination": "copy.txt"})
    assert copied["ok"] and (directory / "copy.txt").read_bytes() == b"shared"
    assert not credentials.calls


async def test_download_bound_path_and_shared_gate_precede_handler(env, monkeypatch):
    from neobot_app.skills import sandbox_manager_skill as module
    service, skill, directory, other, credentials, _ = env
    calls = []
    async def download(self, args):
        calls.append(args)
        return json.dumps({"ok": True})
    monkeypatch.setitem(module._HANDLERS, "download_file", download)
    assert (await invoke(skill, "download_file", {"url": "https://example.test/file", "save_name": str(other / "x")}))["code"] == "permission_denied"
    assert not calls
    result = await invoke(skill, "download_file", {"url": "https://example.test/file", "save_name": "shared:docs/download"})
    assert result["code"] == "CREDENTIAL_REQUIRED" and not calls
    credentials.grants.add(("group:1", "agent_shared_write"))
    assert (await invoke(skill, "download_file", {"url": "https://example.test/file", "save_name": "shared:docs/download"}))["ok"]
    assert calls[-1]["chat_flow_id"] == "group:1"
    assert calls[-1]["save_name"] == str(service.resolve_path("docs/download"))
    assert (await invoke(skill, "download_file", {"url": "https://example.test/file", "save_name": "local"}))["ok"]
    assert calls[-1]["save_name"] == str(directory / "local")


async def test_list_glob_grep_are_current_flow_bounded(env):
    _, skill, directory, _, _, _ = env
    (directory / "a.txt").write_bytes(b"match\n")
    for name, args in (("list_files", {}), ("glob_files", {"pattern": "*.txt"}),
                       ("grep_files", {"pattern": "match", "output_mode": "content"})):
        result = await invoke(skill, name, args)
        assert result["ok"], result
        assert "secret.txt" not in json.dumps(result)
    denied = await invoke(skill, "list_files", {"pattern": "../group_2/*"})
    assert not denied["ok"]


async def test_forged_context_arguments_fail_and_runtime_acl_not_misread(env):
    _, skill, directory, _, _, _ = env
    for field in ("owner", "context", "invocation"):
        result = await invoke(skill, "write_file", {"path": "x", "content": "x", field: "evil"})
        assert result["code"] == "CONTEXT_REQUIRED"
    # Reply performs qualified legacy ACL checks. This set has NEW runtime names.
    result = await invoke(skill, "write_file", {"path": "empty", "content": ""}, allowed=frozenset({"read"}))
    assert result["ok"] and (directory / "empty").read_bytes() == b""


async def test_private_delivery_uses_trusted_private_target(env):
    service, skill, _, _, _, adapter = env
    directory = service.ensure_temp_dir("private:9")
    (directory / "file").write_bytes(b"private")
    result = await invoke(skill, "send_chat_file", {"path": "file"}, owner="private:9:main", flow="private:9")
    assert result["ok"]
    assert adapter.calls[-1][0].kind == "private" and adapter.calls[-1][0].id == "9"
