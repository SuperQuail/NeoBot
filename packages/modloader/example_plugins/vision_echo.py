"""Example plugin for image-aware commands and message-chain replies."""

from neobot_modloader import ImageSegment, Message, MessageChain, Plugin, Reply

plugin = Plugin(
    "vision_echo",
    description="Image command and message-chain reply demo",
    usage="/识图 <image> | /say <text> | echo",
)


@plugin.command("识图 <img:image>")
async def vision(img: ImageSegment, reply: Reply) -> None:
    """Match a command followed by one image segment."""
    await reply.send(
        MessageChain()
        .text("收到图片: ")
        .image(url=img.url, file=img.file)
    )


@plugin.command("say [content:rest]")
async def say(content: str | None, reply: Reply) -> None:
    """Capture the rest of the text after /say."""
    await reply.send(content or "你还没有输入内容")


@plugin.message(text="echo")
async def echo(message: Message, reply: Reply) -> None:
    """Reply with the original message chain."""
    await reply.send(message)


@plugin.message("复读 <img:image>")
async def repeat_image(img: ImageSegment, reply: Reply) -> None:
    """Message-level DSL can match image segments too."""
    await reply.send(img)
