"""Dedicated PTC language, capability, resource, and cancellation tests."""
from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import pytest

from neobot_app.agent_tools.contracts import AgentToolError, tool_definition
from neobot_app.agent_tools.ptc import (
    PtcError, PtcLimits, PtcRunner, ToolCallError, build_python_sdk, ptc_tool_definition,
)

DEFINITIONS = [tool_definition(name, name) for name in ("read", "write", "fail", "run_code")]


async def echo(name, args):
    return args


async def run(code, dispatch=echo, **limits):
    return await PtcRunner(PtcLimits(**limits)).run(code, dispatch, definitions=DEFINITIONS)


async def test_combine_results_loop_index_and_return():
    calls = []

    async def dispatch(name, args):
        calls.append((name, args))
        return {"value": args["id"] * 2}

    output = await run("""
rows = []
for i in range(5):
    if i % 2 == 0:
        row = await tools.read({"id": i})
        rows = rows + [row["value"]]
rows[0] = 1
summary = {"rows": rows, "total": sum(rows)}
summary["count"] = len(rows)
print("total", summary["total"])
return summary
""", dispatch)
    assert output == {"logs": ["total 13"], "logs_truncated": False,
                      "result": {"rows": [1, 4, 8], "total": 13, "count": 3}}
    assert [args["id"] for _, args in calls] == [0, 2, 4]
    assert json.loads(json.dumps(output)) == output


async def test_control_flow_short_circuit_and_builtins():
    output = await run("""
value = 0
for i in range(1, 8, 2):
    if i == 3:
        continue
    if i > 5:
        break
    value = value + i
else:
    value = 100
unused = False and await tools.fail({})
also = True or await tools.fail({})
return [value, abs(-3), min([2, 1]), max([2, 1]), "abc"[-1],
        "x" in {"x": 1}, 1 < 2 < 3, None is None, 5 if not False else 9]
""")
    assert output["result"] == [6, 3, 1, 2, "c", True, True, True, 5]


async def test_error_recovery_preserves_code_tool_name_and_message():
    async def dispatch(name, args):
        if name == "fail":
            raise AgentToolError("NOT_AUTHORIZED", "Permission denied")
        return args

    result = await run("""
try:
    await tools.fail({})
except ToolCallError as e:
    print(e.code, e.toolName)
    recovered = await tools.read({"code": e.code, "tool": e.toolName, "message": e.message})
return recovered
""", dispatch)
    assert result["result"] == {"code": "NOT_AUTHORIZED", "tool": "fail", "message": "Permission denied"}
    assert result["logs"] == ["NOT_AUTHORIZED fail"]


async def test_uncaught_and_generic_tool_errors():
    async def dispatch(name, args):
        raise RuntimeError("secret host internals")

    with pytest.raises(ToolCallError) as caught:
        await run("return await tools.read({})", dispatch)
    assert caught.value.code == "TOOL_FAILED"
    assert caught.value.toolName == "read"
    assert "secret" not in caught.value.message


@pytest.mark.parametrize("code", [
    "import os", "from os import system", "return __import__('os')",
    "return (1).__class__", "return tools.__dict__", "return getattr({}, 'x')",
    "return eval('1')", "exec('1')", "return open('x')", "return globals()",
    "return type(1)", "return tools.read", "tools.read({})", "return tools.read({}).code",
    "return await tools.run_code({})", "return await tools.missing({})",
    "return await tools.__getattribute__({})", "return [1].append(2)",
    "return (lambda: 1)()", "def f():\n    return 1", "class C: pass",
    "while True: pass", "return [x for x in range(3)]", "return [1][0:1]",
    "return f'{1}'", "return (1, 2)", "return {1, 2}", "return b'x'",
    "return 1j", "return {'x': 1, **{}}", "return len(*[[]])",
    "return len(x=[])", "try:\n    pass\nexcept Exception:\n    pass",
    "try:\n    pass\nexcept ToolCallError:\n    pass\nfinally:\n    pass",
    "tools = {}", "len = 1", "parallel = 1", "for tools in []: pass",
    "try:\n    pass\nexcept ToolCallError as tools:\n    pass",
    "return parallel([])", "return await len([])", "return await parallel([], [])",
    "break", "continue", "return 2 ** 999999999", "return 1 << 999999999",
    "await tools.write({})\nif False:\n    import os",
])
async def test_injection_or_unsupported_syntax_rejected_before_dispatch(code):
    calls = []

    async def dispatch(name, args):
        calls.append(name)
        return {}

    with pytest.raises(PtcError):
        await run(code, dispatch)
    assert calls == []


