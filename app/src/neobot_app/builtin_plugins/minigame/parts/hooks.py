"""插件注册面：agent 工具、对外能力、关键词入口与生命周期钩子。"""

from __future__ import annotations

from typing import Any
from typing import Mapping
from neobot_modloader import IncomingEvent, starts_with

from .constants import KEYWORDS, PACKAGE_BASE, RANK_PAGE_SIZE, _MG_COMMAND_RE
from .registration import plugin
from .utils import _event_text


# ── agent 工具（每个玩法都有说明 + 可调用工具，R15）───────────────
# 工具最终名 = {plugin}__{local} = minigame__<local>。
# user_id / user_name 是**可选**参数：省略时用最近一次交互（命令或关键词入口
# 记录）来认人 —— 插件工具没有入站事件，这是唯一可靠的认人方式。


@plugin.tool(
    "bottle_write",
    package="bottle",
    description=(
        "把一句话装进漂流瓶丢进全局瓶池。content 是正文（去空白后 1-500 字，"
        "禁止纯链接，支持 Markdown）；anonymous=true 表示匿名（不显示 QQ 与昵称、"
        "昵称位固定「神秘的人」，但头像照常显示）。瓶子发出后不可查询、不可撤回。"
    ),
)
async def _tool_bottle_write(
    content: str,
    anonymous: bool = False,
    user_id: str = "",
    user_name: str = "",
) -> str:
    runtime = _runtime()
    game: Any = runtime.game_by_id("bottle")
    if game is None:
        return "小游戏未启用「漂流瓶」玩法（插件配置 enabled_games 不含 bottle）。"
    request = runtime.tool_request(user_id=user_id, user_name=user_name, game="bottle")
    if request is None:
        return runtime.NEED_IDENTITY_HINT
    result = await game.write(request, anonymous=bool(anonymous), content=str(content or ""))
    return result or "已发瓶。"


@plugin.tool(
    "bottle_pick",
    package="bottle",
    description=(
        "从全局瓶池随机捞一个别人丢的漂流瓶。会自动排除自己，以及你最近 3 次"
        "捞到过的发送者；因排除而无瓶可捞时会回落普通随机并在结果里说明。"
        "每日捞瓶有上限，捞取没有冷却。"
    ),
)
async def _tool_bottle_pick(user_id: str = "", user_name: str = "") -> str:
    runtime = _runtime()
    game: Any = runtime.game_by_id("bottle")
    if game is None:
        return "小游戏未启用「漂流瓶」玩法（插件配置 enabled_games 不含 bottle）。"
    request = runtime.tool_request(user_id=user_id, user_name=user_name, game="bottle")
    if request is None:
        return runtime.NEED_IDENTITY_HINT
    result = await game.pick(request)
    return result or "已捞取。"


@plugin.tool(
    "checkin",
    package="checkin",
    description=(
        "每日签到：由程序随机给 1-10 积分（连续签到每天附加 +1，上限 +5）。"
        "同一自然日重复签到**不加分**，只会返回既有结果；断签后连续天数归零，"
        "不提供补签。签到结果请由你用自然语言转述给用户。"
    ),
)
async def _tool_checkin(user_id: str = "", user_name: str = "") -> str:
    runtime = _runtime()
    game: Any = runtime.game_by_id("checkin")
    if game is None:
        return "小游戏未启用「签到」玩法（插件配置 enabled_games 不含 checkin）。"
    request = runtime.tool_request(user_id=user_id, user_name=user_name, game="checkin")
    if request is None:
        return runtime.NEED_IDENTITY_HINT
    result = await game.do_checkin(request)
    return result or "已签到。"


@plugin.tool(
    "fortune",
    package="fortune",
    description=(
        "抽今日运势（每天一次，由程序随机并落库）。当天已抽过不会重抽，只返回"
        "同一结果。默认五档：大吉 / 吉 / 中吉 / 小吉 / 平；管理员可配置加入"
        "小凶 / 凶。抽签不附带积分；请由你用自然语言把这个结果讲给用户。"
    ),
)
async def _tool_fortune(user_id: str = "", user_name: str = "") -> str:
    runtime = _runtime()
    game: Any = runtime.game_by_id("fortune")
    if game is None:
        return "小游戏未启用「抽签」玩法（插件配置 enabled_games 不含 fortune）。"
    request = runtime.tool_request(user_id=user_id, user_name=user_name, game="fortune")
    if request is None:
        return runtime.NEED_IDENTITY_HINT
    result = await game.draw(request)
    return result or "已抽签。"


