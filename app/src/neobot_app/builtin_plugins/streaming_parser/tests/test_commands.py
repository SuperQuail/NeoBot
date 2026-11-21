"""命令层测试：参数解析、注册契约（/help 能不能看到）与卡片降级。"""

from __future__ import annotations

import pytest
from streaming_parser import cards
from streaming_parser.commands import (
    command_args,
    conv_group_id,
    parse_switch,
    parse_target,
    register_commands,
)


class FakeRegistrar:
    """替身命令注册器：把注册结果收集下来，便于断言 /help 能看到什么。"""

    available = True

    def __init__(self):
        self.commands = {}

    def register(self, name=None, **kwargs):
        def _decorate(handler):
            self.commands[name] = {'kwargs': kwargs, 'handler': handler}
            return handler

        return _decorate

    def renames(self):
        return []


class FakeLogger:
    def __init__(self):
        self.messages = []

    def _record(self, message, *args, **kwargs):
        self.messages.append(str(message))

    info = _record
    warning = _record
    debug = _record
    error = _record


class FakeCtx:
    def __init__(self):
        self.app_commands = FakeRegistrar()
        self.logger = FakeLogger()
        self.screenshots = None


class FakeService:
    def __init__(self):
        self.images = []

    async def send_image_bytes(self, kind, conv_id, data, *, at_user_id=None, filename=None):
        self.images.append((kind, conv_id, len(data), filename))
        return True


class FakeCommandCtx:
    def __init__(self, args=None, kind='group', conv_id='123'):
        self.kind = kind
        self.conv_id = conv_id
        self.user_id = 42
        self.args = list(args or [])
        self.raw_args = ' '.join(args or [])
        self.service = FakeService()
        self.plain = []

    async def reply_plain(self, text):
        self.plain.append(text)

    async def reply(self, text):
        self.plain.append(text)


class TestParseTarget:
    def test_plain_digits_is_room(self):
        assert parse_target('21452505') == ('room', 21452505)

    def test_live_url_is_room(self):
        assert parse_target('https://live.bilibili.com/1914112138') == ('room', 1914112138)

    def test_space_url_is_uid(self):
        assert parse_target('https://space.bilibili.com/392669996') == ('uid', 392669996)

    def test_uid_prefix(self):
        assert parse_target('uid:392669996') == ('uid', 392669996)

    @pytest.mark.parametrize('bad', ['', '   ', '不是数字', 'https://example.com/abc'])
    def test_invalid_raises(self, bad):
        with pytest.raises(ValueError):
            parse_target(bad)


class TestParseSwitch:
    @pytest.mark.parametrize('value', ['开', '开启', 'on', '1', 'true', 'YES'])
    def test_on(self, value):
        assert parse_switch(value) is True

    @pytest.mark.parametrize('value', ['关', '关闭', 'off', '0', 'false', 'NO'])
    def test_off(self, value):
        assert parse_switch(value) is False

    @pytest.mark.parametrize('value', ['', None, '也许'])
    def test_unknown(self, value):
        assert parse_switch(value) is None


class TestConvGroupId:
    def test_group(self):
        assert conv_group_id(FakeCommandCtx(conv_id='456')) == "456"

    def test_private_is_zero(self):
        assert conv_group_id(FakeCommandCtx(kind='private', conv_id='456')) == ""

    def test_text_conv_id_is_preserved(self):
        """openid 是合法文本 ID，不能当脏数据丢掉。"""
        assert conv_group_id(FakeCommandCtx(conv_id='abc')) == "abc"


class TestCommandArgs:
    def test_returns_strings(self):
        assert command_args(FakeCommandCtx(args=['a', 'b'])) == ['a', 'b']

    def test_missing_args_is_empty(self):
        ctx = FakeCommandCtx()
        ctx.args = None
        assert command_args(ctx) == []


class TestRegistrationContract:
    """这是「/help 能不能查到插件命令」的守门测试。"""

    @pytest.fixture
    def registered(self):
        ctx = FakeCtx()
        names = register_commands(ctx, state=None)
        return ctx, names

    def test_all_commands_are_registered(self, registered):
        _, names = registered
        assert names == [
            '直播监听',
            '直播状态',
            '取消直播监听',
            '直播监听列表',
            '开播推送',
            '下播推送',
            '开播状态',
            '卡片风格',
            'config',
        ]

    def test_renamed_commands_declare_legacy_aliases(self, registered):
        """旧命令名保留为别名，但别名不重复出现在 /help 的命令清单里。"""
        ctx, names = registered
        legacy = {
            '直播监听': ('监听',),
            '取消直播监听': ('取消监听',),
            '直播监听列表': ('监听列表',),
        }
        for name, aliases in legacy.items():
            assert ctx.app_commands.commands[name]['kwargs']['aliases'] == aliases
            for alias in aliases:
                assert alias not in names

    def test_every_command_has_description(self, registered):
        ctx, names = registered
        for name in names:
            entry = ctx.app_commands.commands[name]
            assert entry['kwargs'].get('description'), name + ' 缺少 description（/help 会显示空白）'
            assert callable(entry['handler'])

    def test_commands_with_arguments_have_usage_and_params(self, registered):
        ctx, _ = registered
        for name in ('直播监听', '直播状态', '取消直播监听', '开播推送', '下播推送'):
            kwargs = ctx.app_commands.commands[name]['kwargs']
            assert kwargs.get('usage'), name + ' 缺少 usage'
            assert kwargs.get('params'), name + ' 缺少 params（/help 详情里看不到参数说明）'

    def test_readonly_commands_are_open_to_everyone(self, registered):
        ctx, _ = registered
        assert ctx.app_commands.commands['直播监听列表']['kwargs']['permission'] == 0
        assert ctx.app_commands.commands['直播状态']['kwargs']['permission'] == 0
        assert ctx.app_commands.commands['开播状态']['kwargs']['permission'] == 0

    def test_mutating_commands_require_admin(self, registered):
        ctx, _ = registered
        for name in ('直播监听', '取消直播监听', '开播推送', '下播推送', '卡片风格', 'config'):
            assert ctx.app_commands.commands[name]['kwargs']['permission'] >= 1, name + ' 应当要求管理员'

    def test_registration_logs_nothing_when_registrar_available(self, registered):
        ctx, _ = registered
        assert ctx.logger.messages == []


