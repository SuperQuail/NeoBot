"""ArchiveCRUDSkill 测试:完整保存不截断、摘要生成、offset 分页阅读。"""

from __future__ import annotations

import json
from types import SimpleNamespace

from neobot_app.skills.archive_crud import (
    PENDING_MESSAGES_TABLE,
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
    assert "按需读取" in rendered and "越后的内容越新" in rendered
    assert "mode='outline'" in rendered
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
    assert "按需读取" in rendered
    assert "mode='outline'" in rendered
    body = rendered.split("\n", 1)[1]
    assert "y" * 3999 in body or len(body) < 4500


# ── 总结 agent 行为规范 ──────────────────────────────────────────


def _summary_service(*, item_archive: bool = False, snippet_chars: int = 120):
    from neobot_app.config.schemas.bot import AgentMemoryArchive, BotConfig
    from neobot_app.runtime.archive_memory_summary import ArchiveMemoryAutoSummaryService

    config = BotConfig(
        agent=SimpleNamespace(
            memory=SimpleNamespace(
                archive=AgentMemoryArchive(max_chars=4000, group_profile_max_chars=1500),
                favorability=SimpleNamespace(max_change_per_summary=5),
                trigger=SimpleNamespace(
                    group_interval=500,
                    private_interval=200,
                    prompt_snippet_chars=snippet_chars,
                ),
            )
        )
    )
    svc = object.__new__(ArchiveMemoryAutoSummaryService)
    svc._config = config
    svc._favorability_max_change = 5
    svc._item_archive_enabled = item_archive
    svc._item_archive_table = "item_archive"
    svc._prompt_snippet_chars = snippet_chars
    svc._max_tool_rounds = 20
    return svc


async def test_summary_prompt_requires_incremental_writes() -> None:
    """总结提示词:全量档案只用 patch_archive 增量追加,定长 summary 才允许 save_archive 重写。"""
    svc = _summary_service()

    prompt = svc._build_summary_prompt(
        conversation_kind="group", conversation_id="42", messages=[]
    )

    assert "'group_summary'" in prompt
    assert "'group_profile'" in prompt
    assert "HARD LIMIT: 1500" in prompt
    assert "OVERALL summary" in prompt
    assert "chronological order" in prompt
    assert "NEVER exceed the limit" in prompt
    # 增量写入:append 不需要先读全文
    assert "archive_crud__patch_archive" in prompt
    assert "op='append'" in prompt
    assert "do NOT read the record first" in prompt
    assert "save_archive on this table is forbidden" in prompt
    # 按需查看:先大纲再分页,而不是全量读取
    assert "mode='outline'" in prompt
    assert "read only the relevant page" in prompt
    assert "Read both first" not in prompt
    assert "conversation_key: group:42" in prompt

    private_prompt = svc._build_summary_prompt(
        conversation_kind="private", conversation_id="10001", messages=[]
    )
    assert "'user_summary'" in private_prompt
    assert "'user_profile'" in private_prompt
    assert "HARD LIMIT: 4000" in private_prompt


async def test_summary_prompt_truncates_messages_and_points_to_tool() -> None:
    """消息超长时只注入截断片段,并给出 read_pending_messages 按需读取引导。"""
    svc = _summary_service(snippet_chars=20)
    messages = [
        {"sender_id": "1", "sender_name": "甲", "text": "短消息"},
        {"sender_id": "2", "sender_name": "乙", "text": "很长的消息" * 10},
    ]

    prompt = svc._build_summary_prompt(
        conversation_kind="group", conversation_id="42", messages=messages
    )

    assert "[1] 甲 / QQ:1: 短消息" in prompt
    assert "很长的消息" * 10 not in prompt
    assert "…" in prompt
    assert "read_pending_messages" in prompt
    assert "conversation_key='group:42'" in prompt
    assert "indices: 2" in prompt


# ── 配置默认值 ────────────────────────────────────────────────────


def test_memory_config_defaults() -> None:
    """记忆总结触发条数默认:群聊 500、私聊 200;消息截断 120 字;个人记忆展示上限 500。"""
    from neobot_app.config.schemas.bot import AgentMemoryArchive, AgentMemoryTrigger

    trigger = AgentMemoryTrigger()
    assert trigger.group_interval == 500
    assert trigger.private_interval == 200
    assert trigger.prompt_snippet_chars == 120
    assert trigger.max_tool_rounds == 20

    archive = AgentMemoryArchive()
    assert archive.max_chars == 500
    assert archive.group_profile_max_chars == 1500


# ── 增量编辑 patch_archive ────────────────────────────────────────


class _PatchService:
    """内存版档案服务：记录 set 调用，供 patch_archive 测试断言。"""

    def __init__(self, value: str | None = None, tags: list[str] | None = None) -> None:
        self.value = value
        self.tags = list(tags or [])
        self.sets: list[tuple] = []

    async def get(self, table_name, key):
        if self.value is None:
            return None
        return SimpleNamespace(
            table_name=table_name, key=key, value=self.value, tags=list(self.tags), version=3
        )

    async def set(self, table_name, key, value, tags):
        self.sets.append((table_name, key, value, tags))
        self.value = value
        self.tags = list(tags or [])
        return SimpleNamespace(
            table_name=table_name, key=key, value=value, tags=list(tags or []), version=4
        )


async def test_patch_archive_appends_only_delta() -> None:
    """append 只写增量：写入内容等于旧值 + 新增片段，不需要读全文。"""
    service = _PatchService(value="甲喜欢喝豆浆")
    skill = ArchiveCRUDSkill(archive_service=service)

    result = json.loads(
        await skill.execute(
            "patch_archive",
            {
                "table_name": "user_profile",
                "key": "1",
                "operations": [{"op": "append", "text": "最近迷上了羽毛球"}],
            },
        )
    )

    assert result["ok"] is True
    assert result["total_chars"] == len("甲喜欢喝豆浆\n最近迷上了羽毛球")
    assert service.sets == [("user_profile", "1", "甲喜欢喝豆浆\n最近迷上了羽毛球", [])]
    assert result["version"] == 4


async def test_patch_archive_replace_and_delete_require_unique_old() -> None:
    """replace/delete 只能定位唯一片段；不唯一或不存在时整批失败且不写入。"""
    service = _PatchService(value="旧结论A\n旧结论A\n其他")
    skill = ArchiveCRUDSkill(archive_service=service)

    ambiguous = json.loads(
        await skill.execute(
            "patch_archive",
            {
                "table_name": "user_profile",
                "key": "1",
                "operations": [{"op": "replace", "old": "旧结论A", "new": "新结论"}],
            },
        )
    )
    assert ambiguous["ok"] is False
    assert "不唯一" in ambiguous["error"]
    assert service.sets == []

    missing = json.loads(
        await skill.execute(
            "patch_archive",
            {
                "table_name": "user_profile",
                "key": "1",
                "operations": [{"op": "delete", "old": "不存在的片段"}],
            },
        )
    )
    assert missing["ok"] is False
    assert "未找到" in missing["error"]
    assert service.sets == []


async def test_patch_archive_atomic_on_partial_failure() -> None:
    """批量操作中任一失败则整批不生效（原子语义）。"""
    service = _PatchService(value="第一行")
    skill = ArchiveCRUDSkill(archive_service=service)

    result = json.loads(
        await skill.execute(
            "patch_archive",
            {
                "table_name": "user_profile",
                "key": "1",
                "operations": [
                    {"op": "append", "text": "第二行"},
                    {"op": "replace", "old": "不存在", "new": "x"},
                ],
            },
        )
    )

    assert result["ok"] is False
    assert service.sets == []


async def test_patch_archive_creates_missing_record_with_append() -> None:
    """条目不存在时，append/prepend 允许新建档案。"""
    service = _PatchService(value=None)
    skill = ArchiveCRUDSkill(archive_service=service)

    result = json.loads(
        await skill.execute(
            "patch_archive",
            {
                "table_name": "user_profile",
                "key": "9",
                "operations": [{"op": "append", "text": "新用户"}],
            },
        )
    )

    assert result["ok"] is True
    assert service.sets[0][2] == "新用户"


async def test_patch_archive_unchanged_skips_write() -> None:
    """编辑结果与原文一致时不写库（省一次写入）。"""
    service = _PatchService(value="内容")
    skill = ArchiveCRUDSkill(archive_service=service)

    result = json.loads(
        await skill.execute(
            "patch_archive",
            {
                "table_name": "user_profile",
                "key": "1",
                "operations": [{"op": "replace", "old": "内容", "new": "内容"}],
            },
        )
    )

    assert result["ok"] is True
    assert result["unchanged"] is True
    assert service.sets == []


# ── 大纲读取与待总结消息 ──────────────────────────────────────────


async def test_read_archive_outline_mode_returns_headings() -> None:
    """mode='outline' 只返回每行开头与统计信息，供模型决定读哪一页。"""
    service = _PatchService(value="总体总结\n- 甲喜欢豆浆\n- 乙喜欢羽毛球")
    skill = ArchiveCRUDSkill(archive_service=service)

    result = json.loads(
        await skill.execute(
            "read_archive",
            {"table_name": "group_profile", "key": "42", "mode": "outline"},
        )
    )

    assert result["ok"] is True
    item = result["item"]
    assert item["mode"] == "outline"
    assert item["total_chars"] == len("总体总结\n- 甲喜欢豆浆\n- 乙喜欢羽毛球")
    assert item["outline"][0].endswith("总体总结")
    assert "value" not in item


async def test_read_archive_rejects_unknown_mode() -> None:
    skill = ArchiveCRUDSkill(archive_service=_PatchService(value="x"))

    result = json.loads(
        await skill.execute(
            "read_archive", {"table_name": "group_profile", "key": "42", "mode": "raw"}
        )
    )

    assert result["ok"] is False
    assert "mode" in result["error"]


async def test_read_pending_messages_returns_selected_indices() -> None:
    """read_pending_messages 按序号读取待总结消息全文。"""
    state = {
        "count": 2,
        "messages": [
            {"sender_id": "1", "sender_name": "甲", "text": "第一条"},
            {"sender_id": "2", "sender_name": "乙", "text": "第二条"},
        ],
    }
    service = _PatchService(value=json.dumps(state, ensure_ascii=False))
    skill = ArchiveCRUDSkill(archive_service=service)

    result = json.loads(
        await skill.execute(
            "read_pending_messages",
            {"conversation_key": "group:42", "indices": [2, 99]},
        )
    )

    assert result["ok"] is True
    assert result["total"] == 2
    assert result["count"] == 1
    assert result["messages"] == [
        {"index": 2, "sender_name": "乙", "sender_id": "2", "text": "第二条"}
    ]


async def test_read_pending_messages_missing_counter_is_empty() -> None:
    skill = ArchiveCRUDSkill(archive_service=_PatchService(value=None))

    result = json.loads(
        await skill.execute("read_pending_messages", {"conversation_key": "group:42"})
    )

    assert result["ok"] is True
    assert result["messages"] == []


def test_pending_table_matches_summary_counter_table() -> None:
    """待总结消息表名必须与总结服务的计数器表名一致。"""
    from neobot_app.runtime.archive_memory_summary import COUNTER_TABLE

    assert PENDING_MESSAGES_TABLE == COUNTER_TABLE
