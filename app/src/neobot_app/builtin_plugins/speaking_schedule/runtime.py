"""Runtime instance and configuration consumer owned by a plugin load."""

import tomlkit
from neobot_app.config.hot_reload import HotReloadRule
from neobot_contracts.ports.speaking import SpeakingDecision
from .config import ScheduleConfig
from .schedule import evaluate, next_boundary
from .state import ClockHealth, MuteStore, atomic_write, utc_now


def update_document(doc, values):
    """Keep comments on unchanged tables, including unrelated overrides."""
    for key, value in values.items():
        current = doc.get(key)
        if current == value:
            continue
        if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            result = tomlkit.aot()
            for item in value:
                existing = next((table for table in (current or []) if table == item), None)
                result.append(existing if existing is not None else tomlkit.item(item))
            doc[key] = result
        else:
            doc[key] = tomlkit.item(value)


class ScheduleRuntime:
    name = "speaking_schedule"
    config_paths = ("plugin.speaking_schedule",)
    hot_reload_policies = tuple(
        HotReloadRule("plugin.speaking_schedule." + key, True, "发言策略即时更新")
        for key in ("timezone", "windows", "overrides")
    )

    def __init__(self, ctx):
        self.ctx = ctx
        self.config = ScheduleConfig.model_validate(
            ctx.config.model_dump() if hasattr(ctx.config, "model_dump") else dict(ctx.config)
        )
        self.registry = ctx.plugin_host.services.require("speaking_policy")
        self.mutes = MuteStore(ctx.data_dir / "mutes.json")
        self.clock = ClockHealth()

    @property
    def account(self):
        config = self.ctx.plugin_host.services.get("config")
        account = str(getattr(getattr(config, "bot", None), "account", "") or "")
        self.clock.select_account(account)
        return account

    async def apply_config(self, config):
        updated = ScheduleConfig.model_validate(config)
        self.config = updated
        self.ctx.config.clear()
        self.ctx.config.update(updated.model_dump())

    async def save_config(self, config):
        updated = ScheduleConfig.model_validate(config)
        path = self.ctx.data_dir / "config.toml"
        doc = tomlkit.parse(path.read_text(encoding="utf-8-sig")) if path.exists() else tomlkit.document()
        update_document(doc, updated.model_dump())
        atomic_write(path, tomlkit.dumps(doc))
        await self.apply_config(updated.model_dump())

    def remaining(self, conversation):
        return max(
            self.mutes.remaining(self.account, "default"),
            self.mutes.remaining(self.account, f"{conversation.kind}:{conversation.id}"),
        )

    def evaluate(self, conversation):
        if self.remaining(conversation) > 0:
            return SpeakingDecision(False, "临时静默")
        return evaluate(self.config, conversation, utc_now())

    async def sample(self, event):
        previous = self.clock.health
        self.clock.sample(event, self.account, utc_now().timestamp())
        if self.clock.health != previous and "异常" in self.clock.health:
            self.ctx.logger.warning(self.clock.health)

    def status(self, conversation):
        decision = self.evaluate(conversation)
        boundary = next_boundary(self.config, conversation, utc_now())
        return (
            f"作息：{'允许发言' if decision.allowed else decision.reason}\n"
            f"时区：{self.config.timezone}\n下一日程边界：{boundary.isoformat() if boundary else '无'}\n"
            f"静默剩余：{self.remaining(conversation):.0f}秒\n时间健康：{self.clock.status()}"
        )

    def register_commands(self):
        from .commands import run_command

        if self.ctx.app_commands.available:

            @self.ctx.app_commands.register(
                "作息", permission=1, description="管理发言时段与临时静默", usage="状态 / 设置 / 静默 / 恢复"
            )
            async def command(command_ctx):
                await run_command(self, command_ctx)
