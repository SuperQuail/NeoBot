"""ReplyToolExecutor 测试：工具参数校验、wait 冷却、长回复发送、会话工具排队。"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from neobot_app.reply.tools import ReplyToolExecutor


class _FakeSkillManager:
    """可挂起的假 skill 管理器，用于会话工具排队逻辑。"""

    def __init__(self) -> None:
        self.executions: list[tuple[str, dict]] = []

    def get_tools(self) -> list:
        return []

    def is_session_tool(self, name: str) -> bool:
        return True

    async def execute(self, name: str, args: dict) -> str:
        self.executions.append((name, args))
        await asyncio.sleep(0.5)
        return json.dumps({"ok": True})


def _make_executor(**overrides) -> ReplyToolExecutor:
    return ReplyToolExecutor(**overrides)


# ── send_reply 参数校验 ──────────────────────────────────────────


async def test_send_reply_rejects_non_list_images():
    """images 不是列表时必须返回错误信息且不调用 handler。"""
    called: list = []

    async def handler(**kwargs):
        called.append(kwargs)

    executor = _make_executor(send_reply_handler=handler)
    result = await executor.execute("send_reply", {"text": "你好", "images": 42})
    assert "images 必须为列表" in result
    assert called == []


async def test_send_reply_rejects_bad_reply_to_and_mention():
    """reply_to 非整数、mention 非整数列表时必须返回对应错误信息。"""

    async def handler(**kwargs):
        pass

    executor = _make_executor(send_reply_handler=handler)

    bad_reply_to = await executor.execute(
        "send_reply", {"text": "你好", "reply_to": "abc"}
    )
    bad_mention = await executor.execute(
        "send_reply", {"text": "你好", "mention": ["x"]}
    )

    assert "reply_to 必须为整数" in bad_reply_to
    assert "mention 必须为整数列表" in bad_mention


async def test_send_reply_calls_handler_with_normalized_args():
    """合法参数必须归一化后传给 handler（mention 转 int 列表），并返回发送条数摘要。"""
    captured: dict = {}

    async def handler(**kwargs):
        captured.update(kwargs)

    executor = _make_executor(send_reply_handler=handler)
    result = await executor.execute(
        "send_reply",
        {"text": "你好，今天天气不错", "reply_to": "7", "mention": ["10001", 10002]},
    )

    assert captured["text"] == "你好，今天天气不错"
    assert captured["reply_to"] == 7
    assert captured["mention"] == [10001, 10002]
    assert "已发送" in result


async def test_send_reply_missing_handler_returns_error():
    """未配置 send_reply 处理器时必须返回错误信息而非抛异常。"""
    executor = _make_executor()
    result = await executor.execute("send_reply", {"text": "你好"})
    assert "处理器未配置" in result


# ── wait 冷却与参数校验 ──────────────────────────────────────────


async def test_wait_respects_cooldown():
    """冷却期内再次调用 wait 必须返回冷却提示且不再调用 handler。"""
    calls: list[int] = []

    async def handler(seconds: int = 20) -> str:
        calls.append(seconds)
        return "ok"

    executor = _make_executor(wait_handler=handler, wait_cooldown_seconds=60)
    await executor.execute("wait", {"seconds": 3})
    executor._last_wait_time = __import__("time").monotonic()
    second = await executor.execute("wait", {})

    assert calls == [3]
    assert "冷却" in second


async def test_wait_validates_seconds_and_defaults_to_20():
    """seconds 非整数返回错误；缺省时 handler 收到默认 20 秒。"""
    calls: list[int] = []

    async def handler(seconds: int = 20) -> str:
        calls.append(seconds)
        return "ok"

    executor = _make_executor(wait_handler=handler)
    bad = await executor.execute("wait", {"seconds": "abc"})
    ok = await executor.execute("wait", {})

    assert "seconds 必须为整数" in bad
    assert calls == [20]
    assert ok == "ok"


@pytest.mark.parametrize("seconds", [True, False, -1, "-2", 1.5, "1.5"])
async def test_wait_rejects_invalid_seconds_before_cooldown(seconds):
    """Invalid values must not be hidden by cooldown or reach the handler."""
    calls: list[int] = []

    async def handler(seconds: int = 20) -> str:
        calls.append(seconds)
        return "ok"

    executor = _make_executor(wait_handler=handler, wait_cooldown_seconds=60)
    executor._last_wait_time = __import__("time").monotonic()
    result = await executor.execute("wait", {"seconds": seconds})

    assert result.startswith("错误：seconds")
    assert "冷却" not in result
    assert calls == []


# ── send_long_reply ──────────────────────────────────────────────


async def test_send_long_reply_requires_markdown_or_image_path():
    """markdown 与 image_path 都为空时必须返回错误，且不调用发送 handler。"""
    sent: list = []

    async def handler(**kwargs):
        sent.append(kwargs)

    executor = _make_executor(
        markdown_image_converter=object(),
        send_long_reply_handler=handler,
    )
    result = json.loads(await executor.execute("send_long_reply", {}))

    assert result["ok"] is False
    assert "至少需要提供一个" in result["error"]
    assert sent == []


async def test_send_long_reply_converter_failure_returns_error():
    """converter.convert 抛异常时返回降级错误信息且不发送。"""

    class _BoomConverter:
        async def convert(self, markdown_text: str) -> str:
            raise RuntimeError("render boom")

    executor = _make_executor(markdown_image_converter=_BoomConverter())
    result = json.loads(
        await executor.execute("send_long_reply", {"markdown": "# 标题"})
    )

    assert result["ok"] is False
    assert result["error"] == "Markdown 转图片失败"
    assert "render boom" not in result["error"]


async def test_send_long_reply_pre_rendered_image_skips_converter():
    """提供 image_path 时直接发送预渲染图片，converter 不得被调用。"""

    class _CounterConverter:
        def __init__(self) -> None:
            self.calls = 0

        async def convert(self, markdown_text: str) -> str:
            self.calls += 1
            return "rendered.png"

    converter = _CounterConverter()
    sent: list[dict] = []

    async def handler(**kwargs):
        sent.append(kwargs)

    executor = _make_executor(
        markdown_image_converter=converter,
        send_long_reply_handler=handler,
    )
    result = json.loads(
        await executor.execute(
            "send_long_reply",
            {"image_path": "pre/rendered.png", "markdown": "# 备注", "caption": "说明"},
        )
    )

    assert result["ok"] is True
    assert result["image_path"] == "pre/rendered.png"
    assert converter.calls == 0
    assert sent[0]["image_path"] == "pre/rendered.png"
    assert sent[0]["caption"] == "说明"


# ── 静态辅助 ─────────────────────────────────────────────────────


def test_normalize_segments_cleans_and_returns_none_for_empty():
    """_normalize_segments：非列表返回 None，空/空白条目被清洗后为空时返回 None。"""
    assert ReplyToolExecutor._normalize_segments(None) is None
    assert ReplyToolExecutor._normalize_segments("not-a-list") is None
    assert ReplyToolExecutor._normalize_segments(["  ", ""]) is None
    assert ReplyToolExecutor._normalize_segments([" 第一句 ", "第二句"]) == [
        "第一句",
        "第二句",
    ]


def test_normalize_segments_drops_none_items():
    """_normalize_segments 遇到 None 条目必须丢弃，不得转为字符串 'None'。"""
    assert ReplyToolExecutor._normalize_segments(["有效", None]) == ["有效"]


def test_definitions_include_tools_conditionally():
    """definitions() 按配置注入工具：未配置 wait/converter 时不得出现对应工具定义。"""
    bare = _make_executor()
    names = [d["function"]["name"] for d in bare.definitions()]
    assert "wait" not in names
    assert "send_long_reply" not in names

    full = _make_executor(wait_handler=lambda s: "", markdown_image_converter=object())
    full_names = [d["function"]["name"] for d in full.definitions()]
    assert "wait" in full_names
    assert "send_long_reply" in full_names


def test_search_custom_emoji_requires_emoji_service():
    handler_only = _make_executor(send_emoji_handler=lambda **kwargs: None)
    handler_names = {d["function"]["name"] for d in handler_only.definitions()}
    assert "send_emoji" in handler_names
    assert "search_custom_emoji" not in handler_names

    service_names = {
        d["function"]["name"]
        for d in _make_executor(emoji_service=object()).definitions()
    }
    assert "search_custom_emoji" in service_names


# ── Markdown 技能读取 ─────────────────────────────────────────────


class _FakeSkillRegistry:
    def __init__(self, skills: dict) -> None:
        self.skills = skills


class _FakeSkill:
    def __init__(self, content: str, skill_md_path: Path) -> None:
        self.content = content
        self.path = skill_md_path


def _make_skill_tools(tmp_path: Path) -> ReplyToolExecutor:
    skill_dir = tmp_path / "skills" / "weather"
    skill_dir.mkdir(parents=True)
    refs_dir = skill_dir / "references"
    refs_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("天气说明", encoding="utf-8")
    (refs_dir / "cities.md").write_text("城市列表", encoding="utf-8")
    skill = _FakeSkill("天气说明", skill_dir / "SKILL.md")
    registry = _FakeSkillRegistry({"weather:forecast": skill})
    return _make_executor(skills_registry=registry)


async def test_skills_tools_exposed_only_with_registry(tmp_path: Path):
    """未提供 skills_registry 时不暴露 skills__* 工具。"""
    names = [d["function"]["name"] for d in _make_executor().definitions()]
    assert "skills__read_manifest" not in names

    executor = _make_skill_tools(tmp_path)
    names = [d["function"]["name"] for d in executor.definitions()]
    assert "skills__read_manifest" in names
    assert "skills__read_resource" in names


async def test_read_skill_manifest(tmp_path: Path):
    executor = _make_skill_tools(tmp_path)
    result = await executor.execute(
        "skills__read_manifest", {"skill_id": "weather:forecast"}
    )
    assert result == "天气说明"


async def test_read_skill_manifest_unknown_skill(tmp_path: Path):
    executor = _make_skill_tools(tmp_path)
    result = await executor.execute(
        "skills__read_manifest", {"skill_id": "nope:missing"}
    )
    assert "不存在" in result


async def test_read_skill_resource(tmp_path: Path):
    executor = _make_skill_tools(tmp_path)
    result = await executor.execute(
        "skills__read_resource",
        {"skill_id": "weather:forecast", "path": "references/cities.md"},
    )
    assert result == "城市列表"


async def test_read_skill_resource_rejects_hard_links(tmp_path: Path):
    executor = _make_skill_tools(tmp_path)
    outside = tmp_path / "outside-secret.md"
    outside.write_text("outside secret", encoding="utf-8")
    hard_link = tmp_path / "skills" / "weather" / "references" / "linked.md"
    try:
        os.link(outside, hard_link)
    except OSError as exc:
        pytest.skip(f"hard links unavailable: {exc}")
    if hard_link.stat().st_nlink <= 1:
        pytest.skip("filesystem does not expose meaningful hard-link counts")

    result = await executor.execute(
        "skills__read_resource",
        {"skill_id": "weather:forecast", "path": "references/linked.md"},
    )

    assert "硬链接" in result
    assert "outside secret" not in result


async def test_read_skill_resource_uses_bounded_read(tmp_path: Path):
    executor = _make_skill_tools(tmp_path)
    oversized = tmp_path / "skills" / "weather" / "references" / "large.md"
    oversized.write_bytes(b"x" * (1024 * 1024 + 1))

    result = await executor.execute(
        "skills__read_resource",
        {"skill_id": "weather:forecast", "path": "references/large.md"},
    )

    assert "超过 1MB" in result


async def test_read_skill_resource_rejects_open_handle_race(
    tmp_path: Path, monkeypatch
):
    """An open redirected outside the skill root must not leak that handle's data."""
    executor = _make_skill_tools(tmp_path)
    target = tmp_path / "skills" / "weather" / "references" / "cities.md"
    outside = tmp_path / "race-secret.md"
    outside.write_text("race secret", encoding="utf-8")
    original_open = Path.open
    target_open_count = 0

    def raced_open(path: Path, *args, **kwargs):
        nonlocal target_open_count
        if path == target:
            target_open_count += 1
            return original_open(outside, *args, **kwargs)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", raced_open)
    result = await executor.execute(
        "skills__read_resource",
        {"skill_id": "weather:forecast", "path": "references/cities.md"},
    )

    assert target_open_count == 1
    assert result.startswith("Error:")
    assert "race secret" not in result