class TestHandlerCards:
    """命令回复必须走卡片；渲染不可用时降级成等文本（这里 screenshots=None）。"""

    async def test_missing_args_sends_usage_card(self):
        ctx = FakeCtx()
        register_commands(ctx, state=None)
        handler = ctx.app_commands.commands['直播监听']['handler']
        command_ctx = FakeCommandCtx(args=[])
        await handler(command_ctx)
        assert command_ctx.service.images == []
        assert command_ctx.plain, '应当降级发送纯文本'
        text = command_ctx.plain[0]
        assert '监听直播间' in text
        assert '/直播监听 <房间号' in text

    async def test_private_chat_is_rejected(self):
        ctx = FakeCtx()
        register_commands(ctx, state=None)
        handler = ctx.app_commands.commands['直播监听列表']['handler']
        command_ctx = FakeCommandCtx(kind='private')
        await handler(command_ctx)
        assert '需要在群聊里发送' in command_ctx.plain[0]

    async def test_status_missing_args_sends_usage_card(self):
        ctx = FakeCtx()
        register_commands(ctx, state=None)
        handler = ctx.app_commands.commands['直播状态']['handler']
        command_ctx = FakeCommandCtx(args=[])
        await handler(command_ctx)
        assert command_ctx.service.images == []
        assert command_ctx.plain, '应当降级发送纯文本'
        assert '/直播状态 <房间号' in command_ctx.plain[0]

    async def test_status_private_chat_is_rejected(self):
        ctx = FakeCtx()
        register_commands(ctx, state=None)
        handler = ctx.app_commands.commands['直播状态']['handler']
        command_ctx = FakeCommandCtx(kind='private', args=['10'])
        await handler(command_ctx)
        assert '需要在群聊里发送' in command_ctx.plain[0]

    async def test_status_reports_unready_plugin(self):
        ctx = FakeCtx()
        register_commands(ctx, state=None)
        handler = ctx.app_commands.commands['直播状态']['handler']
        command_ctx = FakeCommandCtx(args=['10'])
        await handler(command_ctx)
        assert '插件还没就绪' in command_ctx.plain[0]

    async def test_toggle_requires_switch_value(self):
        ctx = FakeCtx()
        register_commands(ctx, state=None)
        handler = ctx.app_commands.commands['开播推送']['handler']
        command_ctx = FakeCommandCtx(args=['1914112138'])
        await handler(command_ctx)
        assert '开播推送开关' in command_ctx.plain[0]

    async def test_bad_switch_value_reports_error(self):
        ctx = FakeCtx()
        register_commands(ctx, state=None)
        handler = ctx.app_commands.commands['开播推送']['handler']
        command_ctx = FakeCommandCtx(args=['1914112138', '也许'])
        await handler(command_ctx)
        assert '开关只能填' in command_ctx.plain[0]

    async def test_style_command_lists_available_styles(self):
        ctx = FakeCtx()
        register_commands(ctx, state=None)
        handler = ctx.app_commands.commands['卡片风格']['handler']
        command_ctx = FakeCommandCtx(args=['不存在的风格'])
        await handler(command_ctx)
        assert '没有这个风格' in command_ctx.plain[0]


class TestCardPayloads:
    def test_kv_card_text(self):
        payload = cards.kv_card(title='已开始监听', items=[('主播', 'Icyの狼'), ('房间号', '1914112138')])
        text = cards.payload_text(payload)
        assert '已开始监听' in text
        assert '主播: Icyの狼' in text
        assert '房间号: 1914112138' in text

    def test_rows_card_text(self):
        payload = cards.rows_card(
            title='本群监听的直播间',
            columns=['#', '主播'],
            rows=[['1', 'Icyの狼']],
        )
        text = cards.payload_text(payload)
        assert '# 主播' in text
        assert '1 | Icyの狼' in text

    def test_message_card_skips_blank_lines(self):
        payload = cards.message_card(title='设置', lines=['a', '   ', 'b'])
        assert len(payload['blocks']) == 2

    def test_error_card_is_danger_tone(self):
        payload = cards.error_card(title='失败', text='出错了')
        assert payload['blocks'][0]['tone'] == 'danger'

    async def test_render_without_screenshots_returns_none(self):
        payload = cards.kv_card(title='x', items=[('a', 'b')])
        assert await cards.render_payload_png(payload, screenshots=None) is None


class TestPushDefaults:
    """默认值就是把开播与下播推送都打开（/直播监听 之后无需再手动开）。"""

    def test_config_enables_both_pushes_by_default(self):
        from streaming_parser.config import StreamConfig

        config = StreamConfig()
        assert config.default_push_live is True
        assert config.default_push_live_end is True