@plugin.tool(
    "points",
    package=PACKAGE_BASE,
    description=(
        "查看用户的积分与连续签到天数。积分由玩小游戏（签到 / 漂流瓶 / 成语接龙）"
        "或其它插件的功能产生；本工具**只读**，你不能用它增减积分。"
    ),
)
async def _tool_points(user_id: str = "", user_name: str = "") -> str:
    runtime = _runtime()
    resolved, _name = runtime.resolve_user(user_id, user_name)
    if not resolved or runtime.service is None:
        return runtime.NEED_IDENTITY_HINT
    return await runtime.points_text(resolved)


@plugin.tool(
    "help",
    package=PACKAGE_BASE,
    description=(
        "查看某个小游戏的规则与边界。game 取 bottle / chengyu / checkin / fortune"
        "（也接受中文名，如 漂流瓶 / 成语接龙 / 签到 / 抽签）；留空返回全部玩法说明。"
    ),
)
async def _tool_help(game: str = "") -> str:
    runtime = _runtime()
    return runtime.help_command(str(game or ""))


@plugin.tool(
    "chengyu_submit",
    package="chengyu",
    description=(
        "成语接龙记一步：**不校验内容**（是否算成语、接不接得上、是否重复都由你判断），"
        "只把 word 记入本局流水、计一步、按配置 +1 分，并返回进度（第 k/N 条）。"
        "单局最多 10 步、每条 60 秒，用满步数或超时即结束本局；达成目标 N 额外 +N。"
    ),
)
async def _tool_chengyu_submit(word: str, user_id: str = "", user_name: str = "") -> str:
    runtime = _runtime()
    game: Any = runtime.game_by_id("chengyu")
    if game is None:
        return "小游戏未启用「成语接龙」玩法（插件配置 enabled_games 不含 chengyu）。"
    request = runtime.tool_request(user_id=user_id, user_name=user_name, game="chengyu")
    if request is None:
        return runtime.NEED_IDENTITY_HINT
    result = await game.submit(request, str(word if word is not None else ""))
    return result or "已记录。"


# ── 对外能力：其它插件通过 ctx.require_plugin("minigame").call(...) 读写积分 ──
# 契约（四个能力的入参与返回）见 docs/07-插件开发.md「调用其它插件的功能」与
# docs/04-功能文档/小游戏.md「对外能力」。要点：
#   * 只在这里开放「增减积分」；**不新增模型工具**，模型无法自行给自己加分；
#   * 参数非法抛 ValueError，可预期的业务结果（余额不足 / 总开关关闭）用返回值表达；
#   * user_id 一律是数字 QQ 号，与玩法侧的账户口径一致。


def _points_payload(payload: Any) -> dict[str, Any]:
    return payload if isinstance(payload, dict) else {}


def _points_user_id(data: Mapping[str, Any]) -> str:
    """取出并校验 user_id（数字 QQ 号；长度与 mg_profile.user_id 对齐）。"""
    uid = str(data.get("user_id") or "").strip()
    if not uid:
        raise ValueError("缺少 user_id")
    if not uid.isdigit() or len(uid) > 32:
        raise ValueError(f"user_id 必须是数字 QQ 号（收到 {uid!r}）")
    return uid


def _points_int(data: Mapping[str, Any], key: str, *, default: Any = None) -> int:
    """整数入参：不接受 bool，也不接受带小数部分的浮点（避免 1.5 被悄悄截断成 1）。"""
    if key not in data:
        if default is None:
            raise ValueError(f"缺少 {key}")
        return int(default)
    raw = data[key]
    if isinstance(raw, bool):
        raise ValueError(f"{key} 必须是整数（收到 {raw!r}）")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} 必须是整数（收到 {raw!r}）") from exc
    if isinstance(raw, float) and not float(raw).is_integer():
        raise ValueError(f"{key} 必须是整数（收到 {raw!r}）")
    return value