async def test_read_skill_resource_blocks_escape(tmp_path: Path):
    executor = _make_skill_tools(tmp_path)
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")

    traversal = await executor.execute(
        "skills__read_resource",
        {"skill_id": "weather:forecast", "path": "../../../secret.txt"},
    )
    assert "非法路径" in traversal or "越界" in traversal or "Error" in traversal

    absolute = await executor.execute(
        "skills__read_resource",
        {"skill_id": "weather:forecast", "path": str(outside)},
    )
    assert "非法路径" in absolute or "越界" in absolute

    missing = await executor.execute(
        "skills__read_resource",
        {"skill_id": "weather:forecast", "path": "not-there.md"},
    )
    assert "不存在" in missing


async def test_read_skill_resource_blocks_windows_drive_and_unc(tmp_path: Path):
    """Windows 盘符（C:/x、C:\\x、C:x）与 UNC（\\\\server\\share）路径必须被拒绝。"""
    executor = _make_skill_tools(tmp_path)

    for evil in (
        "C:/secret.txt",
        "C:\\secret.txt",
        "C:secret.txt",
        "\\\\server\\share\\secret.txt",
    ):
        result = await executor.execute(
            "skills__read_resource",
            {"skill_id": "weather:forecast", "path": evil},
        )
        assert "非法路径" in result, f"path={evil!r} 未被拒绝: {result}"

    # 带盘符的越界路径也不能通过
    traversal = await executor.execute(
        "skills__read_resource",
        {"skill_id": "weather:forecast", "path": "C:\\..\\..\\secret.txt"},
    )
    assert "非法路径" in traversal or "越界" in traversal


