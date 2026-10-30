"""从最终插件包启动真实宿主，验证设置页、说明书与业务权限。"""

from __future__ import annotations

from pathlib import Path
import re

import pytest
from playwright.async_api import Page, Request, async_playwright, expect

from neobot_app.builtin_plugins.dashboard.config import DashboardConfig
from neobot_app.builtin_plugins.dashboard.server import DashboardServer
from neobot_app.panel_auth import PanelPasswordStore
from neobot_contracts.ports.logging import NullLogger
from neobot_modloader.installer import PluginInstaller
from neobot_modloader.runtime import PluginRuntime
from neobot_modloader.sdk.tooling import build_package, export_contract

from .plugin_settings_fixture import SETTINGS_PAGE, SETTINGS_SCRIPT

_PASSWORD = "NeoBot-Panel-2026"
_NAME = "workbench_demo"
_PLUGIN = """from pydantic import BaseModel, Field
from neobot_modloader import Plugin


class Config(BaseModel):
    greeting: str = Field(default="你好", title="回复内容")


class Value(BaseModel):
    value: int = Field(ge=1, title="数值")


plugin = Plugin("workbench_demo", version="1.0.0", config=Config)
plugin.current = 0
plugin.action_calls = []


@plugin.action("set", title="保存数值", input_model=Value)
async def set_value(values, invocation):
    plugin.action_calls.append("set")
    plugin.current = values.value
    return {"value": plugin.current}


@plugin.action("list", title="读取数值", permission="read")
async def list_values(values, invocation):
    plugin.action_calls.append("list")
    return [{"value": plugin.current}]


@plugin.action("ready", title="检查设置", permission="read")
async def ready(values, invocation):
    plugin.action_calls.append("ready")
    return {"completed": plugin.current > 0}


plugin.resource("values", title="已保存数值", list_action="list",
                columns=[{"key": "value", "title": "数值"}], create_action="set")
plugin.view("settings", title="数值设置", entry="web/settings/index.html", anchors=["value"])
plugin.guide("first-use", title="设置教程", steps=[
    {"target": "action.set", "text": "填写数值并保存。", "chapter": "填写数值", "example": {"value": 17}},
    {"target": "resource.values", "text": "确认表格已经更新。", "chapter": "核对列表", "example": {"items": [{"value": 17}]}},
], completion_action="ready", demo={"actions": {"set": {"value": 17}, "list": [{"value": 17}], "ready": {"completed": True}}})
plugin.guide("settings-use", title="设置页教程", steps=[
    {"target": "view.settings.value", "text": "在数值设置中填写数值并保存。", "chapter": "填写数值", "example": {"value": 17}},
    {"target": "view.settings.value", "text": "读取已保存的数值，确认结果。", "chapter": "核对结果", "example": {"value": 17}},
], demo={"actions": {"set": {"value": 17}, "list": [{"value": 17}]}})
plugin.guide("reading", title="长篇阅读", steps=[
    {"target": "config.greeting", "chapter": f"章节 {index + 1}",
     "text": f"第 {index + 1} 步说明。" + "核对配置后再返回真实页面操作。" * 12,
     "command": {"text": f"/核对 {index + 1}", "context": "机器人私聊", "reply": "合成结果"}}
    for index in range(14)
])
"""


class _Adapter:
    connected = True

    async def call_api(self, action: str, params: dict, timeout: float = 5.0) -> dict:
        if action == "get_login_info":
            return {"status": "ok", "data": {"user_id": 10001, "nickname": "离线测试"}}
        return {"status": "ok", "data": {}}


class _LoggerFactory:
    def get_logger(self, name: str) -> NullLogger:
        return NullLogger()


