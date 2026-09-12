"""prompt/builder 模块（模板构建、上下文 user 块、占位符容错、关键词快照、自适应提示词）测试。"""

import os
import re
import tempfile
from pathlib import Path
from types import SimpleNamespace

from neobot_app.config.schemas.bot import BotConfig
from neobot_app.prompt.builder import PromptBuilder
from neobot_app.prompt.render import template_placeholders
from neobot_app.prompt.store import PromptStore, sync_default_prompts


class _FakeProfileService:
    """用户档案服务替身：各渲染方法返回固定文本，不触达真实存储/API。"""

    async def get_group_name(self, group_id):
        return "测试群名"

    async def render_group_member_list(
        self, group_id, message_queue, *, archive_fetch_window=None, include_archives=False
    ):
        self.last_include_archives = include_archives
        return "成员列表：小明、小红"

    async def render_bot_group_admin_status(self, group_id, bot_account, message_queue):
        return "你不是该群管理员"

    async def render_group_owner_text(self, group_id, message_queue):
        return "群主：老王（QQ：10086）"

    async def ensure_user_profile(self, user_id):
        return SimpleNamespace(nick_name="小明", remark="测试备注", profile="小明是个程序员")

    async def render_friend_info(self, user_id, *, profile=None):
        return "好友信息：小明"


class _FakeQueue:
    """消息队列替身：iterate_from_newest 可注入消息或抛 KeyError。"""

    def __init__(self, messages=None, *, to_text="消息记录：你好"):
        self._messages = messages or []
        self._to_text = to_text

    def to_text(self, key, last_reply_message_id=None, *, all_new=False):
        return self._to_text

    def iterate_from_newest(self, key):
        if not self._messages:
            raise KeyError(key)
        for message in reversed(self._messages):
            yield message


def _text_message(text: str) -> SimpleNamespace:
    """构造包含单条 text 片段的伪消息对象。"""
    return SimpleNamespace(
        message=[SimpleNamespace(type="text", data={"text": text})]
    )


def _make_builder(template: str, *, friend_template: str | None = None, **kwargs) -> PromptBuilder:
    """构建带自定义模板的 PromptBuilder（模板写入临时 custom 提示词文件）。"""
    config = BotConfig()
    config.bot.nick_name = "小测试"
    config.bot.account = 10001
    config.bot.alias_name = ["测试", "  ", "T"]
    config.chat.group_description = {"123456": "测试群描述"}
    tmp = Path(tempfile.mkdtemp())
    sync_default_prompts(tmp)
    custom = tmp / "prompts" / "custom" / "prompts.toml"
    custom.write_text(
        '[group_chat]\ntemplate = """\n{group}\n"""\n'
        '[friend_chat]\ntemplate = """\n{friend}\n"""\n'.format(
            group=template, friend=friend_template or template
        ),
        encoding="utf-8",
    )
    store = PromptStore(tmp)
    return PromptBuilder(
        config, _FakeProfileService(), prompt_store=store, **kwargs
    )


def _write_custom(tmp: Path, text: str) -> PromptStore:
    """把自定义提示词写入临时目录并返回 store。"""
    custom = tmp / "prompts" / "custom" / "prompts.toml"
    custom.write_text(text, encoding="utf-8")
    return PromptStore(tmp)


async def test_build_group_prompt_renders_all_template_placeholders():
    """群聊模板所有内置占位符必须替换为对应真实值，别名与群描述正确拼接。"""
    # Arrange
    builder = _make_builder(
        "你好{bot_name}（{bot_account}）{group_name}（{group_id}）{other_name}"
        "|{group_description}|{current_time}|{member_list}|{bot_group_admin_status}"
    )

    # Act
    prompt = await builder.build_group_chat_prompt(123456, _FakeQueue())

    # Assert
    assert "你好小测试（10001）测试群名（123456）" in prompt
    assert "也有人叫你测试、T" in prompt
    assert "测试群描述" in prompt
    assert "现在的时间是" in prompt
    assert "成员列表：小明、小红" in prompt
    assert "你不是该群管理员" in prompt


