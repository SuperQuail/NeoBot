"""提示词里 QQ 号的可见性回归：群聊 / 增量新成员 / 私聊。

本文件只锁定现状，不改产品代码。结论（HEAD dbb97549，refactor/prompt-composer）：

1. 群聊正常回复：
   - ``UserProfileService.render_group_member_list`` 对每个成员调用
     ``_format_group_member_line``，在 ``user_profiles.py:768`` 拼出 ``QQ号:{user_id}``。
   - 默认模板没有把 ``{member_list}`` 写进 ``[group_chat]``，它出现在
     ``[group_context]`` 的 ``<群友信息>`` user 块（system 之后、聊天记录之前），
     模型仍然可见；自定义模板把 ``{member_list}`` 写进 ``[group_chat]`` 时同一内容进 system。
   - ``chat.inject_member_archives`` 只控制是否附带群员档案（默认 False）。
     关闭时成员列表与 QQ 号照常注入，只是档案改成 archive_crud__read_archive 按需读取提示。
2. 增量：``render_specific_members`` 复用同一个 ``_format_group_member_line``，
   所以 ``[新出现的群友档案]`` 块含 ``QQ号:``。
3. 私聊：``[friend_context]`` 的 ``{friend_info}`` 来自 ``render_friend_info`` ->
   ``_format_friend_info_line``（``user_profiles.py:814`` 的 ``QQ号:{user_id}``），
   默认模板下对方 QQ 可见；私聊消息行本身只写昵称，不写 QQ 号。
4. 不可见场景：群成员列表为空（消息队列没有该群消息且 get_group_member_list
   返回空）。此时没有 ``<群友信息>`` 块，聊天记录行只有昵称，QQ 号不可见。
   私聊不依赖成员列表，普通私聊仍有 QQ。
   注：get_group_member_list 抛异常时 render_group_member_list 会吞掉异常并跳过成员列表，
   不会把整轮提示词构建带崩（见下方回归用例）。

窗口限制：``render_group_member_list`` 只取最近 ``chat.archive_fetch_window``
（默认 20）条加权消息的发送者；窗口外的人不会出现在名单里。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from neobot_app.config.schemas.bot import BotConfig
from neobot_app.prompt.builder import PromptBuilder
from neobot_app.prompt.store import PromptStore
from neobot_app.user_profiles import UserProfileService

GROUP_ID = 100
USER_ID = 20001


class _FakeRepo:
    """内存版 profiles 仓库：只实现提示词渲染会用到的读/写。"""

    def __init__(self) -> None:
        self.users: dict[str, dict[str, Any]] = {}

    async def get_user(self, user_id: str) -> SimpleNamespace | None:
        record = self.users.get(str(user_id))
        return SimpleNamespace(**record) if record else None

    async def get_group(self, group_id: str) -> None:
        return None

    async def upsert_user(self, user_id: str, **fields: Any) -> None:
        record = self.users.setdefault(str(user_id), {})
        record.update({key: value for key, value in fields.items() if value is not None})


class _FakeUoW:
    def __init__(self, repo: _FakeRepo) -> None:
        self.profiles = repo

    async def __aenter__(self) -> "_FakeUoW":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    async def commit(self) -> None:
        return None


class _FakeAdapter:
    """OneBot 适配器替身：get_group_member_list 返回固定成员或空列表。"""

    def __init__(self, members: list[SimpleNamespace] | None = None) -> None:
        self._members = members

    async def get_stranger_info(self, user_id: int) -> SimpleNamespace:
        return SimpleNamespace(data=None)

    async def get_group_member_list(self, group_id: int) -> SimpleNamespace:
        return SimpleNamespace(data=self._members)

    async def get_group_member_info(self, group_id: int, user_id: int) -> SimpleNamespace:
        return SimpleNamespace(data=None)


class _FailingAdapter(_FakeAdapter):
    """get_group_member_list 直接抛异常，模拟 OneBot API 失败。"""

    async def get_group_member_list(self, group_id: int) -> SimpleNamespace:
        raise RuntimeError("get_group_member_list failed")


class _Archive:
    """个人长期记忆替身：任何用户都返回一段可识别的档案。"""

    async def get(self, table_name: str, key: str) -> SimpleNamespace:
        return SimpleNamespace(value=f"{key} 的长期记忆")


class _FakeQueue(dict):
    """消息队列替身：群成员列表走 dict 索引，关键词规则走 iterate_from_newest。"""

    def iterate_from_newest(self, key: str) -> None:
        raise KeyError(key)

    def to_text(self, key: str, last_reply_message_id: int | None = None, *, all_new: bool = False) -> str:
        return "消息记录：你好"


def _service(adapter: _FakeAdapter) -> UserProfileService:
    config = SimpleNamespace(
        chat=SimpleNamespace(
            enable_periodic_user_info_update=False,
            user_info_update_interval_days=7,
        )
    )
    repo = _FakeRepo()
    return UserProfileService(adapter=adapter, uow_factory=lambda: _FakeUoW(repo), config=config)


def _member(user_id: int = USER_ID, nickname: str = "小明") -> SimpleNamespace:
    return SimpleNamespace(user_id=user_id, nickname=nickname, card=None, sex=None, role="member")


def _message(user_id: int = USER_ID, nickname: str = "小明") -> SimpleNamespace:
    return SimpleNamespace(user_id=user_id, sender=_member(user_id, nickname))


def _group_queue() -> _FakeQueue:
    queue = _FakeQueue()
    queue[str(GROUP_ID)] = [_message()]
    return queue


def _visible_text(system: str, blocks: list[dict[str, str]]) -> str:
    return "\n".join([system, *(block["content"] for block in blocks)])


# ── 群聊：默认成员列表进 [group_context]，档案开关不影响 QQ ──────────────────


async def test_group_context_keeps_qq_when_member_archives_disabled(
    prompt_store: PromptStore, bot_config: BotConfig
) -> None:
    """默认 inject_member_archives=False：成员列表仍注入 [group_context]，含 QQ号:20001。

    证据：builder.py:167 调用 render_group_member_list；user_profiles.py:768 拼 QQ 号；
    builder.py:173-174 只在成员列表非空时追加按需读取档案的提示。
    """
    service = _service(_FakeAdapter([_member()]))
    service._archive_memory_service = _Archive()
    builder = PromptBuilder(bot_config, service, prompt_store=prompt_store)
    blocks: list[dict[str, str]] = []

    system = await builder.build_group_chat_prompt(GROUP_ID, _group_queue(), context_blocks=blocks)
    visible = _visible_text(system, blocks)

    assert bot_config.chat.inject_member_archives is False
    assert "<群友信息>" in visible
    assert "QQ号:20001" in visible
    # 默认 [group_chat] 不消费 {member_list}，所以 QQ 不在 system，而在上下文 user 块
    assert "QQ号:20001" not in system
    # 档案本身没有注入，只有按需读取提示
    assert "你记得关于Ta的信息" not in visible
    assert "archive_crud__read_archive" in visible


async def test_group_context_keeps_qq_when_member_archives_enabled(
    prompt_store: PromptStore, bot_config: BotConfig
) -> None:
    """inject_member_archives=True 只是多注入档案，成员列表与 QQ号:20001 仍在。"""
    bot_config.chat.inject_member_archives = True
    service = _service(_FakeAdapter([_member()]))
    service._archive_memory_service = _Archive()
    builder = PromptBuilder(bot_config, service, prompt_store=prompt_store)
    blocks: list[dict[str, str]] = []

    system = await builder.build_group_chat_prompt(GROUP_ID, _group_queue(), context_blocks=blocks)
    visible = _visible_text(system, blocks)

    assert "QQ号:20001" in visible
    assert "你记得关于Ta的信息:20001 的长期记忆" in visible


async def test_group_system_prompt_carries_qq_when_template_uses_member_list(
    custom_store: Any, bot_config: BotConfig
) -> None:
    """把 {member_list} 写进 [group_chat] 时，QQ号:20001 直接进 system 提示词。"""
    store = custom_store('[group_chat]\ntemplate = """<群友信息>\n{member_list}\n</群友信息>"""\n')
    builder = PromptBuilder(bot_config, _service(_FakeAdapter([_member()])), prompt_store=store)

    system = await builder.build_group_chat_prompt(GROUP_ID, _group_queue())

    assert "<群友信息>" in system
    assert "QQ号:20001" in system


# ── 增量：[新出现的群友档案] 含 QQ ─────────────────────────────────────────


async def test_new_member_profiles_block_carries_qq(
    prompt_store: PromptStore, bot_config: BotConfig
) -> None:
    """增量成员走 render_specific_members -> _format_group_member_line，含 QQ号:20001。"""
    service = _service(_FakeAdapter())
    builder = PromptBuilder(bot_config, service, prompt_store=prompt_store)

    profiles = await service.render_specific_members([str(USER_ID)])
    block = builder.build_new_member_profiles_text(
        profiles, group_name="测试群", group_id=str(GROUP_ID)
    )

    assert "QQ号:20001" in profiles
    assert "[新出现的群友档案]" in block
    assert "QQ号:20001" in block


# ── 私聊：friend_context 的 friend_info 含 QQ ─────────────────────────────


async def test_private_friend_context_carries_qq(
    prompt_store: PromptStore, bot_config: BotConfig
) -> None:
    """私聊默认模板下 [friend_context] 的 <对方信息> 含 QQ号:20001。

    证据：builder.py:264 调 render_friend_info；user_profiles.py:814 拼 QQ 号；
    prompts.toml 的 [friend_context] 用 {friend_info} 渲染 <对方信息>。
    私聊消息行本身只写昵称，QQ 号只来自这条上下文块。
    """
    builder = PromptBuilder(bot_config, _service(_FakeAdapter()), prompt_store=prompt_store)
    blocks: list[dict[str, str]] = []

    system = await builder.build_friend_chat_prompt(USER_ID, _FakeQueue(), context_blocks=blocks)
    visible = _visible_text(system, blocks)

    assert "<对方信息>" in visible
    assert "QQ号:20001" in visible
    # 默认 [friend_chat] 不消费 {friend_info}，QQ 不在 system
    assert "QQ号:20001" not in system


# ── 成员列表拿不到：群聊 QQ 不可见（当前唯一的数据缺失场景） ────────────────


async def test_group_qq_invisible_when_member_list_unavailable(
    prompt_store: PromptStore, bot_config: BotConfig
) -> None:
    """队列空 + get_group_member_list 返回空：没有 <群友信息>，QQ 号不可见。

    这是群聊唯一的「QQ 不可见」场景：消息行只写昵称（queue_parts/text.py:160-168），
    成员列表为空时没有别处提供 QQ。私聊不依赖成员列表，见上一条用例。
    注意：API 抛异常时 render_group_member_list 不兜底，会直接抛出提示词构建；
    本用例只覆盖「调用成功但返回空」的降级结果。
    """
    service = _service(_FakeAdapter(members=None))
    builder = PromptBuilder(bot_config, service, prompt_store=prompt_store)
    blocks: list[dict[str, str]] = []

    system = await builder.build_group_chat_prompt(GROUP_ID, _FakeQueue(), context_blocks=blocks)
    visible = _visible_text(system, blocks)

    assert "<群友信息>" not in visible
    assert "QQ号:20001" not in visible
    assert "QQ号:20001" not in system


async def test_group_member_list_api_failure_does_not_break_prompt(
    prompt_store: PromptStore, bot_config: BotConfig
) -> None:
    """成员列表 API 抛异常时只跳过成员信息，提示词构建仍成功（QQ 自然不可见）。"""
    service = _service(_FailingAdapter(members=None))
    builder = PromptBuilder(bot_config, service, prompt_store=prompt_store)
    blocks: list[dict[str, str]] = []

    system = await builder.build_group_chat_prompt(GROUP_ID, _FakeQueue(), context_blocks=blocks)
    visible = _visible_text(system, blocks)

    assert system  # 构建成功，没有被成员列表异常带崩
    assert "<群友信息>" not in visible
    assert "QQ号:20001" not in visible