@pytest.fixture
async def installed_panel(tmp_path: Path, unused_tcp_port: int):
    source = tmp_path / "source"
    source.mkdir()
    (source / "plugin.toml").write_text(
        'name = "workbench_demo"\nversion = "1.0.0"\n'
        'python_dependencies = ["pydantic>=2,<3"]\n'
        '[sdk]\nversion = 1\ncontract = "plugin.contract.json"\npages = ["web/settings/index.html"]\n',
        encoding="utf-8",
    )
    (source / "__init__.py").write_text(_PLUGIN, encoding="utf-8")
    settings = source / "web" / "settings"
    settings.mkdir(parents=True)
    (settings / "index.html").write_text(SETTINGS_PAGE, encoding="utf-8")
    (settings / "app.js").write_text(SETTINGS_SCRIPT, encoding="utf-8")
    exported = export_contract(source)
    assert exported.ok, exported.errors
    package = tmp_path / "plugin.zip"
    built = build_package(source, package)
    assert built.ok, built.errors
    archive = package.read_bytes()

    async def fetcher(url: str) -> bytes:
        return archive

    installer = PluginInstaller(plugin_dir=tmp_path / "plugins", fetcher=fetcher)
    installed = await installer.install("browser-fixture/plugin")
    assert installed.ok, installed.error
    # 后续运行只使用最终包，删除作者源码可暴露对源码目录的意外依赖。
    (source / "__init__.py").unlink()
    adapter = _Adapter()
    runtime = PluginRuntime(
        plugin_dir=installer.plugin_dir,
        data_dir=tmp_path / "data",
        adapter=adapter,
        logger_factory=_LoggerFactory(),
        installer=installer,
    )
    config = tmp_path / "config.toml"
    config.write_text('version = "0.6.0"\n', encoding="utf-8")
    env = tmp_path / ".env"
    env.write_text("# 离线测试不使用外部服务凭据。\n", encoding="utf-8")
    panel_data = tmp_path / "panel"
    PanelPasswordStore(panel_data / "auth.json").set_password(_PASSWORD)
    server = DashboardServer(
        plugin_name="dashboard",
        config=DashboardConfig(host="127.0.0.1", port=unused_tcp_port),
        data_dir=panel_data,
        logger=NullLogger(),
        adapter=adapter,
        plugin_control=runtime.control,
        config_path=config,
        env_path=env,
        backup_dir=tmp_path / "backups",
    )
    try:
        runtime.load_all()
        await runtime.load_registered()
        await runtime.start_all()
        assert runtime.control.surface(_NAME)["available"]
        await server.start()
        yield server, runtime, f"http://127.0.0.1:{server.bound_port}"
    finally:
        await server.stop()
        for name in reversed(list(runtime.manager.names())):
            await runtime.unload_plugin(name, force=True)


async def _expect_notice_above_dialog(page: Page, title: str) -> None:
    notice = page.get_by_role("group", name=title, exact=True)
    await expect(notice).to_be_visible()
    # 可见性断言不能发现堆叠遮挡，实际命中点也必须属于通知自身。
    above_dialog = await notice.evaluate("""node => {
        const bounds = node.getBoundingClientRect();
        const hit = document.elementFromPoint(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
        return node.contains(hit);
    }""")
    assert above_dialog, "全局 InfoBar 被业务弹窗遮挡"


async def _select_plugin(page: Page) -> None:
    # 窄屏先从列表进入详情，与使用者实际操作路径一致。
    await page.get_by_role("button", name=re.compile(rf"^{_NAME}\b")).click()


