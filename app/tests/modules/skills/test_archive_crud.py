"""ArchiveCRUDSkill 测试:完整保存不截断、摘要生成、offset 分页阅读。"""

from __future__ import annotations

import json
from types import SimpleNamespace

from neobot_app.skills.archive_crud import (
    ArchiveCRUDSkill,
    _read_item_payload,
)


def _item(value: str) -> SimpleNamespace:
    return SimpleNamespace(table_name="group_profile", key="42", value=value, version=1)


def _long_text(lines: int = 10, line_len: int = 100) -> str:
    return "\n".join(f"第{i}行-" + "x" * line_len for i in range(1, lines + 1))


# ── 保存:完整写入,不截断 ─────────────────────────────────────────


async def test_save_archive_keeps_full_value() -> None:
    """保存超长档案时不得截断,原始内容完整入库。"""
    saved: list[tuple] = []

    class _FakeService:
        async def set(self, table_name, key, value, tags):
            saved.append((table_name, key, value, tags))
            return SimpleNamespace(
                table_name=table_name, key=key, value=value, version=7
            )

    skill = ArchiveCRUDSkill(
        archive_service=_FakeService(),
        max_chars={"user_profile": 300, "group_profile": 1500},
    )
    value = "x" * 5000
    result = json.loads(await skill.execute("save_archive", {"table_name": "group_profile", "key": "42", "value": value}))

    assert result["ok"] is True
    assert result["version"] == 7
    assert "truncated" not in result
    assert saved[0][2] == value  # 完整保留


# ── 摘要生成 ─────────────────────────────────────────────────────


def test_build_summary_keeps_tail_within_limit() -> None:
    text = _long_text()
    summary, truncated = ArchiveCRUDSkill.build_summary(text, 500)

    assert truncated is True
    assert len(summary) <= 500
    assert summary.startswith("第")  # 从完整行开始


def test_build_summary_short_text_unchanged() -> None:
    summary, truncated = ArchiveCRUDSkill.build_summary("short", 1500)

    assert truncated is False
    assert summary == "short"


# ── 分页读取 ─────────────────────────────────────────────────────


def test_read_item_payload_without_offset_returns_full() -> None:
    value = _long_text()
    payload = _read_item_payload(_item(value), offset=None)

    assert payload["value"] == value
    assert payload["total_chars"] == len(value)
    assert "offset" not in payload


def test_read_item_payload_positive_offset_pages() -> None:
    value = _long_text(lines=10, line_len=100)  # 每行约 106 字,共约 1060 字
    first = _read_item_payload(_item(value), offset=0)
    second = _read_item_payload(_item(value), offset=1)

    assert first["offset"] == 0
    assert len(first["value"]) <= 500
    assert first["value"].startswith("第1行")
    assert first["has_more_forward"] is True
    assert first["has_more_backward"] is False
    assert second["value"].startswith("第")
    assert second["value"] != first["value"]
    assert second["has_more_backward"] is True


def test_read_item_payload_negative_offset_reads_tail() -> None:
    value = _long_text(lines=10, line_len=100)
    last = _read_item_payload(_item(value), offset=-1)
    prev = _read_item_payload(_item(value), offset=-2)

    # 最后一项包含档案末尾(最新内容)
    assert value.endswith(last["value"]) or last["value"].endswith(value.splitlines()[-1])
    assert last["has_more_forward"] is False
    assert last["has_more_backward"] is True
    # 倒数第二页在最后一页之前
    tail_pos = value.find(last["value"])
    prev_pos = value.find(prev["value"])
    assert prev_pos < tail_pos


def test_read_item_payload_offset_out_of_range() -> None:
    value = _long_text(lines=2, line_len=50)
    payload = _read_item_payload(_item(value), offset=99)

    assert payload["value"] == ""
    assert payload["has_more_forward"] is False
    assert payload["has_more_backward"] is True


def test_read_item_payload_aligns_line_boundaries() -> None:
    # 构造 500 字符整页,确保正偏移 1 的页从完整行开始且不以半行结尾
    value = _long_text(lines=20, line_len=100)
    second = _read_item_payload(_item(value), offset=1)

    content = second["value"]
    if content:
        # 行首对齐(以"第"开头)或为空
        assert content.startswith("第") or content == ""
        # 行尾对齐:结尾是换行或到达档案末尾
        assert content.endswith("\n") or second["has_more_forward"] is False


async def test_read_archive_handler_supports_offset() -> None:
    class _FakeService:
        async def get(self, table_name, key):
            return _item("第1行\n" + "y" * 2000)

    skill = ArchiveCRUDSkill(archive_service=_FakeService())
    result = json.loads(
        await skill.execute(
            "read_archive", {"table_name": "group_profile", "key": "42", "offset": -1}
        )
    )

    assert result["ok"] is True
    item = result["item"]
    assert item["offset"] == -1
    assert item["total_chars"] > 500
    assert len(item["value"]) <= 500
    assert item["has_more_forward"] is False
    assert item["has_more_backward"] is True
    assert item["value"].endswith("y" * 500)


async def test_read_archive_handler_bad_offset_rejected() -> None:
    skill = ArchiveCRUDSkill(archive_service=object())
    result = json.loads(
        await skill.execute(
            "read_archive", {"table_name": "group_profile", "key": "42", "offset": "abc"}
        )
    )

    assert result["ok"] is False
    assert "offset" in result["error"]


# ── 渲染侧:summary 优先 + 头部截断 + 查阅引导 ────────────────────