async def test_group_context_block_carries_content_missing_from_system_template():
    """system 模板未使用的上下文内容必须进入 group_context user 块，而不是被丢弃。"""
    # Arrange
    builder = _make_builder("你好{bot_name}")
    builder._config.chat.key_word = [
        {
            "enabled": True,
            "keywords": ["妈妈"],
            "prompt_list": ["你可以反问对方是不是叫夏亚"],
            "ignore_case": True,
            "match_mode": "any",
            "min_depth": -1,
            "max_depth": -1,
        }
    ]
    queue = _FakeQueue(messages=[_text_message("妈妈在吗")])
    builder = PromptBuilder(builder._config, _FakeProfileService(), prompt_store=builder._store)
    blocks: list[dict[str, str]] = []

    # Act
    prompt = await builder.build_group_chat_prompt(
        123456, queue, context_blocks=blocks
    )

    # Assert
    assert "群主：老王（QQ：10086）" not in prompt
    assert "你可以反问对方是不是叫夏亚" not in prompt
    assert len(blocks) == 1
    assert blocks[0]["role"] == "user"
    context_text = blocks[0]["content"]
    assert "群主：老王（QQ：10086）" in context_text
    assert "你可以反问对方是不是叫夏亚" in context_text


async def test_group_context_block_carries_memory_list():
    """传入的记忆片段必须出现在 group_context user 块中。"""
    # Arrange
    builder = _make_builder("你好{bot_name}")
    blocks: list[dict[str, str]] = []

    # Act
    await builder.build_group_chat_prompt(
        123456, _FakeQueue(), memory_list="记忆：小明生日是明天", context_blocks=blocks
    )

    # Assert
    assert "小明生日是明天" in "\n".join(block["content"] for block in blocks)


async def test_group_context_block_dedups_placeholders_used_in_system_template():
    """system 模板已渲染的成员列表不得在上下文块中重复出现。"""
    # Arrange
    builder = _make_builder("你好{bot_name}|{member_list}")
    blocks: list[dict[str, str]] = []

    # Act
    prompt = await builder.build_group_chat_prompt(
        123456, _FakeQueue(), context_blocks=blocks
    )

    # Assert
    assert "成员列表：小明、小红" in prompt
    assert "成员列表：小明、小红" not in "\n".join(
        block["content"] for block in blocks
    )


async def test_group_context_block_can_be_disabled(tmp_path):
    """[group_context] 写 enabled = false 后不再追加上下文 user 块。"""
    # Arrange
    sync_default_prompts(tmp_path)
    store = _write_custom(tmp_path, "[group_context]\nenabled = false\n")
    builder = PromptBuilder(BotConfig(), _FakeProfileService(), prompt_store=store)
    blocks: list[dict[str, str]] = []

    # Act
    await builder.build_group_chat_prompt(123456, _FakeQueue(), context_blocks=blocks)

    # Assert
    assert blocks == []


async def test_group_prompt_omits_member_archives_and_hints_on_demand_read():
    """群聊默认只注入群档案：不注入群员档案，并给出按需读取引导。"""
    # Arrange
    builder = _make_builder("你好{bot_name}|{member_list}")

    # Act
    prompt = await builder.build_group_chat_prompt(123456, _FakeQueue())

    # Assert
    assert builder._profile_service.last_include_archives is False
    assert "群友记忆" in prompt
    assert "archive_crud__read_archive" in prompt
    assert "user_summary" in prompt and "user_profile" in prompt


async def test_group_prompt_injects_member_archives_when_configured():
    """inject_member_archives=True 时恢复旧行为：注入群员档案且不加按需读取引导。"""
    # Arrange
    builder = _make_builder("你好{bot_name}|{member_list}")
    builder._config.chat.inject_member_archives = True

    # Act
    prompt = await builder.build_group_chat_prompt(123456, _FakeQueue())

    # Assert
    assert builder._profile_service.last_include_archives is True
    assert "群友记忆" not in prompt


async def test_build_group_prompt_tolerates_unknown_placeholder():
    """模板包含未知占位符时不得抛异常，未知占位符应原样保留或忽略。"""
    # Arrange
    builder = _make_builder("你好{bot_name} {custom_placeholder}")

    # Act
    prompt = await builder.build_group_chat_prompt(123456, _FakeQueue())

    # Assert
    assert "你好小测试" in prompt


async def test_escaped_braces_render_as_literal_braces():
    """模板中的双花括号必须渲染成字面量花括号，供模型看到真实的格式示例。"""
    # Arrange
    builder = _make_builder("示例:{{msg_id=123}} 1: 小明: 你好|{bot_name}")

    # Act
    prompt = await builder.build_group_chat_prompt(123456, _FakeQueue())

    # Assert
    assert "示例:{msg_id=123} 1: 小明: 你好|小测试" in prompt