@pytest.mark.browser
@pytest.mark.parametrize("viewport", [(1280, 720), (390, 844)], ids=["desktop", "phone"])
async def test_installed_plugin_manual_keeps_configuration_and_never_runs_actions(
    installed_panel, tmp_path: Path, viewport
):
    server, runtime, base = installed_panel
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page(
                viewport={"width": viewport[0], "height": viewport[1]}, reduced_motion="no-preference"
            )
            mutations: list[str] = []

            def record_mutation(request: Request) -> None:
                if request.method == "POST" and f"/api/plugins/{_NAME}/" in request.url:
                    mutations.append(request.url)

            page.on("request", record_mutation)
            await page.goto(base + "/#/login")
            await page.get_by_label("面板密码", exact=True).fill(_PASSWORD)
            await page.get_by_role("button", name="登录工作台", exact=True).click()
            await expect(page).to_have_url(base + "/#/dashboard")
            await page.goto(base + "/#/plugins")
            await _select_plugin(page)
            await page.get_by_role("tab", name="插件页面", exact=True).click()
            live = page.frame_locator('iframe[title="数值设置"]')
            await expect(live.locator("body")).to_have_attribute("data-ready", "true")
            plugin = runtime.manager.get_plugin(_NAME)
            assert plugin is not None
            assert plugin.action_calls == ["list"]
            mutations.clear()
            await page.get_by_role("tab", name="配置表单", exact=True).click()
            greeting = page.locator("#cfg-greeting")
            original_input = await greeting.element_handle()
            await greeting.fill("尚未保存的问候")
            await expect(greeting).to_have_value("尚未保存的问候")
            await expect(page.get_by_role("button", name="保存并重载", exact=True)).to_be_enabled()
            await page.get_by_role("button", name="使用说明", exact=True).click()
            dialog = page.get_by_role("dialog", name=f"{_NAME} · 思索说明书")
            await expect(dialog).to_be_visible()
            await expect(page.get_by_role("dialog")).to_have_count(1)
            await expect(dialog.get_by_role("tablist")).to_have_count(0)
            await expect(dialog.get_by_role("button", name="跟着做", exact=True)).to_have_count(0)
            await expect(dialog.get_by_role("button", name="检查是否完成", exact=True)).to_have_count(0)
            await expect(dialog.get_by_role("button", name="执行 保存数值", exact=True)).to_have_count(0)
            await expect(dialog.get_by_role("spinbutton")).to_have_count(0)
            # 保留旧 action/resource 契约的说明能力，但不恢复真实通用表单。
            caption = dialog.locator(".ponder-caption")
            await expect(caption).to_contain_text("填写数值并保存。")
            await expect(dialog.get_by_role("button", name="播放演示", exact=True)).to_be_visible()
            bounds = await dialog.bounding_box()
            assert bounds is not None
            assert abs(bounds["x"]) <= 1 and abs(bounds["y"]) <= 1
            assert abs(bounds["width"] - viewport[0]) <= 1
            assert abs(bounds["height"] - viewport[1]) <= 1
            overflow = await dialog.evaluate("node => node.scrollHeight - node.clientHeight")
            assert overflow <= 1
            await dialog.get_by_role("button", name="02 核对列表", exact=True).click()
            await expect(caption).to_contain_text("确认表格已经更新。")
            await dialog.get_by_role("button", name="下一步演示", exact=True).click()
            await _expect_notice_above_dialog(page, "本篇说明已播放完")
            await page.get_by_role("button", name="关闭通知", exact=True).click()
            await expect(dialog).to_be_visible()
            await dialog.get_by_role("button", name="返回配置", exact=True).click()
            await expect(dialog).to_have_count(0)
            await expect(greeting).to_have_value("尚未保存的问候")
            assert await greeting.evaluate("(node, original) => node === original", original_input)
            restore = page.get_by_role("button", name="恢复默认", exact=True)
            await expect(restore).to_be_visible()
            beside_control = await restore.evaluate("""node => {
                const control = node.closest('.cfg-control');
                const input = control?.querySelector('input, textarea, select');
                if (!input) return false;
                const buttonBounds = node.getBoundingClientRect();
                const inputBounds = input.getBoundingClientRect();
                const center = buttonBounds.y + buttonBounds.height / 2;
                return center >= inputBounds.y && center <= inputBounds.bottom;
            }""")
            assert beside_control, "恢复默认图标未与字段控件同行"
            await restore.click()
            await expect(greeting).to_have_value("你好")
            await expect(restore).to_have_count(0)
            assert await greeting.evaluate("(node, original) => node === original", original_input)
            plugin = runtime.manager.get_plugin(_NAME)
            assert plugin is not None
            assert plugin.current == 0
            assert plugin.action_calls == ["list"]
            assert mutations == []

            # 关闭管理权限后不读取配置，说明书仍可阅读。
            server._manage_plugins = False
            await page.reload()
            await _select_plugin(page)
            await page.get_by_role("tab", name="插件页面", exact=True).click()
            await expect(live.locator("body")).to_have_attribute("data-ready", "true")
            assert plugin.action_calls == ["list", "list"]
            assert mutations == [base + f"/api/plugins/{_NAME}/actions/list"]
            mutations.clear()
            await page.get_by_role("tab", name="配置表单", exact=True).click()
            await expect(page.get_by_role("heading", name="当前为只读模式", exact=True)).to_be_visible()
            await expect(greeting).to_have_count(0)
            await expect(page.get_by_role("tab", name="TOML", exact=True)).to_be_disabled()
            await expect(page.get_by_role("button", name="保存并重载", exact=True)).to_be_disabled()
            await page.get_by_role("button", name="使用说明", exact=True).click()
            await expect(dialog).to_be_visible()
            await dialog.get_by_role("button", name="返回配置", exact=True).click()
            stopped = await runtime.stop_plugin(_NAME)
            assert stopped.ok, stopped.error
            await page.reload()
            await _select_plugin(page)
            await page.get_by_role("button", name="使用说明", exact=True).click()
            await expect(dialog).to_be_visible()
            await expect(dialog.get_by_role("button", name="下一步演示", exact=True)).to_be_enabled()
            await page.screenshot(path=str(tmp_path / "plugin-manual.png"), full_page=True)
            assert plugin.current == 0
            assert plugin.action_calls == ["list", "list"]
            assert mutations == []
        finally:
            await browser.close()


