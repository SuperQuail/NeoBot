"""数据层、轮询落库与推送链路测试（需要真实的 neobot_modloader，CI 里会跳过）。"""

from __future__ import annotations

import asyncio

import pytest

modloader = pytest.importorskip('neobot_modloader')
if getattr(modloader, 'IS_TEST_STUB', False):
    pytest.skip('需要真实的 neobot_modloader（CI 环境没有 NeoBot 依赖）', allow_module_level=True)

# 这些导入必须在 importorskip 之后：没有真实 modloader 时整模块跳过，
# 否则收集阶段就会因为缺依赖而报错。因此这里显式豁免 E402。
from streaming_parser import db as pdb  # noqa: E402
from streaming_parser.bilibili.models import LiveRoomInfo  # noqa: E402
from streaming_parser.poller import EVENT_LIVE, EVENT_LIVE_END, LivePoller  # noqa: E402

from neobot_modloader import PluginDatabase  # noqa: E402


@pytest.fixture
async def database(tmp_path):
    database = PluginDatabase(
        'streaming_parser',
        pdb.DATABASE_NAME,
        filename=pdb.DATABASE_FILENAME,
        metadata=pdb.Base.metadata,
        migrations=pdb.MIGRATIONS,
    )
    await database.bind(tmp_path)
    try:
        yield database
    finally:
        await database.close()


class TestSubscriptions:
    async def test_upsert_creates_then_updates(self, database):
        async with database.transaction() as session:
            row, created = await pdb.upsert_subscription(
                session, group_id=100, room_id=5440, uid=9, name='甲'
            )
            assert created is True
            assert row.name == '甲'
        async with database.transaction() as session:
            row, created = await pdb.upsert_subscription(
                session, group_id=100, room_id=5440, uid=9, name='乙'
            )
            assert created is False
            assert row.name == '乙'
        async with database.session() as session:
            rows = await pdb.list_group_subscriptions(session, 100)
        assert len(rows) == 1

    async def test_push_flags_default_and_toggle(self, database):
        async with database.transaction() as session:
            await pdb.upsert_subscription(
                session, group_id=1, room_id=1, push_live=True, push_live_end=False
            )
        async with database.transaction() as session:
            row = pdb.sub_view(
                await pdb.set_subscription_flags(
                    session, 1, 1, push_live=False, push_live_end=True
                )
            )
        assert row is not None
        assert row.push_live is False
        assert row.push_live_end is True

    async def test_set_flags_on_unknown_room_returns_none(self, database):
        async with database.transaction() as session:
            assert await pdb.set_subscription_flags(session, 1, 999) is None

    async def test_remove_subscription(self, database):
        async with database.transaction() as session:
            await pdb.upsert_subscription(session, group_id=1, room_id=7)
        async with database.transaction() as session:
            assert await pdb.remove_subscription(session, 1, 7) is True
        async with database.transaction() as session:
            assert await pdb.remove_subscription(session, 1, 7) is False

    async def test_distinct_rooms_dedupe_across_groups(self, database):
        async with database.transaction() as session:
            await pdb.upsert_subscription(session, group_id=1, room_id=10)
            await pdb.upsert_subscription(session, group_id=2, room_id=10)
            await pdb.upsert_subscription(session, group_id=2, room_id=20)
        async with database.session() as session:
            assert await pdb.distinct_room_ids(session) == [10, 20]

    async def test_followers_of_room(self, database):
        async with database.transaction() as session:
            await pdb.upsert_subscription(session, group_id=1, room_id=10)
            await pdb.upsert_subscription(session, group_id=2, room_id=10)
            await pdb.upsert_subscription(session, group_id=3, room_id=30)
        async with database.session() as session:
            followers = await pdb.followers_of_room(session, 10)
        assert sorted(row.group_id for row in followers) == [1, 2]


