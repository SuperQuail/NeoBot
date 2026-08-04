"""FileStorageSkill 测试 — 文件索引文档（文件存储.md/TODO.md）与持久化目录管理。"""

from __future__ import annotations

import json

from neobot_app.skills.file_storage_skill import (
    FileStorageSkill,
    _apply_storage_update,
    _apply_todo_update,
    _extract_filename,
)

STORAGE_DOC = "文件存储.md"
TODO_DOC = "TODO.md"


def _parse(text: str) -> dict:
    return json.loads(text)


def _make_skill(sandbox=None) -> FileStorageSkill:
    return FileStorageSkill(sandbox_service=sandbox)


async def test_read_storage_doc_returns_default_when_missing(make_sandbox):
    """正常路径：索引文档不存在时应返回默认模板内容。"""
    skill = _make_skill(make_sandbox())

    result = _parse(await skill.execute("read_storage_doc", {}))

    assert result["ok"] is True
    assert "# 沙箱文件存储" in result["content"]
    assert "## tools/" in result["content"]


async def test_update_storage_doc_adds_entry_and_creates_doc(make_sandbox):
    """正常路径：update_storage_doc add 应创建索引文档并写入条目。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)

    result = _parse(await skill.execute("update_storage_doc", {
        "section": "tools", "entry": "- `fetch.py` — 抓取网页", "action": "add",
    }))

    assert result["ok"] is True
    content = (await sandbox.read_file(sandbox.resolve_path(STORAGE_DOC))).decode("utf-8")
    assert "- `fetch.py` — 抓取网页" in content
    assert "## tools/" in content


async def test_update_storage_doc_rejects_invalid_section(make_sandbox):
    """异常路径：section 不是 tools/docs/assets 时应拒绝且不写文件。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)

    result = _parse(await skill.execute("update_storage_doc", {
        "section": "temp", "entry": "- x.py — x", "action": "add",
    }))

    assert result["ok"] is False
    assert "section 必须是 tools/docs/assets" in result["error"]
    assert not sandbox.resolve_path(STORAGE_DOC).exists()


async def test_update_storage_doc_rejects_empty_entry(make_sandbox):
    """异常路径：entry 为空时应拒绝更新。"""
    skill = _make_skill(make_sandbox())

    result = _parse(await skill.execute("update_storage_doc", {
        "section": "tools", "entry": "   ", "action": "add",
    }))

    assert result["ok"] is False
    assert "entry 不能为空" in result["error"]


async def test_update_storage_doc_remove_and_update(make_sandbox):
    """正常路径：action=remove 删除行、action=update 替换同名条目。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)
    await sandbox.write_file(
        sandbox.resolve_path(STORAGE_DOC),
        "# 沙箱文件存储\n\n## tools/\n- `a.py` — 工具A\n- `b.py` — 工具B\n\n## docs/\n（暂无文档）\n".encode("utf-8"),
    )

    removed = _parse(await skill.execute("update_storage_doc", {
        "section": "tools", "entry": "- `a.py` — 工具A", "action": "remove",
    }))
    updated = _parse(await skill.execute("update_storage_doc", {
        "section": "tools", "entry": "- `b.py` — 工具B（v2）", "action": "update",
    }))

    assert removed["ok"] is True and updated["ok"] is True
    content = (await sandbox.read_file(sandbox.resolve_path(STORAGE_DOC))).decode("utf-8")
    assert "- `a.py`" not in content
    assert "- `b.py` — 工具B（v2）" in content
    assert "- `b.py` — 工具B\n" not in content


async def test_read_todo_returns_default_when_missing(make_sandbox):
    """正常路径：TODO.md 不存在时应返回默认模板。"""
    skill = _make_skill(make_sandbox())

    result = _parse(await skill.execute("read_todo", {}))

    assert result["ok"] is True
    assert "# 待实现工具" in result["content"]


async def test_update_todo_add_and_complete_flow(make_sandbox):
    """正常路径：update_todo add 进 Pending、complete 移到 Done 并勾选。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)

    added = _parse(await skill.execute("update_todo", {
        "entry": "- [ ] batch_resize.py — 批量缩放", "action": "add",
    }))
    completed = _parse(await skill.execute("update_todo", {
        "entry": "- [ ] batch_resize.py — 批量缩放", "action": "complete",
    }))

    assert added["ok"] is True and completed["ok"] is True
    content = (await sandbox.read_file(sandbox.resolve_path(TODO_DOC))).decode("utf-8")
    assert "batch_resize" in content
    assert "- [x] batch_resize.py — 批量缩放" in content
    assert "- [ ] batch_resize.py" not in content


