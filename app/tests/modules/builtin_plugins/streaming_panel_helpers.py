"""流媒体面板的真实数据库与合成外部服务，不连接 QQ 或 B 站。"""

from __future__ import annotations

from types import SimpleNamespace

from neobot_app.builtin_plugins.streaming_parser import PluginState, TEMPLATE_DIR, db
from neobot_app.builtin_plugins.streaming_parser.bilibili.models import LiveRoomInfo
from neobot_app.builtin_plugins.streaming_parser.config import StreamConfig
from neobot_app.builtin_plugins.streaming_parser.poller import LivePoller
from neobot_app.builtin_plugins.streaming_parser.render import CardRenderer
from neobot_contracts.ports.logging import NullLogger
from neobot_modloader import PluginDatabase


class Adapter:
    def __init__(self):
        self.calls = []
        self.sent = []

    async def call_api(self, action, params, timeout=5.0):
        self.calls.append((action, params))
        if action == "get_login_info":
            return {"status": "ok", "retcode": 0, "data": {"user_id": 10001, "nickname": "演示机器人"}}
        return {"status": "ok", "retcode": 0, "data": [{"group_id": 20001, "group_name": "演示交流组"}]}

    async def send_group_msg(self, group_id, message):
        self.sent.append((group_id, message))
        return {"status": "ok"}


class LiveClient:
    def __init__(self):
        self.fail = False
        self.closed = 0
        self.queried = []

    async def fetch_live_room_init(self, room_id):
        return SimpleNamespace(room_id=610001, uid=510001, short_id=1001)

    async def fetch_user_live_status(self, uid):
        return SimpleNamespace(has_room=True, room_id=610001)

    async def fetch_user_card(self, uid):
        return SimpleNamespace(name="演示主播", face="")

    async def fetch_live_room_info(self, room_id):
        from neobot_app.builtin_plugins.streaming_parser.bilibili.errors import BilibiliTransportError

        self.queried.append(room_id)
        if self.fail:
            raise BilibiliTransportError("合成的外部连接失败")
        return LiveRoomInfo(
            room_id=room_id,
            short_id=1001,
            uid=510001,
            title="一起认识新的插件面板",
            live_status=0,
            live_time=None,
            area_name="知识分享",
            online=120,
        )

    async def aclose(self):
        self.closed += 1


class Assets:
    async def fetch_data_uri(self, url):
        return ""


class Notifier:
    def __init__(self):
        self.transitions = []

    async def handle_transition(self, transition):
        self.transitions.append(transition)


async def make_state(tmp_path):
    database = PluginDatabase(
        "streaming_parser",
        db.DATABASE_NAME,
        filename=db.DATABASE_FILENAME,
        metadata=db.Base.metadata,
        migrations=db.MIGRATIONS,
    )
    await database.bind(tmp_path)
    state = PluginState()
    state.database = database
    state.config = StreamConfig()
    state.client = LiveClient()
    state.assets = Assets()
    state.renderer = CardRenderer(TEMPLATE_DIR)
    state.notifier = Notifier()
    state.ctx = SimpleNamespace(adapter=Adapter(), logger=NullLogger())
    state.poller = LivePoller(client=state.client, database=database, poll_interval=15)
    return state