@pytest.mark.browser
@pytest.mark.parametrize("viewport", [(1280, 720), (390, 844)], ids=["desktop", "phone"])
async def test_installed_plugin_setting_group_runs_live_and_suspends_during_manual(
    installed_panel, tmp_path: Path, viewport
):
    server, runtime, base = installed_panel
    plugin = runtime.manager.get_plugin(_NAME)
    assert plugin is not None
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
            posts = []

            def record_action(request: Request) -> None:
                if request.method == "POST" and f"/api/plugins/{_NAME}/actions/" in request.url:
                    posts.append(request.url)

            page.on("request", record_action)
            await page.goto(base + "/#/login")
            await page.get_by_label("面板密码", exact=True).fill(_PASSWORD)
            await page.get_by_role("button", name="登录工作台", exact=True).click()
            await expect(page).to_have_url(base + "/#/dashboard")
            await page.goto(base + "/#/plugins")
            await _select_plugin(page)
            await page.get_by_role("tab", name="插件页面", exact=True).click()
            group = page.get_by_role("region", name="数值设置", exact=True, include_hidden=True)
            frame = group.locator('iframe[title="数值设置"]')
            await expect(group).to_be_visible()
            await expect(frame).to_be_visible()
            original_frame = await frame.element_handle()
            live = group.frame_locator('iframe[title="数值设置"]')
            await expect(live.locator("body")).to_have_attribute("data-ready", "true")
            await expect(live.locator("body")).to_have_attribute("data-mode", "live")
            await expect(live.locator("output")).to_have_text("0")
            assert plugin.action_calls == ["list"]
            # 内容高度取代固定视口；短设置不会留下空白或出现第二条正文滚动条。
            await expect(frame).to_have_attribute("style", re.compile(r"height: \d+px"))
            frame_height = await frame.evaluate("node => node.clientHeight")
            body_height = await live.locator("body").evaluate("node => node.getBoundingClientRect().height")
            assert abs(frame_height - body_height) <= 1
            value = live.get_by_role("spinbutton", name="数值", exact=True)
            save = live.get_by_role("button", name="保存数值", exact=True)
            await value.fill("17")
            await save.click()
            await expect(live.locator("output")).to_have_text("17")
            await expect(page.get_by_role("group", name="数值已保存", exact=True)).to_be_visible()
            await expect(live.get_by_text("数值已保存", exact=True)).to_have_count(0)
            assert plugin.current == 17
            assert plugin.action_calls == ["list", "set", "list"]

            saved_calls = list(plugin.action_calls)
            saved_posts = list(posts)
            await page.get_by_role("button", name="使用说明", exact=True).click()
            dialog = page.get_by_role("dialog", name=f"{_NAME} · 思索说明书")
            await expect(dialog).to_be_visible()
            await expect(live.locator("body")).to_have_attribute("data-suspended", "true")
            await expect(save).to_be_disabled()
            await expect(value).to_be_disabled()
            await dialog.get_by_role("combobox", name="选择说明", exact=True).click()
            await page.get_by_role("option", name="设置页教程", exact=True).click()
            demo = dialog.frame_locator('iframe[title="数值设置"]')
            await expect(demo.locator("body")).to_have_attribute("data-mode", "demo")
            await expect(demo.locator("output")).to_have_text("17")
            await expect(dialog.get_by_role("button", name="播放演示", exact=True)).to_be_visible()
            await dialog.get_by_role("button", name="02 核对结果", exact=True).click()
            await dialog.get_by_role("button", name="下一步演示", exact=True).click()
            await _expect_notice_above_dialog(page, "本篇说明已播放完")
            assert await frame.evaluate("(node, original) => node === original", original_frame)
            assert plugin.current == 17
            assert plugin.action_calls == saved_calls
            assert posts == saved_posts
            await dialog.get_by_role("button", name="返回配置", exact=True).click()
            await expect(live.locator("body")).to_have_attribute("data-suspended", "false")
            await expect(save).to_be_enabled()
            await value.fill("18")
            # 两条路径互不混排，切换只暂停 iframe，不能销毁未提交的业务输入。
            await expect(page.get_by_role("button", name="保存并重载", exact=True)).to_have_count(0)
            await page.get_by_role("tab", name="配置表单", exact=True).click()
            await expect(live.locator("body")).to_have_attribute("data-suspended", "true")
            await expect(frame).to_be_hidden()
            await page.get_by_role("tab", name="插件页面", exact=True).click()
            await expect(live.locator("body")).to_have_attribute("data-suspended", "false")
            await expect(value).to_have_value("18")
            assert await frame.evaluate("(node, original) => node === original", original_frame)
            await save.click()
            await expect(live.locator("output")).to_have_text("18")
            assert plugin.current == 18
            assert plugin.action_calls.count("set") == 2

            # 只读仍可读取结果，按钮不能产生写入；停止插件后连读取也应停下。
            server._manage_plugins = False
            await page.reload()
            await _select_plugin(page)
            await page.get_by_role("tab", name="插件页面", exact=True).click()
            await expect(live.locator("body")).to_have_attribute("data-ready", "true")
            await expect(live.locator("output")).to_have_text("18")
            await expect(save).to_be_disabled()
            await expect(value).to_be_disabled()
            readonly_calls = list(plugin.action_calls)
            readonly_posts = list(posts)
            await page.get_by_role("button", name="使用说明", exact=True).click()
            await expect(dialog).to_be_visible()
            await dialog.get_by_role("button", name="返回配置", exact=True).click()
            assert plugin.action_calls == readonly_calls
            assert posts == readonly_posts
            stopped = await runtime.stop_plugin(_NAME)
            assert stopped.ok, stopped.error
            await page.reload()
            await _select_plugin(page)
            await page.get_by_role("tab", name="插件页面", exact=True).click()
            await expect(live.locator("body")).to_have_attribute("data-ready", "true")
            await expect(save).to_be_disabled()
            await expect(live.get_by_role("button", name="读取数值", exact=True)).to_be_disabled()
            assert plugin.current == 18
            assert plugin.action_calls == readonly_calls
            assert posts == readonly_posts
            await page.screenshot(path=str(tmp_path / "plugin-settings.png"), full_page=True)
        finally:
            await browser.close()