class TestGroupSettings:
    async def test_ensure_creates_with_defaults(self, database):
        async with database.transaction() as session:
            setting = pdb.setting_view(
                await pdb.ensure_group_setting(
                    session, 5, {'ai_reply_live': False, 'card_style': 'neon'}
                )
            )
        assert setting is not None
        assert setting.group_id == 5
        assert setting.ai_reply_live is False
        assert setting.card_style == 'neon'
        assert setting.default_push_live is True

    async def test_ensure_is_idempotent(self, database):
        async with database.transaction() as session:
            first = pdb.setting_view(
                await pdb.ensure_group_setting(session, 5, {'card_style': 'neon'})
            )
        async with database.transaction() as session:
            second = pdb.setting_view(
                await pdb.ensure_group_setting(session, 5, {'card_style': 'sakura'})
            )
        assert second is not None and first is not None
        assert second.card_style == 'neon'
        assert first.group_id == second.group_id

    async def test_get_missing_returns_none(self, database):
        async with database.session() as session:
            assert await pdb.get_group_setting(session, 404) is None


class TestRoomState:
    async def test_upsert_creates_then_updates(self, database):
        async with database.transaction() as session:
            row = await pdb.upsert_room_state(session, 10, live_status=0, title='旧')
            assert row.live_status == 0
        async with database.transaction() as session:
            row = await pdb.upsert_room_state(session, 10, live_status=1, title='新')
            assert row.live_status == 1
            assert row.title == '新'
        async with database.session() as session:
            stored = await pdb.get_room_state(session, 10)
        assert stored is not None and stored.live_status == 1

    async def test_missing_state_returns_none(self, database):
        async with database.session() as session:
            assert await pdb.get_room_state(session, 999) is None


class FakeClient:
    def __init__(self, script):
        self.script = script

    async def fetch_live_room_info(self, room_id):
        status = self.script[room_id].pop(0)
        return LiveRoomInfo(
            room_id=room_id,
            short_id=0,
            uid=1,
            title='t',
            live_status=status,
            live_time=None,
            online=5,
        )


class TestPollOnce:
    async def test_transitions_across_polls(self, database):
        async with database.transaction() as session:
            await pdb.upsert_subscription(session, group_id=1, room_id=10)
        client = FakeClient({10: [0, 1, 1, 0]})
        poller = LivePoller(client=client, database=database, poll_interval=15)

        first, stats_first = await poller.poll_once()
        assert first == []
        assert stats_first.checked == 1

        second, _ = await poller.poll_once()
        assert [item.kind for item in second] == [EVENT_LIVE]
        assert second[0].room_id == 10
        assert second[0].previous_status == 0

        third, _ = await poller.poll_once()
        assert third == []

        fourth, _ = await poller.poll_once()
        assert [item.kind for item in fourth] == [EVENT_LIVE_END]
        assert fourth[0].previous_status == 1

    async def test_api_failure_is_counted_not_raised(self, database):
        async with database.transaction() as session:
            await pdb.upsert_subscription(session, group_id=1, room_id=10)

        class Boom:
            async def fetch_live_room_info(self, room_id):
                raise RuntimeError('network down')

        poller = LivePoller(client=Boom(), database=database, poll_interval=15)
        transitions, stats = await poller.poll_once()
        assert transitions == []
        assert stats.failed == 1
        assert stats.checked == 0

    async def test_no_subscriptions_is_noop(self, database):
        poller = LivePoller(client=FakeClient({}), database=database, poll_interval=15)
        transitions, stats = await poller.poll_once()
        assert transitions == []
        assert stats.checked == 0



class FakeCtx:
    """够用的 ctx 替身：只实现 Notifier 真正会用的那几个方法。"""

    def __init__(self, services=None):
        self.sent_images = []
        self.sent_texts = []
        self.plugin_host = _Host(_Services(services or {}))

    def conversation_from_event(self, event):
        return 'conv:' + str(event.get('group_id'))

    async def send_image(self, conversation, *, data, filename):
        self.sent_images.append((conversation, data, filename))

    async def send_group(self, group_id, message):
        self.sent_texts.append((group_id, message))