async def test_read_skill_resource_after_unload(tmp_path: Path):
    executor = _make_skill_tools(tmp_path)
    executor._skills_registry = _FakeSkillRegistry({})
    result = await executor.execute(
        "skills__read_manifest", {"skill_id": "weather:forecast"}
    )
    assert "已卸载" in result


def _try_make_junction(link: Path, target: Path) -> bool:
    """尝试创建真实 junction（Windows mklink /J），失败（无权限/非 Windows）返回 False。"""
    if sys.platform != "win32":
        return False
    try:
        proc = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return proc.returncode == 0
    except Exception:
        return False


async def test_read_skill_resource_rejects_symlink_or_junction_components(
    tmp_path: Path,
):
    """路径组件为 symlink/junction 时必须被拒绝（TOCTOU 缓解）。

    优先用真实 junction 验证（Windows）；其他平台使用目录 symlink。
    """
    executor = _make_skill_tools(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "evil.md").write_text("evil", encoding="utf-8")

    link = tmp_path / "skills" / "weather" / "refs"
    if not _try_make_junction(link, outside):
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            pytest.skip(f"symlinks and junctions unavailable: {exc}")

    result = await executor.execute(
        "skills__read_resource",
        {"skill_id": "weather:forecast", "path": "refs/evil.md"},
    )
    assert "Error" in result, f"junction/symlink path was not rejected: {result}"
    assert result != "evil"


# ── 会话工具排队（后台执行）──────────────────────────────────────


async def test_session_tool_queues_and_rejects_third_submission():
    """同一管线会话工具：第 1 次后台执行、第 2 次排队、第 3 次队列满被拒绝。"""
    skill = _FakeSkillManager()
    executor = _make_executor(
        skill_manager=skill,
        conv_kind="group",
        conv_id="123456",
    )
    try:
        first = json.loads(await executor.execute("download__url", {"url": "http://a"}))
        second = json.loads(
            await executor.execute("download__url", {"url": "http://b"})
        )
        third = json.loads(await executor.execute("download__url", {"url": "http://c"}))

        assert first["status"] == "session_submitted"
        assert second["status"] == "queued"
        assert third["status"] == "queue_full"
        assert third["ok"] is False
    finally:
        await executor.close()


async def test_cancel_task_cancels_queued_session_tool():
    """cancel_task(session_tool) 必须同时清掉排队任务并取消运行中的任务。"""
    skill = _FakeSkillManager()
    executor = _make_executor(
        skill_manager=skill,
        conv_kind="group",
        conv_id="123456",
    )
    try:
        await executor.execute("download__url", {"url": "http://a"})
        await executor.execute("download__url", {"url": "http://b"})

        result = json.loads(
            await executor.execute("cancel_task", {"task_type": "session_tool"})
        )

        assert result["ok"] is True
        assert len(result["cancelled"]) == 2
        assert not executor._session_task_queue
        await asyncio.sleep(0.1)  # 等待取消回调从运行信息中清理任务
        assert not executor._session_task_info
    finally:
        await executor.close()


# ── allowed-tools 白名单 ────────────────────────────────────────


