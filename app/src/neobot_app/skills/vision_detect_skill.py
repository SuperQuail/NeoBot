"""VisionDetectSkill:基于本地 ONNX/YOLO 模型的图像检测工具。

- 支持多种图片来源(本地路径/URL/base64/消息编号/消息ID/聊天流ID)
- 模型清单动态注入工具描述,agent 依据模型描述主动选择使用哪个模型
- 推理毫秒级(CPU 单张约 5-7ms),同步快速返回,不走会话工具队列
- 模型库不可用(onnxruntime 缺失/无模型)时不暴露工具
"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule
from neobot_app.skills.image_parse_skill import ImageParseSkill, _read_image_ref
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
        # 复用 image_parse_skill 的图片来源解析(消息编号/聊天流ID/消息ID回源)
        self._fetcher = ImageParseSkill(
            vision_provider=None,
            adapter=adapter,
            group_message_queue=group_message_queue,
            friend_message_queue=friend_message_queue,
        )

    @property
    def name(self) -> str:
        return "vision_detect"

    @property
    def description(self) -> str:
        return "视觉检测：用本地 ONNX/YOLO 模型检测图片中是否包含特定目标（如机器人自身形象）"

    @property
    def instructions(self) -> str:
        return (
            "视觉检测 Skill 提供以下能力：\n\n"
            "## detect\n"
            "用本地模型检测图片中是否包含特定目标。可检测的目标取决于已配置的模型"
            "（可用模型清单与各自用途见工具描述的「可用模型」部分，按需选择 model 参数）。\n"
            "图片来源（任选其一）：\n"
            "  - image_path — 本地图片路径\n"
            "  - image_url — HTTP/data/file URL\n"
            "  - image_base64 — base64 编码图片\n"
            "  - msg_number — 聊天记录中显示的消息编号（如「75: 用户名: [图片]」中的 75）\n"
            "  - chat_flow_id + image_index — 聊天流 ID + 图片编号\n"
            "  - message_id — OneBot 消息 ID\n"
            "【msg_number 选择规则】\n"
            "  - 用户回复了某条消息（聊天记录形如「N: [被回复消息] 发送者: [图片]」）时，"
            "    使用被回复消息的编号 N，而非用户自己那条回复的编号\n"
            "  - 用户直接发的图片，使用该消息的编号\n"
            "model 参数缺省时对所有启用模型各检测一次（本地推理毫秒级，可接受）。\n"
            "返回格式：{ok, results:[{model, model_name, detections:[{class, conf, box}]}], summary}。\n"
            "summary 为中文摘要，可直接依据它判断图片中是否有对应目标。"
        )

    def reset(self) -> None:
        pass

    # ── 工具定义(动态注入模型清单) ──

    def get_tools(self) -> list[dict]:
        if not self._service.available:
            return []
        models = self._service.list_models()
        if not models:
            return []
        model_lines = []
        for model in models:
            description = model["description"].strip() or "（未配置描述）"
            model_lines.append(
                f"- {model['id']}：{description}"
            )
        model_enum = [model["id"] for model in models]
        return [
            self._tool_def(
                "detect",
                "用本地 ONNX/YOLO 模型检测图片中是否包含特定目标（如机器人自身形象、特定角色形象）。\n"
                "model 参数缺省时对所有启用模型各检测一次。\n"
                f"可用模型（共 {len(model_enum)} 个）：\n"
                + "\n".join(model_lines),
                {
                    "properties": {
                        "image_path": {"type": "string", "description": "可选，本地图片路径"},
                        "image_url": {"type": "string", "description": "可选，图片 HTTP/file/data URL"},
                        "image_base64": {"type": "string", "description": "可选，base64 编码的图片数据"},
                        "msg_number": {
                            "type": "integer",
                            "description": "可选，聊天记录中显示的消息编号（如「75: 用户名: [图片]」中的 75）；"
                            "用户回复某条含图消息时请用被回复消息的编号",
                        },
                        "chat_flow_id": {"type": "string", "description": "可选，聊天流 ID（Group_xxx / Friend_xxx），配合 image_index 使用"},
                        "message_id": {"type": "integer", "description": "可选，OneBot 消息 ID（不常用，勿将显示编号当作 message_id 传入）"},
                        "image_index": {"type": "integer", "description": "可选，消息中第几张图（0-based），默认 0", "default": 0},
                        "model": {
                            "type": "string",
                            "enum": model_enum,
                            "description": "可选，使用的模型 id（见上方可用模型清单）；缺省对所有启用模型检测",
                        },
                        "min_conf": {
                            "type": "number",
                            "description": "可选，覆盖本次检测的置信度阈值（0.0-1.0）",
                        },
                    },
                },
            )
        ]

    # ── 执行 ──

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        if tool_name != "detect":
            return json.dumps({"ok": False, "error": f"unknown vision_detect tool: {tool_name}"}, ensure_ascii=False)
        image_bytes, image_error = await self._resolve_image(args)
        if image_bytes is None:
            return json.dumps(
                {"ok": False, "error": image_error or "无法获取图片"}, ensure_ascii=False
            )
        model_ids = None
        raw_model = args.get("model")
        if raw_model:
            model_ids = [str(raw_model)]
        min_conf = args.get("min_conf")
        if min_conf is not None and not isinstance(min_conf, (int, float)):
            return json.dumps({"ok": False, "error": "min_conf 必须是数字"}, ensure_ascii=False)
        try:
            result = await self._service.detect_bytes_async(
                image_bytes, model_ids=model_ids, min_conf=min_conf
            )
        except Exception as exc:
            return json.dumps({"ok": False, "error": f"检测失败: {exc}"}, ensure_ascii=False)
        return json.dumps(result, ensure_ascii=False)

    async def _resolve_image(self, args: dict[str, Any]) -> tuple[bytes | None, str | None]:
        """从参数解析图片字节(复用 image_parse_skill 的来源解析)。"""
        image_index = int(args.get("image_index") or 0)
        if image_index < 0:
            return None, "image_index 不能为负数"
        ref = args.get("image_base64") or args.get("image_path") or args.get("image_url")
        if ref:
            if not isinstance(ref, str) or not ref.strip():
                return None, "图片引用参数不能为空"
            if args.get("image_base64") and not ref.startswith("base64://"):
                ref = f"base64://{ref}"
            try:
                data = await _read_image_ref(ref, timeout=_MAX_IMAGE_TIMEOUT)
            except Exception as exc:
                return None, f"图片引用无效: {exc}"
            if data is None:
                return None, "图片下载/解码失败"
            return data, None
        if args.get("msg_number") is not None:
            pipeline_key = str(args.get("pipeline_key") or "")
            if not pipeline_key:
                return None, "无法确定当前会话（缺少 pipeline_key）"
            numbering_mapping = args.get("_numbering_mapping")
            return await self._fetcher._resolve_by_msg_number(
                pipeline_key,
                int(args["msg_number"]),
                image_index=image_index,
                numbering_mapping=numbering_mapping if isinstance(numbering_mapping, dict) else None,
                timeout=_MAX_IMAGE_TIMEOUT,
            )
        if args.get("chat_flow_id"):
            data = await self._fetcher._resolve_by_chat_flow(
                str(args["chat_flow_id"]), image_index=image_index, timeout=_MAX_IMAGE_TIMEOUT
            )
            if data is None:
                return None, "按聊天流 ID 获取图片失败"
            return data, None
        if args.get("message_id") is not None:
            return await self._fetcher._resolve_by_message_id_with_error(
                int(args["message_id"]), image_index=image_index, timeout=_MAX_IMAGE_TIMEOUT
            )
        return None, "缺少图片来源参数：请提供 image_path / image_url / image_base64 / msg_number / chat_flow_id / message_id 之一"
