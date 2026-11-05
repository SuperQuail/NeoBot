"""最终 ZIP 与真实面板的源码、表单和隔离页面热重载验收。"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest
from playwright.async_api import Page, async_playwright, expect

from neobot_modloader.hot_reload import PluginHotReloader

from .test_plugin_workbench_browser import (
    _NAME,
    _PASSWORD,
    installed_panel as installed_panel,
)


async def _open_plugin(page: Page, base: str) -> None:
    await page.goto(base + "/#/login")
    await page.get_by_label("面板密码", exact=True).fill(_PASSWORD)
    await page.get_by_role("button", name="登录工作台", exact=True).click()
    await expect(page).to_have_url(base + "/#/dashboard")
    await page.goto(base + "/#/plugins")
    await page.get_by_role("button", name=re.compile(rf"^{_NAME}\b")).click()
    await expect(page.locator("#cfg-greeting")).to_have_value("你好")


async def _next_resource(page: Page, resource: str) -> dict:
    response = await page.wait_for_event(
        "response",
        predicate=lambda response: (
            response.url.endswith(f"/api/plugins/{_NAME}/{resource}")
            and response.request.method == "GET"
            and response.ok
        ),
        timeout=10_000,
    )
    return await response.json()


async def _surface_has_field(page: Page, field: str) -> None:
    async with asyncio.timeout(10):
        while True:
            payload = await _next_resource(page, "surface")
            if field in payload.get("contract", {}).get("config", {}).get("properties", {}):
                return


def _add_config_fields(source: str, *fields: str) -> str:
    declarations = "".join(f'    {field}: str = Field(default="初始值", title="{field}")\n' for field in fields)
    return source.replace("class Config(BaseModel):\n", "class Config(BaseModel):\n" + declarations)


@pytest.mark.browser
@pytest.mark.parametrize("viewport", [(1280, 720), (390, 844)], ids=["desktop", "phone"])
async def test_source_reload_updates_open_form_and_preserves_dirty_draft(installed_panel, viewport) -> None:
    _server, runtime, base = installed_panel
    root = runtime._loaded_paths[_NAME]
    source = root / "__init__.py"
    original = source.read_text(encoding="utf-8")
    watcher = PluginHotReloader(runtime, poll_interval=0.1, debounce=0.1)
    await watcher.start()
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
                await _open_plugin(page, base)
                source.write_text(_add_config_fields(original, "new_field"), encoding="utf-8")
                await expect(page.locator("#cfg-new_field")).to_have_value("初始值", timeout=10_000)
                assert "new_field" in runtime.control.config_model(_NAME).model_fields
                greeting = page.locator("#cfg-greeting")
                original_input = await greeting.element_handle()
                await greeting.fill("保留正在填写的内容")
                await expect(page.get_by_role("button", name="保存并重载", exact=True)).to_be_enabled()
                source.write_text(_add_config_fields(original, "new_field", "later_field"), encoding="utf-8")
                await _surface_has_field(page, "later_field")
                # 第二轮真实契约轮询后，草稿与原控件仍保留，新增字段延后装配。
                await _next_resource(page, "surface")
                await expect(greeting).to_have_value("保留正在填写的内容")
                await expect(page.locator("#cfg-later_field")).to_have_count(0)
                assert await greeting.evaluate("(node, original) => node === original", original_input)
                assert "later_field" in runtime.control.config_model(_NAME).model_fields
            finally:
                await browser.close()
    finally:
        await watcher.stop()


def _write_view_revision(directory: Path, html: str, script: str, revision: str) -> None:
    (directory / "index.html").write_text(
        html.replace("</head>", '<link rel="stylesheet" href="hot.css"></head>').replace(
            "</section>", f'<p id="hot-marker">页面版本 {revision}</p></section>'
        ),
        encoding="utf-8",
    )
    (directory / "app.js").write_text(
        script + f'\ndocument.body.dataset.assetVersion = "{revision}";\n', encoding="utf-8"
    )
    (directory / "hot.css").write_text("#hot-marker { color: rgb(12, 34, 56); }\n", encoding="utf-8")


@pytest.mark.browser
@pytest.mark.parametrize("viewport", [(1280, 720), (390, 844)], ids=["desktop", "phone"])
async def test_view_assets_reload_after_returning_from_hidden_or_focused_frame(installed_panel, viewport) -> None:
    _server, runtime, base = installed_panel
    root = runtime._loaded_paths[_NAME]
    directory = root / "web" / "settings"
    html = (directory / "index.html").read_text(encoding="utf-8")
    script = (directory / "app.js").read_text(encoding="utf-8")
    plugin = runtime.manager.get_plugin(_NAME)
    watcher = PluginHotReloader(runtime, poll_interval=0.1, debounce=0.1)
    await watcher.start()
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
                await _open_plugin(page, base)
                pages_tab = page.get_by_role("tab", name="插件页面", exact=True)
                await pages_tab.click()
                frame = page.locator('iframe[title="数值设置"]')
                live = page.frame_locator('iframe[title="数值设置"]')
                await expect(live.locator("body")).to_have_attribute("data-ready", "true")
                first_frame = await frame.element_handle()
                first_url = await frame.get_attribute("src")
                await page.get_by_role("tab", name="配置表单", exact=True).click()
                await expect(frame).to_be_hidden()
                _write_view_revision(directory, html, script, "hidden")
                # 隐藏期间真实契约继续轮询，页面窗口和其输入会话不被替换。
                await _next_resource(page, "surface")
                await _next_resource(page, "surface")
                assert await frame.get_attribute("src") == first_url
                assert await frame.evaluate("(node, original) => node === original", first_frame)
                await pages_tab.click()
                await expect(live.locator("body")).to_have_attribute("data-asset-version", "hidden", timeout=10_000)
                await expect(live.locator("#hot-marker")).to_have_text("页面版本 hidden")
                await expect(live.locator("#hot-marker")).to_have_css("color", "rgb(12, 34, 56)")
                second_frame = await frame.element_handle()
                second_url = await frame.get_attribute("src")
                assert second_url != first_url
                value = live.get_by_role("spinbutton", name="数值", exact=True)
                await value.fill("18")
                await expect(value).to_be_focused()
                _write_view_revision(directory, html, script, "focused")
                # 已实际读到新资源 revision，iframe 内输入期间仍沿用旧窗口。
                async with asyncio.timeout(10):
                    while True:
                        payload = await _next_resource(page, "views")
                        if payload["items"][0]["revision"] not in second_url:
                            break
                await _next_resource(page, "views")
                assert await frame.get_attribute("src") == second_url
                assert await frame.evaluate("(node, original) => node === original", second_frame)
                await expect(value).to_have_value("18")
                await expect(live.locator("body")).to_have_attribute("data-asset-version", "hidden")
                await pages_tab.click()
                await expect(live.locator("body")).to_have_attribute("data-asset-version", "focused", timeout=10_000)
                await expect(live.locator("#hot-marker")).to_have_text("页面版本 focused")
                assert runtime.manager.get_plugin(_NAME) is plugin, "修改页面资源不应重启插件后端"
            finally:
                await browser.close()
    finally:
        await watcher.stop()