class _FakeSkillManagerPlain:
    """普通（非会话）假 skill 管理器，用于验证 allowed-tools 对 skill 工具生效。"""

    def __init__(self, tools: list[dict]) -> None:
        self._tools = tools
        self.executed: list[str] = []
        self.executed_args: list[dict] = []

    def get_tools(self) -> list:
        return self._tools

    def is_session_tool(self, name: str) -> bool:
        return False

    async def execute(self, name: str, args: dict) -> str:
        self.executed.append(name)
        self.executed_args.append(dict(args))
        return f"executed:{name}"


def _skill_def(name: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": name,
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }


def test_allowed_tools_filters_definitions_and_keeps_base():
    """allowed_tools 生效时 definitions 只保留基础白名单 + allowed_tools 内的工具。"""
    executor = _make_executor(
        cancel_handler=lambda reason=None: None,
        send_reply_handler=lambda **kw: None,
        wait_handler=lambda s=20: "",
        send_emoji_handler=lambda number=0, text="": None,
        emoji_service=object(),
        markdown_image_converter=object(),
        tts_service=type("TTS", (), {"enabled": True})(),
        poke_user_handler=lambda user_id=0: "ok",
        drawing_manager=object(),
        scheduled_task_manager=object(),
        skill_manager=_FakeSkillManagerPlain(
            [_skill_def("demo__ping"), _skill_def("demo__hack")]
        ),
        allowed_tools={"send_emoji", "demo__ping"},
    )
    names = {d["function"]["name"] for d in executor.definitions()}

    for base in (
        "cancel",
        "split_reply",
        "send_reply",
        "wait",
        "send_long_reply",
        "speak",
        "check_background_tasks",
        "cancel_task",
        "check_last_drawing",
        "mark_scheduled_task_complete",
    ):
        assert base in names, f"基础工具 {base} 必须始终可用"
    assert "send_emoji" in names  # 在 allowed_tools 内
    assert "demo__ping" in names  # 在 allowed_tools 内
    assert "poke_user" not in names  # 白名单外
    assert "search_custom_emoji" not in names
    assert "demo__hack" not in names


def test_allowed_tools_none_keeps_all_definitions():
    """allowed_tools=None 时不限制 definitions。"""
    executor = _make_executor(
        send_emoji_handler=lambda number=0, text="": None,
        emoji_service=object(),
        poke_user_handler=lambda user_id=0: "ok",
    )
    names = {d["function"]["name"] for d in executor.definitions()}
    assert "poke_user" in names
    assert "search_custom_emoji" in names


def test_allowed_tools_keeps_skill_read_infrastructure_definitions(tmp_path: Path):
    """allowed-tools 限制时 definitions 保留技能读取基础设施
    （skills__read_manifest / skills__read_resource / agents__list /
    agents__delegate），普通工具仍被过滤。"""
    executor = _make_skill_tools(tmp_path)
    executor._skill_manager = _FakeSkillManagerPlain(
        [
            _skill_def("agents__list"),
            _skill_def("agents__delegate"),
            _skill_def("demo__ping"),
        ]
    )
    executor._allowed_tools = {"send_emoji"}
    names = {d["function"]["name"] for d in executor.definitions()}

    assert "skills__read_manifest" in names
    assert "skills__read_resource" in names
    assert "agents__list" in names
    assert "agents__delegate" in names  # 子代理委托是插件能力核心通道，不被技能限制掉
    assert "demo__ping" not in names
    assert "poke_user" not in names


async def test_execute_blocks_tool_not_in_allowed_tools():
    """allowed_tools 生效时，白名单外的工具调用被拦截并返回友好错误。"""
    executor = _make_executor(
        poke_user_handler=lambda user_id=0: "ok",
        allowed_tools={"send_reply"},
    )
    result = await executor.execute("poke_user", {"user_id": 1})
    assert result == "Error: 工具 poke_user 不在当前技能允许的工具列表内"


async def test_execute_base_tool_always_available_under_allowed_tools():
    """即使允许列表很小，基础回复工具仍可正常执行。"""
    calls: list[str] = []

    async def handler(**kwargs):
        calls.append("called")

    executor = _make_executor(send_reply_handler=handler, allowed_tools={"send_emoji"})
    result = await executor.execute("send_reply", {"text": "你好"})
    assert calls == ["called"]
    assert "已发送" in result


async def test_execute_allowed_skill_tool_still_runs():
    """allowed_tools 内的 skill 工具正常执行，不被拦截。"""
    skill = _FakeSkillManagerPlain([_skill_def("demo__ping")])
    executor = _make_executor(skill_manager=skill, allowed_tools={"demo__ping"})
    result = await executor.execute("demo__ping", {"x": 1})
    assert result == "executed:demo__ping"
    assert skill.executed == ["demo__ping"]


async def test_execute_skills_read_tools_always_available_under_allowed_tools(
    tmp_path: Path,
):
    """allowed-tools 限制时，技能读取基础设施（skills__read_manifest / skills__read_resource）
    仍可执行，不能被技能声明限制掉（拦截须先于该路由，但基础白名单包含它们）。"""
    executor = _make_skill_tools(tmp_path)
    executor._allowed_tools = {"send_emoji"}
    manifest = await executor.execute(
        "skills__read_manifest", {"skill_id": "weather:forecast"}
    )
    resource = await executor.execute(
        "skills__read_resource",
        {"skill_id": "weather:forecast", "path": "references/cities.md"},
    )
    assert manifest == "天气说明"
    assert resource == "城市列表"


async def test_execute_agents_list_always_available_under_allowed_tools():
    """allowed-tools 限制时 agents__list 仍可执行（只读基础设施，不能被技能限制掉）。"""
    skill = _FakeSkillManagerPlain(
        [_skill_def("agents__list"), _skill_def("agents__delegate")]
    )
    executor = _make_executor(skill_manager=skill, allowed_tools={"send_emoji"})
    result = await executor.execute("agents__list", {"agent": "x"})
    assert result == "executed:agents__list"
    assert skill.executed == ["agents__list"]


