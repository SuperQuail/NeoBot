"""ImageParseSkill 的元信息、工具声明与分发入口。"""

from __future__ import annotations

from typing import Any

from .helpers import _json
from .handlers import _HANDLERS

class ImageParseSkillBase:

    @property
    def name(self) -> str:
        return "image_parse"

    @property
    def description(self) -> str:
        return "图片内容解析：按需求解析图片，支持本地路径/URL/base64/消息ID"

    @property
    def instructions(self) -> str:
        return (
            "图片解析 Skill 提供以下能力：\n\n"
            "## parse_image\n"
            "按指定需求解析图片内容，支持多种图片来源：\n"
            "  - image_path — 本地图片路径（推荐，与沙箱系统协作）\n"
            "  - image_url — HTTP/data/file URL\n"
            "  - image_base64 — base64 编码图片\n"
            "  - msg_number — **推荐**，聊天记录中显示的消息编号（如「75: 用户名: [图片]」中的 75）\n"
            "  - chat_flow_id + image_index — 通过聊天流 ID 和图片编号定位\n"
            "  - message_id — OneBot 消息 ID（不常用，勿将显示编号当作 message_id 传入）\n\n"
            "【msg_number 选择规则 — 关键，请认真阅读】\n"
            "  1. 如果用户**回复了某条消息**（聊天记录中形如\"N: [被回复消息] 发送者: [图片]\"),\n"
            "     请使用 **被回复消息的编号 N**，而非用户回复消息的编号!\n"
            "     用户回复消息的编号对应的是用户发送的文字（无图片），解析它是没有意义的。\n"
            "     示例：聊天记录中显示：\n"
            "       1: [被回复消息] 小明: [图片]\n"
            "       6: 唐天: [回复:消息ID=xxx] @bot 解析这张图\n"
            "     → 正确做法: msg_number=1（被回复消息，含图片）\n"
            "     → 错误做法: msg_number=6（唐天的消息，仅含文字回复引用的内容）\n"
            "  2. 如果用户直接发了一张图（聊天记录中形如\"N: 用户名: [图片]\"),\n"
            "     直接用该消息的编号 N。\n"
            "  3. 如果消息中含多张图片，用 image_indices 数组（0-based）而非多次调用。\n\n"
            "parse_image 为会话工具(session模式)：\n"
            "  - 调用后立即返回 session_submitted，实际解析在后台进行\n"
            "  - timeout_seconds 默认为 300 秒（5分钟），agent 可按需设置，最长 1800 秒（30分钟）\n"
            "  - 收到返回后请立即结束本轮回复，不要继续调用其他工具或使用 wait\n"
            "  - 系统会在解析完成后通过通知自动唤醒你，届时携带解析结果\n\n"
            "多张图片（推荐用法，省 API 调用）：\n"
            "  - 同一消息多张图：msg_number + image_indices=[0,1,2]（0-based）一次解析\n"
            "  - 多个 URL：image_url_list=[...] \n"
            "  - 多个本地路径：image_path_list=[...] \n"
            "  - 多图时返回 {ok:true, descriptions:[{index,ok,description/error},...], full_text, errors}\n"
            "  - 单图保持原 {ok, description} 兼容格式\n\n"
            "仅负责解析回传结果，不保存、不导入、不管理图库/表情包。"
        )

    @property
    def session_tools(self) -> set[str]:
        return {"parse_image"}

    def __init__(
        self,
        vision_provider: Any = None,
        adapter: Any = None,
        group_message_queue: Any = None,
        friend_message_queue: Any = None,
    ) -> None:
        self._vision_provider = vision_provider
        self._adapter = adapter
        self._group_queue = group_message_queue
        self._friend_queue = friend_message_queue

    def install_vision_provider(self, provider: Any) -> Any:
        """换用新的视觉 provider，返回旧的（热重载：只换引用，不负责关闭旧对象）。

        issue #75：技能在启动期建好后一直持有视觉 provider，而且**真的在用**
        （解析图片内容）—— 换模型后不推给它，就会一直用旧的。
        """
        previous = self._vision_provider
        self._vision_provider = provider
        return previous

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        return [
            self._tool_def(
                "parse_image",
                "【会话工具】解析一张或多张图片的内容。"
                "⚠️ 用户回复某条消息要求「解析这张图」时，msg_number 应为"
                "**被回复消息**（带\"[被回复消息]\"前缀的那行）的编号，而非用户自己的回复编号!\n"
                "支持 image_path（本地图片路径）、image_url（HTTP/data/file URL）、image_base64（base64编码）、"
                "msg_number（聊天记录中的消息编号，如「75: 用户名: [图片]」中的 75）、"
                "chat_flow_id+image_index（聊天流ID+图片编号）。\n"
                "多张图片：可传 image_indices 数组（从0开始）、image_url_list、image_path_list 一次解析多张，"
                "返回 descriptions 列表；单张时返回 description 字段以兼容旧调用。",
                {
                    "properties": {
                        "requirement": {
                            "type": "string",
                            "description": "解析要求，例如「请简洁描述这张图片的主要内容」",
                            "default": "请简洁描述这张图片的主要内容。",
                        },
                        "image_path": {"type": "string", "description": "可选，本地图片路径"},
                        "image_url": {"type": "string", "description": "可选，图片 HTTP/file/data URL"},
                        "image_base64": {"type": "string", "description": "可选，base64 编码的图片数据"},
                        "image_path_list": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "可选，一次解析多个本地图片路径",
                        },
                        "image_url_list": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "可选，一次解析多个图片 URL",
                        },
                        "mime_type": {"type": "string", "description": "可选，图片 MIME 类型，默认 image/png"},
                        "msg_number": {"type": "integer", "description": "可选，聊天记录中的消息编号（如「75: xxx: [图片]」中的75）。用户回复引用图片时，请使用被回复消息（[被回复消息]行）的编号，不是用户回复的编号。"},
                        "message_id": {"type": "integer", "description": "可选，OneBot 消息 ID（不常用，优先使用 msg_number）"},
                        "chat_flow_id": {"type": "string", "description": "可选，聊天流 ID（如 Group_12345），与 image_index 配合使用"},
                        "image_index": {"type": "integer", "description": "可选，图片编号（从0开始），与 chat_flow_id / msg_number / message_id 配合使用", "default": 0},
                        "image_indices": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "可选，一张消息内多张图片时，传入多个 image_index（从0开始）一起解析；与 msg_number / message_id / chat_flow_id 配合使用",
                        },
                        "timeout_seconds": {"type": "integer", "description": "可选，下载超时秒数，默认 300（5分钟），最长 1800（30分钟）", "default": 300},
                    },
                    "required": [],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown image_parse tool: {tool_name}"})
        return await handler(self, args)
