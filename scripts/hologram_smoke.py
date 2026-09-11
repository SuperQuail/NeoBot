"""全息终端浏览器回归：可读布局、保持连接移动、远处隐藏。"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "adapter" / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from bridge_perf_probe import _find_browser, _free_port, _start_server  # noqa: E402
from bridge_render_smoke import PASSWORD  # noqa: E402

#: 截图默认写进临时目录，避免浏览器回归把仓库工作区弄脏；需要留档时用 HOLOGRAM_SHOT_DIR 指定。
SHOT_DIR = Path(os.environ.get("HOLOGRAM_SHOT_DIR") or tempfile.mkdtemp(prefix="hologram-shots-"))

MEASURE = """
const host = document.querySelector('.panel-anchor');
const engine = window.__bridgeDebug && window.__bridgeDebug.getEngine();
const cam = engine ? engine.camera : null;
const rect = (el) => {
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)];
};
const out = {
  viewport: [window.innerWidth, window.innerHeight],
  anchor: rect(host),
  holo: rect(document.querySelector('.panel-anchor-holo')),
  hologram: rect(document.querySelector('.hologram')),
  lift: host ? host.style.getPropertyValue('--panel-lift') : null,
  opacity: host ? host.style.opacity : null,
  elementSize: host ? [host.offsetWidth, host.offsetHeight] : null,
  transform: host ? host.style.transform.slice(0, 72) : null,
};
if (engine) {
  out.player = [+engine.player.position.x.toFixed(2), +engine.player.position.y.toFixed(2),
                +engine.player.position.z.toFixed(2)];
  out.yaw = +engine.player.yaw.toFixed(2);
}
if (cam) out.camera = [+cam.position.x.toFixed(2), +cam.position.y.toFixed(2), +cam.position.z.toFixed(2)];
return JSON.stringify(out);
"""

#: 逐座终端检查内容是否撑出机框：hologram 的 scrollWidth/Height 不得超过自身
OVERFLOW = """
const holo = document.querySelector('.hologram');
if (!holo) return JSON.stringify({ error: 'no panel' });
const head = holo.querySelector('.hologram-head');
const body = holo.querySelector('.hologram-body');
const over = (el) => el
  ? [Math.max(0, el.scrollWidth - el.clientWidth), Math.max(0, el.scrollHeight - el.clientHeight)]
  : null;