async def test_execute_agents_delegate_always_available_under_allowed_tools():
    """allowed-tools 限制时 agents__delegate 仍可执行（子代理委托受
    AgentRegistry 注册表 + 超时/排空管理约束，是插件能力的核心通道，不能被技能限制掉）。"""
    skill = _FakeSkillManagerPlain(
        [_skill_def("agents__list"), _skill_def("agents__delegate")]
    )
    executor = _make_executor(skill_manager=skill, allowed_tools={"send_emoji"})
    result = await executor.execute("agents__delegate", {"task": "x"})
    assert result == "executed:agents__delegate"
    assert skill.executed == ["agents__delegate"]


async def test_execute_allowed_skills_read_tool_still_runs(tmp_path: Path):
    """allowed_tools 内的 skills__read_* 工具正常读取。"""
    executor = _make_skill_tools(tmp_path)
    executor._allowed_tools = {"skills__read_manifest"}
    result = await executor.execute(
        "skills__read_manifest", {"skill_id": "weather:forecast"}
    )
    assert result == "天气说明"


# ── allowed-tools 下后台任务工具可用性 ────────────────────────────


class _FakeDrawingManager:
    """假绘图管理器：支持状态查询、绘图记录查询与冷却取消。"""

    def get_pipeline_status(self, pipeline_key: str) -> dict:
        return {"has_active_task": False}

    def get_last_draw_info(self, pipeline_key: str) -> dict:
        return {"found": False}

    def cancel_cooldown(self, pipeline_key: str) -> None:
        pass


class _FakeScheduledTaskManager:
    """假定时任务管理器：支持状态查询与标记完成。"""

    def get_pipeline_status(self, pipeline_key: str) -> dict:
        return {}

    async def mark_completed(self, task_id: str) -> dict:
        return {"ok": True, "task_id": task_id}


def test_allowed_tools_keeps_background_task_tool_definitions():
    """allowed-tools 限制激活时，后台任务工具（查询/取消/绘图记录/定时任务）
    属会话基础设施，definitions 必须保留（不依赖技能声明）。"""
    executor = _make_executor(
        drawing_manager=_FakeDrawingManager(),
        scheduled_task_manager=_FakeScheduledTaskManager(),
        allowed_tools={"send_reply"},
    )
    names = {d["function"]["name"] for d in executor.definitions()}
    for name in (
        "check_background_tasks",
        "cancel_task",
        "check_last_drawing",
        "mark_scheduled_task_complete",
    ):
        assert name in names, f"后台任务工具 {name} 必须始终可用"


async def test_allowed_tools_does_not_block_background_task_tools():
    """allowed-tools 限制激活时，后台任务工具 execute 不被拦截，正常执行。"""
    executor = _make_executor(
        drawing_manager=_FakeDrawingManager(),
        scheduled_task_manager=_FakeScheduledTaskManager(),
        conv_kind="group",
        conv_id="123456",
        allowed_tools={"send_reply"},
    )

    tasks = json.loads(await executor.execute("check_background_tasks", {}))
    assert tasks["ok"] is True

    cancelled = json.loads(
        await executor.execute("cancel_task", {"task_type": "drawing_cooldown"})
    )
    assert cancelled["ok"] is True

    last_drawing = json.loads(await executor.execute("check_last_drawing", {}))
    assert last_drawing["ok"] is True
    assert last_drawing["found"] is False

    completed = json.loads(
        await executor.execute("mark_scheduled_task_complete", {"task_id": "uuid-1"})
    )
    assert completed["ok"] is True
    assert completed["task_id"] == "uuid-1"


def test_definitions_reject_duplicate_final_tool_names(tmp_path: Path):
    executor = _make_skill_tools(tmp_path)
    executor._skill_manager = _FakeSkillManagerPlain(
        [_skill_def("skills__read_manifest")]
    )

    try:
        executor.definitions()
    except ValueError as exc:
        assert "重复的最终工具定义: skills__read_manifest" in str(exc)
    else:
        raise AssertionError("duplicate final tool definition was accepted")


def test_skill_manager_rejects_reserved_and_duplicate_final_names():
    from neobot_app.skills.base import SkillManager

    class _Module:
        description = "test"
        instructions = ""
        session_tools: set[str] = set()

        def __init__(self, name: str, tools: list[dict]) -> None:
            self.name = name
            self._tools = tools

        def get_tools(self) -> list[dict]:
            return self._tools

        async def execute(self, tool_name: str, args: dict) -> str:
            return "ok"

        def reset(self) -> None:
            return None

    manager = SkillManager()
    for module, expected in (
        (_Module("skills", [_skill_def("read_resource")]), "保留的最终工具名"),
        (
            _Module("dup", [_skill_def("same"), _skill_def("same")]),
            "重复的最终工具定义",
        ),
    ):
        try:
            manager.register(module)
        except ValueError as exc:
            assert expected in str(exc)
        else:
            raise AssertionError("invalid final tool name was accepted")


class _SnapshotSkill:
    description = "snapshot"
    instructions = ""

    def __init__(self, name: str, value: str, *, session: bool = False) -> None:
        self.name = name
        self.value = value
        self.session_tools = {"run"} if session else set()
        self.calls: list[str] = []

    def get_tools(self) -> list[dict]:
        return [_skill_def("run")]

    async def execute(self, tool_name: str, args: dict) -> str:
        self.calls.append(tool_name)
        return self.value

    def reset(self) -> None:
        pass