class _Host:
    def __init__(self, services):
        self.services = services


class _Services:
    def __init__(self, mapping):
        self._mapping = mapping

    def get(self, name, default=None):
        return self._mapping.get(name, default)


class FakeRenderer:
    def __init__(self, data=b'PNG'):
        self.data = data
        self.calls = []

    async def render_card(self, values, *, style):
        self.calls.append((values, style))
        return self.data


class FakeAssets:
    def __init__(self):
        self.urls = []

    async def fetch_data_uri(self, url):
        self.urls.append(url)
        return 'data:image/png;base64,AA' if url else ''


class FakeHub:
    def __init__(self):
        self.calls = []

    async def publish(self, **kwargs):
        self.calls.append(kwargs)
        return True


async def make_transition(room_id=10, kind=EVENT_LIVE, live_status=1):
    from streaming_parser.poller import RoomSnapshot, Transition

    snapshot = RoomSnapshot(
        room_id=room_id,
        live_status=live_status,
        title='今晚杂谈',
        cover_url='https://example.invalid/cover.jpg',
        area_name='虚拟主播',
        online=12345,
    )
    return Transition(kind=kind, room_id=room_id, snapshot=snapshot, previous_status=0)


def build_notifier(database, ctx, *, renderer=None, config=None, assets=None):
    from streaming_parser.config import StreamConfig
    from streaming_parser.notify import Notifier

    return Notifier(
        ctx=ctx,
        database=database,
        renderer=renderer or FakeRenderer(),
        assets=assets or FakeAssets(),
        config=config or StreamConfig(),
    )


class TestNotifierIntegration:
    async def test_live_push_sends_card_and_triggers_ai(self, database):
        async with database.transaction() as session:
            await pdb.upsert_subscription(
                session, group_id=100, room_id=10, uid=7, name='星野遥', push_live=True
            )
        hub = FakeHub()
        ctx = FakeCtx({'notification_hub': hub})
        renderer = FakeRenderer(data=b'CARD')
        notifier = build_notifier(database, ctx, renderer=renderer)

        await notifier.handle_transition(await make_transition())

        assert len(ctx.sent_images) == 1
        conversation, data, filename = ctx.sent_images[0]
        assert conversation == 'conv:100'
        assert data == b'CARD'
        assert filename.endswith('.png')
        assert ctx.sent_texts == []
        values, style = renderer.calls[0]
        assert values['name'] == '星野遥'
        assert values['status_text'] == '开播了'
        assert values['room_id'] == '房间 10'
        assert style in ('sakura', 'neon', 'minimal')
        assert len(hub.calls) == 1
        assert hub.calls[0]['conversation_id'] == '100'
        assert '星野遥' in hub.calls[0]['content']

    async def test_push_disabled_sends_nothing(self, database):
        async with database.transaction() as session:
            await pdb.upsert_subscription(
                session, group_id=100, room_id=10, push_live=False
            )
        hub = FakeHub()
        ctx = FakeCtx({'notification_hub': hub})
        notifier = build_notifier(database, ctx)

        await notifier.handle_transition(await make_transition())

        assert ctx.sent_images == []
        assert ctx.sent_texts == []
        assert hub.calls == []

    async def test_render_failure_falls_back_to_text(self, database):
        async with database.transaction() as session:
            await pdb.upsert_subscription(session, group_id=100, room_id=10, name='甲')
        hub = FakeHub()
        ctx = FakeCtx({'notification_hub': hub})
        notifier = build_notifier(database, ctx, renderer=FakeRenderer(data=None))

        await notifier.handle_transition(await make_transition())

        assert ctx.sent_images == []
        assert len(ctx.sent_texts) == 1
        group_id, text = ctx.sent_texts[0]
        assert group_id == 100
        assert '【开播】甲' in text
        assert 'live.bilibili.com/10' in text
        assert len(hub.calls) == 1

    async def test_ai_reply_can_be_disabled_per_group(self, database):
        async with database.transaction() as session:
            await pdb.upsert_subscription(session, group_id=100, room_id=10)
            setting = await pdb.ensure_group_setting(session, 100, {})
            setting.ai_reply_live = False
        hub = FakeHub()
        ctx = FakeCtx({'notification_hub': hub})
        notifier = build_notifier(database, ctx)

        await notifier.handle_transition(await make_transition())

        assert len(ctx.sent_images) == 1
        assert hub.calls == []

    async def test_live_end_uses_its_own_switch(self, database):
        async with database.transaction() as session:
            await pdb.upsert_subscription(
                session, group_id=100, room_id=10, name='甲',
                push_live=True, push_live_end=True,
            )
            setting = await pdb.ensure_group_setting(session, 100, {})
            setting.ai_reply_live = True
            setting.ai_reply_live_end = False
        hub = FakeHub()
        ctx = FakeCtx({'notification_hub': hub})
        renderer = FakeRenderer()
        notifier = build_notifier(database, ctx, renderer=renderer)

        await notifier.handle_transition(await make_transition(kind=EVENT_LIVE_END, live_status=0))

        assert len(ctx.sent_images) == 1
        assert renderer.calls[0][0]['status_text'] == '下播了'
        assert renderer.calls[0][0]['live_time_text'] == ''
        assert hub.calls == []

    async def test_hub_missing_falls_back_to_orchestrator(self, database):
        async with database.transaction() as session:
            await pdb.upsert_subscription(session, group_id=100, room_id=10)

        class FakeOrchestrator:
            def __init__(self):
                self.started = []

            def start_background_reply(self, **kwargs):
                self.started.append(kwargs)
                return object()

        orchestrator = FakeOrchestrator()
        ctx = FakeCtx({'reply_orchestrator': orchestrator})
        notifier = build_notifier(database, ctx)

        await notifier.handle_transition(await make_transition())

        assert len(orchestrator.started) == 1
        assert orchestrator.started[0]['kind'] == 'group'

    async def test_group_style_override_is_used(self, database):
        async with database.transaction() as session:
            await pdb.upsert_subscription(session, group_id=100, room_id=10)
            setting = await pdb.ensure_group_setting(session, 100, {})
            setting.card_style = 'neon'
        ctx = FakeCtx()
        renderer = FakeRenderer()
        notifier = build_notifier(database, ctx, renderer=renderer)

        await notifier.handle_transition(await make_transition())

        assert renderer.calls[0][1] == 'neon'