class _FakeArchiveGet:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    async def get(self, table_name: str, key: str) -> SimpleNamespace | None:
        value = self._values.get(f"{table_name}:{key}")
        if value is None:
            return None
        return SimpleNamespace(value=value)


def _fake_prompt_config(user_limit: int = 4000, group_limit: int = 1500) -> SimpleNamespace:
    class _Chat:
        key_word = []

    return SimpleNamespace(
        chat=_Chat(),
        agent=SimpleNamespace(
            memory=SimpleNamespace(
                archive=SimpleNamespace(max_chars=user_limit, group_profile_max_chars=group_limit)
            )
        ),
    )


async def test_group_memory_prefers_summary_then_full() -> None:
    """群聊渲染:group_summary 优先,缺失时回退 group_profile。"""
    from neobot_app.prompt.builder import PromptBuilder

    archive = _FakeArchiveGet(
        {
            "group_summary:42": "群聊总体总结",
            "group_profile:42": "群聊全量档案",
        }
    )
    pb = PromptBuilder(_fake_prompt_config(), profile_service=object())
    pb._archive_memory_service = archive

    assert await pb._fetch_group_memory("42") == "群聊总体总结"

    archive = _FakeArchiveGet({"group_profile:42": "群聊全量档案"})
    pb._archive_memory_service = archive
    assert await pb._fetch_group_memory("42") == "群聊全量档案"

    archive = _FakeArchiveGet({})
    pb._archive_memory_service = archive
    assert await pb._fetch_group_memory("42") is None


async def test_group_memory_truncates_head_and_guides() -> None:
    """群聊记忆超长:截取开头部分(1500 内)并附分页查阅引导。"""
    from neobot_app.prompt.builder import PromptBuilder

    long_value = "总体概述\n" + "x" * 3000
    archive = _FakeArchiveGet({"group_summary:42": long_value})
    pb = PromptBuilder(_fake_prompt_config(), profile_service=object())
    pb._archive_memory_service = archive

    rendered = await pb._fetch_group_memory("42")

    assert rendered is not None
    assert "以下为开头部分" in rendered
    assert "分页阅读" in rendered and "越后的内容越新" in rendered
    assert "总体概述" in rendered  # 头部(总体总结)保留
    assert rendered.startswith("[记忆较长")


async def test_user_archive_prefers_summary_and_truncates_at_4000() -> None:
    """个人记忆:user_summary 优先;超长时截取前 4000 字符并附引导。"""
    from neobot_app.user_profiles import UserProfileService

    archive = _FakeArchiveGet(
        {
            "user_summary:10001": "个人总体总结",
            "user_profile:10001": "个人全量档案",
        }
    )
    service = UserProfileService(
        adapter=object(), uow_factory=object(), config=_fake_prompt_config()
    )
    service._archive_memory_service = archive

    assert await service._fetch_user_archive("10001") == "个人总体总结"

    long_value = "开头概述\n" + "y" * 6000
    archive = _FakeArchiveGet({"user_summary:10001": long_value})
    service._archive_memory_service = archive
    rendered = await service._fetch_user_archive("10001")

    assert rendered is not None
    assert rendered.startswith("[记忆较长")
    assert "开头概述" in rendered
    assert "分页阅读" in rendered
    body = rendered.split("\n", 1)[1]
    assert "y" * 3999 in body or len(body) < 4500


# ── 总结 agent 行为规范 ──────────────────────────────────────────


async def test_summary_prompt_requires_summary_and_full_records() -> None:
    """总结提示词:要求维护受限 summary(总体在前+依次总结+硬限制)与全量记忆。"""
    from neobot_app.config.schemas.bot import AgentMemoryArchive, BotConfig
    from neobot_app.runtime.archive_memory_summary import ArchiveMemoryAutoSummaryService

    config = BotConfig(
        agent=SimpleNamespace(
            memory=SimpleNamespace(
                archive=AgentMemoryArchive(max_chars=4000, group_profile_max_chars=1500),
                favorability=SimpleNamespace(max_change_per_summary=5),
            )
        )
    )
    svc = object.__new__(ArchiveMemoryAutoSummaryService)
    svc._config = config
    svc._favorability_max_change = 5
    svc._item_archive_enabled = False

    prompt = svc._build_summary_prompt(
        conversation_kind="group", conversation_id="42", messages=[]
    )

    assert "'group_summary'" in prompt
    assert "'group_profile'" in prompt
    assert "HARD LIMIT: 1500" in prompt
    assert "OVERALL summary" in prompt
    assert "chronological order" in prompt
    assert "REWRITE and compress it with save_archive" in prompt
    assert "NEVER append beyond the limit" in prompt
    assert "negative offset reads from the tail" in prompt

    private_prompt = svc._build_summary_prompt(
        conversation_kind="private", conversation_id="10001", messages=[]
    )
    assert "'user_summary'" in private_prompt
    assert "'user_profile'" in private_prompt
    assert "HARD LIMIT: 4000" in private_prompt


# ── 配置默认值 ────────────────────────────────────────────────────


def test_memory_config_defaults() -> None:
    """记忆总结触发条数默认:群聊 500、私聊 200;个人记忆展示上限 4000。"""
    from neobot_app.config.schemas.bot import AgentMemoryArchive, AgentMemoryTrigger

    trigger = AgentMemoryTrigger()
    assert trigger.group_interval == 500
    assert trigger.private_interval == 200

    archive = AgentMemoryArchive()
    assert archive.max_chars == 4000
    assert archive.group_profile_max_chars == 1500