async def test_current_definition_execution_token_runs_normally():
    from neobot_app.skills.base import SkillManager

    manager = SkillManager()
    skill = _SnapshotSkill("snap", "current")
    manager.register(skill)
    token = manager.capture_execution_token("snap__run")

    assert token is not None
    assert await manager.execute("snap__run", {}, token=token) == "current"
    assert skill.calls == ["run"]


async def test_executor_reports_unknown_declared_skill_suffix_as_unknown_tool():
    from neobot_app.skills.base import SkillManager

    manager = SkillManager()
    manager.register(_SnapshotSkill("snap", "current"))
    executor = _make_executor(skill_manager=manager)

    result = await executor.execute("snap__missing", {})

    assert result == "未知工具: snap__missing"
    assert "未找到 Skill" not in result


async def test_definition_execution_token_rejects_unregister():
    from neobot_app.skills.base import SkillManager

    manager = SkillManager()
    old = _SnapshotSkill("snap", "old")
    manager.register(old)
    executor = _make_executor(skill_manager=manager)
    executor.definitions()
    manager.unregister("snap")

    result = await executor.execute("snap__run", {})
    assert result == "工具不可用或已更新 [snap__run]"
    assert old.calls == []


async def test_definition_execution_token_rejects_replacement():
    from neobot_app.skills.base import SkillManager

    manager = SkillManager()
    old = _SnapshotSkill("snap", "old")
    manager.register(old)
    executor = _make_executor(skill_manager=manager)
    executor.definitions()
    manager.unregister("snap")
    new = _SnapshotSkill("snap", "new")
    manager.register(new)

    result = await executor.execute("snap__run", {})
    assert result == "工具不可用或已更新 [snap__run]"
    assert old.calls == []
    assert new.calls == []


async def _run_queued_stale_token_scenario(
    *, replace: bool
) -> tuple[list[str], list[str], list[dict]]:
    from neobot_app.skills.base import SkillManager

    class _QueuedSkill(_SnapshotSkill):
        def __init__(self, name: str, value: str) -> None:
            super().__init__(name, value, session=True)
            self.release = asyncio.Event()

        async def execute(self, tool_name: str, args: dict) -> str:
            self.calls.append(tool_name)
            if len(self.calls) == 1:
                await self.release.wait()
            return self.value

    manager = SkillManager()
    old = _QueuedSkill("queuegen", "old")
    manager.register(old)
    executor = _make_executor(
        skill_manager=manager,
        conv_kind="group",
        conv_id="generation",
    )
    executor.definitions()
    try:
        await executor.execute("queuegen__run", {"id": 1})
        for _ in range(100):
            if old.calls:
                break
            await asyncio.sleep(0.01)
        assert old.calls == ["run"]
        await executor.execute("queuegen__run", {"id": 2})
        manager.unregister("queuegen")
        new = _SnapshotSkill("queuegen", "new", session=True)
        if replace:
            manager.register(new)
        old.release.set()
        for _ in range(100):
            history = executor._session_completed.get("group:generation", [])
            if len(history) == 2:
                break
            await asyncio.sleep(0.01)
        return old.calls, new.calls, executor._session_completed["group:generation"]
    finally:
        await executor.close()


async def test_queued_session_tool_rejects_token_after_unregister():
    old_calls, new_calls, history = await _run_queued_stale_token_scenario(
        replace=False
    )
    assert old_calls == ["run"]
    assert new_calls == []
    assert history[-1]["status"] == "failed"
    assert "不可用或已更新" in history[-1]["summary"]


async def test_queued_session_tool_rejects_token_after_replacement():
    old_calls, new_calls, history = await _run_queued_stale_token_scenario(replace=True)
    assert old_calls == ["run"]
    assert new_calls == []
    assert history[-1]["status"] == "failed"
    assert "不可用或已更新" in history[-1]["summary"]


def test_skill_registration_is_atomic_and_session_tools_must_be_declared():
    from neobot_app.skills.base import SkillManager

    manager = SkillManager()
    skill = _SnapshotSkill("atomic", "x")
    skill.session_tools = {"missing"}
    try:
        manager.register(skill)
    except ValueError as exc:
        assert "undeclared" in str(exc)
    else:
        raise AssertionError("undeclared session tool was accepted")
    assert manager.skill_names == []


async def test_skill_rejects_empty_suffix_and_reports_execute_failure():
    from neobot_app.skills.base import SkillManager

    class _Fail(_SnapshotSkill):
        async def execute(self, tool_name: str, args: dict) -> str:
            raise RuntimeError("secret-token=abc123")

    manager = SkillManager()
    manager.register(_Fail("fail", "x"))
    assert "未知工具" in await manager.execute("fail__", {})
    result = await manager.execute("fail__run", {})
    # 失败原因必须保留（旧实现只回一句固定文案，故障不可诊断）……
    assert "工具执行失败 [fail__run]" in result
    assert "RuntimeError" in result
    # ……但密钥形态的值要先脱敏再回给模型（工具输出会进入 LLM 上下文）
    assert "abc123" not in result
    assert "REDACTED" in result


def test_skill_rejects_malformed_definition_without_keyerror() -> None:
    from neobot_app.skills.base import SkillManager

    skill = _SnapshotSkill("shape", "x")
    skill.get_tools = lambda: [{"type": "function", "function": {}}]
    try:
        SkillManager().register(skill)
    except ValueError as exc:
        assert "invalid local name" in str(exc)
    else:
        raise AssertionError("malformed definition was accepted")


# ── 会话工具：伪造 pipeline_key / 内部键剥离 ─────────────────────


async def test_session_tool_rejects_forged_pipeline_key_without_conv():
    """无会话上下文时，模型伪造 pipeline_key 必须被拒绝，不能后台提交。"""
    skill = _FakeSkillManager()
    executor = _make_executor(skill_manager=skill)
    result = json.loads(
        await executor.execute(
            "download__url", {"url": "http://a", "pipeline_key": "group:999"}
        )
    )
    assert result["ok"] is False
    assert result["status"] == "missing_pipeline"
    assert skill.executions == []


