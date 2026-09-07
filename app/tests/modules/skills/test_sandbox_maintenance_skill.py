"""通过公开 Skill 工具入口验证沙箱维护不再丢失中文文件名。"""

import json
from unittest.mock import AsyncMock

from neobot_app.runtime.sandbox_maintenance import SandboxMaintenanceManager
from neobot_app.skills.base import SkillManager
from neobot_app.skills.sandbox_maintenance_skill import SandboxMaintenanceSkill


async def test_trigger_maintenance_preserves_chinese_files_through_skill_manager(tmp_path):
    root = tmp_path / "sandbox"
    tools = root / "tools"
    tools.mkdir(parents=True)
    names = ["天天星消乐.html", "另一个游戏.html", "游戏Demo.html"]
    for name in names:
        (tools / name).write_text(f"<html>{name}</html>", encoding="utf-8")
    # 旧版本留下的文件也不能覆盖或凭空猜测恢复原名。
    (tools / ".html").write_bytes(b"legacy")
    skill = SandboxMaintenanceSkill(maintenance_manager=SandboxMaintenanceManager(root))
    registry = SkillManager()
    registry.register(skill)

    result = json.loads(await registry.execute("sandbox_maintenance__trigger_maintenance", {}))

    assert result["ok"] is True
    assert result["skipped"] is False
    assert result["renamed"] == []
    assert result["doc_updated"] is True
    assert {path.name for path in tools.iterdir()} == {*names, ".html"}
    assert (tools / ".html").read_bytes() == b"legacy"
    index = (root / "文件存储.md").read_text(encoding="utf-8")
    for name in names:
        assert (tools / name).read_text(encoding="utf-8") == f"<html>{name}</html>"
        assert f"`{name}`" in index


async def test_trigger_reports_missing_manager():
    result = json.loads(await SandboxMaintenanceSkill().execute("trigger_maintenance", {}))
    assert result["ok"] is False
    assert "maintenance_manager" in result["error"]


async def test_trigger_preserves_skip_response():
    manager = AsyncMock()
    manager.run_once.return_value = {"ok": True, "skipped": True, "reason": "无文件变更"}
    skill = SandboxMaintenanceSkill(maintenance_manager=manager)

    result = json.loads(await skill.execute("trigger_maintenance", {}))

    assert result == manager.run_once.return_value
    manager.run_once.assert_awaited_once_with()


async def test_trigger_reports_maintenance_error():
    manager = AsyncMock()
    manager.run_once.side_effect = OSError("maintenance failed")

    result = json.loads(await SandboxMaintenanceSkill(manager).execute("trigger_maintenance", {}))

    assert result == {"ok": False, "error": "maintenance failed"}


def test_skill_documents_unicode_preservation_and_mutation():
    skill = SandboxMaintenanceSkill()
    assert "中文名保留原样" in skill.instructions
    assert "Unicode" in skill.instructions
    assert "不会自动恢复" in skill.instructions
    trigger = next(tool["function"] for tool in skill.get_tools()
                   if tool["function"]["name"] == "trigger_maintenance")
    assert "Unicode" in trigger["description"]
    assert "删除文件" in trigger["description"]
    assert trigger["parameters"]["required"] == []
