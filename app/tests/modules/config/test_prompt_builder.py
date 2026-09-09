"""prompt/builder 模块（模板构建、占位符容错、关键词快照、自适应提示词、角色消息）测试。"""

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

from neobot_app.config.schemas.bot import BotConfig
from neobot_app.prompt.builder import PromptBuilder
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
    """消息队列替身：to_text 返回固定文本，iterate_from_newest 可注入消息或抛 KeyError。"""

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


def _make_builder(template: str, **kwargs) -> PromptBuilder:
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
        '[group_chat]\ntemplate = """\n{template}\n"""\n[friend_chat]\ntemplate = """\n{template}\n"""\n'.format(
            template=template
        ),
        encoding="utf-8",
    )
    store = PromptStore(tmp)
    return PromptBuilder(
        config, _FakeProfileService(), prompt_store=store, **kwargs
    )


async def test_build_group_prompt_renders_all_template_placeholders():
    """群聊模板所有内置占位符必须替换为对应真实值，别名与群描述正确拼接。"""
    # Arrange
    builder = _make_builder(
        "你好{bot_name}（{bot_account}）{group_name}（{group_id}）{other_name}"
        "|{group_description}|{current_time}|{member_list}"
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


async def test_build_group_prompt_appends_extra_fragments_when_placeholders_missing():
    """模板缺少 group_admin/key_word_reaction_list 占位符时，对应片段必须追加到尾部而非丢弃。"""
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

    # Act
    prompt = await builder.build_group_chat_prompt(123456, queue)

    # Assert
    assert "群主：老王（QQ：10086）" in prompt
    assert "你可以反问对方是不是叫夏亚" in prompt


async def test_build_group_prompt_appends_memory_list_without_placeholder():
    """群聊模板缺少 {memory_list} 占位符时，传入的记忆片段必须追加到提示词（与私聊行为一致）。"""
    # Arrange
    builder = _make_builder("你好{bot_name}")

    # Act
    prompt = await builder.build_group_chat_prompt(
        123456, _FakeQueue(), memory_list="记忆：小明生日是明天"
    )

    # Assert
    assert "小明生日是明天" in prompt


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


async def test_build_friend_prompt_renders_and_appends_memory_and_private_tips():
    """私聊模板必须渲染好友信息，且记忆片段与私聊提示被追加到提示词尾部。"""
    # Arrange
    builder = _make_builder(
        "你好{bot_name}（{friend_name}）{remark} {profile} {friend_info}"
    )

    # Act
    prompt = await builder.build_friend_chat_prompt(
        10086, _FakeQueue(), memory_list="小明生日是明天"
    )

    # Assert
    assert "你好小测试（小明）测试备注" in prompt
    assert "小明是个程序员" in prompt
    assert "好友信息：小明" in prompt
    assert "小明生日是明天" in prompt
    assert "<私聊提示>" in prompt


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

    # Act
    prompt = await builder.build_group_chat_prompt(123456, queue)

    # Assert
    assert "禁用规则不触发" not in prompt
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


async def test_default_templates_have_no_conversation_placeholder():
    """内置默认模板必须不再引用 {message_list}（聊天记录已拆分为角色消息）。"""
    # Arrange
    tmp = Path(tempfile.mkdtemp())
    sync_default_prompts(tmp)
    store = PromptStore(tmp)

    # Act / Assert
    assert "{message_list}" not in store.template("group_chat")
    assert "{message_list}" not in store.template("friend_chat")
    assert "{numbering_guide}" in store.template("group_chat")
    assert "{numbering_guide}" in store.template("friend_chat")


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
    assert "解题 Agent" in store.get("problem_solver", "system_prompt")
    assert store.template("long_reply_fallback")
    # 同步默认提示词不得覆盖自定义内容
    sync_default_prompts(tmp)
    store.reload()
    assert store.template("group_chat") == "只改群聊模板"
