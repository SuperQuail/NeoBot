"""neobot_app.user_profiles UserProfileService 用户档案服务层测试。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

from neobot_app.user_profiles import UserProfileService


class _FakeProfilesRepo:
    """内存版 profiles 仓库：get_user / get_group / upsert_user。"""

    def __init__(self) -> None:
        self.users: dict[str, dict[str, Any]] = {}
        self.groups: dict[str, dict[str, Any]] = {}

    async def get_user(self, user_id: str) -> SimpleNamespace | None:
        record = self.users.get(str(user_id))
        return SimpleNamespace(**record) if record else None

    async def get_group(self, group_id: str) -> SimpleNamespace | None:
        record = self.groups.get(str(group_id))
        return SimpleNamespace(**record) if record else None

    async def upsert_user(self, user_id: str, **fields: Any) -> None:
        current = self.users.setdefault(str(user_id), {})
        for key, value in fields.items():
            if value is not None:
                current[key] = value


class _FakeUoW:
    """假工作单元：持有一个共享仓库并记录 commit 次数。"""

    def __init__(self, repo: _FakeProfilesRepo) -> None:
        self.profiles = repo
        self.committed = 0

    async def __aenter__(self) -> "_FakeUoW":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    async def commit(self) -> None:
        self.committed += 1


class _FakeAdapter:
    """假适配器：按需返回陌生人信息 / 群成员列表 / 成员信息。"""

    def __init__(self, stranger: Any = None, members: Any = None, member_info: Any = None) -> None:
        self._stranger = stranger
        self._members = members
        self._member_info = member_info
        self.calls: list[tuple[str, tuple]] = []

    async def get_stranger_info(self, user_id: int) -> SimpleNamespace:
        self.calls.append(("get_stranger_info", (user_id,)))
        return SimpleNamespace(data=self._stranger)

    async def get_group_member_list(self, group_id: int) -> SimpleNamespace:
        self.calls.append(("get_group_member_list", (group_id,)))
        return SimpleNamespace(data=self._members)

    async def get_group_member_info(self, group_id: int, user_id: int) -> SimpleNamespace:
        self.calls.append(("get_group_member_info", (group_id, user_id)))
        return SimpleNamespace(data=self._member_info)


def _make_service(repo: _FakeProfilesRepo, adapter: Any, *, periodic: bool = False) -> UserProfileService:
    """构造 UserProfileService：注入假仓库/适配器与最小配置。"""
    config = SimpleNamespace(
        chat=SimpleNamespace(
            enable_periodic_user_info_update=periodic,
            user_info_update_interval_days=7,
        )
    )
    return UserProfileService(
        adapter=adapter,
        uow_factory=lambda: _FakeUoW(repo),
        config=config,
    )


def _stranger_data() -> SimpleNamespace:
    return SimpleNamespace(
        nickname="小明",
        sex="male",
        age=18,
        city="广州",
        country="中国",
        long_nick="岁月静好",
        labs=["二次元", "音乐"],
        birthday_year=2006,
        birthday_month=5,
        birthday_day=20,
    )


async def test_ensure_user_profile_refreshes_and_persists_when_missing() -> None:
    """Arrange: 仓库无记录且适配器返回陌生人信息；Act: ensure_user_profile；Assert: 落库并返回昵称。"""
    repo = _FakeProfilesRepo()
    adapter = _FakeAdapter(stranger=_stranger_data())
    service = _make_service(repo, adapter)

    record = await service.ensure_user_profile("123456")

    assert record.nick_name == "小明"
    assert repo.users["123456"]["nick_name"] == "小明"
    assert repo.users["123456"]["sex"] == "male"
    assert repo.users["123456"]["birthday"] == "2006-5-20"
    assert repo.users["123456"]["labs"] == "二次元,音乐"
    assert record.fetched_at is not None


async def test_ensure_user_profile_merges_observed_fields_without_api_call() -> None:
    """Arrange: 已有档案（昵称为空）且周期刷新关闭；Act: 传入 observed_fields；Assert: 只合并不调 API。"""
    repo = _FakeProfilesRepo()
    fetched = datetime.now(timezone.utc) - timedelta(minutes=1)
    repo.users["123456"] = {"nick_name": "", "fetched_at": fetched}
    adapter = _FakeAdapter(stranger=_stranger_data())
    service = _make_service(repo, adapter)

    record = await service.ensure_user_profile(
        "123456",
        observed_fields={"nick_name": "小明", "sex": "male"},
    )

    assert record.nick_name == "小明"
    assert record.sex == "male"
    assert record.fetched_at == fetched
    assert adapter.calls == []


async def test_ensure_user_profile_refreshes_when_stale_periodic_enabled() -> None:
    """Arrange: 周期刷新开启且 fetched_at 超过 7 天；Act: ensure_user_profile；Assert: 触发 API 刷新。"""
    repo = _FakeProfilesRepo()
    repo.users["123456"] = {
        "nick_name": "旧昵称",
        "fetched_at": datetime.now(timezone.utc) - timedelta(days=10),
    }
    adapter = _FakeAdapter(stranger=_stranger_data())
    service = _make_service(repo, adapter, periodic=True)

    record = await service.ensure_user_profile("123456")

    assert adapter.calls == [("get_stranger_info", (123456,))]
    assert record.nick_name == "小明"


def test_build_user_fields_preserves_current_when_api_data_none() -> None:
    """Arrange: API data 为 None 且当前档案有非空字段；Act: _build_user_fields；Assert: 保留现状不丢数据。"""
    current = SimpleNamespace(
        relation_ship="单身",
        profile="安静的朋友",
        known_gender="男",
        birthday="2000-1-1",
        avatar_analysis="戴眼镜",
    )

    fields = UserProfileService._build_user_fields(None, current_profile=current)

    assert fields["relation_ship"] == "单身"
    assert fields["profile"] == "安静的朋友"
    assert fields["known_gender"] == "男"
    assert fields["birthday"] == "2000-1-1"
    assert fields["avatar_analysis"] == "戴眼镜"


def test_build_user_fields_api_value_takes_precedence_over_observed() -> None:
    """Arrange: API 与 observed 同时提供昵称；Act: _build_user_fields；Assert: API 值优先，观测值补缺。"""
    data = SimpleNamespace(nickname="API昵称", sex="female", age=25)
    observed = {"nick_name": "观测昵称", "sex": "male"}

    fields = UserProfileService._build_user_fields(data, observed_fields=observed)

    assert fields["nick_name"] == "API昵称"
    assert fields["sex"] == "female"


def test_build_user_fields_observed_fills_api_gaps() -> None:
    """Arrange: API 未返回昵称；Act: _build_user_fields；Assert: observed 值补上缺口。"""
    data = SimpleNamespace(nickname=None, sex="male", age=25)
    observed = {"nick_name": "观测昵称", "sex": "male"}

    fields = UserProfileService._build_user_fields(data, observed_fields=observed)

    assert fields["nick_name"] == "观测昵称"


def test_format_group_member_line_includes_profile_segments() -> None:
    """Arrange: 群成员带昵称/性别且档案含印象与头像记忆；Act: _format_group_member_line；Assert: 输出完整段落。"""
    member = SimpleNamespace(
        user_id=10001,
        nickname="群友A",
        card="卡片A",
        sex="male",
        role="member",
    )
    profile = SimpleNamespace(
        nick_name="群友A",
        remark="同事",
        profile="靠谱的人",
        avatar_analysis="头像是一只猫",
        favorability=30,
    )

    line = UserProfileService._format_group_member_line(1, member, profile)

    assert line.startswith("<群友_1>")
    assert "昵称:群友A" in line
    assert "你对Ta的备注:同事" in line
    assert "群昵称:卡片A" in line
    assert "QQ号:10001" in line
    assert "QQ登记的性别:男" in line
    assert "你对Ta的印象:靠谱的人" in line
    assert "头像记忆:头像是一只猫" in line
    assert "好感度:" in line
    assert line.endswith("</群友_1>")


async def test_collect_group_members_from_queue_full_scan_dedupes() -> None:
    """Arrange: 队列含同一用户多条消息且后续补充昵称；Act: 全量扫描；Assert: 去重且信息最全。"""
    class _Sender:
        def __init__(self, nickname: str | None = None, card: str | None = None,
                     sex: str | None = None, role: str | None = None) -> None:
            self.nickname = nickname
            self.card = card
            self.sex = sex
            self.role = role

    class _Message:
        def __init__(self, user_id: int, sender: _Sender) -> None:
            self.user_id = user_id
            self.sender = sender

    class _FakeQueue(dict):
        pass

    queue = _FakeQueue()
    queue["100"] = [
        _Message(1, _Sender(nickname="小A")),
        _Message(1, _Sender(nickname="小A", card="卡片", sex="male", role="admin")),
        _Message(2, _Sender()),
    ]

    members = UserProfileService._collect_group_members_from_queue("100", queue)

    assert len(members) == 2
    assert members[0].user_id == 1
    assert members[0].card == "卡片"
    assert members[0].sex == "male"
    assert members[0].role == "admin"
    assert members[1].user_id == 2


async def test_is_bot_group_admin_uses_member_info_then_list_fallback() -> None:
    """Arrange: 成员信息接口返回 admin；Act: is_bot_group_admin；Assert: 判定为管理员且不再调列表接口。"""
    repo = _FakeProfilesRepo()
    adapter = _FakeAdapter(member_info=SimpleNamespace(role="admin"))
    service = _make_service(repo, adapter)

    result = await service.is_bot_group_admin("100", "888")

    assert result is True
    assert adapter.calls == [("get_group_member_info", (100, 888))]


async def test_get_group_name_falls_back_to_placeholder() -> None:
    """Arrange: 仓库无该群记录；Act: get_group_name；Assert: 返回 群聊<id> 占位名。"""
    repo = _FakeProfilesRepo()
    service = _make_service(repo, _FakeAdapter())

    result = await service.get_group_name("999")

    assert result == "群聊999"


async def test_render_group_member_list_formats_all_members() -> None:
    """Arrange: 假队列提供 2 名成员、档案为空；Act: render_group_member_list；Assert: 输出两行群友段落。"""
    class _Sender:
        def __init__(self, nickname: str) -> None:
            self.nickname = nickname
            self.card = None
            self.sex = None
            self.role = None

    class _Message:
        def __init__(self, user_id: int, sender: _Sender) -> None:
            self.user_id = user_id
            self.sender = sender

    class _FakeQueue(dict):
        pass

    queue = _FakeQueue()
    queue["100"] = [
        _Message(1, _Sender("成员一")),
        _Message(2, _Sender("成员二")),
    ]
    repo = _FakeProfilesRepo()
    adapter = _FakeAdapter()
    service = _make_service(repo, adapter)

    text = await service.render_group_member_list("100", message_queue=queue)

    assert "<群友_1>" in text
    assert "<群友_2>" in text
    assert "昵称:成员一" in text
    assert "昵称:成员二" in text
    assert text.index("<群友_1>") < text.index("<群友_2>")
    # 默认不注入群员档案
    assert "你记得关于Ta的信息" not in text


async def test_render_group_member_list_injects_archives_only_when_enabled() -> None:
    """include_archives=True 时才注入群员档案（默认关闭，改由 agent 按需读取）。"""

    class _Sender:
        def __init__(self, nickname: str) -> None:
            self.nickname = nickname
            self.card = None
            self.sex = None
            self.role = None

    class _Message:
        def __init__(self, user_id: int, sender: _Sender) -> None:
            self.user_id = user_id
            self.sender = sender

    class _Archive:
        async def get(self, table_name, key):
            return SimpleNamespace(value=f"{key} 的长期记忆")

    class _FakeQueue(dict):
        pass

    queue = _FakeQueue()
    queue["100"] = [_Message(1, _Sender("成员一"))]
    service = _make_service(_FakeProfilesRepo(), _FakeAdapter())
    service._archive_memory_service = _Archive()

    without = await service.render_group_member_list("100", message_queue=queue)
    with_archives = await service.render_group_member_list(
        "100", message_queue=queue, include_archives=True
    )

    assert "你记得关于Ta的信息" not in without
    assert "你记得关于Ta的信息:1 的长期记忆" in with_archives