@pytest.mark.parametrize("code", [
    "return 'x' * 99999999999999999999999999",
    "return [1] * 99999999999999999999999999",
    "return range(99999999999999999999999999)",
    "return 'x' * 20000 + 'y' * 20000",
    "return 999999999999999999999999999999999999999999999999999999999999999999999999999999999999999",
    "x = 1000000000000000000000000000000000000000000000000000000000000\nreturn x * x",
    "return 1e999", "return {1: 'not JSON'}", "return 'x' % 1000000000",
    "return {}.code", "return [1][True]", "return await tools.read([])",
])
async def test_resource_and_value_rejections(code):
    with pytest.raises(PtcError):
        await run(code)


@pytest.mark.parametrize(("code", "limits"), [
    ("return 1", {"max_code_bytes": 3}),
    ("return [1,2,3,4]", {"max_ast_nodes": 5}),
    ("return [[[[1]]]]", {"max_ast_depth": 3}),
    ("for i in range(10): pass", {"max_iterations": 3}),
    ("for i in range(10): pass", {"max_steps": 5}),
    ("return [1,2,3,4]", {"max_collection_items": 3}),
    ("return [[[[1]]]]", {"max_value_depth": 2}),
    ("return [1,2,3,4]", {"max_value_nodes": 3}),
    ("return 'abcd'", {"max_string_chars": 3}),
    ("return 'abcd'", {"max_value_bytes": 3}),
    ("return 'x' * 100", {"max_result_bytes": 80}),
])
async def test_configurable_limits(code, limits):
    with pytest.raises(PtcError) as caught:
        await run(code, **limits)
    assert caught.value.code == "PTC_LIMIT"


async def test_tool_call_limit_and_limits_not_catchable():
    calls = []

    async def dispatch(name, args):
        calls.append(name)
        return {}

    with pytest.raises(PtcError) as caught:
        await run("""
try:
    for i in range(4):
        await tools.read({})
except ToolCallError:
    return "wrong"
""", dispatch, max_tool_calls=2)
    assert caught.value.code == "PTC_LIMIT"
    assert len(calls) == 2


async def test_data_expansion_and_environment_aggregate_are_bounded():
    with pytest.raises(PtcError):
        await run("x = [0]\nfor i in range(20):\n    x = [x, x]\nreturn x")
    with pytest.raises(PtcError):
        await run("a = 'x' * 100\nb = 'y' * 100\nreturn 1", max_value_bytes=180)


async def test_print_truncation_is_bounded_in_serialized_bytes():
    output = await run("for i in range(20): print('你好\\\"' * 5)\nreturn 1", max_log_bytes=45)
    assert output["logs_truncated"] is True
    assert sum(len(json.dumps(line, ensure_ascii=True)) for line in output["logs"]) <= 45
    assert output["result"] == 1
    entries = await run("for i in range(10): print(i)", max_log_entries=2)
    assert entries["logs"] == ["0", "1"] and entries["logs_truncated"]


async def test_output_limit_includes_logs_and_json_escaping():
    with pytest.raises(PtcError):
        await run("print('x' * 50)\nreturn 'y' * 50", max_result_bytes=120)
    with pytest.raises(PtcError):
        await run("return '你' * 30", max_result_bytes=180)


async def test_complete_result_byte_budget_includes_default_json_separators():
    for size in (80, 100, 150, 250):
        for code in ("return range(30)", "return {'a': [1,2,3], 'b': [4,5,6]}", "print('你')\nreturn True"):
            try:
                output = await run(code, max_result_bytes=size)
            except PtcError as exc:
                assert exc.code == "PTC_LIMIT"
            else:
                assert len(json.dumps(output, ensure_ascii=True).encode("utf-8")) <= size


async def test_dispatch_values_are_exact_json_and_copied():
    touched = []

    class HostObject:
        @property
        def code(self):
            touched.append(True)
            return "danger"

    class HostDict(dict):
        def items(self):
            touched.append(True)
            return super().items()

    cyclic = []
    cyclic.append(cyclic)
    for value in (HostObject(), HostDict(), cyclic, {1: "bad"}, float("nan"), (1, 2)):
        async def dispatch(name, args):
            return value

        with pytest.raises(PtcError):
            await run("return await tools.read({})", dispatch)
    assert touched == []

    original = {"a": [1]}
    received = []

    async def dispatch(name, args):
        received.append(args)
        args["x"][0] = 99
        return original

    result = await run("x = [1]\ny = await tools.read({'x': x})\ny['a'][0] = 3\nreturn [x, y]", dispatch)
    assert result["result"] == [[1], {"a": [3]}]
    assert original == {"a": [1]} and received == [{"x": [99]}]