async def test_empty_tag_blocks_are_removed_from_rendered_prompt():
    """只含空白的区块渲染后必须被删除，避免可选区块留下空壳。"""
    # Arrange
    builder = _make_builder(
        "你好{bot_name}\n<群友信息>\n{member_list}\n</群友信息>\n"
        "<你的印象>\n{memory_list}\n</你的印象>"
    )

    # Act
    prompt = await builder.build_group_chat_prompt(123456, _FakeQueue())

    # Assert
    assert "<你的印象>" not in prompt
    assert "<群友信息>" in prompt


async def test_build_friend_prompt_renders_and_appends_memory_and_private_tips():
    """私聊模板必须渲染好友信息，记忆片段进入 friend_context 块，私聊提示仍在 system 尾部。"""
    # Arrange
    builder = _make_builder(
        "你好{bot_name}（{friend_name}）{remark} {profile} {friend_info}"
    )
    blocks: list[dict[str, str]] = []

    # Act
    prompt = await builder.build_friend_chat_prompt(
        10086, _FakeQueue(), memory_list="小明生日是明天", context_blocks=blocks
    )

    # Assert
    assert "你好小测试（小明）测试备注" in prompt
    assert "小明是个程序员" in prompt
    assert "好友信息：小明" in prompt
    assert "<私聊提示>" in prompt
    assert "小明生日是明天" in "\n".join(block["content"] for block in blocks)


async def test_friend_context_block_can_be_disabled_and_hint_removed(tmp_path):
    """[friend_context] / [friend_chat_hint] 均可通过 enabled = false 关闭。"""
    # Arrange
    sync_default_prompts(tmp_path)
    store = _write_custom(
        tmp_path,
        "[friend_context]\nenabled = false\n[friend_chat_hint]\nenabled = false\n",
    )
    builder = PromptBuilder(BotConfig(), _FakeProfileService(), prompt_store=store)
    blocks: list[dict[str, str]] = []

    # Act
    prompt = await builder.build_friend_chat_prompt(
        10086, _FakeQueue(), context_blocks=blocks
    )

    # Assert
    assert blocks == []
    assert "<私聊提示>" not in prompt


async def test_current_time_block_is_rendered_before_reply():
    """回复前的 <当前时间> user 块必须来自 [current_time] 模板并带真实时间。"""
    # Arrange
    builder = _make_builder("你好{bot_name}")

    # Act
    block = builder.build_current_time_message()

    # Assert
    assert block is not None
    assert block["role"] == "user"
    assert "<当前时间>" in block["content"]
    assert "现在的时间是" in block["content"]


async def test_current_time_block_respects_custom_template_and_disable(tmp_path):
    """自定义 [current_time] 模板生效，enabled = false 时不产生时间块。"""
    # Arrange
    sync_default_prompts(tmp_path)
    store = _write_custom(
        tmp_path,
        '[current_time]\ntemplate = "现在是{current_datetime}（{current_weekday}）"\n',
    )
    builder = PromptBuilder(BotConfig(), _FakeProfileService(), prompt_store=store)

    # Act
    block = builder.build_current_time_message()

    # Assert
    assert block is not None
    assert block["content"].startswith("现在是")
    assert "星期" in block["content"]

    disabled_store = _write_custom(tmp_path, "[current_time]\nenabled = false\n")
    disabled_builder = PromptBuilder(
        BotConfig(), _FakeProfileService(), prompt_store=disabled_store
    )
    assert disabled_builder.build_current_time_message() is None


async def test_new_member_profiles_and_resume_text_use_templates():
    """新群友档案与挂起恢复说明必须走 [new_member_profiles] / [group_chat_resume]。"""
    # Arrange
    builder = _make_builder("你好{bot_name}")

    # Act
    profiles = builder.build_new_member_profiles_text("小明：程序员")
    resume = builder.build_group_chat_resume_text(new_member_profiles=profiles)

    # Assert
    assert "[新出现的群友档案]" in profiles
    assert "小明：程序员" in profiles
    assert "小明：程序员" in resume
    assert "续接" in resume


