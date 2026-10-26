"""聊天流与上下文提示词接口。"""

from __future__ import annotations

import time
from typing import Any

from aiohttp import web
from ._common import _json_ok, _json_error


class ChatFlowsMixin:
    # ------------------------------------------------------------------
    # 聊天流（最近一次发给模型的内容 + 后台任务）
    # ------------------------------------------------------------------

    def _flow_registry(self) -> Any:
        return self._service("chat_flow_registry")

    def _profile_service(self) -> Any:
        return self._service("profile_service")

    @staticmethod
    def _split_pipeline_key(pipeline_key: str, state: dict[str, Any] | None = None) -> tuple[str, str]:
        """解析聊天流身份：优先 split(pipeline_key)，其次回落记录里的 conversation_kind/id。

        不依赖 record_prompt 是否被调用过（features/spec(3) §4.5）。
        """
        key = str(pipeline_key or "").strip()
        kind = ""
        conversation_id = ""
        if ":" in key:
            kind, conversation_id = key.split(":", 1)
        data = state or {}
        if not kind:
            kind = str(data.get("conversation_kind") or "")
        if not conversation_id:
            conversation_id = str(data.get("conversation_id") or "")
        return kind.strip(), conversation_id.strip()

    async def _display_name(self, pipeline_key: str, state: dict[str, Any] | None = None) -> str:
        """把 pipeline_key（group:123）解析成可读名称（群名 / 昵称）。

        - 只走 profile_service 的**纯 DB** 路径（绝不调用 adapter.get_group_name，
          那会在缓存未命中时打 OneBot API —— 面板 5s 轮询会造出周期性 API 调用）；
        - 结果按 TTL 缓存，避免每轮每流一次 DB 查询；
        - 任何异常都回落 pipeline_key，绝不让接口 500（R2）。
        """
        key = str(pipeline_key or "").strip()
        if not key:
            return ""
        now = time.time()
        if now - self._display_names_at > self.DISPLAY_NAME_TTL_SECONDS:
            self._display_names.clear()
            self._display_names_at = now
        cached = self._display_names.get(key)
        if cached is not None:
            return cached

        name = ""
        try:
            kind, conversation_id = self._split_pipeline_key(key, state)
            service = self._profile_service()
            getter = None
            if service is not None and conversation_id:
                if kind == "group":
                    getter = getattr(service, "get_group_name", None)
                elif kind in {"private", "friend"}:
                    getter = getattr(service, "get_user_name", None)
            if kind == "bilibili_live":
                name = f"B站直播间 {conversation_id}"
            elif kind == "bilibili_comment":
                name = f"B站评论 {conversation_id}"
            elif kind == "bilibili_private":
                name = f"B站私信 {conversation_id}"
            elif kind == "bilibili_task":
                name = "B站跨聊天任务"
            elif callable(getter):
                name = str(await getter(conversation_id) or "").strip()
        except Exception as exc:
            self.logger.debug(f"聊天流名称解析失败，回落 pipeline_key: {key} {exc}")
            name = ""
        resolved = name or key
        self._display_names[key] = resolved
        return resolved

    async def chat_flows(self, request: web.Request) -> web.Response:
        registry = self._flow_registry()
        if registry is None:
            return _json_error(
                "聊天流登记处不可用（未注入 chat_flow_registry）", status=503
            )
        items = list(registry.list_flows() or [])
        for item in items:
            if isinstance(item, dict):
                item["display_name"] = await self._display_name(
                    str(item.get("pipeline_key") or ""), item
                )
        return _json_ok({"items": items})

    async def chat_flow_detail(self, request: web.Request) -> web.Response:
        registry = self._flow_registry()
        if registry is None:
            return _json_error(
                "聊天流登记处不可用（未注入 chat_flow_registry）", status=503
            )
        key = str(request.query.get("key") or "").strip()
        if not key:
            return _json_error("缺少查询参数 key")
        snapshot = await registry.snapshot(key)
        if snapshot is None:
            return _json_error(f"没有该聊天流的记录: {key}", status=404)
        snapshot["display_name"] = await self._display_name(key, snapshot)
        return _json_ok(snapshot)

    # ------------------------------------------------------------------
    # 完整提示词历史（features/spec(3) 建立；spec(10) 改为纯内存 + 逐份 diff）
    # ------------------------------------------------------------------

    def _context_recorder(self) -> Any:
        return self._service("context_recorder")

    async def chat_flow_prompts(self, request: web.Request) -> web.Response:
        """列出最近 N 份完整提示词的**元数据**（可按 pipeline_key 过滤）。"""
        recorder = self._context_recorder()
        if recorder is None:
            return _json_error(
                "提示词历史记录器不可用（未注入 context_recorder）", status=503
            )
        pipeline_key = str(request.query.get("key") or "").strip()
        try:
            entries = recorder.list_entries(pipeline_key or None) or []
        except Exception as exc:
            self.logger.warning(f"提示词历史读取失败: {exc}")
            return _json_error(f"提示词历史读取失败: {exc}", status=500)
        items = [
            entry.to_dict() if hasattr(entry, "to_dict") else dict(entry)
            for entry in entries
        ]
        return _json_ok(
            {
                "items": items,
                "pipeline_key": pipeline_key,
                "limit": int(getattr(recorder, "limit", 0) or 0),
                # 纯内存存储的实际驻留量（快照 + 全部补丁），供面板展示成本
                "storage_bytes": int(getattr(recorder, "storage_bytes", 0) or 0),
                "image_refs": int(getattr(recorder, "image_refs", 0) or 0),
            }
        )

    async def chat_flow_prompt(self, request: web.Request) -> web.Response:
        """读取**单份完整提示词全文**（不截断；逐份重建自内存里的快照 + 补丁）。"""
        recorder = self._context_recorder()
        if recorder is None:
            return _json_error(
                "提示词历史记录器不可用（未注入 context_recorder）", status=503
            )
        raw = request.query.get("seq")
        if raw is None or str(raw).strip() == "":
            return _json_error("缺少查询参数 seq")
        try:
            seq = int(str(raw))
        except (TypeError, ValueError):
            return _json_error("查询参数 seq 必须是整数")
        entry = recorder.read_entry(seq)
        if entry is None:
            return _json_error(f"没有该份提示词历史: seq={seq}", status=404)
        return _json_ok({"seq": seq, "entry": entry})

    async def chat_flow_prompts_clear(self, request: web.Request) -> web.Response:
        """清空完整提示词历史（内存快照 + 补丁，顺带删除旧落盘残留）。"""
        denied = self._require_manage(request, action="清空提示词历史")
        if denied is not None:
            return denied
        recorder = self._context_recorder()
        if recorder is None:
            return _json_error(
                "提示词历史记录器不可用（未注入 context_recorder）", status=503
            )
        try:
            removed = int(recorder.clear() or 0)
        except Exception as exc:
            return _json_error(f"清空提示词历史失败: {exc}", status=500)
        self.logger.info(f"面板清空完整提示词历史: removed={removed}")
        return _json_ok(
            {"removed": removed, "message": f"已清空 {removed} 份提示词历史（内存）"}
        )
