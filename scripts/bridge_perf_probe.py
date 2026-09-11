"""在真实浏览器里测量舰桥帧耗时（面板打开前后），用于定位卡顿。

用法（仓库根目录）：
    .venv/Scripts/python.exe scripts/bridge_perf_probe.py

脚本自己拉起面板服务、驱动无头浏览器进入 3D 舰桥，用 PerformanceObserver 抓
longtask 并采样 requestAnimationFrame 间隔，最后分别报告「未开面板」与
「打开面板后」的帧耗时分布。任何阶段超过总预算就会中断并打印已收集的数据。
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "adapter" / "src"))

from neobot_app.builtin_plugins.dashboard.config import DashboardConfig  # noqa: E402
from neobot_app.builtin_plugins.dashboard.server import DashboardServer  # noqa: E402
from neobot_app.panel_auth import get_panel_password_store  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
from bridge_render_smoke import BROWSER_CANDIDATES, PASSWORD, _Logger, _free_port  # noqa: E402

TOTAL_BUDGET_SECONDS = 90
#: 页内采样脚本：记录每帧间隔与 longtask，读一次就清空
SAMPLER = """
window.__frames = window.__frames || [];
window.__longTasks = window.__longTasks || [];
if (!window.__perfHooked) {
  window.__perfHooked = true;
  let last = performance.now();
  const tick = () => {
    const now = performance.now();
    window.__frames.push(now - last);
    last = now;
    window.__raf = requestAnimationFrame(tick);
  };
  window.__raf = requestAnimationFrame(tick);
  try {
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) window.__longTasks.push(Math.round(entry.duration));
    }).observe({ entryTypes: ['longtask'] });
  } catch (e) { /* 浏览器不支持 longtask 时忽略 */ }
}
"""


def _find_browser() -> str | None:
    for path in BROWSER_CANDIDATES:
        if Path(path).is_file():
            return path
    return None


async def _start_server():
    tmp = Path(tempfile.mkdtemp(prefix="bridge-perf-"))
    config_path = tmp / "config.toml"
    config_path.write_text('version = "0.5.0"\n[dashboard]\nenabled = true\n', encoding="utf-8")
    env_path = tmp / ".env"
    env_path.write_text("", encoding="utf-8")
    data_dir = tmp / "data"
    get_panel_password_store(data_dir / "auth.json").set_password(PASSWORD)
    server = DashboardServer(
        plugin_name="dashboard",
        config=DashboardConfig(enabled=True, host="127.0.0.1", port=_free_port()),
        data_dir=data_dir,
        logger=_Logger(),
        adapter=None,
        plugin_control=None,
        services=None,
        config_path=config_path,
        env_path=env_path,
        backup_dir=tmp / "backup",
    )
    await server.start()
    return server


def _stats(page) -> dict:
    return json.loads(
        str(
            page.run_js(
                """
                const f = (window.__frames || []).slice().sort((a, b) => a - b);
                const pick = (q) => f.length ? Math.round(f[Math.min(f.length - 1, Math.floor(f.length * q))]) : null;
                const result = {
                  frames: f.length,
                  medianMs: pick(0.5),
                  p90Ms: pick(0.9),
                  worstMs: f.length ? Math.round(f[f.length - 1]) : null,
                  longTasks: (window.__longTasks || []).slice(-8),
                };
                window.__frames = [];
                window.__longTasks = [];
                return JSON.stringify(result);
                """
            )
        )
    )


def _drive(browser_path: str, url: str) -> None:
    from DrissionPage import ChromiumOptions, ChromiumPage

    options = ChromiumOptions()
    options.set_browser_path(browser_path)
    options.headless(True)
    options.set_argument("--no-sandbox")
    options.set_argument("--disable-dev-shm-usage")
    options.set_argument("--enable-unsafe-swiftshader")
    options.set_argument("--use-gl=angle")
    options.set_argument("--use-angle=swiftshader")
    # 窗口开小一点：软件渲染下像素数量直接决定耗时，这里看的是相对变化
    options.set_argument("--window-size=800,500")
    options.set_local_port(_free_port())

    page = ChromiumPage(options)
    try:
        page.get(url)
        page.wait.doc_loaded()
        try:
            page.ele("@id=password", timeout=8).input(PASSWORD)
            page.ele("tag:button@@text():登 录", timeout=5).click()
        except Exception:
            pass
        page.wait(2)
        page.get(url.rstrip("/") + "/#/bridge")
        page.wait(3)
        try:
            page.ele("tag:button@@text():登舰", timeout=8).click()
        except Exception:
            pass
        page.wait(3)

        print("运行中：采样基准帧耗时…")
        page.run_js(SAMPLER)
        page.wait(3)
        print("  基准：", json.dumps(_stats(page), ensure_ascii=False))

        # 用页内 JS 驱动界面：无头环境下模拟真实点击经常点不中，
        # 直接派发 click 事件更稳，而且这里要测的是渲染耗时不是点击本身
        print("运行中：打开终端总览…")
        print(
            "  打开浮层：",
            page.run_js(
                "const b = document.querySelector('.bridge-dock button'); if (b) b.click(); return !!b;"
            ),
        )
        page.wait(1.2)
        print(
            "  点击卡片：",
            page.run_js(
                """
                const cards = document.querySelectorAll('.ov-terminal');
                if (cards.length) cards[0].click();
                return cards.length;
                """
            ),
        )
        page.wait(5)
        state = page.run_js(
            """
            const host = document.querySelector('.panel-anchor');
            const rect = host ? host.getBoundingClientRect() : null;
            // 面板必须真的落在视口里，而且要够大：跃迁落点算错时它会整块跑到屏幕外
            const onScreen = !!rect && rect.right > 0 && rect.bottom > 0
              && rect.left < window.innerWidth && rect.top < window.innerHeight
              && rect.width > 40 && rect.height > 30;
            return JSON.stringify({
              anchorFound: !!host,
              opacity: host ? host.style.opacity : null,
              hasMatrix: host ? getComputedStyle(host).transform.startsWith('matrix3d(') : false,
              panelTitle: document.querySelector('.hologram h2') ? document.querySelector('.hologram h2').textContent : null,
              rect: rect ? [Math.round(rect.left), Math.round(rect.top), Math.round(rect.width), Math.round(rect.height)] : null,
              onScreen,
            });
            """
        )
        print("  面板状态：", state)
        page.wait(3)
        print("  开面板后：", json.dumps(_stats(page), ensure_ascii=False))
    finally:
        try:
            page.quit()
        except Exception:
            print("警告：浏览器退出失败，如系统变卡请手动结束 msedge/chrome 进程")


async def main() -> int:
    browser = _find_browser()
    if browser is None:
        print("未找到 Edge / Chrome，跳过性能采样。")
        return 0
    server = await _start_server()
    base = f"http://127.0.0.1:{server.bound_port}"
    try:
        await asyncio.wait_for(
            asyncio.to_thread(_drive, browser, base + "/bridge/"),
            timeout=TOTAL_BUDGET_SECONDS,
        )
    except asyncio.TimeoutError:
        print(f"超过 {TOTAL_BUDGET_SECONDS}s 仍未完成 —— 这段代码很可能就是卡顿来源。")
        return 1
    finally:
        await server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