async def test_timeout_cancels_and_drains_dispatch():
    cleaned = asyncio.Event()

    async def dispatch(name, args):
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            cleaned.set()

    with pytest.raises(PtcError) as caught:
        await run("return await tools.read({})", dispatch, wall_time_seconds=0.02)
    assert caught.value.code == "PTC_TIMEOUT"
    assert cleaned.is_set()


async def test_external_cancellation_propagates_after_dispatch_cleanup():
    started, cleaned = asyncio.Event(), asyncio.Event()

    async def dispatch(name, args):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            cleaned.set()

    task = asyncio.create_task(run("try:\n    await tools.read({})\nexcept ToolCallError:\n    return 1", dispatch))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cleaned.is_set()


async def test_cpu_loop_yields_for_cancellation_and_deadline():
    limits = PtcLimits(max_iterations=100000, max_steps=10000000)
    task = asyncio.create_task(PtcRunner(limits).run(
        "for i in range(4000):\n    for j in range(4000):\n        pass", echo, definitions=[]))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    with pytest.raises(PtcError) as caught:
        await PtcRunner(replace(limits, wall_time_seconds=0.001)).run(
            "for i in range(4000):\n    for j in range(4000):\n        pass", echo, definitions=[])
    assert caught.value.code == "PTC_TIMEOUT"


BATCH = "return await parallel([{'tool':'read','args':{'id':0}}, {'tool':'read','args':{'id':1}}])"


async def test_parallel_runs_safe_calls_concurrently_and_preserves_order():
    started = []
    both = asyncio.Event()

    async def dispatch(name, args):
        started.append(args["id"])
        if len(started) == 2:
            both.set()
        await both.wait()
        return args["id"]

    output = await PtcRunner().run(BATCH, dispatch, definitions=DEFINITIONS, concurrency_safe={"read"})
    assert output["result"] == [0, 1]


@pytest.mark.parametrize("safe", [set(), {"read"}])
async def test_unsafe_or_mixed_batches_run_sequentially(safe):
    active, maximum = 0, 0
    order = []

    async def dispatch(name, args):
        nonlocal active, maximum
        active += 1
        maximum = max(active, maximum)
        order.append(name)
        await asyncio.sleep(0)
        active -= 1
        return name

    code = "return await parallel([{'tool':'read','args':{}}, {'tool':'write','args':{}}])"
    output = await PtcRunner().run(code, dispatch, definitions=DEFINITIONS, concurrency_safe=safe)
    assert maximum == 1 and order == ["read", "write"]
    assert output["result"] == order


@pytest.mark.parametrize(("code", "limits"), [
    (BATCH, {"max_batch_calls": 1}), (BATCH, {"max_tool_calls": 1}),
    ("return await parallel([{'tool':'read','args':{}}, {'tool':'run_code','args':{}}])", {}),
    ("return await parallel([{'tool':'read','args':{}}, {'tool':'missing','args':{}}])", {}),
    ("return await parallel([{'tool':'read','args':{},'safe':True}])", {}),
    ("return await parallel([{'tool':'read','args':[]}])", {}),
    ("return await parallel({})", {}),
])
async def test_batch_preflight_never_partially_dispatches(code, limits):
    calls = []

    async def dispatch(name, args):
        calls.append(name)
        return {}

    with pytest.raises(PtcError):
        await run(code, dispatch, **limits)
    assert calls == []


async def test_parallel_failure_cancels_and_drains_siblings_before_recovery():
    started, cleaned = asyncio.Event(), asyncio.Event()

    async def dispatch(name, args):
        if args["id"] == 0:
            await started.wait()
            raise AgentToolError("READ_FAILED", "failed")
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            cleaned.set()

    code = "try:\n    " + BATCH.replace("return ", "") + "\nexcept ToolCallError as e:\n    return [e.code, e.toolName]"
    output = await PtcRunner().run(code, dispatch, definitions=DEFINITIONS, concurrency_safe={"read"})
    assert output["result"] == ["READ_FAILED", "read"]
    assert cleaned.is_set()


