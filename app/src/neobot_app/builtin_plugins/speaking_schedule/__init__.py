"""Official opt-in speaking schedule; each load owns its runtime state."""

from neobot_modloader import Plugin
from neobot_modloader.context import RuntimePluginContext
from neobot_modloader.hooks import HookSubscription
from .config import ScheduleConfig

plugin = Plugin("speaking_schedule", version="1.0.0", config=ScheduleConfig, config_hot_reload=True)


@plugin.on_load
async def load(ctx: RuntimePluginContext):
    from .runtime import ScheduleRuntime

    runtime = ScheduleRuntime(ctx)
    ctx.record_subscription(HookSubscription(runtime.registry.register("speaking_schedule", runtime.evaluate)))
    ctx.record_subscription(ctx.hook_bus.subscribe(runtime.sample))
    ctx.plugin_control.register_config_consumer(ctx.plugin_name, runtime)
    runtime.register_commands()
