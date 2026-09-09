"""综合示例插件：命令 + 工具 + 子 Agent + SKILL.md。"""

from __future__ import annotations

from pydantic import BaseModel

from neobot_modloader import AgentRequest, Plugin, Reply


class Config(BaseModel):
    default_city: str = "Shanghai"


plugin = Plugin(
    "full_plugin",
    version="1.0.0",
    description="Demo: commands, tools, sub-agents and SKILL.md",
    config=Config,
)


# ── 命令 ──────────────────────────────────────────────────────────


@plugin.command("weather [city:rest]")
async def weather_command(city: str | None, config: Config, reply: Reply) -> None:
    await reply.send(f"{city or config.default_city}: 晴")


# ── 工具（主 Agent 可直接调用）─────────────────────────────────────


@plugin.tool("query", description="查询指定城市的天气")
async def query_weather(city: str, days: int = 1) -> str:
    return f"{city} 未来 {days} 天晴，22-28 度"


@plugin.tool("alert", description="当出现极端天气时发送提醒")
async def alert_weather(city: str, reason: str) -> str:
    return f"已提醒 {city}: {reason}"


# ── 子 Agent（主 Agent 可委托）────────────────────────────────────


@plugin.agent("advice", description="根据天气情况给出出行建议")
async def advice_agent(task: str, request: AgentRequest, config: Config) -> str:
    return f"建议（{config.default_city}）: {task}"


# ── 生命周期 ──────────────────────────────────────────────────────


@plugin.on_load
async def loaded(ctx) -> None:
    ctx.logger.info("full_plugin 已加载")