async def test_keyword_rules_snapshot_survives_config_replacement():
    """构建时配置的关键词规则必须作为快照保留，替换 config 后仍按旧规则触发。"""
    # Arrange
    builder = _make_builder("你好{bot_name} {key_word_reaction_list}")
    builder._config.chat.key_word = [
        {
            "enabled": True,
            "keywords": ["妈妈"],
            "prompt_list": ["你可以反问对方是不是叫夏亚"],
            "ignore_case": True,
            "match_mode": "any",
            "min_depth": -1,
            "max_depth": -1,
        }
    ]
    queue = _FakeQueue(messages=[_text_message("妈妈在吗")])
    builder = PromptBuilder(builder._config, _FakeProfileService(), prompt_store=builder._store)

    # Act
    first_prompt = await builder.build_group_chat_prompt(123456, queue)
    builder._config.chat.key_word = []
    second_prompt = await builder.build_group_chat_prompt(123456, queue)

    # Assert
    assert "你可以反问对方是不是叫夏亚" in first_prompt
    assert "你可以反问对方是不是叫夏亚" in second_prompt


async def test_keyword_rules_disabled_or_no_match_produce_no_reaction():
    """禁用或未命中的关键词规则不得产生任何追加信息片段。"""
    # Arrange
    builder = _make_builder("你好{bot_name} {key_word_reaction_list}")
    builder._config.chat.key_word = [
        {
            "enabled": False,
            "keywords": ["妈妈"],
            "prompt_list": ["禁用规则不触发"],
            "ignore_case": True,
            "match_mode": "any",
            "min_depth": -1,
            "max_depth": -1,
        }
    ]
    queue = _FakeQueue(messages=[_text_message("妈妈在吗")])
    builder = PromptBuilder(builder._config, _FakeProfileService(), prompt_store=builder._store)
    blocks: list[dict[str, str]] = []

    # Act
    prompt = await builder.build_group_chat_prompt(123456, queue, context_blocks=blocks)

    # Assert
    assert "禁用规则不触发" not in prompt
    assert "禁用规则不触发" not in "\n".join(block["content"] for block in blocks)
    assert "追加信息" not in prompt


async def test_adaptive_prompt_loading_and_mtime_cache(tmp_path):
    """自适应提示词必须按 mtime(ns) 缓存：同 mtime 不重读，文件更新后才刷新。"""
    # Arrange
    adaptive_path = tmp_path / "adaptive.txt"
    adaptive_path.write_text("自适应记忆A", encoding="utf-8")
    builder = _make_builder("你好{bot_name}", adaptive_prompt_path=adaptive_path)

    # Act
    first_prompt = await builder.build_group_chat_prompt(123456, _FakeQueue())
    same_mtime_ns = adaptive_path.stat().st_mtime_ns
    adaptive_path.write_text("自适应记忆B", encoding="utf-8")
    os.utime(adaptive_path, ns=(same_mtime_ns, same_mtime_ns))
    second_prompt = await builder.build_group_chat_prompt(123456, _FakeQueue())
    os.utime(adaptive_path, ns=(same_mtime_ns + 10**9, same_mtime_ns + 10**9))
    third_prompt = await builder.build_group_chat_prompt(123456, _FakeQueue())

    # Assert
    assert "<自适应提示词>" in first_prompt
    assert "自适应记忆A" in first_prompt
    assert "自适应记忆B" not in second_prompt
    assert "自适应记忆B" in third_prompt


async def test_adaptive_prompt_ignored_when_path_absent_or_missing(tmp_path):
    """未配置路径或文件不存在时，提示词不得包含自适应提示词片段。"""
    # Arrange
    no_path_builder = _make_builder("你好{bot_name}")
    missing_path_builder = _make_builder(
        "你好{bot_name}", adaptive_prompt_path=tmp_path / "nope.txt"
    )

    # Act
    no_path_prompt = await no_path_builder.build_group_chat_prompt(123456, _FakeQueue())
    missing_path_prompt = await missing_path_builder.build_group_chat_prompt(
        123456, _FakeQueue()
    )

    # Assert
    assert "<自适应提示词>" not in no_path_prompt
    assert "<自适应提示词>" not in missing_path_prompt