class FakePoller:
    """只会返回预设实时快照的轮询器替身。"""

    def __init__(self, snapshots):
        self.snapshots = snapshots
        self.calls = []

    async def refresh(self, room_ids):
        self.calls.append(list(room_ids))
        return {rid: self.snapshots[rid] for rid in room_ids if rid in self.snapshots}


class FakeLogger:
    def __init__(self):
        self.messages = []

    def _record(self, message, *args, **kwargs):
        self.messages.append(str(message))

    info = _record
    warning = _record
    debug = _record
    error = _record


class TestRefresh:
    async def test_refresh_returns_snapshots_without_writing_store(self, database):
        async with database.transaction() as session:
            await pdb.upsert_subscription(session, group_id=1, room_id=10)
        client = FakeClient({10: [1]})
        poller = LivePoller(client=client, database=database, poll_interval=15)

        fresh = await poller.refresh([10])

        assert fresh[10].live_status == 1
        async with database.session() as session:
            assert await pdb.get_room_state(session, 10) is None

    async def test_refresh_empty_list_is_noop(self, database):
        poller = LivePoller(client=FakeClient({}), database=database, poll_interval=15)
        assert await poller.refresh([]) == {}


class TestCollectStates:
    """覆盖用户报告的问题：库里是旧状态时，/开播状态 必须以实时查询为准。"""

    async def test_prefers_fresh_over_stored(self, database):
        from types import SimpleNamespace

        from streaming_parser.poller import RoomSnapshot
        from streaming_parser.settings_commands import collect_states

        async with database.transaction() as session:
            await pdb.upsert_subscription(session, group_id=1, room_id=10, name='甲')
            await pdb.upsert_room_state(session, 10, live_status=0, title='旧标题')
        snapshot = RoomSnapshot(room_id=10, live_status=1, title='新标题', online=123)
        state = SimpleNamespace(
            database=database,
            poller=FakePoller({10: snapshot}),
            logger=FakeLogger(),
        )
        async with database.session() as session:
            rows = [pdb.sub_view(row) for row in await pdb.list_group_subscriptions(session, 1)]

        states, is_fresh = await collect_states(state, state, rows)

        assert is_fresh is True
        assert states[10].live_status == 1
        assert states[10].title == '新标题'

    async def test_falls_back_to_stored_when_live_query_fails(self, database):
        from types import SimpleNamespace

        from streaming_parser.settings_commands import collect_states

        async with database.transaction() as session:
            await pdb.upsert_subscription(session, group_id=1, room_id=10, name='甲')
            await pdb.upsert_room_state(session, 10, live_status=1, title='库里的标题')
        logger = FakeLogger()
        state = SimpleNamespace(database=database, poller=FakePoller({}), logger=logger)
        async with database.session() as session:
            rows = [pdb.sub_view(row) for row in await pdb.list_group_subscriptions(session, 1)]

        states, is_fresh = await collect_states(state, state, rows)

        assert is_fresh is False
        assert states[10].live_status == 1
        assert states[10].title == '库里的标题'

    async def test_poller_unavailable_uses_stored(self, database):
        from types import SimpleNamespace

        from streaming_parser.settings_commands import collect_states

        async with database.transaction() as session:
            await pdb.upsert_subscription(session, group_id=1, room_id=10)
            await pdb.upsert_room_state(session, 10, live_status=2)
        state = SimpleNamespace(database=database, poller=None, logger=FakeLogger())
        async with database.session() as session:
            rows = [pdb.sub_view(row) for row in await pdb.list_group_subscriptions(session, 1)]

        states, is_fresh = await collect_states(state, state, rows)

        assert is_fresh is False
        assert states[10].live_status == 2


