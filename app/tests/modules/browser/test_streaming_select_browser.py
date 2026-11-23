"""在真实 Chromium 中验证原生选择值与直播页面自绘控件同步。"""

import re
from pathlib import Path

import pytest
from playwright.async_api import async_playwright, expect


@pytest.mark.browser
async def test_subscription_surfaces_follow_dashboard_theme():
    plugins = Path(__file__).resolve().parents[3] / "src/neobot_app/builtin_plugins"
    root = plugins / "streaming_parser/web/subscriptions"
    markup = re.sub(r"<script[^>]*>.*?</script>", "", (root / "index.html").read_text(encoding="utf-8"), flags=re.S)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page()
            await page.set_content(markup)
            await page.add_style_tag(path=plugins / "dashboard/frontend/public/assets/plugin-view-ui.css")
            for stylesheet in ("style.css", "settings.css", "preview.css", "records.css"):
                await page.add_style_tag(path=root / stylesheet)
            for panel, inset in [("rgb(25, 48, 76)", "rgb(18, 42, 67)"), ("rgb(255, 255, 255)", "rgb(248, 250, 252)")]:
                await page.evaluate(
                    """([panel, inset]) => {
                    document.documentElement.style.setProperty('--panel', panel);
                    document.documentElement.style.setProperty('--panel-2', inset);
                }""",
                    [panel, inset],
                )
                for selector, color in [
                    (".preview-panel", panel),
                    (".toggle-card", panel),
                    (".group-settings-card", inset),
                    (".health-strip", inset),
                ]:
                    await expect(page.locator(selector).first).to_have_css("background-color", color, timeout=1500)
        finally:
            await browser.close()


@pytest.mark.browser
async def test_streaming_select_sync_and_readonly_in_real_browser():
    root = Path(__file__).resolve().parents[3] / "src/neobot_app/builtin_plugins/streaming_parser/web/subscriptions"
    markup = re.sub(r"<script[^>]*>.*?</script>", "", (root / "index.html").read_text(encoding="utf-8"), flags=re.S)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        try:
            await page.set_content(markup)
            await page.evaluate("""() => {
                window.NeoBotPlugin = {
                    ready: async () => ({available: true, suspended: false, permissions: ['manage'], mode: 'live'}),
                    action: async (name) => {
                        if (name === 'subscriptions.groups') return {items: [{group_id: 20001, name: '测试群'}]};
                        if (name === 'groups.settings.get') return {group_id: 20001, card_style: 'minimal', default_push_live: true};
                        if (name === 'subscriptions.health') return {running: true, subscriptions: 0};
                        return {items: []};
                    },
                    notify: async () => {}, registerAnchor: () => () => {},
                    onContext: (callback) => {window.updateContext = callback; return () => {};},
                    onGuideStep: () => () => {},
                };
            }""")
            await page.add_script_tag(content=(root / "app.js").read_text(encoding="utf-8"))
            trigger = page.locator("#group_id").locator("..", has=page.locator("#group_id")).locator(".select-control")
            await expect(trigger).to_be_enabled()
            await trigger.click()
            await page.locator("#group_id").locator("..").locator('[data-value="20001"]').click()
            await expect(page.locator("#group_id")).to_have_value("20001")
            await expect(trigger).to_contain_text("测试群")
            await expect(page.locator("#settings-style")).to_have_value("minimal")
            await expect(page.locator("#settings-style").locator("..").locator(".select-control")).to_contain_text(
                "极简白"
            )
            await page.evaluate(
                "window.updateContext({available: true, suspended: false, permissions: [], mode: 'live'})"
            )
            await expect(page.locator("#settings-style").locator("..").locator(".select-control")).to_be_disabled()
            await page.evaluate("window.dispatchEvent(new Event('pagehide'))")
        finally:
            await browser.close()