async def test_default_templates_keep_message_format_rules():
    """内置默认模板必须保留编号格式说明，且不再引用聊天记录占位符。"""
    # Arrange
    tmp = Path(tempfile.mkdtemp())
    sync_default_prompts(tmp)
    store = PromptStore(tmp)

    # Act / Assert
    assert "{message_list}" not in store.template("group_chat")
    assert "{message_list}" not in store.template("friend_chat")
    assert "{numbering_guide}" in store.template("group_chat")
    assert "{numbering_guide}" in store.template("friend_chat")
    # 聊天记录/上下文不再内嵌 system:成员列表与当前时间由独立 user 块承载
    assert "{member_list}" not in store.template("group_chat")
    assert "{member_list}" in store.template("group_context")
    assert "{current_time}" in store.template("current_time")


async def test_default_templates_carry_history_consistency_rules():
    """默认主提示词必须包含"不重复回答/不忽略自己之前的话/系统标注"三条规则。"""
    tmp = Path(tempfile.mkdtemp())
    sync_default_prompts(tmp)
    store = PromptStore(tmp)

    for section in ("group_chat", "friend_chat"):
        template = store.template(section)
        assert "已经回答过" in template
        assert "忽略自己之前说过的话" in template
        assert "使用 reply 工具引用回复" in template
        assert "[msg_id=" in template


async def test_current_time_section_is_renderable_and_documented():
    """[current_time] 分区必须存在且带完整格式说明。"""
    tmp = Path(tempfile.mkdtemp())
    sync_default_prompts(tmp)
    store = PromptStore(tmp)

    template = store.template("current_time")
    assert "{current_time}" in template


async def test_custom_prompt_partial_override_inherits_defaults():
    """自定义提示词只覆盖部分分区/键时，其余自动继承默认值（跨版本升级兼容）。"""
    # Arrange
    tmp = Path(tempfile.mkdtemp())
    sync_default_prompts(tmp)
    custom = tmp / "prompts" / "custom" / "prompts.toml"
    custom.write_text(
        '[group_chat]\ntemplate = """只改群聊模板"""\n', encoding="utf-8"
    )
    store = PromptStore(tmp)

    # Assert
    assert store.template("group_chat") == "只改群聊模板"
    assert store.template("friend_chat").startswith("<你是谁>")
    assert "problem-solving agent" in store.get("problem_solver", "system_prompt")
    assert store.template("long_reply_fallback")
    # 同步默认提示词不得覆盖自定义内容
    sync_default_prompts(tmp)
    store.reload()
    assert store.template("group_chat") == "只改群聊模板"


async def test_store_enabled_flag_parses_booleans_and_strings(tmp_path):
    """enabled 支持布尔与常见字符串写法，无法解析时按启用处理并告警。"""
    sync_default_prompts(tmp_path)
    store = _write_custom(
        tmp_path,
        "[current_time]\nenabled = false\n"
        '[group_context]\nenabled = "否"\n'
        '[friend_context]\nenabled = true\n',
    )

    assert store.enabled("current_time") is False
    assert store.enabled("group_context") is False
    assert store.enabled("friend_context") is True
    assert store.enabled("not_a_section") is True


async def test_get_template_value_falls_back_to_builtin_templates():
    """文件缺失时 get_template_value 必须回退到内置兜底模板而不是空串。"""
    from neobot_app.prompt.store import get_template_value

    assert "当前时间" in get_template_value(None, "current_time")
    assert "member_profiles" in get_template_value(None, "new_member_profiles")
    assert "已压缩" in get_template_value(None, "tool_result_compressed")
    assert get_template_value(None, "tool_result_compressed_detail")
    assert "tool_name" in get_template_value(None, "tool_result_compressed_detail")


# ── §12–§15:新增提示词分区与基础提示词引导 ────────────────────────────────────

LONG_TASK_MARKER = "<长任务回复>"
#: [avoid_repeat] / [silent_nudge] 的定稿文本(与 description.md §14.2 逐字一致)
AVOID_REPEAT_TEXT = (
    "不要重复执行已经完成过的工作,不要反复回答已经回答过的话,"
    "已经开始做但没有做完的,在没有人询问的情况下不需要再次告知已经开始工作."
)
SILENT_NUDGE_TEXT = (
    "[系统提示] 请检查是否有必要使用回复工具告知其他人你的工作进度."
    "不使用send_reply的情况下他们不知道你做了什么."
)
#: 基础 <回复要求> 里新增的「适时回话」原则
TIMELY_REPLY_PRINCIPLE = "需要时间的事情要适时回话"