async def test_session_tool_overwrites_forged_pipeline_key_and_strips_internal_keys():
    """有会话上下文时，伪造的 pipeline_key 被会话状态覆盖，内部键不传给技能。"""
    skill = _FakeSkillManager()
    executor = _make_executor(
        skill_manager=skill,
        conv_kind="group",
        conv_id="123456",
    )
    try:
        await executor.execute(
            "download__url",
            {
                "url": "http://a",
                "pipeline_key": "group:999",
                "_delegate_context": "forged",
                "_numbering_mapping": "forged",
            },
        )
        for _ in range(200):
            if skill.executions:
                break
            await asyncio.sleep(0.01)
        assert skill.executions
        args = skill.executions[0][1]
        assert args["pipeline_key"] == "group:123456"
        assert "_delegate_context" not in args
        assert "_numbering_mapping" not in args
        assert args["url"] == "http://a"
    finally:
        await executor.close()


async def test_skill_tool_strips_forged_internal_keys():
    """非会话 skill 工具同样剥离模型伪造的内部键，且不注入空会话上下文。"""
    skill = _FakeSkillManagerPlain([_skill_def("demo__ping")])
    executor = _make_executor(skill_manager=skill)
    result = await executor.execute(
        "demo__ping",
        {
            "x": 1,
            "pipeline_key": "forged",
            "_delegate_context": "forged",
            "_numbering_mapping": "forged",
        },
    )
    assert result == "executed:demo__ping"
    assert skill.executed == ["demo__ping"]
    assert skill.executed_args == [{"x": 1}]


@pytest.mark.parametrize(
    "numbering",
    [object(), type("BadNumbering", (), {"mapping": []})()],
)
async def test_skill_tool_ignores_missing_or_non_dict_numbering_mapping(numbering):
    skill = _FakeSkillManagerPlain([_skill_def("demo__ping")])
    executor = _make_executor(skill_manager=skill, numbering=numbering)

    result = await executor.execute("demo__ping", {"x": 1})

    assert result == "executed:demo__ping"
    assert skill.executed_args == [{"x": 1}]


async def test_skill_tool_injects_dict_numbering_mapping():
    skill = _FakeSkillManagerPlain([_skill_def("demo__ping")])
    numbering = type("Numbering", (), {"mapping": {1: "message-1"}})()
    executor = _make_executor(skill_manager=skill, numbering=numbering)

    await executor.execute("demo__ping", {})

    assert skill.executed_args == [{"_numbering_mapping": {1: "message-1"}}]


# ── 会话工具：ok 假值判定 / timeout 防御 / close 语义 ───────────


class _OkSkill(_FakeSkillManager):
    def __init__(self, payload: dict) -> None:
        super().__init__()
        self._payload = payload

    async def execute(self, name: str, args: dict) -> str:
        self.executions.append((name, args))
        return json.dumps(self._payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"ok": "false"},
        {"ok": 0},
        {"ok": "no"},
        {"ok": "0"},
        {"ok": None},
        {"ok": "0.0"},
        {"ok": ""},
        {"ok": "none"},
        {"ok": "  NO  "},
    ],
)
async def test_session_tool_ok_falsey_values_mark_failed(payload: dict):
    skill = _OkSkill(payload)
    executor = _make_executor(
        skill_manager=skill,
        conv_kind="group",
        conv_id="123456",
    )
    await executor._run_session_tool(
        "download__url",
        {"url": "http://a"},
        "group:123456",
        "group",
        "123456",
    )
    history = executor._session_completed["group:123456"]
    assert history[-1]["status"] == "failed"


class _SessionResultSkill(_FakeSkillManager):
    def __init__(self, result) -> None:
        super().__init__()
        self._result = result

    async def execute(self, name: str, args: dict):
        self.executions.append((name, args))
        return self._result


async def _run_session_result(result) -> dict:
    executor = _make_executor(skill_manager=_SessionResultSkill(result))
    await executor._run_session_tool("demo__run", {}, "group:result", "group", "result")
    return executor._session_completed["group:result"][-1]


@pytest.mark.parametrize("result", [{}, []])
async def test_session_tool_empty_json_containers_are_successful(result):
    history = await _run_session_result(result)
    assert history["status"] == "completed"


@pytest.mark.parametrize(
    "result",
    [
        {"error": "boom"},
        {"errors": ["boom"]},
        {"ok": True, "error": None},
        "未知工具: demo__missing",
        "工具执行失败 [demo__run]",
        "错误：执行失败",
    ],
)
async def test_session_tool_explicit_error_results_are_failed(result):
    history = await _run_session_result(result)
    assert history["status"] == "failed"


async def test_session_tool_bad_timeout_uses_default_and_completes():
    """timeout_seconds 为畸形值时防御性回退默认值，后台任务不得崩溃。"""
    skill = _FakeSkillManager()
    executor = _make_executor(
        skill_manager=skill,
        conv_kind="group",
        conv_id="123456",
    )
    await executor._run_session_tool(
        "download__url",
        {"url": "http://a", "timeout_seconds": "abc"},
        "group:123456",
        "group",
        "123456",
    )
    history = executor._session_completed["group:123456"]
    assert history[-1]["status"] == "completed"


@pytest.mark.parametrize(
    "bad",
    [
        0,
        "0",
        "0.0",
        "",
        None,
        0.0,
        float("inf"),
        float("nan"),
        "inf",
        "nan",
        True,
        False,
        "abc",
    ],
)
def test_session_timeout_parse_defaults_on_falsy_or_malformed(bad):
    """0/空串/None/Infinity/NaN/布尔/畸形输入一律回退默认 300 秒。"""
    assert ReplyToolExecutor._parse_session_timeout(bad) == 300


