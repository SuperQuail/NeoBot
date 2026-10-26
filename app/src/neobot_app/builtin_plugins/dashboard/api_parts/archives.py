"""档案增删改查接口。"""

from __future__ import annotations

from typing import Any

from aiohttp import web
from ._common import _json_ok, _json_error


class ArchivesMixin:
    # ------------------------------------------------------------------
    # 档案管理（features/spec(2)：把模型侧 CRUD 暴露到面板）
    # ------------------------------------------------------------------

    def _archive_service(self) -> Any:
        return self._service("archive_memory_service")

    def _archive_delete_enabled(self) -> bool:
        """面板删除开关：**独立于** agent.memory.archive.allow_delete（spec §2.7）。"""
        config = getattr(self.console, "runtime_config", None)
        return bool(getattr(config, "allow_archive_delete", False))

    def _archive_missing(self) -> web.Response:
        return _json_error(
            "档案记忆服务不可用（未注入 archive_memory_service）", status=503
        )

    async def archives(self, request: web.Request) -> web.Response:
        service = self._archive_service()
        if service is None:
            return self._archive_missing()
        from .. import archives as archive_admin

        try:
            payload = await archive_admin.list_tables(service)
        except Exception as exc:
            self.logger.warning(f"档案表清单读取失败: {exc}")
            return _json_error(f"档案表清单读取失败: {exc}", status=500)
        payload["delete_enabled"] = self._archive_delete_enabled()
        payload["can_manage"] = self._can_manage(request)
        # AI 压缩入口可用性 + 目标字符数区间（spec(4) Part C / §4.10.2）。
        summary = self._archive_summary_service()
        payload["summarize_available"] = summary is not None
        bounds = self._summarize_target_bounds(summary)
        if bounds is not None:
            payload["min_target_chars"], payload["max_target_chars"] = bounds
        return _json_ok(payload)

    async def archives_over_limit(self, request: web.Request) -> web.Response:
        """当前超过存储上限的档案（spec(1) A7 的可视化落点）。"""
        service = self._archive_service()
        if service is None:
            return self._archive_missing()
        from .. import archives as archive_admin

        table = str(request.query.get("table") or "").strip()
        payload = await archive_admin.list_over_limit(
            service,
            table=table,
            limit=self._int_arg(
                request, "limit", 100, minimum=1, maximum=archive_admin.MAX_LIST_LIMIT
            ),
        )
        return _json_ok(payload)

    async def archive_items(self, request: web.Request) -> web.Response:
        service = self._archive_service()
        if service is None:
            return self._archive_missing()
        from .. import archives as archive_admin

        table = str(request.query.get("table") or "").strip()
        if not table:
            return _json_error("缺少查询参数 table")
        over_limit_only = str(request.query.get("over_limit") or "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        payload = await archive_admin.list_items(
            service,
            table=table,
            key_query=str(request.query.get("key_query") or "").strip(),
            value_query=str(request.query.get("value_query") or "").strip(),
            tags=archive_admin.normalize_tags(request.query.get("tags")),
            limit=self._int_arg(
                request, "limit", 50, minimum=1, maximum=archive_admin.MAX_LIST_LIMIT
            ),
            offset=self._int_arg(request, "offset", 0, minimum=0, maximum=1_000_000),
            over_limit_only=over_limit_only,
        )
        payload["max_total_chars"] = int(getattr(service, "max_total_chars", 0) or 0)
        payload["delete_enabled"] = self._archive_delete_enabled()
        payload["can_manage"] = self._can_manage(request)
        return _json_ok(payload)

    async def archive_item(self, request: web.Request) -> web.Response:
        service = self._archive_service()
        if service is None:
            return self._archive_missing()
        from .. import archives as archive_admin

        table = str(request.query.get("table") or "").strip()
        key = str(request.query.get("key") or "").strip()
        if not table or not key:
            return _json_error("缺少查询参数 table / key")
        payload = await archive_admin.get_item(service, table=table, key=key)
        if payload is None:
            return _json_error(f"没有该档案: {table}:{key}", status=404)
        payload["delete_enabled"] = self._archive_delete_enabled()
        payload["can_manage"] = self._can_manage(request)
        return _json_ok(payload)

    async def archive_update(self, request: web.Request) -> web.Response:
        """编辑档案内容（乐观锁：version 不一致返回 409 + 当前内容）。"""
        denied = self._require_manage(request, action="编辑档案")
        if denied is not None:
            return denied
        service = self._archive_service()
        if service is None:
            return self._archive_missing()
        from .. import archives as archive_admin

        try:
            body = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        table = str(body.get("table") or "").strip()
        key = str(body.get("key") or "").strip()
        if not table or not key:
            return _json_error("缺少 table / key")
        if archive_admin.is_internal_table(table):
            return _json_error(
                f"{table} 是程序维护的内部表，禁止手工编辑（改坏会导致重复总结或漏总结）"
            )
        if "value" not in body or body.get("value") is None:
            return _json_error("缺少 value")
        value = str(body.get("value"))
        if not value.strip():
            return _json_error("档案内容不能为空（对齐 patch_archive 的空内容拒绝语义）")
        try:
            expected = int(body.get("version"))
        except (TypeError, ValueError):
            return _json_error("缺少或非法的 version（乐观锁要求带上读取时的版本号）")
        tags = archive_admin.normalize_tags(body.get("tags"))

        from neobot_memory.archive_service import ArchiveVersionConflictError

        try:
            item = await service.set_if_version(table, key, value, tags, expected)
        except ArchiveVersionConflictError as exc:
            current = await archive_admin.get_item(service, table=table, key=key)
            return _json_error(
                f"档案已被其它会话修改（当前 version={exc.actual_version}），请重新读取后再保存",
                status=409,
                current=current,
                actual_version=int(getattr(exc, "actual_version", 0) or 0),
            )
        except Exception as exc:
            return _json_error(f"档案保存失败: {exc}", status=500)

        detail = archive_admin.item_detail(item)
        self.logger.info(
            f"面板编辑档案 table={table} key={key} chars={detail['total_chars']} "
            f"version={detail['version']} ip={self.console.request_ip(request)}"
        )
        detail["message"] = "档案已保存"
        return _json_ok(detail)

    async def archive_delete(self, request: web.Request) -> web.Response:
        """删除档案（硬删除 + 审计日志；受独立开关 allow_archive_delete 控制）。"""
        denied = self._require_manage(request, action="删除档案")
        if denied is not None:
            return denied
        if not self._archive_delete_enabled():
            return _json_error(
                "面板档案删除未开启：请在 dashboard 插件配置里把 allow_archive_delete 设为 true",
                status=403,
            )
        service = self._archive_service()
        if service is None:
            return self._archive_missing()
        try:
            body = await self._read_json(request)
        except ValueError as exc:
            return _json_error(str(exc))
        table = str(body.get("table") or "").strip()
        key = str(body.get("key") or "").strip()
        if not table or not key:
            return _json_error("缺少 table / key")

        current = await service.get(table, key)
        if current is None:
            return _json_error(f"没有该档案: {table}:{key}", status=404)
        if body.get("version") is not None:
            try:
                expected = int(body.get("version"))
            except (TypeError, ValueError):
                return _json_error("version 必须是整数")
            actual = int(getattr(current, "version", 0) or 0)
            if expected != actual:
                return _json_error(
                    f"档案已被其它会话修改（当前 version={actual}），请重新读取后再删除",
                    status=409,
                    actual_version=actual,
                )
        value = str(getattr(current, "value", "") or "")
        version = int(getattr(current, "version", 0) or 0)
        deleted = await service.delete(table, key)
        # 硬删除不可恢复：把被删内容写进审计日志（只留前 500 字符，避免日志被大档案撑爆）
        self.logger.info(
            f"面板删除档案 table={table} key={key} chars={len(value)} version={version} "
            f"deleted={deleted} ip={self.console.request_ip(request)} "
            f"preview={value[:500]!r}"
        )
        return _json_ok(
            {
                "deleted": bool(deleted),
                "table": table,
                "key": key,
                "message": "档案已删除（可在 neobot.log 中追溯被删内容）",
            }
        )
