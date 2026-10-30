"""插件公共契约、业务动作与教程引用的端到端单元回归。"""

from __future__ import annotations

import dataclasses
import json

import pytest
from pydantic import BaseModel, ConfigDict, Field, RootModel

from neobot_modloader import Plugin
from neobot_modloader.sdk.contract import validate_contract


class Subscription(BaseModel):
    room: str
    group: str


class Settings(BaseModel):
    subscription: Subscription
    interval: int = Field(default=60, ge=15)


class CreateSubscription(BaseModel):
    model_config = ConfigDict(extra="forbid")
    room: str
    group: str


class Rows(RootModel[list[Subscription]]):
    pass


class CountInput(BaseModel):
    count: int


class CountOutput(BaseModel):
    total: int


def invocation(*permissions, context=None):
    from neobot_modloader.sdk import ActionInvocation

    return ActionInvocation(identity="test-user", permissions=frozenset(permissions), context=context)


def action_error():
    from neobot_modloader.sdk import ActionError

    return ActionError


def test_plugin_without_new_features_has_an_empty_surface():
    plugin = Plugin("legacy", description="兼容旧插件")
    contract = plugin.surface.describe(plugin)
    assert contract == {
        "schema_version": 1,
        "plugin": {"name": "legacy", "version": "0.1.0", "description": "兼容旧插件"},
        "config": None,
        "actions": [],
        "resources": [],
        "guides": [],
    }


@pytest.mark.parametrize("separate_aliases", [False, True])
async def test_action_result_uses_the_serialized_names_advertised_in_its_schema(separate_aliases):
    class Output(BaseModel):
        display_name: str = (
            Field(validation_alias="inputName", serialization_alias="displayName")
            if separate_aliases
            else Field(alias="displayName")
        )

    plugin = Plugin("aliases")
    source_key = "inputName" if separate_aliases else "displayName"

    @plugin.action("profile", permission="read", output_model=Output)
    def profile(payload, caller):
        return Output.model_validate({source_key: "公开名称"})

    contract = plugin.surface.describe(plugin)
    advertised = contract["actions"][0]["output_schema"]
    assert advertised["required"] == ["displayName"]
    assert set(advertised["properties"]) == {"displayName"}
    result = await plugin.surface.invoke(plugin, "profile", {}, invocation("read"))
    assert result == {"displayName": "公开名称"}


async def test_one_business_handler_supports_a_resource_and_a_guide():
    plugin = Plugin("subscriptions", version="1.2.0", config=Settings)
    rows = []

    @plugin.action("list", output_model=Rows, permission="read", title="订阅列表")
    async def list_rows(payload, caller):
        return list(rows)

    @plugin.action("create", input_model=CreateSubscription, output_model=Subscription)
    async def create_row(payload, caller):
        assert caller.identity == "test-user"
        assert caller.context == "runtime-context"
        row = payload.model_dump()
        rows.append(row)
        return row

    plugin.resource(
        "subscriptions", title="直播订阅", list_action="list", columns=["room", "group"], create_action="create"
    )
    plugin.view("subscriptions", title="订阅管理", entry="web/index.html", anchors=["create"])
    plugin.guide(
        "first",
        title="创建第一个订阅",
        steps=[
            {"target": "config.subscription.room", "text": "填写直播间"},
            {"target": "action.create", "text": "添加订阅"},
            {"target": "resource.subscriptions", "text": "查看结果"},
            {"target": "view.subscriptions.create", "text": "打开订阅管理页面"},
        ],
        completion_action="list",
    )
    contract = plugin.surface.describe(plugin)
    assert contract["config"]["properties"]["interval"]["minimum"] == 15
    assert contract["actions"][1]["permission"] == "manage"
    assert contract["actions"][1]["input_schema"]["required"] == ["room", "group"]
    assert contract["resources"][0]["columns"] == [{"key": "room", "title": "room"}, {"key": "group", "title": "group"}]
    assert contract["views"] == [
        {"id": "subscriptions", "title": "订阅管理", "entry": "web/index.html", "anchors": ["create"]}
    ]
    assert validate_contract(contract) == []
    json.dumps(contract, allow_nan=False)

    result = await plugin.surface.invoke(
        plugin, "create", {"room": "test-room", "group": "test-group"}, invocation("manage", context="runtime-context")
    )
    assert result == {"room": "test-room", "group": "test-group"}
    assert await plugin.surface.invoke(plugin, "list", {}, invocation("read")) == [result]


