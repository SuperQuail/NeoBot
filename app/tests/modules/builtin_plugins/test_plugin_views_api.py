"""页面静态资源可分发，动作与私有配置仍经过会话和 CSRF。"""

import httpx
import pytest

from neobot_modloader import ActionError

from test_dashboard_api import _login, _start_panel


async def test_plugin_view_metadata_needs_session_and_documents_have_an_opaque_origin(tmp_path, monkeypatch):
    server, control, base, _ = await _start_panel(tmp_path)
    public = tmp_path / "public"
    public.mkdir()
    (public / "index.html").write_text('<script src="_sdk.js"></script><h1>插件页面</h1>', encoding="utf-8")
    (public / "app.js").write_text("window.example = true", encoding="utf-8")

    def views(name):
        return [{"id": "subscriptions", "title": "直播订阅", "entry": "web/index.html", "anchors": ["group"]}]

    def asset(name, view, relative):
        if name != "demo" or view != "subscriptions" or relative not in {"", "app.js"}:
            raise ActionError("view_asset_not_found", "页面资源不存在")
        return public / (relative or "index.html")

    monkeypatch.setattr(control, "views", views, raising=False)
    monkeypatch.setattr(control, "view_asset", asset, raising=False)
    try:
        token, csrf = await _login(base)
        async with httpx.AsyncClient() as client:
            denied = await client.get(base + "/api/plugins/demo/views")
            assert denied.status_code == 401
            listed = await client.get(base + "/api/plugins/demo/views", headers={"X-Token": token})
            assert listed.status_code == 200
            view_url = listed.json()["items"][0]["url"]
            assert view_url == "/plugins-ui/demo/subscriptions/"
            document = await client.get(base + view_url)
            assert document.status_code == 200
            assert "插件页面" in document.text
            policy = document.headers["Content-Security-Policy"]
            assert "sandbox allow-scripts" in policy
            assert "allow-same-origin" not in policy
            assert "connect-src 'none'" in policy
            assert document.headers["X-Frame-Options"] == "SAMEORIGIN"
            assert document.headers["Cache-Control"] == "no-store"
            assert document.headers["Access-Control-Allow-Origin"] == "*"
            assert "Access-Control-Allow-Credentials" not in document.headers
            script = await client.get(base + view_url + "app.js")
            assert script.status_code == 200
            assert "window.example" in script.text
            shared_style = await client.get(base + view_url + "_ui.css")
            assert shared_style.status_code == 200
            assert shared_style.headers["Content-Type"].startswith("text/css")
            assert ".nb-field" in shared_style.text
            assert "sandbox allow-scripts" in shared_style.headers["Content-Security-Policy"]
            missing_view_style = await client.get(base + "/plugins-ui/absent/subscriptions/_ui.css")
            assert missing_view_style.status_code == 404
            hidden = await client.get(base + view_url + "config.toml")
            assert hidden.status_code == 404
            no_csrf = await client.post(
                base + "/api/plugins/demo/actions/write", headers={"X-Token": token}, json={"values": {}}
            )
            assert no_csrf.status_code == 403
            assert csrf
    finally:
        await server.stop()


@pytest.mark.browser
async def test_plugin_form_can_use_submit_events_but_cannot_submit_network_requests(tmp_path, monkeypatch):
    from playwright.async_api import async_playwright, expect

    server, control, base, _ = await _start_panel(tmp_path)
    public = tmp_path / "public"
    public.mkdir()
    (public / "index.html").write_text(
        '<form id="handled"><input aria-label="事项" required><button>添加</button></form>'
        '<p id="result">等待操作</p><form action="/healthz" method="post"><button>外发表单</button></form>'
        '<p id="network">尚未外发</p><script src="app.js"></script>',
        encoding="utf-8",
    )
    (public / "app.js").write_text(
        "document.querySelector('#handled').addEventListener('submit', event => {"
        "event.preventDefault(); document.querySelector('#result').textContent='事件已处理'; });"
        "document.addEventListener('securitypolicyviolation', event => { if(event.violatedDirective === 'form-action')"
        "document.querySelector('#network').textContent='外发已阻止'; });",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        control, "view_asset", lambda name, view, relative: public / (relative or "index.html"), raising=False
    )
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page()
                outbound = []
                page.on("request", lambda request: outbound.append(request.url) if request.method == "POST" else None)
                await page.goto(base + "/healthz")
                await page.evaluate(
                    "url => { const frame=document.createElement('iframe'); frame.src=url; "
                    "frame.sandbox='allow-scripts allow-forms'; document.body.append(frame); }",
                    base + "/plugins-ui/demo/form/",
                )
                frame = page.frame_locator("iframe")
                await frame.get_by_role("textbox", name="事项").fill("合成事项")
                await frame.get_by_role("button", name="添加", exact=True).click()
                await expect(frame.locator("#result")).to_have_text("事件已处理")
                await frame.get_by_role("button", name="外发表单", exact=True).click()
                await expect(frame.locator("#network")).to_have_text("外发已阻止")
                assert outbound == []
            finally:
                await browser.close()
    finally:
        await server.stop()


@pytest.mark.browser
@pytest.mark.parametrize("embedded", [True, False])
@pytest.mark.parametrize("module_script", [False, True])
async def test_plugin_document_has_no_dashboard_origin_even_when_opened_directly(
    tmp_path, monkeypatch, embedded, module_script
):
    from playwright.async_api import async_playwright, expect

    server, control, base, _ = await _start_panel(tmp_path)
    public = tmp_path / "public"
    public.mkdir()
    kind = ' type="module"' if module_script else ""
    (public / "index.html").write_text(
        f'<h1 id="result">等待脚本</h1><script{kind} src="app.js"></script>', encoding="utf-8"
    )
    (public / "chunk.js").write_text('export const isolated = "来源已隔离";', encoding="utf-8")
    (public / "app.js").write_text(
        ('const { isolated } = await import("./chunk.js");' if module_script else 'const isolated = "来源已隔离";')
        + "try { localStorage.getItem('neobot-dashboard-token'); document.querySelector('#result').textContent='未隔离'; }"
        "catch (error) { document.querySelector('#result').textContent=isolated; }",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        control, "view_asset", lambda name, view, relative: public / (relative or "index.html"), raising=False
    )
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page()
                await page.goto(base + "/healthz")
                await page.evaluate("localStorage.setItem('neobot-dashboard-token', 'synthetic-view-token')")
                url = base + "/plugins-ui/demo/example/"
                if embedded:
                    await page.evaluate(
                        "url => { const frame = document.createElement('iframe'); frame.src=url; "
                        "frame.sandbox='allow-scripts'; document.body.append(frame); }",
                        url,
                    )
                    result = page.frame_locator("iframe").locator("#result")
                else:
                    await page.goto(url)
                    result = page.locator("#result")
                await expect(result).to_have_text("来源已隔离")
            finally:
                await browser.close()
    finally:
        await server.stop()
