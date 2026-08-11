"""VisionDetectSkill:基于本地 YOLO 模型的图像检测工具。

- list_models:查看可用模型清单(含能力描述),agent 依据描述选择模型
- detect:必须指定 model,只检测 agent 选择的模型(不做全量检测)
- 图片来源解析统一走 neobot_app.image.source(与 parse_image/emoji_add 一致)
- 双推理栈:.onnx 走 onnxruntime(毫秒级);.pt 走 PyTorch/ultralytics
  (onnxruntime 不可用环境的备选方案,如虚拟机未透传 CPU 指令集)
- 模型库不可用(两推理栈均缺失/无模型)时不暴露工具
"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.image.source import ImageSourceResolver
from neobot_app.skills.base import SkillModule
from neobot_app.vision_detect.service import VisionDetectService

_MAX_IMAGE_TIMEOUT = 30.0


class VisionDetectSkill(SkillModule):
    """视觉检测 Skill — 用本地模型检测图片中是否包含特定目标。"""

    def __init__(
        self,
        service: VisionDetectService,
        adapter: Any = None,
        group_message_queue: Any = None,
        friend_message_queue: Any = None,
    ) -> None:
        self._service = service
        # 统一的图片来源解析(消息编号/聊天流ID/消息ID回源/path/URL/base64)
        self._resolver = ImageSourceResolver(
            adapter=adapter,
            group_message_queue=group_message_queue,
            friend_message_queue=friend_message_queue,
        )

    @property
    def name(self) -> str:
        return "vision_detect"

    @property
    def description(self) -> str:
        return "视觉检测：用本地 YOLO 模型检测图片中是否包含特定目标（如机器人自身形象）"

    @property
    def instructions(self) -> str:
        if not self._service.available:
            # 服务不可用(推理引擎缺失/无模型):不注入说明,避免引导调用不存在的工具
            return ""
        return (
            "视觉检测 Skill 提供以下能力：\n\n"
            "## list_models\n"
            "查看当前可用的检测模型清单（模型 id、能力描述、可检测的目标类别）。\n"
            "**使用 detect 之前应先调用 list_models，根据模型描述选择最合适的模型，"
            "并把模型 id 传给 detect 的 model 参数。**\n\n"
            "## detect\n"
            "用**指定模型**检测图片中是否包含特定目标。model 参数为必填（先调用 list_models 查看可用模型）。\n"
            "图片来源（任选其一）：\n"
            "  - msg_number — **推荐**，聊天记录中显示的消息编号（如「75: 用户名: [图片]」中的 75）\n"
            "  - image_path — 本地图片路径\n"
            "  - image_url — HTTP/file/data URL\n"
            "  - image_base64 — base64 编码图片（仅限小图）\n"
            "  - chat_flow_id + image_index — 聊天流 ID + 图片编号\n"
            "  - message_id — OneBot 消息 ID\n"
            "【msg_number 选择规则】\n"
            "  - 用户回复了某条消息（聊天记录形如「N: [被回复消息] 发送者: [图片]」）时，"
            "    使用**被回复消息**的编号 N。用户那条回复本身通常只有文字（无图），解析它没有意义。\n"
            "    示例：聊天记录中「1: [被回复消息] 小明: [图片]」「6: 唐天: [回复:…] @bot 看看这张图」，"
            "    应取 msg_number=1 而非 6。\n"
            "  - 用户直接发的图片，使用该消息的编号\n"
            "  - 消息含多张图片时，用 image_index 指定第几张（0-based）；"
            "只给 msg_number 不指定 image_index 时默认取第 0 张\n"
            "【显示模式 mode】\n"
            "  - filter（默认）：按置信度阈值筛查，只显示达到阈值的目标。"
            "阈值可用 min_conf 自行设定（0.0-1.0），不传则用模型默认阈值，传 0 输出全部候选；"
            "用于回答「这张图里有没有 X」「哪些图检出 X」这类问题。\n"
            "  - all：不筛查，显示模型输出的全部检测结果（可能包含大量低置信度目标，"
            "其中多数为噪声），用于需要完整观察所有候选位置的场景；此模式下 min_conf 不生效。\n"
            "detect 为同步工具，调用后直接返回结果，无需等待通知。\n"
            "返回格式：{ok, mode, elapsed_ms, checked_models, failed_models, "
            "results:[{model, model_name, detections:[{name, conf, box:[x1,y1,x2,y2]}]}], summary}；\n"
            "box 为原图像素坐标；summary 为中文摘要，可直接据此判断。\n"
            "filter 模式未检出时摘要会标注阈值，如用户追问可降低 min_conf 复查；"
            "置信度低于 60% 的结果应视为「疑似」，向用户表述用「可能/看起来像」等概率语气。"
        )

    def reset(self) -> None:
        pass

    # ── 工具定义 ──

    def get_tools(self) -> list[dict]:
        if not self._service.available:
            return []
        models = self._service.list_models()
        if not models:
            return []
        return [
            self._tool_def(
                "list_models",
                "查看当前可用的本地检测模型清单（模型 id、名称、能力描述、可检测类别）。"
                "使用 detect 前应先调用本工具，根据模型描述选择最合适的模型，"
                "再把模型 id 传给 detect 的 model 参数。",
                {
                    "properties": {},
                },
            ),
            self._tool_def(
                "detect",
                "用指定模型检测图片中是否包含特定目标（如机器人自身形象、特定角色形象）。\n"
                "model 为必填：先调用 list_models 查看可用模型与各自描述，选择最合适的模型 id"
                "（模型清单可能随运行变化，以 list_models 实时输出为准）。\n"
                "mode=filter（默认）按置信度阈值筛查，只显示达标目标，阈值用 min_conf 设定（0.0-1.0，"
                "不传用模型默认阈值，传 0 输出全部候选）；"
                "mode=all 不筛查，显示全部检测结果（可能含低置信度，此时 min_conf 不生效；"
                "all 模式下大量低置信度结果多为噪声，转述以高置信度结果为主）。",
                {
                    "properties": {
                        "model": {
                            "type": "string",
                            "description": "必填，模型 id（先调用 list_models 查看可用模型与描述）",
                        },
                        "image_path": {"type": "string", "description": "可选，本地图片路径"},
                        "image_url": {"type": "string", "description": "可选，图片 HTTP/file/data URL"},
                        "image_base64": {"type": "string", "description": "可选，base64 编码的图片数据（仅限小图）"},
                        "msg_number": {
                            "type": "integer",
                            "description": "可选，聊天记录中显示的消息编号（如「75: 用户名: [图片]」中的 75）；"
                            "用户回复某条含图消息时请用被回复消息的编号；聊天中的图片优先使用本参数",
                        },
                        "chat_flow_id": {"type": "string", "description": "可选，聊天流 ID（Group_xxx / Friend_xxx），配合 image_index 使用"},
                        "message_id": {"type": "integer", "description": "可选，OneBot 消息 ID（不常用，勿将显示编号当作 message_id 传入）"},
                        "image_index": {"type": "integer", "description": "可选，消息中第几张图（0-based），默认 0", "default": 0},
                        "mode": {
                            "type": "string",
                            "enum": ["filter", "all"],
                            "default": "filter",
                            "description": "可选，显示模式：filter=按置信度阈值筛查，只显示达标目标（默认）；all=不筛查，显示全部检测结果（可能含低置信度）",
                        },
                        "min_conf": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                            "description": "可选，filter 模式下的置信度阈值（0.0-1.0），不传则用模型默认阈值，传 0 输出全部候选",
                        },
                    },
                    "required": ["model"],
                },
            ),
        ]

    # ── 执行 ──

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        if tool_name == "list_models":
            return await self._execute_list_models()
        if tool_name != "detect":
            return json.dumps(
                {"ok": False, "error": f"unknown vision_detect tool: {tool_name}"},
                ensure_ascii=False,
            )
        return await self._execute_detect(args)

    async def _execute_list_models(self) -> str:
        models = self._service.list_models()
        items = []
        for model in models:
            items.append(
                {
                    "id": model["id"],
                    "name": model["name"],
                    "description": model["description"],
                    "classes": list(model["classes"]),
                    "conf": model["conf"],
                }
            )
        return json.dumps(
            {"ok": True, "total": len(items), "models": items},
            ensure_ascii=False,
        )

    async def _execute_detect(self, args: dict[str, Any]) -> str:
        raw_model = args.get("model")
        if not isinstance(raw_model, str) or not raw_model.strip():
            return json.dumps(
                {
                    "ok": False,
                    "error": "缺少 model 参数：请先调用 list_models 查看可用模型，"
                    "再传入最合适的模型 id",
                },
                ensure_ascii=False,
            )
        mode = args.get("mode", "filter")
        if mode not in ("filter", "all"):
            return json.dumps(
                {"ok": False, "error": f"mode 必须是 filter 或 all,收到: {mode!r}"},
                ensure_ascii=False,
            )
        min_conf = args.get("min_conf")
        if min_conf is not None:
            if not isinstance(min_conf, (int, float)) or isinstance(min_conf, bool):
                return json.dumps({"ok": False, "error": "min_conf 必须是数字"}, ensure_ascii=False)
            if not 0.0 <= float(min_conf) <= 1.0:
                return json.dumps(
                    {"ok": False, "error": "min_conf 必须在 0.0 到 1.0 之间"},
                    ensure_ascii=False,
                )
        image_bytes, image_error = await self._resolve_image(args)
        if image_bytes is None:
            return json.dumps(
                {"ok": False, "error": image_error or "无法获取图片"}, ensure_ascii=False
            )
        try:
            result = await self._service.detect_bytes_async(
                image_bytes, model_ids=[raw_model], min_conf=min_conf, mode=mode
            )
        except Exception as exc:
            return json.dumps({"ok": False, "error": f"检测失败: {exc}"}, ensure_ascii=False)
        return json.dumps(result, ensure_ascii=False)

    async def _resolve_image(self, args: dict[str, Any]) -> tuple[bytes | None, str | None]:
        """从参数解析图片字节(统一走 neobot_app.image.source)。"""
        return await self._resolver.resolve(args, timeout=_MAX_IMAGE_TIMEOUT)
