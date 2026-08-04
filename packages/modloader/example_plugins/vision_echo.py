"""支持图片识别命令与消息链回复的示例插件。"""

from neobot_modloader import ImageSegment, Message, MessageChain, Plugin, Reply

plugin = Plugin(
    "vision_echo",
    description="Image command and message-chain reply demo",
    usage="/识图 <image> | /say <text> | echo",
)


@plugin.command("识图 <img:image>")
async def vision(img: ImageSegment, reply: Reply) -> None:
    """匹配一个命令后跟随一张图片段的格式。"""
    await reply.send(
        MessageChain()
        .text("收到图片: ")
        .image(url=img.url, file=img.file)
    )


@plugin.command("say [content:rest]")
async def say(content: str | None, reply: Reply) -> None:
    """捕获 /say 之后的剩余文本。"""
    await reply.send(content or "你还没有输入内容")


@plugin.message(text="echo")
async def echo(message: Message, reply: Reply) -> None:
    """原样回复原始消息链。"""
    await reply.send(message)


@plugin.message("复读 <img:image>")
async def repeat_image(img: ImageSegment, reply: Reply) -> None:
    """消息级 DSL 同样支持匹配图片段。"""
    await reply.send(img)
