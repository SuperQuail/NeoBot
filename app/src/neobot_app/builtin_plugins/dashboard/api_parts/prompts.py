"""提示词查看、预览、保存与重置接口。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aiohttp import web
from ._common import _json_ok, _json_error, _redact_prompt_report, _prompt_value


class PromptsMixin:
    def _prompt_analyzer(self) -> Any:
        return self._service("prompt_analyzer")

    async def analysis_prompts(self, request: web.Request) -> web.Response:
        """提示词分析：各 agent 装配出的提示词字符数与估算 token（不调用模型）。

        统计口径来自分析器自身（中文 ×0.6 + 其他 ×0.3）；单个来源装配失败只影响
        该条目，接口仍返回可用数据。
        """
        analyzer = self._prompt_analyzer()
        if analyzer is None:
            return _json_error("提示词分析不可用（未注入分析器）", status=503)
        try:
            report = await analyzer.collect()
        except Exception as exc:
            return _json_error(f"提示词分析失败: {exc}", status=500)
        # 提示词原文/工具 schema 属于运营内部信息：非管理会话（远程或关闭管理功能）
        # 只返回计数，与 config_get 的按权限裁剪保持一致。
        if not self._can_manage(request):
            report = _redact_prompt_report(report)
        return _json_ok(report)


    # ------------------------------------------------------------------
    # 提示词模板（data/prompts）
    # ------------------------------------------------------------------

    def _prompt_store(self) -> Any:
        return self._service("prompt_store")

    def _custom_prompts_file(self) -> Any:
        store = self._prompt_store()
        custom_file = getattr(store, "custom_file", None)
        if custom_file is None:
            return None
        return Path(custom_file)

    async def prompts(self, request: web.Request) -> web.Response:
        """提示词分区总览：默认值、自定义值与合并后的实际取值。"""
        from .. import prompt_admin

        store = self._prompt_store()
        if store is None:
            return _json_error("提示词存储不可用（未注入 prompt_store）", status=503)
        custom_file = self._custom_prompts_file()
        custom_sections = (
            prompt_admin.read_custom_sections(custom_file)
            if custom_file is not None
            else {}
        )
        payload = prompt_admin.describe_sections(
            store, custom_sections=custom_sections
        )
        payload["editable"] = self._can_manage(request)
        return _json_ok(payload)

    async def prompts_preview(self, request: web.Request) -> web.Response:
        """按模拟取值渲染模板，返回「转义后内容」。

        纯计算，不写盘；values 里可以覆盖任意占位符的模拟取值。
        """
        from .. import prompt_admin

        payload = await self._read_json(request)
        template = payload.get("template")
        if template is None:
            section = str(payload.get("section") or "").strip()
            path = str(payload.get("path") or "template").strip() or "template"
            store = self._prompt_store()
            if store is None:
                return _json_error("提示词存储不可用（未注入 prompt_store）", status=503)
            template = _prompt_value(store, section, path)
            if template is None:
                return _json_error(f"未找到提示词 {section}.{path}", status=404)
        values = payload.get("values")
        if values is not None and not isinstance(values, dict):
            return _json_error("values 必须是对象")
        result = prompt_admin.preview_template(str(template), values or {})
        return _json_ok(result)

    async def prompts_save(self, request: web.Request) -> web.Response:
        """把某个键写进 data/prompts/custom/prompts.toml（只动自定义文件）。"""
        from .. import prompt_admin

        denied = self._require_manage(request, action="编辑提示词")
        if denied is not None:
            return denied
        custom_file = self._custom_prompts_file()
        if custom_file is None:
            return _json_error("提示词存储不可用（未注入 prompt_store）", status=503)
        payload = await self._read_json(request)
        section = str(payload.get("section") or "").strip()
        path = str(payload.get("path") or "template").strip() or "template"
        value = payload.get("value")
        if value is None:
            return _json_error("缺少 value")
        try:
            prompt_admin.write_override(custom_file, section, path, str(value))
        except ValueError as exc:
            return _json_error(str(exc))
        self._reload_prompt_store()
        self.logger.info(
            f"面板修改提示词 ip={self.console.request_ip(request)} {section}.{path}"
        )
        return _json_ok({"message": f"已保存 {section}.{path}", "section": section, "path": path})

    async def prompts_reset(self, request: web.Request) -> web.Response:
        """删除自定义覆盖，恢复该键的默认提示词。"""
        from .. import prompt_admin

        denied = self._require_manage(request, action="恢复默认提示词")
        if denied is not None:
            return denied
        custom_file = self._custom_prompts_file()
        if custom_file is None:
            return _json_error("提示词存储不可用（未注入 prompt_store）", status=503)
        payload = await self._read_json(request)
        section = str(payload.get("section") or "").strip()
        path = str(payload.get("path") or "template").strip() or "template"
        try:
            result = prompt_admin.remove_override(custom_file, section, path)
        except ValueError as exc:
            return _json_error(str(exc))
        self._reload_prompt_store()
        message = (
            f"已恢复默认 {section}.{path}" if result.get("removed") else "该键没有自定义内容"
        )
        return _json_ok({**result, "message": message})

    def _reload_prompt_store(self) -> None:
        store = self._prompt_store()
        reload_store = getattr(store, "reload", None)
        if callable(reload_store):
            try:
                reload_store()
            except Exception as exc:
                self.logger.warning(f"提示词缓存刷新失败: {exc}")