def _default_store(tmp: Path) -> PromptStore:
    """同步内置默认提示词后的 store(只读断言用)。"""
    sync_default_prompts(tmp)
    return PromptStore(tmp)


async def test_long_task_progress_appended_to_group_and_friend_prompts():
    """群聊与私聊 system 都要追加 <长任务回复>:追加逻辑在 builder 层。"""
    builder = _make_builder("你好{bot_name}")

    group_prompt = await builder.build_group_chat_prompt(123456, _FakeQueue())
    friend_prompt = await builder.build_friend_chat_prompt(10086, _FakeQueue())

    assert LONG_TASK_MARKER in group_prompt
    assert "先用 send_reply 简短说一句你要开始做" in group_prompt
    assert LONG_TASK_MARKER in friend_prompt
    assert friend_prompt.index(LONG_TASK_MARKER) > friend_prompt.index("你好小测试")


async def test_long_task_progress_can_be_disabled(tmp_path):
    """[long_task_progress] enabled = false 后群聊/私聊都不再追加。"""
    sync_default_prompts(tmp_path)
    store = _write_custom(tmp_path, "[long_task_progress]\nenabled = false\n")
    builder = PromptBuilder(BotConfig(), _FakeProfileService(), prompt_store=store)

    group_prompt = await builder.build_group_chat_prompt(123456, _FakeQueue())
    friend_prompt = await builder.build_friend_chat_prompt(10086, _FakeQueue())

    assert LONG_TASK_MARKER not in group_prompt
    assert LONG_TASK_MARKER not in friend_prompt


async def test_long_task_progress_survives_custom_group_chat_override(tmp_path):
    """部署方整段覆盖 [group_chat] 后 <长任务回复> 仍生效(守住 DL1-1 的核心优势)。"""
    sync_default_prompts(tmp_path)
    store = _write_custom(
        tmp_path, '[group_chat]\ntemplate = """自定义群聊模板{bot_name}"""\n'
    )
    builder = PromptBuilder(BotConfig(), _FakeProfileService(), prompt_store=store)

    prompt = await builder.build_group_chat_prompt(123456, _FakeQueue())

    assert "自定义群聊模板" in prompt
    assert LONG_TASK_MARKER in prompt


def test_new_prompt_sections_match_finalized_text(tmp_path):
    """新增分区必须存在、默认启用、文本与定稿逐字一致且无占位符。"""
    store = _default_store(tmp_path)

    assert store.template("avoid_repeat") == AVOID_REPEAT_TEXT
    assert store.template("silent_nudge") == SILENT_NUDGE_TEXT
    assert template_placeholders(store.template("avoid_repeat")) == set()
    assert template_placeholders(store.template("silent_nudge")) == set()
    assert template_placeholders(store.template("long_task_progress")) == set()
    assert "{current_datetime}" in store.template("current_time_short")

    for key in ("long_task_progress", "avoid_repeat", "silent_nudge", "current_time_short"):
        assert store.enabled(key) is True


def test_reply_requirements_get_timely_reply_principle(tmp_path):
    """[group_chat] / [friend_chat] 的 <回复要求> 补「适时回话」,并把成功通知限定为收尾后。"""
    store = _default_store(tmp_path)

    for section in ("group_chat", "friend_chat"):
        template = store.template(section)
        assert TIMELY_REPLY_PRINCIPLE in template
        assert "任务收尾后" in template
        assert "这类开工与进度的回复不算多余回复" in template


def test_build_short_time_message_renders_timestamp_only():
    """build_short_time_message 只渲染 YYYY-MM-DD HH:MM:SS,不带完整时间描述。"""
    builder = _make_builder("你好{bot_name}")

    block = builder.build_short_time_message()

    assert block is not None
    assert block["role"] == "user"
    assert re.fullmatch(
        r"<当前时间>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}</当前时间>",
        block["content"],
    ), block["content"]
    assert "现在的时间是" not in block["content"]
    assert "农历" not in block["content"]


def test_build_short_time_message_can_be_disabled(tmp_path):
    """[current_time_short] enabled = false 时不再产生短时间戳块。"""
    sync_default_prompts(tmp_path)
    store = _write_custom(tmp_path, "[current_time_short]\nenabled = false\n")
    builder = PromptBuilder(BotConfig(), _FakeProfileService(), prompt_store=store)

    assert builder.build_short_time_message() is None
    # 完整时间块不受影响
    assert builder.build_current_time_message() is not None