def test_session_timeout_parse_clamps_to_range():
    for negative in (-5, -5.5, "-5", "-5.5"):
        assert ReplyToolExecutor._parse_session_timeout(negative) == 1
    assert ReplyToolExecutor._parse_session_timeout(99999) == 1800
    assert ReplyToolExecutor._parse_session_timeout("60") == 60
    assert ReplyToolExecutor._parse_session_timeout("120.5") == 120
    assert ReplyToolExecutor._parse_session_timeout(120.9) == 120
    assert ReplyToolExecutor._parse_session_timeout(300) == 300


async def test_session_tool_infinite_timeout_does_not_crash():
    """int(float('inf')) 曾抛 OverflowError 使后台任务崩溃；现在回退默认值并完成。"""
    skill = _OkSkill({"ok": True})
    executor = _make_executor(
        skill_manager=skill,
        conv_kind="group",
        conv_id="123456",
    )
    await executor._run_session_tool(
        "download__url",
        {"url": "http://a", "timeout_seconds": float("inf")},
        "group:123456",
        "group",
        "123456",
    )
    history = executor._session_completed["group:123456"]
    assert history[-1]["status"] == "completed"


async def test_close_does_not_start_queued_session_tool():
    """close() 后排队任务不得被执行：_cleanup 必须丢弃排队项且不再启动新任务。"""

    class _HoldingSkill(_FakeSkillManager):
        def __init__(self) -> None:
            super().__init__()
            self.release = asyncio.Event()

        async def execute(self, name: str, args: dict) -> str:
            self.executions.append((name, args))
            await self.release.wait()
            return json.dumps({"ok": True})

    skill = _HoldingSkill()
    executor = _make_executor(
        skill_manager=skill,
        conv_kind="group",
        conv_id="close-test",
    )
    try:
        first = json.loads(await executor.execute("download__url", {"url": "http://a"}))
        assert first["status"] == "session_submitted"
        for _ in range(200):
            if skill.executions:
                break
            await asyncio.sleep(0.01)
        assert skill.executions
        second = json.loads(
            await executor.execute("download__url", {"url": "http://b"})
        )
        assert second["status"] == "queued"

        await executor.close()
        assert executor.closed
        assert not executor._session_task_queue

        skill.release.set()
        await asyncio.sleep(0.05)
        assert len(skill.executions) == 1
    finally:
        skill.release.set()
        await executor.close()


async def test_executor_context_manager_exposes_idempotent_close_semantics():
    skill = _FakeSkillManager()
    executor = _make_executor(
        skill_manager=skill,
        conv_kind="group",
        conv_id="closed",
    )

    async with executor as active:
        assert active is executor
        assert not executor.closed

    assert executor.closed
    result = json.loads(await executor.execute("download__url", {"url": "http://a"}))
    assert result["status"] == "closed"
    assert result["ok"] is False
    assert skill.executions == []
    await asyncio.gather(executor.close(), executor.close())


async def test_close_cleanup_survives_caller_cancellation():
    class _SlowCancellationSkill(_FakeSkillManager):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()
            self.cancelling = asyncio.Event()
            self.release_cleanup = asyncio.Event()

        async def execute(self, name: str, args: dict) -> str:
            self.executions.append((name, args))
            self.started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelling.set()
                await self.release_cleanup.wait()
                raise

    skill = _SlowCancellationSkill()
    executor = _make_executor(
        skill_manager=skill,
        conv_kind="group",
        conv_id="cancel-close",
    )
    await executor.execute("download__url", {})
    await asyncio.wait_for(skill.started.wait(), timeout=1)

    first_close = asyncio.create_task(executor.close())
    await asyncio.wait_for(skill.cancelling.wait(), timeout=1)
    first_close.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first_close

    second_close = asyncio.create_task(executor.close())
    await asyncio.sleep(0)
    assert not second_close.done()
    skill.release_cleanup.set()
    await asyncio.wait_for(second_close, timeout=1)

    assert executor.closed
    assert not executor._session_tasks
    assert not executor._session_task_info


# ── Skill 定义校验器：缺省 parameters / 布尔 schema / pattern ─────


def _skill_def_params(name: str, parameters: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": name,
            "parameters": parameters,
        },
    }


def test_skill_definition_allows_missing_parameters():
    """缺少 parameters 键的工具定义按空对象处理，注册与聚合均可用。"""
    from neobot_app.skills.base import SkillManager

    skill = _SnapshotSkill("noparams", "x")
    skill.get_tools = lambda: [
        {"type": "function", "function": {"name": "run", "description": "no params"}}
    ]
    manager = SkillManager()
    manager.register(skill)
    params = manager.get_tools()[0]["function"]["parameters"]
    assert params == {"type": "object", "properties": {}, "required": []}


def test_skill_schema_accepts_boolean_items_and_additional_properties():
    from neobot_app.skills.base import SkillManager

    skill = _SnapshotSkill("bool", "x")
    skill.get_tools = lambda: [
        _skill_def_params(
            "run",
            {
                "type": "object",
                "properties": {
                    "tags": {"type": "array", "items": True},
                    "meta": {"type": "object", "additionalProperties": False},
                },
                "required": [],
            },
        )
    ]
    SkillManager().register(skill)


def test_skill_schema_rejects_invalid_regex_pattern():
    from neobot_app.skills.base import SkillManager

    skill = _SnapshotSkill("badpat", "x")
    skill.get_tools = lambda: [
        _skill_def_params(
            "run",
            {
                "type": "object",
                "properties": {"x": {"type": "string", "pattern": "["}},
                "required": [],
            },
        )
    ]
    try:
        SkillManager().register(skill)
    except ValueError as exc:
        assert "pattern" in str(exc)
    else:
        raise AssertionError("invalid regex pattern was accepted")
