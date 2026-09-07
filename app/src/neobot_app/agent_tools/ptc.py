"""Bounded, capability-free Python-subset interpreter for programmatic tool calls.

Model source is parsed, never eval/exec'ed or imported. This is not a claim that
Python processes/VMs are security sandboxes. The trusted dispatcher must authorize
every call and cooperate with cancellation; it owns any tasks/resources it spawns.
Only exact JSON primitives enter the interpreter, never arbitrary host objects.
"""
from __future__ import annotations

import ast
import asyncio
import json
import keyword
import math
import operator
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .contracts import AgentToolError, tool_definition

Dispatch = Callable[[str, dict], Awaitable[Any]]


class PtcError(AgentToolError):
    """Non-catchable interpreter failure (stable PTC_* code)."""


class ToolCallError(AgentToolError):
    """The only error model programs may catch."""

    def __init__(self, code: str, toolName: str, message: str) -> None:
        super().__init__(code, message)
        self.toolName = toolName
        self.message = message


@dataclass(frozen=True, slots=True)
class PtcLimits:
    max_code_bytes: int = 32_768
    max_ast_nodes: int = 4_000
    max_ast_depth: int = 64
    max_steps: int = 30_000
    max_iterations: int = 4_000
    max_tool_calls: int = 32
    max_batch_calls: int = 16
    max_collection_items: int = 4_000
    max_value_nodes: int = 16_000
    max_value_depth: int = 32
    max_string_chars: int = 32_768
    max_integer_bits: int = 256
    max_value_bytes: int = 262_144
    max_result_bytes: int = 262_144
    max_log_bytes: int = 16_384
    max_log_entries: int = 128
    wall_time_seconds: float = 30.0

    def __post_init__(self) -> None:
        for field in self.__dataclass_fields__:
            value = getattr(self, field)
            if field == "wall_time_seconds":
                if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                    raise ValueError("wall_time_seconds must be positive and finite")
            elif type(value) is not int or value <= 0:
                raise ValueError(f"{field} must be a positive integer")


_BUILTINS = frozenset({"len", "range", "sum", "min", "max", "abs", "print"})
_RESERVED = _BUILTINS | {"tools", "ToolCallError", "run_code", "parallel"}
_NODES = (
    ast.Module, ast.Assign, ast.Expr, ast.Return, ast.If, ast.For, ast.Try,
    ast.ExceptHandler, ast.Pass, ast.Break, ast.Continue, ast.Name, ast.Constant,
    ast.List, ast.Dict, ast.Subscript, ast.BinOp, ast.UnaryOp, ast.BoolOp,
    ast.Compare, ast.IfExp, ast.Call, ast.Await, ast.Attribute,
    ast.Load, ast.Store, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv,
    ast.Mod, ast.UAdd, ast.USub, ast.Not, ast.And, ast.Or, ast.Eq, ast.NotEq,
    ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot,
)


def _identifier(name: str) -> bool:
    return name.isidentifier() and not keyword.iskeyword(name) and not name.startswith("_") and "__" not in name


def _tool_identifier(name: str) -> bool:
    """Registered namespaces may contain __; Python magic/private names may not."""
    return (name.isidentifier() and not keyword.iskeyword(name)
            and not name.startswith("_") and not name.endswith("__"))


def _allowed(definitions: list[dict]) -> dict[str, dict]:
    result = {}
    for definition in definitions:
        function = definition.get("function", definition)
        name = function.get("name")
        if type(name) is str and _tool_identifier(name) and name not in _RESERVED:
            result[name] = function
    return result