class TestSubscribeEnablesBothPushes:
    """监听一个直播间后，开播与下播推送都应当自动建好（用户要求的行为）。"""

    @staticmethod
    def _make_state(database, config):
        class FakeState:
            def __init__(self):
                self.database = database
                self.config = config
                self.poller = None

            async def resolve_target(self, kind, value):
                return {
                    'room_id': 1914112138,
                    'uid': 392669996,
                    'short_id': 0,
                    'name': 'Icyの狼',
                    'avatar_url': '',
                }

        return FakeState()

    @staticmethod
    def _make_ctx():
        class Registrar:
            available = True

            def __init__(self):
                self.commands = {}

            def register(self, name=None, **kwargs):
                def _decorate(handler):
                    self.commands[name] = handler
                    return handler

                return _decorate

            def renames(self):
                return []

        class Logger:
            def _record(self, *args, **kwargs):
                pass

            info = _record
            warning = _record
            debug = _record
            error = _record

        class Ctx:
            def __init__(self):
                self.app_commands = Registrar()
                self.logger = Logger()
                self.screenshots = None

        return Ctx()

    @staticmethod
    def _make_command_ctx(args):
        class Service:
            async def send_image_bytes(self, *args, **kwargs):
                return False  # 强制走文本降级，便于断言卡片内容

        class CommandCtx:
            def __init__(self):
                self.kind = 'group'
                self.conv_id = '123'
                self.user_id = 42
                self.args = list(args)
                self.raw_args = ' '.join(args)
                self.service = Service()
                self.plain = []

            async def reply_plain(self, text):
                self.plain.append(text)

        return CommandCtx()

    async def test_subscribe_enables_live_and_live_end_push(self, database):
        from streaming_parser.commands import register_commands
        from streaming_parser.config import StreamConfig

        ctx = self._make_ctx()
        register_commands(ctx, self._make_state(database, StreamConfig()))
        command_ctx = self._make_command_ctx(['392669996'])

        await ctx.app_commands.commands['监听'](command_ctx)

        async with database.session() as session:
            rows = [pdb.sub_view(row) for row in await pdb.list_group_subscriptions(session, 123)]
        assert len(rows) == 1
        assert rows[0].push_live is True
        assert rows[0].push_live_end is True
        text = command_ctx.plain[0]
        assert '开播推送: 开' in text
        assert '下播推送: 开' in text

    async def test_relisten_keeps_manual_override(self, database):
        from streaming_parser.commands import register_commands
        from streaming_parser.config import StreamConfig

        ctx = self._make_ctx()
        register_commands(ctx, self._make_state(database, StreamConfig()))
        handler = ctx.app_commands.commands['监听']
        await handler(self._make_command_ctx(['392669996']))
        async with database.transaction() as session:
            await pdb.set_subscription_flags(session, 123, 1914112138, push_live_end=False)

        # 再次监听同一个房间：只刷新信息，不能把用户手动关掉的开关又打开
        second = self._make_command_ctx(['392669996'])
        await handler(second)

        async with database.session() as session:
            rows = [pdb.sub_view(row) for row in await pdb.list_group_subscriptions(session, 123)]
        assert len(rows) == 1
        assert rows[0].push_live_end is False
        assert '下播推送: 关' in second.plain[0]


