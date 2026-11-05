"""真实命令与配置的使用说明；演示不执行群聊命令或业务动作。"""

import base64
from pathlib import Path

from neobot_modloader import Plugin

from .notify import build_card_values
from .panel_form_guide import register_config_form_guide
from .poller import EVENT_LIVE
from .render import CardRenderer


def _svg(source: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(source.encode()).decode()


DEMO_COVER = _svg(
    '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="405" viewBox="0 0 720 405">'
    '<rect width="720" height="405" fill="#17324d"/><circle cx="586" cy="70" r="180" fill="#235675"/>'
    '<circle cx="125" cy="370" r="160" fill="#285574"/><path d="M105 228h58v-78h29v144h29V116h29v204h29V82h29v258h29V128h29v178h29V156h29v118h29V190h58" '
    'fill="none" stroke="#79d4e5" stroke-width="11" stroke-linejoin="round"/>'
    '<text x="42" y="58" fill="#d9f4fa" font-size="24" font-family="sans-serif">演示直播间</text>'
    '<text x="42" y="370" fill="#d9f4fa" font-size="18" font-family="sans-serif">一起认识新的插件面板</text></svg>'
)
DEMO_AVATAR = _svg(
    '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120">'
    '<rect width="120" height="120" rx="60" fill="#287f9a"/>'
    '<text x="60" y="80" text-anchor="middle" fill="white" font-size="62" font-family="sans-serif">演</text></svg>'
)


def demonstration() -> dict:
    target = {
        "room_id": 610001,
        "uid": 510001,
        "short_id": 1001,
        "name": "演示主播",
        "avatar_url": "",
        "url": "https://live.bilibili.com/610001",
    }
    item = {
        "group_id": 20001,
        "room_id": 610001,
        "uid": 510001,
        "short_id": 1001,
        "name": "演示主播",
        "avatar_url": "",
        "push_live": True,
        "push_live_end": True,
        "live_status": 0,
        "checked_at": "2026-10-28T12:00:00Z",
    }
    html = CardRenderer(Path(__file__).parent / "templates").card_html(
        build_card_values(
            kind=EVENT_LIVE,
            room_id=610001,
            name="演示主播",
            title="一起认识新的插件面板",
            area_name="知识分享",
            online=120,
            live_time=None,
            cover_src=DEMO_COVER,
            avatar_src=DEMO_AVATAR,
        ),
        style="minimal",
    )
    health = {
        "running": True,
        "subscriptions": 1,
        "watched_rooms": 1,
        "checked_at": "2026-10-28T12:00:00Z",
        "success_at": "2026-10-28T12:00:00Z",
        "checked": 1,
        "failed": 0,
        "error": "",
        "message": "示例订阅已建立，后台会按开关通知接收群。",
    }
    return {
        "actions": {
            "groups.settings.get": {
                "group_id": 20001,
                "card_style": "minimal",
                "ai_reply_live": False,
                "ai_reply_live_end": False,
                "default_push_live": True,
                "default_push_live_end": True,
                "inherited": True,
            },
            "groups.settings.update": {
                "group_id": 20001,
                "card_style": "minimal",
                "ai_reply_live": False,
                "ai_reply_live_end": False,
                "default_push_live": True,
                "default_push_live_end": True,
                "inherited": False,
            },
            "subscriptions.groups": {
                "items": [{"group_id": 20001, "name": "演示交流组", "bot_id": "10001"}]
            },
            "subscriptions.resolve": target,
            "subscriptions.preview": {
                "target": target,
                "style": "minimal",
                "html": html,
                "fallback_text": "【开播】演示主播\n一起认识新的插件面板\n知识分享 · 120人气",
            },
            "subscriptions.create": {"created": True, "item": item},
            "subscriptions.list": {"items": []},
            "subscriptions.remove": {"removed": True},
            "subscriptions.toggle": {"item": item},
            "subscriptions.health": health,
            "subscriptions.ready": {
                "completed": True,
                "reason": "演示流程已经完整展示。",
            },
        }
    }


def register_guide(plugin: Plugin) -> None:
    # 教程复用真实 iframe 页面，演示会话只读取合成数据，不执行写动作。
    _register_start_guide(plugin)
    register_config_form_guide(plugin)
    _register_chat_guide(plugin)
    _register_config_guide(plugin)


MANAGE_CONTEXT = (
    "在接收通知的 QQ 群里，先 @机器人，再发送命令；需要 NeoBot 次级管理员权限。"
)
READ_CONTEXT = "在接收通知的同一个 QQ 群里，先 @机器人，再发送命令；所有人可用。"


def _register_start_guide(plugin: Plugin) -> None:
    sample = {"group_id": 20001, "target": "https://live.bilibili.com/610001"}
    item = demonstration()["actions"]["subscriptions.create"]["item"]
    plugin.guide(
        "first-subscription",
        title="从零添加订阅",
        steps=[
            {
                "chapter": "打开空白订阅表单",
                "target": "view.subscriptions.group",
                "text": "选择插件页面后直接看到订阅表单，不需要再展开。开始时接收群和直播间都未填写；教程只使用合成群和主播，不会读取或改动你的订阅。",
                "example": {"group_id": 0, "target": ""},
            },
            {
                "chapter": "选择接收通知的群",
                "target": "view.subscriptions.group",
                "text": "先选择接收通知的群。真实页面只列出当前机器人加入的群；没有可选群时请先检查机器人连接和加群状态。这里只选群，还没有建立订阅。",
                "example": {"group_id": 20001, "target": ""},
            },
            {
                "chapter": "填写并识别直播间",
                "target": "view.subscriptions.target",
                "text": "再填写直播间链接，点击识别核对主播和房间号。也支持房间号、短号、UP 主空间链接及 uid: 写法。前一步的群选择会保留。",
                "example": sample,
            },
            {
                "chapter": "预览通知",
                "target": "view.subscriptions.preview",
                "text": "预览后核对主播、接收群、卡片风格和文字内容。预览不会创建订阅，也不会往群里发送消息；修改群或链接后需要重新预览。",
                "example": sample,
            },
            {
                "chapter": "确认并开始监听",
                "target": "view.subscriptions.start",
                "text": "确认预览后点击开始监听，订阅即时保存，不需要再保存配置表单。同一群重复添加相同直播间会更新主播信息，并保留已有推送开关。",
                "example": sample,
            },
            {
                "chapter": "检查保存结果",
                "target": "view.subscriptions.status",
                "text": "新增记录出现在下方列表，可按群筛选、查看房间与最近直播状态、调整开播和下播推送、取消监听。未首次检查的房间显示未检查，不会冒充正在直播。",
                "example": {**sample, "items": [item]},
            },
            {
                "chapter": "设置本群通知",
                "target": "view.subscriptions.settings",
                "text": "本群可选择通知卡片风格、开播和下播 AI 回复，以及新订阅的默认推送开关。保存后即时生效；新订阅默认值不修改列表里已有订阅的开关，全局配置也不会覆盖已保存的群设置。",
                "example": {**sample, "items": [item]},
            },
            {
                "chapter": "确认监听健康",
                "target": "view.subscriptions.health-panel",
                "text": "最后查看轮询是否运行、最近检查和成功时间、成功与失败数量。首次检查只记录基线，之后状态变化才推送；看完演示不代表真实订阅或外部连接已经完成。",
                "example": {**sample, "items": [item]},
            },
        ],
        demo=demonstration(),
    )


def _register_chat_guide(plugin: Plugin) -> None:
    plugin.guide(
        "group-commands",
        title="群聊命令",
        steps=[
            {
                "chapter": "在目标群添加监听",
                "target": "action.subscriptions.create",
                "text": "除了直播订阅设置，也可在目标群里用命令添加。610001 是示例房间号，实际请换成自己的；房间号、短号、直播间链接和 UP 主空间链接都支持。回复会列出主播、房间号与推送开关；重复监听保留已有开关。",
                "command": {"text": "/监听 610001", "context": MANAGE_CONTEXT},
            },
            {
                "chapter": "核对本群订阅",
                "target": "resource.subscriptions",
                "text": "用监听列表核对主播、房间号、开播推送和下播推送。列表只显示当前群，其他群需要到对应群里查询。命令若因重名改了名称，可在 /help 或插件信息中核对。",
                "command": {"text": "/监听列表", "context": READ_CONTEXT},
            },
            {
                "chapter": "查看开播状态",
                "target": "action.subscriptions.health",
                "text": "开播状态会查询本群关注的主播；查询失败或超时会使用最近一次轮询结果，并标明来源。首次检查只记录状态，不会补发已经发生的开播通知；以后状态变化才按开关推送。看完说明不代表已建立订阅。",
                "command": {"text": "/开播状态", "context": READ_CONTEXT},
            },
            {
                "chapter": "查看本群设置",
                "target": "resource.subscriptions",
                "text": "这里查看本群的 AI 回复、卡片风格和新订阅默认推送。群设置通过聊天命令调整，配置表单里的 default 字段是全局默认值。",
                "command": {"text": "/config", "context": MANAGE_CONTEXT},
            },
            {
                "chapter": "关闭一条开播推送",
                "target": "action.subscriptions.toggle",
                "text": "只修改本群这个直播间的开播推送，其他订阅不受影响。要恢复，把命令末尾的关改成开。",
                "command": {"text": "/开播推送 610001 关", "context": MANAGE_CONTEXT},
            },
            {
                "chapter": "调整一条下播推送",
                "target": "action.subscriptions.toggle",
                "text": "开播和下播是两个独立开关。这里开启本群这个直播间的下播推送；只想接收开播时可以改成关。",
                "command": {"text": "/下播推送 610001 开", "context": MANAGE_CONTEXT},
            },
            {
                "chapter": "开播只发通知",
                "target": "resource.subscriptions",
                "text": "关闭本群开播通知后的 AI 回复，通知卡片仍按订阅开关发送。AI 开关只决定是否请求一次回复，不保证 AI 一定发言。",
                "command": {"text": "/config 开播AI 关", "context": MANAGE_CONTEXT},
            },
            {
                "chapter": "调整下播 AI",
                "target": "resource.subscriptions",
                "text": "下播通知后的 AI 回复单独设置；把关改成开即可请求下播后的 AI 回复。",
                "command": {"text": "/config 下播AI 关", "context": MANAGE_CONTEXT},
            },
            {
                "chapter": "选择本群卡片风格",
                "target": "resource.subscriptions",
                "text": "可选 sakura、neon、minimal 或随机。影响本群之后的通知卡片；可回到直播订阅设置预览，但预览不会向群里发消息。",
                "command": {"text": "/卡片风格 minimal", "context": MANAGE_CONTEXT},
            },
            {
                "chapter": "新订阅默认不开播推送",
                "target": "resource.subscriptions",
                "text": "只影响本群之后新增的订阅，已经监听的直播间不变。已有订阅请用开播推送命令逐条修改。",
                "command": {
                    "text": "/config 开播推送默认 关",
                    "context": MANAGE_CONTEXT,
                },
            },
            {
                "chapter": "新订阅默认开下播推送",
                "target": "resource.subscriptions",
                "text": "新订阅的默认下播推送也可独立设置。此项不批量修改已有订阅，重复监听也不会重置已有开关。",
                "command": {
                    "text": "/config 下播推送默认 开",
                    "context": MANAGE_CONTEXT,
                },
            },
            {
                "chapter": "取消本群监听",
                "target": "action.subscriptions.remove",
                "text": "取消当前群的这条订阅，其他群的监听保留。取消后可再用监听列表核对。",
                "command": {"text": "/取消监听 610001", "context": MANAGE_CONTEXT},
            },
        ],
    )


def _register_config_guide(plugin: Plugin) -> None:
    plugin.guide(
        "panel-settings",
        title="面板设置",
        steps=[
            {
                "chapter": "检查间隔与配置生效",
                "target": "config.poll_interval_seconds",
                "text": "入口是插件管理 → streaming_parser → 配置表单，也可编辑同页 TOML。这里设置全局检查间隔，范围 15–3600 秒。插件未声明配置热更新，保存后需重启 NeoBot 生效；请以全局通知中的生效结果为准。",
                "example": {"poll_interval_seconds": 60},
            },
            {
                "chapter": "默认卡片风格",
                "target": "config.default_card_style",
                "text": "全局默认可填 random、sakura、neon 或 minimal。已有群设置优先；修改此项不会覆盖群里用卡片风格命令保存的选择。",
                "example": {"default_card_style": "minimal"},
            },
            {
                "chapter": "默认开播推送",
                "target": "config.default_push_live",
                "text": "没有单独群设置时，新订阅采用这个默认值。已有订阅的开关不变；有群设置时以 /config 开播推送默认 的值为准。",
                "example": {"default_push_live": True},
            },
            {
                "chapter": "默认下播推送",
                "target": "config.default_push_live_end",
                "text": "决定新订阅默认是否推送下播，与开播开关独立。已有订阅不变；群里的下播推送默认设置优先。",
                "example": {"default_push_live_end": True},
            },
            {
                "chapter": "默认开播 AI 回复",
                "target": "config.default_ai_reply_live",
                "text": "没有群设置时，决定开播通知后是否请求一次 AI 回复。已有群设置不会被这个全局默认覆盖，本群请用 /config 开播AI 调整。",
                "example": {"default_ai_reply_live": False},
            },
            {
                "chapter": "默认下播 AI 回复",
                "target": "config.default_ai_reply_live_end",
                "text": "没有群设置时，决定下播通知后是否请求一次 AI 回复。与开播 AI 独立，本群可用 /config 下播AI 覆盖。",
                "example": {"default_ai_reply_live_end": False},
            },
            {
                "chapter": "请求超时",
                "target": "config.request_timeout",
                "text": "每次 B 站请求的超时秒数，大于 0 且不超过 60。网络不稳定时可以适度增加；此项不会改变已有订阅。",
                "example": {"request_timeout": 10.0},
            },
            {
                "chapter": "并发检查数量",
                "target": "config.poll_concurrency",
                "text": "同一轮同时检查的房间数，范围 1–16。它控制请求并发，不是允许监听的主播总数。",
                "example": {"poll_concurrency": 4},
            },
            {
                "chapter": "B 站 Cookie",
                "target": "config.cookie",
                "text": "留空表示匿名请求。需要时在真实配置字段中填写；说明书只展示空样例，不读取或展示已保存的凭据。",
                "example": {"cookie": ""},
            },
            {
                "chapter": "请求 User-Agent",
                "target": "config.user_agent",
                "text": "留空使用插件内置 User-Agent。通常无需修改；它是请求头设置，不是聊天里展示的机器人名称。",
                "example": {"user_agent": ""},
            },
            {
                "chapter": "状态总览数量",
                "target": "config.overview_max_hosts",
                "text": "控制 /开播状态 总览最多展示多少位主播，范围 1–100。超出显示上限的订阅仍会被轮询。",
                "example": {"overview_max_hosts": 30},
            },
            {
                "chapter": "图片缓存天数",
                "target": "config.asset_cache_days",
                "text": "头像和封面的本地缓存保留天数，范围 0–365。它不控制订阅保留时间，也不会取消监听。",
                "example": {"asset_cache_days": 14},
            },
            {
                "chapter": "卡片渲染超时",
                "target": "config.render_timeout",
                "text": "卡片出图的超时秒数，大于 0 且不超过 120。渲染不可用时通知可降级为文字，仍需宿主具备正常发送消息的能力。",
                "example": {"render_timeout": 30.0},
            },
            {
                "chapter": "卡片清晰度",
                "target": "config.render_scale",
                "text": "渲染倍率范围 1–4，默认 2。更高倍率会增加图片尺寸和出图开销；修改后同样需要重启 NeoBot，再看后续实际通知。",
                "example": {"render_scale": 2.0},
            },
        ],
    )