async def test_update_todo_rejects_empty_entry(make_sandbox):
    """异常路径：entry 为空时应拒绝更新。"""
    skill = _make_skill(make_sandbox())

    result = _parse(await skill.execute("update_todo", {"entry": "", "action": "add"}))

    assert result["ok"] is False
    assert "entry 不能为空" in result["error"]


async def test_list_storage_dirs_shows_persistent_dirs(make_sandbox):
    """正常路径：list_storage_dirs 应展示 tools/docs/assets/gift 下文件概览。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)
    await sandbox.write_file(sandbox.resolve_path("tools/fetch.py"), b"print(1)")
    await sandbox.write_file(sandbox.resolve_path("docs/guide.md"), b"# guide")

    result = _parse(await skill.execute("list_storage_dirs", {}))

    assert result["ok"] is True
    assert {f["name"] for f in result["dirs"]["tools"]} == {"fetch.py"}
    assert {f["name"] for f in result["dirs"]["docs"]} == {"guide.md"}
    assert result["dirs"]["assets"] == []
    assert result["dirs"]["gift"] == []


async def test_list_storage_dirs_empty_when_dirs_missing(make_sandbox):
    """边界：持久化目录尚未创建时应返回空列表而非报错。"""
    skill = _make_skill(make_sandbox())

    result = _parse(await skill.execute("list_storage_dirs", {}))

    assert result["ok"] is True
    assert all(v == [] for v in result["dirs"].values())


async def test_handlers_without_sandbox_rejected():
    """异常路径：sandbox_service 未配置时所有处理器应返回配置错误。"""
    skill = _make_skill(sandbox=None)

    for tool in ("read_storage_doc", "update_storage_doc", "read_todo", "update_todo", "list_storage_dirs"):
        result = _parse(await skill.execute(tool, {}))

        assert result["ok"] is False
        assert "sandbox_service 未配置" in result["error"]


async def test_unknown_tool_returns_error(make_sandbox):
    """异常路径：未知工具名应返回明确错误。"""
    skill = _make_skill(make_sandbox())

    result = _parse(await skill.execute("no_such_tool", {}))

    assert result["ok"] is False
    assert "unknown file_storage tool" in result["error"]


def test_apply_storage_update_add_to_placeholder_section():
    """正常路径：纯函数 add 到「（暂无）」占位 section 应替换占位行。"""
    content = "# 沙箱文件存储\n\n## tools/\n（暂无工具脚本）\n\n## docs/\n（暂无文档）\n"

    result = _apply_storage_update(content, "tools", "- `t.py` — 工具", "add")

    assert "- `t.py` — 工具" in result
    assert "（暂无工具脚本）" not in result


def test_apply_storage_update_add_to_unknown_section_appends_end():
    """边界：add 到内容中不存在的 section 时应在文件末尾追加条目。"""
    content = "# 沙箱文件存储\n\n## tools/\n（暂无工具脚本）\n"

    result = _apply_storage_update(content, "docs", "- `d.py` — 文档", "add")

    assert result.rstrip().endswith("- `d.py` — 文档")


def test_apply_todo_update_complete_moves_entry():
    """正常路径：纯函数 complete 应把 Pending 中匹配条目移到 Done 并勾选。"""
    content = "# 待实现工具\n\n## Pending\n- [ ] batch.py — 批量\n- [ ] other.py — 其他\n\n## Done\n（暂无已完成项）\n"

    result = _apply_todo_update(content, "- [ ] batch.py — 批量", "complete")

    assert "- [x] batch.py — 批量" in result
    assert "- [ ] batch.py" not in result
    assert "- [ ] other.py" in result


def test_apply_todo_update_complete_moves_backtick_entry():
    """边界：纯函数 complete 对反引号格式条目（_extract_filename 可解析）应正确移动。"""
    content = "# 待实现工具\n\n## Pending\n- [ ] `batch.py` — 批量\n\n## Done\n（暂无已完成项）\n"

    result = _apply_todo_update(content, "- [ ] `batch.py` — 批量", "complete")

    assert "- [x] `batch.py` — 批量" in result
    assert "- [ ] `batch.py`" not in result


def test_extract_filename_from_backtick_entry():
    """正常路径：_extract_filename 应提取反引号中的文件名。"""
    assert _extract_filename("- `script.py` — 用途") == "script.py"
    assert _extract_filename("no code fence here") == ""