class TestSubscribeUsesGroupDefaults:
    """/config 写入的群级默认必须真的影响 /监听——之前只读全局配置，是死配置。"""

    async def test_group_default_overrides_global_config(self, database):
        from streaming_parser.commands import register_commands
        from streaming_parser.config import StreamConfig

        async with database.transaction() as session:
            setting = await pdb.ensure_group_setting(session, 123, {})
            setting.default_push_live = False
            setting.default_push_live_end = True
        ctx = TestSubscribeEnablesBothPushes._make_ctx()
        state = TestSubscribeEnablesBothPushes._make_state(database, StreamConfig())
        register_commands(ctx, state)
        command_ctx = TestSubscribeEnablesBothPushes._make_command_ctx(['392669996'])

        await ctx.app_commands.commands['监听'](command_ctx)

        async with database.session() as session:
            rows = [pdb.sub_view(row) for row in await pdb.list_group_subscriptions(session, 123)]
        assert rows[0].push_live is False
        assert rows[0].push_live_end is True
        assert '开播推送: 关' in command_ctx.plain[0]
        assert '下播推送: 开' in command_ctx.plain[0]

    async def test_global_config_is_used_without_group_setting(self, database):
        from streaming_parser.commands import register_commands
        from streaming_parser.config import StreamConfig

        ctx = TestSubscribeEnablesBothPushes._make_ctx()
        config = StreamConfig(default_push_live=False, default_push_live_end=True)
        state = TestSubscribeEnablesBothPushes._make_state(database, config)
        register_commands(ctx, state)
        command_ctx = TestSubscribeEnablesBothPushes._make_command_ctx(['392669996'])

        await ctx.app_commands.commands['监听'](command_ctx)

        async with database.session() as session:
            rows = [pdb.sub_view(row) for row in await pdb.list_group_subscriptions(session, 123)]
        assert rows[0].push_live is False
        assert rows[0].push_live_end is True

    async def test_config_writes_the_same_defaults_used_by_listen(self, database):
        """/config 建行时的默认值要和 /监听 的回退值一致，否则显示与实际不符。"""
        from streaming_parser.config import StreamConfig
        from streaming_parser.settings_commands import group_defaults

        config = StreamConfig(default_push_live=False, default_push_live_end=True)
        assert group_defaults(config) == {
            'card_style': config.default_card_style,
            'ai_reply_live': config.default_ai_reply_live,
            'ai_reply_live_end': config.default_ai_reply_live_end,
            'default_push_live': False,
            'default_push_live_end': True,
        }


