"""bilibili_video_frames skill：抽关键帧、拼 4x4 接触印相纸、可选视觉描述。

只读、不自动发图：返回本地文件路径，需要看画面时再调用 read_image。
"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.bilibili._compat import call_client
from neobot_app.skills.base import SkillModule
from neobot_app.utils.logger import get_module_logger

logger = get_module_logger("bilibili.video_frames_skill")


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _flag(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "no", "off")
    return bool(value)


class BilibiliVideoFramesSkill(SkillModule):
    """把 VideoFrameService 暴露成 agent 工具。"""

    def __init__(self, video_frames_service: Any = None) -> None:
        self._frames = video_frames_service

    @property
    def name(self) -> str:
        return "bilibili_video_frames"

    @property
    def description(self) -> str:
        return "B站视频画面：按时间抽关键帧、拼4x4接触印相纸、可选视觉模型描述画面"

    @property
    def instructions(self) -> str:
        return (
            "B站视频画面 Skill：video_frames 按 every 秒抽关键帧（默认 60 秒、最多 32 帧），"
            "生成 4x4 接触印相纸，并在配置了视觉模型时给出画面描述。\n"
            "适合没有字幕、或需要核对字幕里型号/数字/场景的视频；"
            "和 watch_video 的字幕/转写互补。\n"
            "只读；返回的是本地文件路径，需要细看某一帧时再调用 read_image 读取，"
            "本工具不会自动把图片发给用户。"
        )

    def get_tools(self) -> list[dict]:
        if self._frames is None:
            return []
        return [
            self._tool_def(
                "video_frames",
                "按时间间隔抽取B站视频关键帧，生成4x4接触印相纸，并可让视觉模型描述画面；"
                "返回本地文件路径，可用 read_image 查看，不会自动发图。",
                {
                    "properties": {
                        "identifier": {
                            "type": "string",
                            "description": "BV号、av号或视频链接",
                        },
                        "every": {
                            "type": "integer",
                            "description": "抽帧间隔秒，默认60；演示类可调小，口播访谈可调大",
                            "default": 60,
                        },
                        "max_frames": {
                            "type": "integer",
                            "description": "最多抽多少帧，默认32（上限32）",
                            "default": 32,
                        },
                        "describe": {
                            "type": "boolean",
                            "description": "是否让视觉模型描述拼图画面，默认true；没有视觉模型时忽略",
                            "default": True,
                        },
                    },
                    "required": ["identifier"],
                },
            )
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        if tool_name != "video_frames":
            return _json({"ok": False, "error": f"未知工具: {tool_name}"})
        if self._frames is None:
            return _json({"ok": False, "error": "视频画面服务未配置，暂时不能抽帧"})
        identifier = str(args.get("identifier") or "").strip()
        if not identifier:
            return _json({"ok": False, "error": "缺少 identifier（BV号、av号或视频链接）"})
        every = min(max(_to_int(args.get("every"), 60) or 60, 1), 3600)
        max_frames = min(max(_to_int(args.get("max_frames"), 32) or 32, 1), 32)
        describe = _flag(args.get("describe"), True)
        try:
            result = await call_client(
                self._frames.frames,
                identifier,
                every=every,
                max_frames=max_frames,
                describe=describe,
            )
        except Exception as exc:
            logger.warning(f"抽帧工具调用失败: identifier={identifier}: {type(exc).__name__}: {exc}")
            return _json(
                {
                    "ok": False,
                    "identifier": identifier,
                    "error": f"获取视频画面失败：{type(exc).__name__}: {exc}",
                }
            )
        if not isinstance(result, dict):
            return _json({"ok": False, "identifier": identifier, "error": "视频画面服务返回了无法识别的结果"})
        if not result.get("ok"):
            reason = str(result.get("error") or "视频画面服务未能获取该视频")
            logger.warning(f"抽帧服务返回失败: identifier={identifier}: {reason}")
            return _json({"ok": False, "identifier": identifier, "error": f"获取视频画面失败：{reason}"})
        return _json(
            {
                "ok": True,
                "bvid": str(result.get("bvid") or ""),
                "frames": [str(item) for item in result.get("frames") or []],
                "sheets": [str(item) for item in result.get("sheets") or []],
                "description": str(result.get("description") or ""),
                "count": len(result.get("frames") or []),
                "note": "帧图与拼图是本地文件，可用 read_image 查看；本工具不会自动发图。",
            }
        )
