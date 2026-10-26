"""档案总结与快照接口。"""

from __future__ import annotations

from typing import Any

from aiohttp import web
from ._common import _json_ok, _json_error


class ArchiveSummaryMixin:
    # ------------------------------------------------------------------
    # AI 压缩（spec(4) Part C：面板手动 / 批量触发 + 压缩历史只读）
    # ------------------------------------------------------------------

    def _archive_summary_service(self) -> Any:
        """档案自动总结服务（宿主服务 archive_summary_service）。"""
        return self._service("archive_summary_service")

    def _archive_summary_missing(self) -> web.Response:
        return _json_error(
            "档案总结服务不可用（未注入 archive_summary_service）", status=503
        )

    @staticmethod
    def _summarize_target_bounds(summary: Any) -> tuple[int, int] | None:
        """面板显示用的目标区间（由服务层给出唯一真相，缺失时不显示）。"""
        getter = getattr(summary, "manual_target_bounds", None)
        if not callable(getter):
            return None
        try:
            lower, upper = getter()
        except Exception:
            return None
        return int(lower), int(upper)

    @staticmethod
    def _target_chars_arg(body: dict[str, Any]) -> Any:
        """从请求体取 target_chars（缺失即报错，不在面板侧做隐式默认）。"""
        return body.get("target_chars")

    async def archives_summarize_start(self, request: web.Request) -> web.Response:
        """对指定一条档案手动触发一轮 AI 压缩（R14 / R15；202 + task_id）。"""
        denied = self._require_manage(request, action="触发档案压缩")
        if denied is not None:
            return denied
        summary = self._archive_summary_service()
        if summary is None:
            return self._archive_summary_missing()
        try:
            body = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        table = str(body.get("table") or "").strip()
        key = str(body.get("key") or "").strip()
        if not table or not key:
            return _json_error("缺少 table / key")
        from .. import archives as archive_admin

        if archive_admin.is_internal_table(table):
            return _json_error(
                f"{table} 是程序维护的内部表，禁止触发 AI 压缩（与禁止编辑同口径）"
            )
        target = self._target_chars_arg(body)
        if target is None:
            return _json_error("缺少 target_chars（本次压缩的目标字符数）")
        ip = self.console.request_ip(request)
        try:
            payload = await summary.start_manual_compression(
                table, key, target_chars=target, operator_ip=ip
            )
        except ValueError as exc:
            return _json_error(str(exc))
        except RuntimeError as exc:
            return _json_error(str(exc), status=503)
        self.logger.info(
            f"面板触发 AI 档案压缩 table={table} key={key} "
            f"target_chars={payload.get('target_chars')} status={payload.get('status')} "
            f"task_id={payload.get('task_id')} ip={ip}"
        )
        if payload.get("task_id") and payload.get("status") == "running":
            return web.json_response(payload, status=202)
        return _json_ok(payload)

    async def archives_summarize_status(self, request: web.Request) -> web.Response:
        """轮询一次压缩任务的状态（R18：running / done / failed + 前后字数）。"""
        denied = self._require_manage(request, action="查看档案压缩状态")
        if denied is not None:
            return denied
        summary = self._archive_summary_service()
        if summary is None:
            return self._archive_summary_missing()
        task_id = str(request.query.get("task_id") or "").strip()
        if not task_id:
            return _json_error("缺少查询参数 task_id")
        payload = summary.get_manual_task(task_id)
        if payload is None:
            return _json_error(
                f"没有该压缩任务: {task_id}（进程重启后任务状态会清空）",
                status=404,
            )
        return _json_ok(payload)

    async def archives_summarize_over_limit(self, request: web.Request) -> web.Response:
        """批量压缩当前超限档案（R20：逐条串行、统一目标、返回 truncated 与 skipped）。"""
        denied = self._require_manage(request, action="批量压缩超限档案")
        if denied is not None:
            return denied
        summary = self._archive_summary_service()
        if summary is None:
            return self._archive_summary_missing()
        try:
            body = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        target = self._target_chars_arg(body)
        if target is None:
            return _json_error("缺少 target_chars（本次压缩的目标字符数）")
        table = str(body.get("table") or "").strip() or None
        ip = self.console.request_ip(request)
        try:
            payload = await summary.start_batch_compression(
                target_chars=target, operator_ip=ip, table_name=table
            )
        except ValueError as exc:
            return _json_error(str(exc))
        except RuntimeError as exc:
            return _json_error(str(exc), status=503)
        self.logger.info(
            f"面板触发批量档案压缩 target_chars={payload.get('target_chars')} "
            f"count={len(payload.get('items') or [])} truncated={payload.get('truncated')} "
            f"task_id={payload.get('task_id')} ip={ip}"
        )
        if payload.get("task_id") and payload.get("status") == "running":
            return web.json_response(payload, status=202)
        return _json_ok(payload)

    async def archives_snapshots(self, request: web.Request) -> web.Response:
        """某条档案的压缩历史（只读快照列表；**不提供一键恢复**，A47）。"""
        denied = self._require_manage(request, action="查看档案压缩历史")
        if denied is not None:
            return denied
        service = self._archive_service()
        if service is None:
            return self._archive_missing()
        table = str(request.query.get("table") or "").strip()
        key = str(request.query.get("key") or "").strip()
        if not table or not key:
            return _json_error("缺少查询参数 table / key")
        from .. import archives as archive_admin

        current = await service.get(table, key)
        current_chars = (
            len(str(getattr(current, "value", "") or "")) if current is not None else None
        )
        payload = await archive_admin.snapshot_history(
            service, table=table, key=key, current_chars=current_chars
        )
        return _json_ok(payload)

    async def archives_snapshot(self, request: web.Request) -> web.Response:
        """读取某一份快照的全文（只读；恢复需人工走编辑接口）。"""
        denied = self._require_manage(request, action="查看档案压缩快照")
        if denied is not None:
            return denied
        service = self._archive_service()
        if service is None:
            return self._archive_missing()
        raw = request.query.get("id")
        try:
            snapshot_id = int(str(raw))
        except (TypeError, ValueError):
            return _json_error("查询参数 id 必须是整数")
        getter = getattr(service, "get_snapshot", None)
        entry = await getter(snapshot_id) if callable(getter) else None
        if entry is None:
            return _json_error(f"没有该快照: {snapshot_id}", status=404)
        return _json_ok({"snapshot": entry})