class FlakyAssets(FakeAssets):
    """对某个头像 URL 抛异常，用来验证单群失败不拖累其他群。"""

    async def fetch_data_uri(self, url):
        if url == 'https://cdn/bad':
            raise RuntimeError('头像服务挂了')
        return await super().fetch_data_uri(url)


class TestNotifierPerGroupIsolation:
    async def test_one_group_failure_does_not_block_other_groups(self, database):
        async with database.transaction() as session:
            await pdb.upsert_subscription(
                session, group_id=100, room_id=10, name='甲', avatar_url='https://cdn/bad'
            )
            await pdb.upsert_subscription(
                session, group_id=200, room_id=10, name='乙', avatar_url='https://cdn/good'
            )
        ctx = FakeCtx()
        notifier = build_notifier(database, ctx, assets=FlakyAssets())

        await notifier.handle_transition(await make_transition())

        # 群 100 取头像时炸了：只记日志，群 200 必须照常收到卡片
        assert [conversation for conversation, *_ in ctx.sent_images] == ['conv:200']


class FakeSlowPoller:
    """refresh 永远卡住，用来验证 /开播状态 的总超时回退。"""

    def __init__(self):
        self.calls = 0

    async def refresh(self, room_ids):
        self.calls += 1
        await asyncio.sleep(5)
        return {}


class FakeOverviewRenderer:
    def __init__(self):
        self.calls = 0

    async def render_overview(self, hosts, *, style, title_text, summary_text):
        self.calls += 1
        return b'OVERVIEW'


def build_overview_state(database, *, poller=None):
    from streaming_parser.config import StreamConfig

    class State:
        def __init__(self):
            self.database = database
            self.config = StreamConfig()
            self.poller = poller
            self.renderer = FakeOverviewRenderer()
            self.logger = FakeLogger()

        async def style_for(self, group_id):
            return 'sakura'

        async def build_overview_hosts(self, rows, states):
            return [
                {
                    'avatar_src': '',
                    'name': row.name or 'x',
                    'live': row.room_id in states and int(states[row.room_id].live_status) == 1,
                }
                for row in rows
            ]

    return State()


class TestOverviewCommand:
    @staticmethod
    def _register(database, state):
        from streaming_parser.commands import register_commands

        ctx = TestSubscribeEnablesBothPushes._make_ctx()
        register_commands(ctx, state)
        return ctx, ctx.app_commands.commands['开播状态']

    async def test_status_query_timeout_falls_back_to_stored(self, database, monkeypatch):
        from streaming_parser import settings_commands

        async with database.transaction() as session:
            await pdb.upsert_subscription(session, group_id=123, room_id=10, name='甲')
            await pdb.upsert_room_state(session, 10, live_status=1, title='库里的标题')
        state = build_overview_state(database, poller=FakeSlowPoller())
        ctx, handler = self._register(database, state)
        monkeypatch.setattr(settings_commands, 'STATUS_QUERY_TIMEOUT', 0.01)
        command_ctx = TestSubscribeEnablesBothPushes._make_command_ctx([])

        await handler(command_ctx)

        text = command_ctx.plain[0]
        assert '最近一次轮询' in text
        assert '直播中' in text

    async def test_image_send_failure_does_not_render_again(self, database, monkeypatch):
        from streaming_parser import cards

        async with database.transaction() as session:
            await pdb.upsert_subscription(session, group_id=123, room_id=10, name='甲')
        state = build_overview_state(database)
        ctx, handler = self._register(database, state)
        renders = []

        async def fake_render(*args, **kwargs):
            renders.append(1)
            return None

        monkeypatch.setattr(cards, 'render_payload_png', fake_render)
        command_ctx = TestSubscribeEnablesBothPushes._make_command_ctx([])

        await handler(command_ctx)

        # 图片发不出去就发文字：不能再用卡片渲染器把同一份表格重画一遍
        assert state.renderer.calls == 1
        assert renders == []
        assert len(command_ctx.plain) == 1
        assert '本群关注的主播' in command_ctx.plain[0]

