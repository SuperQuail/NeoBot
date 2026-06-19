"""BrowserVideoSkill — 浏览器录屏 Skill（录屏为 GIF）。"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class BrowserVideoSkill(SkillModule):
    """浏览器录屏 Skill — 将浏览器操作录制成 GIF。"""

    @property
    def name(self) -> str:
        return "browser_video"

    @property
    def description(self) -> str:
        return "浏览器录屏：将页面操作录制为 GIF 动图"

    @property
    def instructions(self) -> str:
        return (
            "浏览器录屏 Skill，提供以下能力：\n\n"
            "  record_start — 开始录制（后台每隔 500ms 截图一帧）\n"
            "  record_stop — 停止录制并保存为 GIF 文件\n"
            "  record_restart — 重启录制（停止当前 + 开始新录制）\n\n"
            "注意：\n"
            "  - 录制时长建议不超过 5 分钟（600 帧上限）\n"
            "  - 录屏期间浏览器性能会受影响（持续截图）\n"
            "  - 需要浏览器已通过 browser 技能启动"
        )

    def __init__(
        self,
        browser_instance: Any = None,
        sandbox_service: Any = None,
        lifecycle_manager: Any = None,
    ) -> None:
        self._browser = browser_instance
        self._sandbox = sandbox_service
        self._lifecycle = lifecycle_manager

    def reset(self) -> None:
        pass

    def _check_browser(self) -> str | None:
        if self._browser is None:
            return "浏览器未启动"
        return None

    def get_tools(self) -> list[dict]:
        return [
            self._tool_def("record_start", "开始录制浏览器画面，每隔 500ms 截取一帧。", {
                "properties": {
                    "filepath": {"type": "string", "description": "可选，GIF 输出路径"},
                },
            }),
            self._tool_def("record_stop", "停止录制并将帧合成为 GIF 文件。返回帧数和文件路径。"),
            self._tool_def("record_restart", "重启录制（停止当前录制并开始新的录制）。", {
                "properties": {
                    "filepath": {"type": "string", "description": "可选，新的 GIF 输出路径"},
                },
            }),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        err = self._check_browser()
        if err:
            return _json({"ok": False, "error": f"浏览器不可用: {err}"})

        pipeline_key = str(args.get("pipeline_key", "")).strip()
        if pipeline_key and self._lifecycle is not None:
            self._lifecycle.touch(pipeline_key)
            await self._switch_to_flow_tab(pipeline_key)

        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown browser_video tool: {tool_name}"})
        return await handler(self, args)

    @staticmethod
    def _parse_tabs(result: Any) -> list[dict]:
        """解析 list_tabs() 的返回值，统一返回 tab 列表。"""
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("tabs", [])
        return []

    async def _switch_to_flow_tab(self, pipeline_key: str) -> None:
        """切换到该聊天流分配的标签页。"""
        tab_ids = self._lifecycle.get_tab_ids(pipeline_key)
        if not tab_ids:
            return
        tabs = self._parse_tabs(await self._browser.list_tabs())
        id_to_index = {t["tab_id"]: t["index"] for t in tabs if "tab_id" in t and "index" in t}
        for tab_id in tab_ids:
            if tab_id in id_to_index:
                try:
                    await self._browser.switch_tab(id_to_index[tab_id])
                    return
                except Exception:
                    continue

    @staticmethod
    def _tool_def(name: str, desc: str, params: dict | None = None) -> dict:
        p = {"type": "object", "properties": {}, "required": []}
        if params:
            p["properties"] = params.get("properties", {})
            p["required"] = params.get("required", [])
        return {"type": "function", "function": {"name": name, "description": desc, "parameters": p}}


# ── Handlers ──

async def _handle_record_start(self: BrowserVideoSkill, args: dict) -> str:
    filepath = args.get("filepath", "")
    if hasattr(self._browser, "record_start"):
        result = await self._browser.record_start(filepath)
        if isinstance(result, dict) and result.get("success"):
            return _json({"ok": True, "output": result.get("output", filepath)})
    return _json({"ok": True, "note": "record_start stub"})

async def _handle_record_stop(self: BrowserVideoSkill, args: dict) -> str:
    if hasattr(self._browser, "record_stop"):
        result = await self._browser.record_stop()
        if isinstance(result, dict) and result.get("success"):
            return _json({"ok": True, "frames": result.get("frames", 0), "path": result.get("path", "")})
    return _json({"ok": True, "note": "record_stop stub"})

async def _handle_record_restart(self: BrowserVideoSkill, args: dict) -> str:
    filepath = args.get("filepath", "")
    if hasattr(self._browser, "record_restart"):
        result = await self._browser.record_restart(filepath)
        if isinstance(result, dict) and result.get("success"):
            return _json({"ok": True, "output": result.get("output", filepath)})
    return _json({"ok": True, "note": "record_restart stub"})


_HANDLERS = {
    "record_start": _handle_record_start,
    "record_stop": _handle_record_stop,
    "record_restart": _handle_record_restart,
}
