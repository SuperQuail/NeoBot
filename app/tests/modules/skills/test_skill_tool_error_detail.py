"""工具执行失败必须保留原因（日志与模型可见）。

两处旧实现都会销毁错误信息：
- SkillManager.execute: `except Exception: return f"工具执行失败 [{name}]"`
  ——不记日志、不带异常信息；
- 回复编排器的工具调用分支只记 error_type，`str(exc)` 既不进日志也不回给模型。
"""

from __future__ import annotations

from neobot_app.skills.base import SkillManager, SkillModule


class _BoomSkill(SkillModule):
    @property
    def name(self) -> str:
        return "boom"

    @property
    def description(self) -> str:
        return "总是抛异常"

    def get_tools(self) -> list[dict]:
        return [self._tool_def("fail", "总是失败")]

    async def execute(self, tool_name: str, args: dict) -> str:
        raise ValueError("磁盘已满：/dev/sda1")


async def test_skill_tool_failure_returns_reason() -> None:
    manager = SkillManager()
    manager.register(_BoomSkill())

    result = await manager.execute("boom__fail", {})

    assert "工具执行失败 [boom__fail]" in result
    assert "ValueError" in result
    assert "磁盘已满" in result


async def test_skill_tool_failure_is_truncated() -> None:
    class _VerboseBoom(_BoomSkill):
        async def execute(self, tool_name: str, args: dict) -> str:
            raise RuntimeError("x" * 2000)

    manager = SkillManager()
    manager.register(_VerboseBoom())

    result = await manager.execute("boom__fail", {})

    assert len(result) < 500


async def test_skill_success_path_unchanged() -> None:
    class _Ok(_BoomSkill):
        async def execute(self, tool_name: str, args: dict) -> str:
            return '{"ok": true}'

    manager = SkillManager()
    manager.register(_Ok())

    assert await manager.execute("boom__fail", {}) == '{"ok": true}'