@pytest.mark.parametrize("timeout", [False, True])
async def test_parallel_cancellation_drains_all_dispatches(timeout):
    count = 0
    both = asyncio.Event()
    cleaned = []

    async def dispatch(name, args):
        nonlocal count
        count += 1
        if count == 2:
            both.set()
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            cleaned.append(args["id"])

    runner = PtcRunner(PtcLimits(wall_time_seconds=0.03 if timeout else 30))
    task = asyncio.create_task(runner.run(BATCH, dispatch, definitions=DEFINITIONS, concurrency_safe={"read"}))
    await both.wait()
    if timeout:
        with pytest.raises(PtcError) as caught:
            await task
        assert caught.value.code == "PTC_TIMEOUT"
    else:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert sorted(cleaned) == [0, 1]


async def test_reusable_runner_isolates_runs_and_deny_list():
    runner = PtcRunner()
    first, second = await asyncio.gather(
        runner.run("x = 1\nreturn x", echo, definitions=[]),
        runner.run("x = 2\nreturn x", echo, definitions=[]),
    )
    assert [first["result"], second["result"]] == [1, 2]
    with pytest.raises(PtcError):
        await runner.run("return x", echo, definitions=[])
    with pytest.raises(PtcError) as caught:
        await runner.run("return await tools.read({})", echo, definitions=[])
    assert caught.value.code == "PTC_TOOL_DENIED"


@pytest.mark.parametrize("name", ["image_context__add_image", "credential__request"])
async def test_registered_namespaced_tools_work_in_direct_calls_batches_and_sdk(name):
    definitions = [tool_definition(name, "Namespaced skill")]
    calls = []

    async def dispatch(tool_name, args):
        calls.append((tool_name, args))
        return args

    runner = PtcRunner()
    direct = await runner.run(f"return await tools.{name}({{'value': 1}})", dispatch, definitions=definitions)
    batch = await runner.run(
        f"return await parallel([{{'tool': '{name}', 'args': {{'value': 2}}}}])",
        dispatch, definitions=definitions, concurrency_safe={name},
    )
    assert direct["result"] == {"value": 1} and batch["result"] == [{"value": 2}]
    assert calls == [(name, {"value": 1}), (name, {"value": 2})]
    assert f"await tools.{name}(args)" in build_python_sdk(definitions)


@pytest.mark.parametrize("name", ["__class__", "__dict__", "_private", "read__", "missing__tool"])
async def test_namespace_support_does_not_expose_magic_private_or_unregistered_tools(name):
    definitions = [tool_definition(registered, "test") for registered in
                   ("__class__", "__dict__", "_private", "read__", "image_context__add_image")]
    calls = []

    async def dispatch(tool_name, args):
        calls.append(tool_name)
        return {}

    for code in (f"return await tools.{name}({{}})",
                 f"return await parallel([{{'tool': '{name}', 'args': {{}}}}])"):
        with pytest.raises(PtcError) as caught:
            await PtcRunner().run(code, dispatch, definitions=definitions)
        assert caught.value.code == "PTC_TOOL_DENIED"
    assert calls == []
    assert f"await tools.{name}(args)" not in build_python_sdk(definitions)


@pytest.mark.parametrize("code", [
    "a__b = 1", "return {}.__dict__", "return {}.image_context__add_image",
    "try:\n    pass\nexcept ToolCallError as a__b:\n    pass",
])
async def test_namespace_support_keeps_variables_and_error_attributes_strict(code):
    with pytest.raises(PtcError) as caught:
        await run(code)
    assert caught.value.code == "PTC_SYNTAX"


def test_sdk_truthfully_documents_subset_schemas_and_parallel():
    definitions = DEFINITIONS + [tool_definition("__bad", "bad"), tool_definition("not-python", "bad")]
    sdk = build_python_sdk(definitions, concurrency_safe={"read", "unknown"})
    assert "NOT full Python" in sdk and "Host concurrency-safe tools: read" in sdk
    assert "await tools.read(args)" in sdk and "await tools.run_code(args)" not in sdk
    assert "await tools.__bad" not in sdk and "await tools.not-python" not in sdk
    definition = ptc_tool_definition(definitions)["function"]
    assert definition["name"] == "run_code"
    assert definition["parameters"]["required"] == ["code", "description"]
    assert definition["parameters"]["properties"]["code"]["type"] == "string"
    assert definition["parameters"]["properties"]["description"]["type"] == "string"
    assert definition["parameters"]["additionalProperties"] is False


@pytest.mark.parametrize("limits", [{"max_steps": 0}, {"max_steps": True}, {"wall_time_seconds": float("inf")}])
def test_invalid_host_limits_rejected(limits):
    with pytest.raises(ValueError):
        PtcLimits(**limits)