def _points_flag(data: Mapping[str, Any], key: str, *, default: bool = False) -> bool:
    """布尔入参：字符串形态也接受，但写错的字符串必须报错而不是当 True。"""
    if key not in data:
        return default
    value = data[key]
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in ("", "0", "false", "no", "off"):
        return False
    if text in ("1", "true", "yes", "on"):
        return True
    raise ValueError(f"{key} 必须是布尔值（收到 {value!r}）")


@plugin.capability("points.get")
async def _capability_points_get(payload: Any) -> dict[str, Any]:
    """查询某个用户的积分档案（积分 / 最高分 / 场次 / 胜场 / 连续签到 / 今日是否签到）。

    用法::

        handle = ctx.require_plugin("minigame", ">=1.0.0")
        data = await handle.call("points.get", {"user_id": "2002"})
    """
    data = _points_payload(payload)
    return await _runtime().points_snapshot(_points_user_id(data))


@plugin.capability("points.add")
async def _capability_points_add(payload: Any) -> dict[str, Any]:
    """增减某个用户的积分（唯一写入口）。

    入参：user_id（必填，数字 QQ 号）、delta（必填，整数，可负）、
    source（哪个插件 / 功能加的，写日志用）、note（说明）、
    allow_negative（默认 false：扣分不允许把余额扣成负数，余额不足整笔不生效）、
    play / win（是否同时累计场次 / 胜场）。

    用法::

        await handle.call("points.add", {
            "user_id": "2002", "delta": -30, "source": "shop", "note": "买道具",
        })
    """
    data = _points_payload(payload)
    return await _runtime().adjust_points(
        user_id=_points_user_id(data),
        delta=_points_int(data, "delta"),
        source=str(data.get("source") or ""),
        note=str(data.get("note") or ""),
        allow_negative=_points_flag(data, "allow_negative"),
        play=_points_flag(data, "play"),
        win=_points_flag(data, "win"),
    )


@plugin.capability("points.rank")
async def _capability_points_rank(payload: Any) -> dict[str, Any]:
    """查询积分排行榜：不传 conversation_id 查全局榜，传了就查该会话的本群榜。

    用法::

        await handle.call("points.rank", {"page": 1, "page_size": 10})
        await handle.call("points.rank", {"conversation_id": "888"})
    """
    data = _points_payload(payload)
    return await _runtime().points_rank(
        page=_points_int(data, "page", default=1),
        page_size=_points_int(data, "page_size", default=RANK_PAGE_SIZE),
        conversation_id=str(data.get("conversation_id") or ""),
    )


@plugin.capability("points.describe")
async def _capability_points_describe(payload: Any) -> dict[str, Any]:
    """积分接口自描述：接口名 / 版本 / 能力清单 / 单次上限 / 当前写开关。"""
    return _runtime().describe_points_api()


def _command_rule(event: dict[str, Any]) -> bool:
    """只对本插件的命令文本登记「预激活」意图（不消费、不改写消息）。"""
    return _MG_COMMAND_RE.match(_event_text(event).strip()) is not None


@plugin.message(
    keywords=tuple(KEYWORDS),
    rule=~starts_with("/"),
    priority=10,
)
async def _minigame_keyword_entry(ctx: Any, incoming: IncomingEvent) -> str:
    return _runtime().on_keyword(ctx, dict(incoming.raw))


@plugin.event(
    post_type="message",
    rule=_command_rule,
    priority=9,
)
async def _minigame_command_intent_entry(ctx: Any, incoming: IncomingEvent) -> str:
    """命令入口的预激活声明（背景仍由本体命令结果提供）。"""
    return _runtime().on_command_intent(ctx, dict(incoming.raw))


# ── 生命周期 ──────────────────────────────────────────────────


@plugin.on_load
async def _minigame_load(ctx: Any) -> None:
    await _runtime().load(ctx)


@plugin.on_shutdown
async def _minigame_shutdown() -> None:
    await _runtime().unload()


_runtime_provider = None


def bind_runtime(provider):
    """由入口模块注入「当前插件实例」的取值函数（测试会替换 minigame._instance）。"""
    global _runtime_provider
    _runtime_provider = provider


def _runtime():
    return _runtime_provider()
