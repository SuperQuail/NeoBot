"""Example plugin demonstrating the Plugin API."""

from neobot_modloader import Message, Plugin, Reply

plugin = Plugin(
    "ping",
    description="Ping-pong demo for the Plugin API",
    usage="/ping [args]",
)


@plugin.command("ping [args:rest]")
async def ping(args: str | None, reply: Reply) -> None:
    await reply.send(f"pong! args: {args}" if args else "pong!")


@plugin.message(text="ping")
async def keyword_ping(message: Message, reply: Reply) -> None:
    await reply.send(message)