def build_python_sdk(definitions: list[dict], *, concurrency_safe: set[str] | None = None) -> str:
    """Generate a truthful SDK description, not executable Python bindings."""
    lines = [
        "PTC is a bounded Python AST subset, NOT full Python or a Python process sandbox.",
        "Use top-level return for a JSON result; print(...) adds bounded logs.",
        "Supported: assignment to names/list or dict indexes, list/dict literals, indexing,",
        "for/if, break/continue, and/or/not, comparisons, conditional expressions,",
        "bounded + - * / // % (numeric; + and * also strings/lists). No exponentiation.",
        "Builtins: len(x), range(stop) / range(start, stop[, step]) (bounded list),",
        "sum(numbers), min(numbers), max(numbers), abs(number), print(*values).",
        "Tools: await tools.NAME({JSON arguments}); every call is re-authorized.",
        "Batch: await parallel([{\"tool\": \"NAME\", \"args\": {...}}, ...]); results preserve order.",
        "Only batches entirely in the host concurrency-safe list run concurrently; others run sequentially.",
        "A failed concurrent batch cancels and drains remaining calls; completed effects are not rolled back.",
        "Assignments copy JSON values (no Python container aliasing).",
        "Catch tool failures only: try: ... except ToolCallError as e: ...",
        "Only e.code, e.toolName, e.message are accessible. Other errors terminate the run.",
        "No imports, functions/classes, recursion, comprehensions, while, tuples, sets,",
        "slices, f-strings, object methods, getattr, arbitrary calls/attributes, or asyncio.",
        "No OS/file/network access except through allowed tools. run_code cannot call itself.",
        "Source/AST/steps/loops/calls/data/logs/result/time are limited; oversized results fail.",
        "Logs may truncate (logs_truncated=true). Result: {logs, result, logs_truncated}.",
        "Available tool signatures and JSON argument schemas:",
    ]
    lines.append("Host concurrency-safe tools: " + ", ".join(sorted(set(_allowed(definitions)) & (concurrency_safe or set()))))
    for name, function in _allowed(definitions).items():
        lines.append(f"await tools.{name}(args): {function.get('description', '')}")
        lines.append(json.dumps(function.get("parameters", {}), ensure_ascii=True))
    return "\n".join(lines)


def ptc_tool_definition(definitions: list[dict], *, concurrency_safe: set[str] | None = None) -> dict:
    return tool_definition(
        "run_code", build_python_sdk(definitions, concurrency_safe=concurrency_safe),
        {
            "code": {"type": "string", "description": "Bounded Python-subset program, not full Python."},
            "description": {"type": "string", "description": "Brief user-facing summary of this program."},
        },
        ["code", "description"],
    )


class _Return(Exception):
    def __init__(self, value: Any) -> None:
        self.value = value


class _Break(Exception):
    pass


class _Continue(Exception):
    pass


class PtcRunner:
    """Reusable configuration; each run has isolated variables and resource counters."""

    def __init__(self, limits: PtcLimits | None = None) -> None:
        self.limits = limits or PtcLimits()

    async def run(
        self, code: str, dispatch: Dispatch, *, definitions: list[dict],
        concurrency_safe: set[str] | None = None,
    ) -> dict:
        state = _Interpreter(self.limits, dispatch, set(_allowed(definitions)), concurrency_safe or set())
        try:
            async with asyncio.timeout(self.limits.wall_time_seconds):
                tree = state.parse(code)
                result = None
                try:
                    await state.block(tree.body)
                except _Return as returned:
                    result = returned.value
                output = {"logs": state.logs, "result": state.json_value(result),
                          "logs_truncated": state.logs_truncated}
                state.json_value(output, byte_limit=self.limits.max_result_bytes)
                await state.tick()
                return output
        except TimeoutError as exc:
            raise PtcError("PTC_TIMEOUT", "Program wall-clock limit exceeded") from exc
        except (PtcError, ToolCallError, asyncio.CancelledError):
            raise
        except (ArithmeticError, LookupError, TypeError, ValueError, RecursionError) as exc:
            raise PtcError("PTC_RUNTIME", f"Invalid operation: {type(exc).__name__}") from exc