// 抬头里各个子元素是否被挤出机框（标题竖排时 h2 的宽度会塌成一行字）
const title = holo.querySelector('.hologram-title h2');
return JSON.stringify({
  hologram: [holo.clientWidth, holo.clientHeight],
  overflow: over(holo),
  headOverflow: over(head),
  bodyOverflow: over(body),
  title: title ? [Math.round(title.getBoundingClientRect().width), Math.round(title.getBoundingClientRect().height)] : null,
});
"""


def _stations(browser_path: str, url: str) -> None:
    from DrissionPage import ChromiumOptions, ChromiumPage

    options = ChromiumOptions()
    options.set_browser_path(browser_path)
    options.headless(os.environ.get("HOLOGRAM_HEADED") != "1")
    options.set_argument("--no-sandbox")
    options.set_argument("--disable-dev-shm-usage")
    options.set_argument("--enable-unsafe-swiftshader")
    options.set_argument("--use-gl=angle")
    options.set_argument("--use-angle=swiftshader")
    options.set_argument("--window-size=1600,900")
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
        page.wait(4)

        for index in range(8):
            page.run_js("document.querySelectorAll('.bridge-dock button')[1].click();")
            page.wait(0.6)
            page.run_js(f"const b = document.querySelectorAll('.ov-nav-item')[{index}]; if (b) b.click();")
            page.wait(2.5)
            print(f"  [{index + 1}]", page.run_js(OVERFLOW))
            page.run_js("const a = document.querySelector('.hologram-close'); if (a) a.click();")
            page.wait(0.8)
    finally:
        try:
            page.quit()
        except Exception:
            pass


def _drive(browser_path: str, url: str) -> None:
    from DrissionPage import ChromiumOptions, ChromiumPage

    options = ChromiumOptions()
    options.set_browser_path(browser_path)
    options.headless(os.environ.get("HOLOGRAM_HEADED") != "1")
    options.set_argument("--no-sandbox")
    options.set_argument("--disable-dev-shm-usage")
    options.set_argument("--enable-unsafe-swiftshader")
    options.set_argument("--use-gl=angle")
    options.set_argument("--use-angle=swiftshader")
    options.set_argument("--window-size=1600,900")
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
        page.wait(4)

        # 通过终端总览打开 CPU-05（主机机柜）——与用户截图里的那一座相同
        page.run_js("const b = document.querySelector('.bridge-dock button'); if (b) b.click();")
        page.wait(1.2)
        clicked = page.run_js(
            """
            const cards = [...document.querySelectorAll('.ov-terminal')];
            const target = cards.find((c) => c.textContent.includes('CPU-05')) || cards[4];
            if (target) target.click();
            return !!target;
            """
        )
        print("点击 CPU-05：", clicked)
        page.wait(5)
        print("刚打开：", page.run_js(MEASURE))
        assert page.run_js("return window.__bridgeDebug.getEngine().input.isEnabled();"), "terminal froze movement"
        assert page.run_js("return document.querySelector('.hologram-title h2').clientWidth > 120;"), "cramped title"
        assert page.run_js("return document.querySelector('.hologram-body').clientHeight > 250;"), "collapsed body"
        before = page.run_js("return window.__bridgeDebug.getEngine().player.position.toArray();")
        page.run_js("window.dispatchEvent(new KeyboardEvent('keydown', {code: 'KeyS', bubbles: true}));")
        page.wait(0.7)
        page.run_js("window.dispatchEvent(new KeyboardEvent('keyup', {code: 'KeyS', bubbles: true}));")
        after = page.run_js("return window.__bridgeDebug.getEngine().player.position.toArray();")
        assert sum((a - b) ** 2 for a, b in zip(after, before)) > 0.01, "player did not move"
        assert page.run_js("return !!document.querySelector('.hologram');"), "walking disconnected terminal"
        print("PASS: readable layout and walking without disconnect", before, after)
        # CDP mouse events exercise real DOM hit testing, not an input-state shortcut.
        yaw = page.run_js("return window.__bridgeDebug.getEngine().player.yaw;")
        point = page.run_js("const r = document.querySelector('.hologram-head').getBoundingClientRect(); return [r.x + 50, r.y + 20];")
        x, y = point
        page.run_cdp("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
        page.run_cdp("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="right", buttons=2, clickCount=1)
        page.run_cdp("Input.dispatchMouseEvent", type="mouseMoved", x=x+70, y=y+20, button="right", buttons=2)
        page.run_cdp("Input.dispatchMouseEvent", type="mouseReleased", x=x+70, y=y+20, button="right", buttons=0, clickCount=1)
        page.wait(0.5)
        assert abs(page.run_js("return window.__bridgeDebug.getEngine().player.yaw;") - yaw) > 0.05, "right drag did not rotate camera"
        assert page.run_js("return !document.pointerLockElement && !!document.querySelector('.hologram');"), "drag changed terminal connection"
        print("PASS: right-drag camera with free cursor")
        page.run_js("window.__smokeStation = window.__bridgeDebug.stations.find(s => s.id === document.querySelector('.panel-anchor').dataset.station); window.__bridgeDebug.getEngine().warpTo(window.__smokeStation);")
        page.wait(0.5)
        page.get_screenshot(path=str(SHOT_DIR / "near.png"))

        # 把玩家挪回中央枢纽 —— 复刻用户截图里的位置（坐标 0/0，面板仍开着）
        page.run_js(
            """
            const engine = window.__bridgeDebug.getEngine();
            engine.player.teleport([0, 0, 0], Math.PI / 2);
            return true;
            """
        )
        page.wait(3)
        print("回到枢纽：", page.run_js(MEASURE))
        assert page.run_js("return Number(document.querySelector('.panel-anchor').style.opacity) === 0;"), "hidden terminal stuck to view"
        page.get_screenshot(path=str(SHOT_DIR / "far.png"))

        def press(key, code, vk):
            page.run_cdp("Input.dispatchKeyEvent", type="keyDown", key=key, code=code, windowsVirtualKeyCode=vk)
            page.run_cdp("Input.dispatchKeyEvent", type="keyUp", key=key, code=code, windowsVirtualKeyCode=vk)
            page.wait(0.6)

        if os.environ.get("HOLOGRAM_SIMULATE_LOCK") == "1":
            # Explicit integration-only mode for hosts that reject native pointer lock.
            # Mouse drag/hit testing and keyboard events above/below remain real CDP input.
            print("SIMULATED pointer lock: native acquisition is NOT validated in this mode")
            page.run_js("""
              let locked = null;
              Object.defineProperty(document, 'pointerLockElement', {configurable: true, get: () => locked});
              document.querySelector('.bridge-canvas').requestPointerLock = function() {
                locked = this;
                document.dispatchEvent(new Event('pointerlockchange'));
                return Promise.resolve();
              };
              document.exitPointerLock = () => {
                locked = null;
                document.dispatchEvent(new Event('pointerlockchange'));
              };
            """)
        page.run_js("""
          window.__lockProbe = [];
          const canvas = document.querySelector('.bridge-canvas');
          const request = canvas.requestPointerLock.bind(canvas);
          canvas.requestPointerLock = (...args) => {
            window.__lockProbe.push({request: true, active: navigator.userActivation.isActive, focus: document.hasFocus()});
            const result = request(...args);
            result?.catch(e => window.__lockProbe.push({error: e.message}));
            return result;
          };
          window.addEventListener('keydown', e => window.__lockProbe.push({key: e.code, target: e.target.tagName, trusted: e.isTrusted}), true);
        """)
        press("v", "KeyV", 86)
        print("V lock diagnostics:", page.run_js("return window.__lockProbe;"))
        assert page.run_js("return !!document.pointerLockElement;"), "V failed to acquire pointer lock"
        page.run_js("window.__bridgeDebug.getEngine().warpTo(window.__smokeStation);")
        page.wait(1)
        print("reentry target:", page.run_js("return window.__bridgeDebug.getEngine().snapshot().target;"))
        press("f", "KeyF", 70)
        assert page.run_js("return !document.pointerLockElement && !!document.querySelector('.hologram');"), "same-station F failed to return cursor"
        page.wait(0.5)
        assert page.run_js("return !!document.querySelector('.hologram');"), "programmatic F unlock closed terminal"
        press("Escape", "Escape", 27)
        assert page.run_js("return !document.querySelector('.hologram') && !document.pointerLockElement;"), "one Escape did not close terminal"
        print("PASS: leave, return, F reentry, single Escape")

        press("f", "KeyF", 70)
        press("v", "KeyV", 86)
        assert page.run_js("return !!document.pointerLockElement;"), "lock not acquired for browser-unlock regression"
        # Emulate the browser consuming Escape: no page keydown, only a lock loss.
        page.run_js("document.exitPointerLock();")
        page.wait(1)
        assert page.run_js("return !document.querySelector('.hologram') && !document.pointerLockElement;"), "browser-consumed Escape required a second press"
        print("PASS: browser-consumed Escape closes without relocking")
    finally:
        try:
            page.quit()
        except Exception:
            pass


async def main() -> int:
    browser = _find_browser()
    if browser is None:
        print("未找到浏览器")
        return 0
    server = await _start_server()
    base = f"http://127.0.0.1:{server.bound_port}"
    mode = sys.argv[1] if len(sys.argv) > 1 else "one"
    try:
        await asyncio.wait_for(
            asyncio.to_thread(
                _drive if mode == "one" else _stations, browser, base + "/bridge/"
            ),
            timeout=180,
        )
    except asyncio.TimeoutError:
        print("超时")
    finally:
        await server.stop()
        print("截图目录：", SHOT_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
