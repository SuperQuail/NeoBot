"""插件常量：工具前缀、关键词表、积分接口标识与菜单页脚。"""

from __future__ import annotations

import re


#: 最终工具名的前缀：框架按 {plugin}__{tool} 生成（插件名 = minigame）
TOOL_PREFIX = "minigame"

#: 关键词 -> 玩法 id（D11：插件消息处理器承接，不改造本体启动期关键词快照）
KEYWORDS: dict[str, str] = {
    "漂流瓶": "bottle",
    "丢瓶子": "bottle",
    "捞瓶子": "bottle",
    "成语接龙": "chengyu",
    "接龙": "chengyu",
    "签到": "checkin",
    "打卡": "checkin",
    "抽签": "fortune",
    "今日运势": "fortune",
    "运势": "fortune",
}

#: 交互上下文的有效期（秒）：工具通道没有入站事件，只能靠最近一次交互认人
INTERACTION_TTL_SECONDS = 300.0

#: 排行榜每页条数
RANK_PAGE_SIZE = 10

#: 积分对外接口（其它插件调用）的接口名与版本：进 points.describe，便于调用方做兼容判断
POINTS_API_NAME = "minigame.points"

POINTS_API_VERSION = 1

#: points.rank 单页条数上限（避免调用方一次拉太多）
POINTS_RANK_MAX_PAGE_SIZE = 100

MENU_FOOTER = (
    "其他：/mg rank [页码] 排行榜 · /mg 积分 查积分 · /mg help <游戏> 规则 · "
    "/mg stop 结束当前会话局\n"
    "也可以直接对我说话（例如「我想玩漂流瓶」「签到」「抽签」），由我陪你玩。"
)

#: 通用工具（规则查询 / 积分查询）所在的工具包名
PACKAGE_BASE = "base"

# ── 关键词 / 意图入口（插件消息处理器；不拦截 AI 回复）────────────
# R14 / D11：入口实现放在插件消息处理器里，不改造本体启动期关键词快照。
# 命中后经 ctx.agent_reply(background, preactivate=[...]) 把控制权交回主回复
# 管线，并**按玩法**预激活对应技能包（见 neobot_modloader.agent_intent）。

#: 小游戏命令文本（含 /游戏 别名）
_MG_COMMAND_RE = re.compile(r"^/(?:mg|游戏)\s*(.*)$", re.IGNORECASE | re.DOTALL)