@pytest.mark.parametrize(
    "granted, required, allowed",
    [
        ("read", "read", True),
        ("read", "operate", False),
        ("read", "manage", False),
        ("operate", "read", True),
        ("operate", "operate", True),
        ("operate", "manage", False),
        ("manage", "read", True),
        ("manage", "operate", True),
        ("manage", "manage", True),
        ("admin", "read", False),
    ],
)
async def test_action_permissions_use_only_the_immutable_invocation(granted, required, allowed):
    plugin = Plugin("permissions")
    calls = []

    @plugin.action("perform", permission=required)
    def perform(payload, caller):
        calls.append(caller.identity)
        return {"identity": caller.identity}

    payload = {"identity": "forged-user", "permissions": ["manage"]}
    if allowed:
        assert await plugin.surface.invoke(plugin, "perform", payload, invocation(granted)) == {"identity": "test-user"}
        assert calls == ["test-user"]
        return
    with pytest.raises(action_error()) as raised:
        await plugin.surface.invoke(plugin, "perform", payload, invocation(granted))
    assert raised.value.code == "permission_denied"
    assert calls == []


def test_invocation_copies_permission_sets_and_is_frozen():
    from neobot_modloader.sdk import ActionInvocation

    permissions = {"read"}
    caller = ActionInvocation(identity="test-user", permissions=permissions)
    permissions.add("manage")
    assert caller.permissions == frozenset({"read"})
    with pytest.raises(dataclasses.FrozenInstanceError):
        caller.identity = "forged-user"


async def test_invocation_cannot_be_supplied_as_request_json():
    plugin = Plugin("invocation")

    @plugin.action("perform")
    def perform(payload, caller):
        raise AssertionError("未授权请求不应进入业务处理器")

    with pytest.raises(action_error()) as raised:
        await plugin.surface.invoke(plugin, "perform", {}, {"identity": "forged-user", "permissions": ["manage"]})
    assert raised.value.code == "invalid_invocation"


@pytest.mark.parametrize("failure", ["input", "output", "handler", "json"])
async def test_action_failures_are_structured_and_hide_sensitive_inputs(failure):
    plugin = Plugin("errors")
    sensitive = "private-input-value"

    @plugin.action("perform", input_model=CountInput, output_model=CountOutput if failure != "json" else None)
    async def perform(payload, caller):
        if failure == "handler":
            raise ValueError(sensitive)
        if failure == "output":
            return {"total": sensitive}
        if failure == "json":
            return {"value": object()}
        return {"total": payload.count}

    with pytest.raises(action_error()) as raised:
        await plugin.surface.invoke(
            plugin, "perform", {"count": sensitive if failure == "input" else 1}, invocation("manage")
        )
    expected = {
        "input": "invalid_input",
        "output": "invalid_output",
        "handler": "action_failed",
        "json": "invalid_output",
    }
    assert raised.value.code == expected[failure]
    assert sensitive not in str(raised.value)
    assert sensitive not in json.dumps(raised.value.to_dict())
    assert "code" in raised.value.to_dict()


async def test_unknown_actions_and_unserializable_input_are_rejected():
    plugin = Plugin("missing")

    @plugin.action("perform")
    def perform(payload, caller):
        return payload

    with pytest.raises(action_error()) as missing:
        await plugin.surface.invoke(plugin, "absent", {}, invocation("manage"))
    assert missing.value.code == "action_not_found"
    with pytest.raises(action_error()) as invalid:
        await plugin.surface.invoke(plugin, "perform", {"bad": object()}, invocation("manage"))
    assert invalid.value.code == "invalid_input"


@pytest.mark.parametrize("kind", ["action", "resource", "guide"])
def test_duplicate_ids_are_rejected(kind):
    plugin = Plugin("duplicates")

    def register():
        if kind == "action":
            return plugin.action("same")(lambda payload, caller: {})
        if kind == "resource":
            return plugin.resource("same", title="列表", list_action="list", columns=["name"])
        return plugin.guide("same", title="教程", steps=[{"target": "action.list", "text": "查看"}])

    register()
    with pytest.raises(ValueError, match="same"):
        register()


@pytest.mark.parametrize("target", ["config.missing", "action.missing", "resource.missing", "css.#button"])
def test_guides_reject_missing_or_uncontrolled_targets(target):
    plugin = Plugin("targets", config=Settings)
    plugin.guide("first", title="教程", steps=[{"target": target, "text": "查看"}])
    with pytest.raises(ValueError):
        plugin.surface.describe(plugin)


