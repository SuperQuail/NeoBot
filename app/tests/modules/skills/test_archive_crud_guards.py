"""archive_crud 的 allow_delete / allowed_tables 开关必须真正生效。

历史上这两个参数只被存进字段（``self._allow_delete`` / ``self._allowed_tables``）
而全仓再无读取，于是：
- ``agent.memory.archive.allow_delete = false`` 形同虚设，模型可以无条件删档案；
- ``allowed_tables`` 也无法把访问限制在指定表上。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from neobot_app.skills.archive_crud import PENDING_MESSAGES_TABLE, ArchiveCRUDSkill


class _FakeService:
    def __init__(self) -> None:
        self.deleted: list[tuple[str, str]] = []
        self.saved: list[tuple[str, str]] = []
        self.items: dict[tuple[str, str], SimpleNamespace] = {}

    async def set(self, table_name, key, value, tags=None):
        self.saved.append((table_name, key))
        item = SimpleNamespace(table_name=table_name, key=key, value=value, version=1)
        self.items[(table_name, key)] = item
        return item

    async def get(self, table_name, key):
        return self.items.get((table_name, key))

    async def delete(self, table_name, key):
        self.deleted.append((table_name, key))
        return True

    async def list(self, table_name, limit=10, offset=0):
        return [
            item for (name, _), item in self.items.items() if name == table_name
        ][:limit]


def _skill(**kwargs) -> tuple[ArchiveCRUDSkill, _FakeService]:
    service = _FakeService()
    skill = ArchiveCRUDSkill(archive_service=service, **kwargs)
    return skill, service


# ── allow_delete ────────────────────────────────────────────────────


async def test_delete_is_rejected_by_default() -> None:
    skill, service = _skill()

    result = json.loads(
        await skill.execute(
            "delete_archive", {"table_name": "user_profile", "key": "42"}
        )
    )

    assert result["ok"] is False
    assert "allow_delete" in result["error"]
    assert service.deleted == []


async def test_delete_allowed_when_enabled() -> None:
    skill, service = _skill(allow_delete=True)

    result = json.loads(
        await skill.execute(
            "delete_archive", {"table_name": "user_profile", "key": "42"}
        )
    )

    assert result["ok"] is True
    assert service.deleted == [("user_profile", "42")]


# ── allowed_tables ──────────────────────────────────────────────────


async def test_allowed_tables_blocks_write() -> None:
    skill, service = _skill(allowed_tables=("user_profile",))

    result = json.loads(
        await skill.execute(
            "save_archive",
            {"table_name": "group_profile", "key": "1", "value": "x"},
        )
    )

    assert result["ok"] is False
    assert "group_profile" in result["error"]
    assert service.saved == []


async def test_allowed_tables_permits_listed_table() -> None:
    skill, service = _skill(allowed_tables=("user_profile",))

    result = json.loads(
        await skill.execute(
            "save_archive",
            {"table_name": "user_profile", "key": "1", "value": "x"},
        )
    )

    assert result["ok"] is True
    assert service.saved == [("user_profile", "1")]


async def test_allowed_tables_blocks_delete_even_when_enabled() -> None:
    skill, service = _skill(allow_delete=True, allowed_tables=("user_profile",))

    result = json.loads(
        await skill.execute(
            "delete_archive", {"table_name": "group_profile", "key": "1"}
        )
    )

    assert result["ok"] is False
    assert service.deleted == []


async def test_allowed_tables_blocks_read() -> None:
    skill, _ = _skill(allowed_tables=("user_profile",))

    result = json.loads(
        await skill.execute("read_archive", {"table_name": "group_profile", "key": "1"})
    )

    assert result["ok"] is False


async def test_allowed_tables_blocks_every_item_of_batch_read() -> None:
    """items 批量读取必须逐项校验，不能只看顶层 table_name。

    否则只要顶层填一个合法表名，就能用 items 里的任意表名读到未授权的档案。
    """
    skill, service = _skill(allowed_tables=("user_profile",))
    service.items[("secret_table", "k")] = SimpleNamespace(
        table_name="secret_table", key="k", value="TOP-SECRET", version=1
    )

    result = json.loads(
        await skill.execute(
            "read_archive",
            {
                "table_name": "user_profile",
                "key": "1",
                "items": [{"table_name": "secret_table", "key": "k"}],
            },
        )
    )

    assert result["ok"] is False
    assert "secret_table" in result["error"]
    assert "TOP-SECRET" not in json.dumps(result, ensure_ascii=False)


async def test_batch_read_returns_allowed_items() -> None:
    skill, service = _skill(allowed_tables=("user_profile",))
    service.items[("user_profile", "1")] = SimpleNamespace(
        table_name="user_profile", key="1", value="hello", version=1
    )

    result = json.loads(
        await skill.execute(
            "read_archive",
            {"items": [{"table_name": "user_profile", "key": "1"}]},
        )
    )

    assert result["ok"] is True
    assert len(result["items"]) == 1


async def test_empty_allowed_tables_means_unrestricted() -> None:
    skill, service = _skill()

    result = json.loads(
        await skill.execute(
            "save_archive", {"table_name": "item_archive", "key": "k", "value": "v"}
        )
    )

    assert result["ok"] is True
    assert service.saved == [("item_archive", "k")]


async def test_pending_messages_read_is_exempt_from_allowlist() -> None:
    """内部计数表不能被 allowed_tables 掐掉，否则自动总结会整体失效。"""
    skill, service = _skill(allowed_tables=("user_profile",))
    service.items[(PENDING_MESSAGES_TABLE, "group:1")] = SimpleNamespace(
        table_name=PENDING_MESSAGES_TABLE,
        key="group:1",
        value=json.dumps({"count": 1, "messages": []}),
        version=1,
    )

    result = json.loads(
        await skill.execute("read_pending_messages", {"conversation_key": "group:1"})
    )

    assert result["ok"] is True


# ── 工具可见性 ──────────────────────────────────────────────────────


def _tool_names(skill: ArchiveCRUDSkill) -> list[str]:
    return [tool["function"]["name"] for tool in skill.get_tools()]


def test_delete_tool_hidden_when_disabled() -> None:
    skill, _ = _skill()

    assert "delete_archive" not in _tool_names(skill)
    assert "save_archive" in _tool_names(skill)


def test_instructions_do_not_advertise_hidden_delete_tool() -> None:
    """提示词与工具表必须一致：隐藏了删除工具就不能再教模型去调用它。"""
    disabled, _ = _skill()
    enabled, _ = _skill(allow_delete=True)

    assert "delete_archive" not in disabled.instructions
    assert "删除档案未启用" in disabled.instructions
    assert "删除" not in disabled.description
    assert "delete_archive" in enabled.instructions
    assert "删除" in enabled.description


def test_instructions_declare_allowed_tables_limit() -> None:
    skill, _ = _skill(allowed_tables=("user_profile",))

    assert "user_profile" in skill.instructions


def test_delete_tool_exposed_when_enabled() -> None:
    skill, _ = _skill(allow_delete=True)

    assert "delete_archive" in _tool_names(skill)