@pytest.mark.browser
@pytest.mark.parametrize("color_scheme", ["light", "dark"])
@pytest.mark.parametrize("viewport", [(1366, 768), (1920, 1080), (390, 844), (390, 560)])
async def test_manual_contents_search_and_return_remain_reachable(installed_panel, tmp_path, viewport, color_scheme):
    _server, runtime, base = installed_panel
    plugin = runtime.manager.get_plugin(_NAME)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page(
                viewport={"width": viewport[0], "height": viewport[1]},
                color_scheme=color_scheme,
            )
            await page.goto(base + "/#/login")
            await page.get_by_label("面板密码", exact=True).fill(_PASSWORD)
            await page.get_by_role("button", name="登录工作台", exact=True).click()
            await expect(page).to_have_url(base + "/#/dashboard")
            await page.goto(base + "/#/plugins")
            await _select_plugin(page)
            await page.get_by_role("button", name="使用说明", exact=True).click()
            dialog = page.get_by_role("dialog", name=f"{_NAME} · 思索说明书")
            await dialog.get_by_role("combobox", name="选择说明", exact=True).click()
            await page.get_by_role("option", name="长篇阅读", exact=True).click()
            await expect(dialog.get_by_role("button", name="播放演示", exact=True)).to_be_visible()
            await page.get_by_role("button", name="关闭通知", exact=True).click()
            contents = dialog.get_by_role("button", name="目录与全文", exact=True)
            await expect(contents).to_be_in_viewport()
            await contents.click()
            reader = dialog.get_by_role("region", name="说明目录与全文", exact=True)
            await expect(reader).to_be_visible()
            await expect(reader.get_by_role("button")).to_have_count(14)
            last = reader.get_by_role("button", name="查看第 14 步：章节 14", exact=True)
            await last.scroll_into_view_if_needed()
            await expect(last).to_be_in_viewport()
            search = reader.get_by_role("searchbox", name="搜索说明", exact=True)
            await search.fill("/核对 14")
            await expect(reader.get_by_role("button")).to_have_count(1)
            await expect(reader.get_by_text("/核对 14", exact=True)).to_be_visible()
            overflow = await dialog.evaluate("node => node.scrollWidth - node.clientWidth")
            assert overflow <= 1
            await page.screenshot(path=str(tmp_path / "plugin-manual-contents.png"), full_page=True)
            await last.click()
            await expect(reader).to_have_count(0)
            await expect(contents).to_be_focused()
            await expect(dialog.locator(".ponder-caption")).to_contain_text("第 14 步说明。")
            await expect(dialog.get_by_role("button", name="播放演示", exact=True)).to_be_visible()
            assert plugin.action_calls == []
            assert plugin.current == 0
            await dialog.get_by_role("button", name="返回配置", exact=True).click()
            await expect(dialog).to_have_count(0)
        finally:
            await browser.close()