class _Interpreter:
    def __init__(self, limits: PtcLimits, dispatch: Dispatch, allowed: set[str], safe: set[str]) -> None:
        self.limits, self.dispatch, self.allowed = limits, dispatch, allowed
        self.safe = allowed & safe
        self.env: dict[str, Any] = {}
        self.logs: list[str] = []
        self.logs_truncated = False
        self.log_bytes = self.steps = self.iterations = self.tool_calls = 0
        self.deadline = time.monotonic() + limits.wall_time_seconds

    def fail(self, message: str, code: str = "PTC_LIMIT") -> None:
        raise PtcError(code, message)

    async def tick(self) -> None:
        self.steps += 1
        if self.steps > self.limits.max_steps:
            self.fail("Step limit exceeded")
        if time.monotonic() >= self.deadline:
            self.fail("Program wall-clock limit exceeded", "PTC_TIMEOUT")
        if self.steps % 64 == 0:
            await asyncio.sleep(0)

    def parse(self, code: str) -> ast.Module:
        if type(code) is not str:
            self.fail("code must be a string", "PTC_SYNTAX")
        if len(code) > self.limits.max_code_bytes or len(code.encode("utf-8")) > self.limits.max_code_bytes:
            self.fail("Source limit exceeded")
        try:
            tree = ast.parse(code, mode="exec")
        except (SyntaxError, ValueError, RecursionError) as exc:
            raise PtcError("PTC_SYNTAX", "Invalid Python-subset syntax") from exc
        pending = [(tree, None, 0, 0)]
        count = 0
        while pending:
            node, parent, depth, loops = pending.pop()
            count += 1
            if count > self.limits.max_ast_nodes or depth > self.limits.max_ast_depth:
                self.fail("AST size/depth limit exceeded")
            if type(node) not in _NODES:
                self.fail(f"Unsupported syntax: {type(node).__name__}", "PTC_SYNTAX")
            if isinstance(node, ast.Name):
                if not _identifier(node.id) or (isinstance(node.ctx, ast.Store) and node.id in _RESERVED):
                    self.fail("Forbidden identifier", "PTC_SYNTAX")
            if isinstance(node, ast.Constant):
                self.json_value(node.value)
            if isinstance(node, ast.Assign):
                if len(node.targets) != 1 or not isinstance(node.targets[0], (ast.Name, ast.Subscript)):
                    self.fail("Only single name/index assignment is supported", "PTC_SYNTAX")
            if isinstance(node, ast.For) and not isinstance(node.target, ast.Name):
                self.fail("for requires a name target", "PTC_SYNTAX")
            if isinstance(node, (ast.Break, ast.Continue)) and not loops:
                self.fail("Loop control outside loop", "PTC_SYNTAX")
            if isinstance(node, ast.Try):
                if node.finalbody or len(node.handlers) != 1:
                    self.fail("Only one ToolCallError handler, without finally, is supported", "PTC_SYNTAX")
            if isinstance(node, ast.ExceptHandler):
                if not isinstance(node.type, ast.Name) or node.type.id != "ToolCallError":
                    self.fail("Only ToolCallError may be caught", "PTC_SYNTAX")
                if node.name and (not _identifier(node.name) or node.name in _RESERVED):
                    self.fail("Forbidden exception name", "PTC_SYNTAX")
            if isinstance(node, ast.Dict) and any(key is None for key in node.keys):
                self.fail("Dictionary unpacking is unsupported", "PTC_SYNTAX")
            if isinstance(node, ast.Attribute):
                tool = (isinstance(parent, ast.Call) and parent.func is node
                        and isinstance(node.value, ast.Name) and node.value.id == "tools")
                if tool:
                    if not _tool_identifier(node.attr) or node.attr == "run_code" or node.attr not in self.allowed:
                        self.fail("Tool is not in allowed definitions", "PTC_TOOL_DENIED")
                elif node.attr not in {"code", "toolName", "message"} or not isinstance(node.ctx, ast.Load):
                    self.fail("Arbitrary attributes are forbidden", "PTC_SYNTAX")
            if isinstance(node, ast.Await):
                if (not isinstance(node.value, ast.Call)
                        or not (isinstance(node.value.func, ast.Attribute)
                                or isinstance(node.value.func, ast.Name) and node.value.func.id == "parallel")):
                    self.fail("Only await tools.NAME({...}) or await parallel([...]) is supported", "PTC_SYNTAX")
            if isinstance(node, ast.Call):
                if node.keywords:
                    self.fail("Keyword arguments are unsupported", "PTC_SYNTAX")
                if isinstance(node.func, ast.Name):
                    if node.func.id == "parallel":
                        if not isinstance(parent, ast.Await) or len(node.args) != 1:
                            self.fail("parallel requires await and one descriptor list", "PTC_SYNTAX")
                    elif node.func.id not in _BUILTINS:
                        self.fail("Arbitrary calls are forbidden", "PTC_SYNTAX")
                elif isinstance(node.func, ast.Attribute):
                    if (not isinstance(parent, ast.Await) or not isinstance(node.func.value, ast.Name)
                            or node.func.value.id != "tools" or len(node.args) != 1):
                        self.fail("Tools require await tools.NAME(one_dict)", "PTC_SYNTAX")
                else:
                    self.fail("Arbitrary calls are forbidden", "PTC_SYNTAX")
            for child in ast.iter_child_nodes(node):
                child_loops = loops + int(isinstance(node, ast.For) and child in node.body)
                pending.append((child, node, depth + 1, child_loops))
        return tree

    def json_value(self, value: Any, *, byte_limit: int | None = None) -> Any:
        """Bound traversal BEFORE serialization; reject cycles, non-JSON and subclasses.

        Copy containers at trust boundaries so dispatch cannot mutate interpreter data.
        Repeated aliases are charged on every appearance (no exponential expansion).
        """
        nodes = 0
        budget = self.limits.max_value_bytes if byte_limit is None else byte_limit
        active: set[int] = set()

        def visit(item: Any, depth: int) -> Any:
            nonlocal nodes, budget
            nodes += 1
            if nodes > self.limits.max_value_nodes or depth > self.limits.max_value_depth:
                self.fail("JSON node/depth limit exceeded")
            kind = type(item)
            if kind is str:
                if len(item) > self.limits.max_string_chars:
                    self.fail("String limit exceeded")
                budget -= len(json.dumps(item, ensure_ascii=True))
                result = item
            elif item is None or kind is bool:
                budget -= 5
                result = item
            elif kind is int:
                if item.bit_length() > self.limits.max_integer_bits:
                    self.fail("Integer limit exceeded")
                budget -= len(str(item))
                result = item
            elif kind is float:
                if not math.isfinite(item):
                    self.fail("Non-finite number is not JSON", "PTC_VALUE")
                budget -= len(json.dumps(item))
                result = item
            elif kind in (list, dict):
                if len(item) > self.limits.max_collection_items:
                    self.fail("Collection limit exceeded")
                if id(item) in active:
                    self.fail("Cyclic values are forbidden", "PTC_VALUE")
                # Conservatively includes default json.dumps comma/colon spaces.
                budget -= 2 + len(item) * (4 if kind is dict else 2)
                if budget < 0:
                    self.fail("JSON byte limit exceeded")
                active.add(id(item))
                if kind is list:
                    result = [visit(value, depth + 1) for value in item]
                else:
                    result = {}
                    for key, value in item.items():
                        if type(key) is not str:
                            self.fail("JSON object keys must be strings", "PTC_VALUE")
                        result[visit(key, depth + 1)] = visit(value, depth + 1)
                active.remove(id(item))
            else:
                self.fail("Only exact JSON primitives are allowed", "PTC_VALUE")
            if budget < 0:
                self.fail("JSON byte limit exceeded")
            return result

        return visit(value, 0)

    def check_env(self) -> None:
        self.json_value({key: value for key, value in self.env.items() if type(value) is not ToolCallError})

    async def block(self, statements: list[ast.stmt]) -> None:
        for statement in statements:
            await self.statement(statement)

    async def statement(self, node: ast.stmt) -> None:
        await self.tick()
        if isinstance(node, ast.Assign):
            value = self.json_value(await self.expr(node.value))
            target = node.targets[0]
            if isinstance(target, ast.Name):
                self.env[target.id] = value
            else:
                container = await self.expr(target.value)
                index = await self.expr(target.slice)
                self.index(container, index, writing=True)
                container[index] = value
            self.check_env()
        elif isinstance(node, ast.Expr):
            await self.expr(node.value)
        elif isinstance(node, ast.Return):
            raise _Return(await self.expr(node.value) if node.value else None)
        elif isinstance(node, ast.If):
            await self.block(node.body if await self.expr(node.test) else node.orelse)
        elif isinstance(node, ast.For):
            values = self.json_value(await self.expr(node.iter))
            if type(values) not in (list, dict, str):
                self.fail("for requires a list, dict or string", "PTC_RUNTIME")
            for value in values:
                self.iterations += 1
                if self.iterations > self.limits.max_iterations:
                    self.fail("Iteration limit exceeded")
                self.env[node.target.id] = value
                self.check_env()
                try:
                    await self.block(node.body)
                except _Continue:
                    continue
                except _Break:
                    break
            else:
                await self.block(node.orelse)
        elif isinstance(node, ast.Try):
            try:
                await self.block(node.body)
            except ToolCallError as exc:
                handler = node.handlers[0]
                if handler.name:
                    self.env[handler.name] = exc
                try:
                    await self.block(handler.body)
                finally:
                    if handler.name:
                        self.env.pop(handler.name, None)
            else:
                await self.block(node.orelse)
        elif isinstance(node, ast.Break):
            raise _Break()
        elif isinstance(node, ast.Continue):
            raise _Continue()
        elif not isinstance(node, ast.Pass):
            self.fail("Unsupported statement", "PTC_SYNTAX")

    def index(self, container: Any, index: Any, *, writing: bool = False) -> None:
        if type(container) is dict and type(index) is str:
            return
        if type(container) in ((list,) if writing else (list, str)) and type(index) is int:
            return
        self.fail("Only JSON list/string integer or dict string indexing is allowed", "PTC_RUNTIME")

    async def expr(self, node: ast.expr) -> Any:
        await self.tick()
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in self.env:
                self.fail(f"Unknown variable: {node.id}", "PTC_RUNTIME")
            return self.env[node.id]
        if isinstance(node, ast.List):
            return self.json_value([await self.expr(value) for value in node.elts])
        if isinstance(node, ast.Dict):
            result = {}
            for key, value in zip(node.keys, node.values):
                name = await self.expr(key)
                if type(name) is not str:
                    self.fail("JSON object keys must be strings", "PTC_VALUE")
                result[name] = await self.expr(value)
            return self.json_value(result)
        if isinstance(node, ast.Subscript):
            container, index = await self.expr(node.value), await self.expr(node.slice)
            self.index(container, index)
            return container[index]
        if isinstance(node, ast.Attribute):
            error = await self.expr(node.value)
            if type(error) is not ToolCallError or node.attr not in {"code", "toolName", "message"}:
                self.fail("Only ToolCallError fields are accessible", "PTC_RUNTIME")
            return self.json_value({"code": error.code, "toolName": error.toolName, "message": error.message}[node.attr])
        if isinstance(node, ast.Await):
            call = node.value
            args = self.json_value(await self.expr(call.args[0]))
            if isinstance(call.func, ast.Name):
                return await self.parallel(args)
            self.validate_call(call.func.attr, args)
            self.charge_calls(1)
            return await self.invoke(call.func.attr, args)
        if isinstance(node, ast.Call):
            return self.builtin(node.func.id, [await self.expr(arg) for arg in node.args])
        if isinstance(node, ast.IfExp):
            return await self.expr(node.body if await self.expr(node.test) else node.orelse)
        if isinstance(node, ast.BoolOp):
            for child in node.values:
                result = await self.expr(child)
                if isinstance(node.op, ast.And) and not result or isinstance(node.op, ast.Or) and result:
                    return result
            return result
        if isinstance(node, ast.UnaryOp):
            value = await self.expr(node.operand)
            if isinstance(node.op, ast.Not):
                return not value
            self.numeric(value)
            return self.json_value(-value if isinstance(node.op, ast.USub) else value)
        if isinstance(node, ast.BinOp):
            return self.binary(node.op, await self.expr(node.left), await self.expr(node.right))
        if isinstance(node, ast.Compare):
            left = self.json_value(await self.expr(node.left))
            comparisons = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
                           ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
                           ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b}
            for op, child in zip(node.ops, node.comparators):
                right = self.json_value(await self.expr(child))
                if isinstance(op, (ast.Is, ast.IsNot)):
                    if left is not None and right is not None:
                        self.fail("is/is not only support None checks", "PTC_RUNTIME")
                    passed = (left is right) if isinstance(op, ast.Is) else (left is not right)
                else:
                    passed = comparisons[type(op)](left, right)
                if not passed:
                    return False
                left = right
            return True
        self.fail("Unsupported expression", "PTC_SYNTAX")

    def validate_call(self, name: Any, args: Any) -> None:
        if type(name) is not str or name not in self.allowed or name == "run_code":
            self.fail("Tool is not in allowed definitions", "PTC_TOOL_DENIED")
        if type(args) is not dict:
            self.fail("Tool arguments must be a JSON object", "PTC_VALUE")

    def charge_calls(self, count: int) -> None:
        self.tool_calls += count
        if self.tool_calls > self.limits.max_tool_calls:
            self.fail("Tool call limit exceeded")

    async def invoke(self, name: str, args: dict) -> Any:
        try:
            result = await self.dispatch(name, args)
        except AgentToolError as exc:
            code = exc.code if type(exc.code) is str else "TOOL_FAILED"
            raise ToolCallError(code[:128], name, str(exc)[:1024]) from exc
        except Exception as exc:
            raise ToolCallError("TOOL_FAILED", name, "Tool dispatch failed") from exc
        await self.tick()
        return self.json_value(result)

    async def parallel(self, descriptors: Any) -> list:
        if type(descriptors) is not list:
            self.fail("parallel requires a list", "PTC_VALUE")
        if len(descriptors) > self.limits.max_batch_calls:
            self.fail("Batch size limit exceeded")
        for descriptor in descriptors:
            if type(descriptor) is not dict or set(descriptor) != {"tool", "args"}:
                self.fail("Each descriptor requires exactly tool and args", "PTC_VALUE")
            self.validate_call(descriptor["tool"], descriptor["args"])
        # Charge/validate the entire batch before starting any side effect.
        self.charge_calls(len(descriptors))
        if not all(descriptor["tool"] in self.safe for descriptor in descriptors):
            results = []
            for descriptor in descriptors:
                results.append(await self.invoke(descriptor["tool"], descriptor["args"]))
                self.json_value(results)
            return results
        tasks = [asyncio.create_task(self.invoke(item["tool"], item["args"])) for item in descriptors]
        try:
            return self.json_value(await asyncio.gather(*tasks))
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            # Drain cancellation/failures before exposing results or leaving run.
            # Shield the drain against repeated caller cancellation, retaining the
            # original exception. A non-cooperative host dispatch cannot be killed.
            drain = asyncio.gather(*tasks, return_exceptions=True)
            cancelled = False
            while not drain.done():
                try:
                    await asyncio.shield(drain)
                except asyncio.CancelledError:
                    cancelled = True
            drain.result()
            if cancelled:
                raise asyncio.CancelledError

    def numeric(self, value: Any) -> None:
        if type(value) not in (int, float):
            self.fail("Expected a number (not bool)", "PTC_RUNTIME")

    def binary(self, op: ast.operator, left: Any, right: Any) -> Any:
        if isinstance(op, ast.Add) and type(left) is type(right) and type(left) in (str, list):
            limit = self.limits.max_string_chars if type(left) is str else self.limits.max_collection_items
            if len(left) + len(right) > limit:
                self.fail("Concatenation limit exceeded")
            return self.json_value(left + right)
        if isinstance(op, ast.Mult):
            if type(left) is int and type(right) in (str, list):
                left, right = right, left
            if type(left) in (str, list) and type(right) is int:
                limit = self.limits.max_string_chars if type(left) is str else self.limits.max_collection_items
                if len(left) * max(0, right) > limit or right.bit_length() > self.limits.max_integer_bits:
                    self.fail("Repetition limit exceeded")
                # Handle empty sequences before Python's Py_ssize_t conversion.
                return self.json_value(left * right if left and right > 0 else left[:0])
        self.numeric(left)
        self.numeric(right)
        operations = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
                      ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod}
        return self.json_value(operations[type(op)](left, right))

    def builtin(self, name: str, args: list[Any]) -> Any:
        args = self.json_value(args)
        if name == "print":
            self.log(args)
            return None
        if name == "range":
            if not 1 <= len(args) <= 3 or any(type(arg) is not int for arg in args):
                self.fail("range takes 1-3 integers", "PTC_RUNTIME")
            values = range(*args)
            try:
                size = len(values)
            except OverflowError:
                self.fail("Range limit exceeded")
            if size > self.limits.max_collection_items:
                self.fail("Range limit exceeded")
            return self.json_value(list(values))
        if len(args) != 1:
            self.fail(f"{name} takes exactly one argument", "PTC_RUNTIME")
        value = args[0]
        if name == "len":
            if type(value) not in (str, list, dict):
                self.fail("len requires string/list/dict", "PTC_RUNTIME")
            return len(value)
        if name == "abs":
            self.numeric(value)
            return self.json_value(abs(value))
        if type(value) is not list:
            self.fail(f"{name} requires a numeric list", "PTC_RUNTIME")
        for item in value:
            self.numeric(item)
        if name == "sum":
            total = 0
            for item in value:
                total = self.binary(ast.Add(), total, item)
            return total
        return self.json_value((min if name == "min" else max)(value))

    def log(self, args: list[Any]) -> None:
        if len(self.logs) >= self.limits.max_log_entries:
            self.logs_truncated = True
            return
        line = " ".join(value if type(value) is str else json.dumps(value, ensure_ascii=True) for value in args)
        # Count serialized JSON string bytes, not just raw bytes: escaping is bounded.
        remaining = self.limits.max_log_bytes - self.log_bytes
        encoded = json.dumps(line, ensure_ascii=True)
        if len(encoded) > remaining:
            self.logs_truncated = True
            low, high = 0, min(len(line), remaining)
            while low < high:
                mid = (low + high + 1) // 2
                if len(json.dumps(line[:mid], ensure_ascii=True)) <= remaining:
                    low = mid
                else:
                    high = mid - 1
            line = line[:low]
            encoded = json.dumps(line, ensure_ascii=True)
            if len(encoded) > remaining:
                return
        self.logs.append(line)
        self.log_bytes += len(encoded)