@pytest.mark.parametrize("kind", ["list", "completion", "create", "delete"])
def test_surfaces_reject_unknown_action_references(kind):
    plugin = Plugin("references")
    if kind == "completion":
        plugin.guide(
            "first", title="教程", steps=[{"target": "action.list", "text": "查看"}], completion_action="missing"
        )
    else:
        plugin.resource(
            "rows",
            title="列表",
            list_action="missing" if kind == "list" else "list",
            columns=["name"],
            create_action="missing" if kind == "create" else None,
            delete_action="missing" if kind == "delete" else None,
        )

    @plugin.action("list", permission="read")
    def list_rows(payload, caller):
        return []

    with pytest.raises(ValueError, match="missing"):
        plugin.surface.describe(plugin)


@pytest.mark.parametrize("kind", ["list", "completion"])
def test_automatic_checks_and_queries_must_be_read_actions(kind):
    plugin = Plugin("readability")

    @plugin.action("write", permission="operate")
    def write(payload, caller):
        return {}

    if kind == "list":
        plugin.resource("rows", title="列表", list_action="write", columns=["name"])
    else:
        plugin.guide(
            "first", title="教程", steps=[{"target": "action.write", "text": "查看"}], completion_action="write"
        )
    with pytest.raises(ValueError, match="read"):
        plugin.surface.describe(plugin)


@pytest.mark.parametrize("kind", ["create", "delete"])
def test_resource_mutations_cannot_reuse_read_actions(kind):
    plugin = Plugin("mutation")

    @plugin.action("list", permission="read")
    def list_rows(payload, caller):
        return []

    plugin.resource(
        "rows",
        title="列表",
        list_action="list",
        columns=["name"],
        create_action="list" if kind == "create" else None,
        delete_action="list" if kind == "delete" else None,
    )
    with pytest.raises(ValueError, match="operate|manage"):
        plugin.surface.describe(plugin)


def test_forward_references_are_validated_after_registration_and_definitions_are_copied():
    plugin = Plugin("forward")
    steps = [{"target": "action.list", "text": "查看列表"}]
    columns = [{"key": "name", "title": "名称"}]
    plugin.guide("first", title="教程", steps=steps, completion_action="list")
    plugin.resource("rows", title="列表", list_action="list", columns=columns)
    steps[0]["target"] = "action.missing"
    columns[0]["key"] = "changed"

    @plugin.action("list", permission="read")
    def list_rows(payload, caller):
        return []

    contract = plugin.surface.describe(plugin)
    assert contract["guides"][0]["steps"][0]["target"] == "action.list"
    assert contract["resources"][0]["columns"] == [{"key": "name", "title": "名称"}]
    contract["resources"][0]["columns"][0]["key"] = "outside-change"
    assert plugin.surface.describe(plugin)["resources"][0]["columns"][0]["key"] == "name"


@pytest.mark.parametrize("name", ["", "../escape", "has/slash", "space name", "double..dot"])
def test_surface_ids_are_not_paths(name):
    plugin = Plugin("ids")
    with pytest.raises(ValueError):
        plugin.action(name)


def test_invalid_permissions_models_and_columns_are_rejected_at_registration():
    plugin = Plugin("invalid")
    with pytest.raises(ValueError):
        plugin.action("permission", permission="admin")
    with pytest.raises(ValueError):
        plugin.action("model", input_model=dict)
    with pytest.raises(ValueError):
        plugin.resource("columns", title="列表", list_action="list", columns=["name", "name"])


async def test_user_mapping_keys_do_not_appear_in_validation_errors():
    class MappingInput(BaseModel):
        values: dict[str, int]

    plugin = Plugin("mapping")

    @plugin.action("perform", input_model=MappingInput)
    def perform(payload, caller):
        raise AssertionError("非法输入不应进入业务处理器")

    sensitive = "private-mapping-key"
    with pytest.raises(action_error()) as raised:
        await plugin.surface.invoke(plugin, "perform", {"values": {sensitive: "bad"}}, invocation("manage"))
    assert raised.value.code == "invalid_input"
    assert sensitive not in json.dumps(raised.value.to_dict())
    assert raised.value.fields == [{"path": ["values"], "type": "int_parsing"}]


async def test_invocation_rejects_a_surface_from_another_plugin():
    plugin = Plugin("owner")
    other = Plugin("other")

    @plugin.action("perform")
    def perform(payload, caller):
        raise AssertionError("错误的契约归属不应进入业务处理器")

    with pytest.raises(action_error()) as raised:
        await plugin.surface.invoke(other, "perform", {}, invocation("manage"))
    assert raised.value.code == "contract_invalid"


async def test_cancellation_is_not_reported_as_a_business_failure():
    import asyncio

    plugin = Plugin("cancellation")

    @plugin.action("perform")
    async def perform(payload, caller):
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await plugin.surface.invoke(plugin, "perform", {}, invocation("manage"))
