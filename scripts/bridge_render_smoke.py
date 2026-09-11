"""舰桥渲染冒烟：用无头浏览器真实加载 3D 舰桥，抓取控制台报错与着色器编译失败。

着色器是唯一「静态检查看不出来、跑起来才知道」的部分（GLSL 编译错误只会出现在
浏览器控制台），因此这里必须用真实浏览器验一遍。

用法（仓库根目录）：
    .venv/Scripts/python.exe scripts/bridge_render_smoke.py

需要本机有 Edge 或 Chrome。找不到浏览器时脚本会跳过并返回 0。
"""

from __future__ import annotations

import asyncio
import json
import os
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

PASSWORD = "bridge-render-pass"
#: 整个浏览器阶段的上限：无头实例偶发卡死时必须能自己退出，否则会把整机拖住
BROWSER_TIMEOUT_SECONDS = 120
BROWSER_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]
# 这些关键字出现在控制台就意味着渲染链路断了
FATAL_PATTERNS = [
    "THREE.WebGLProgram",
    "shader",
    "Shader Error",
    "GL_INVALID",
    "WebGL: INVALID",
    "Cannot initialize WebGL",
    "无法初始化 WebGL",
]


class _Logger:
    def info(self, *_a, **_k) -> None: ...
    def warning(self, *_a, **_k) -> None: ...
    def exception(self, *_a, **_k) -> None: ...


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _find_browser() -> str | None:
    for path in BROWSER_CANDIDATES:
        if Path(path).is_file():
            return path
    return None


async def _start_server():
    tmp = Path(tempfile.mkdtemp(prefix="bridge-render-"))
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


def _browse(browser_path: str, url: str, *, open_panel: bool = False) -> tuple[list[str], dict]:
    """打开页面、登录、进入舰桥，返回（控制台消息, 页面状态摘要）。

    浏览器一定要 quit：无头实例漏掉会留下几十个进程把整机拖死
    （开发时踩过一次，taskkill 都要跑很久才恢复），因此这里用 try/finally 兜住。
    """
    from DrissionPage import ChromiumOptions, ChromiumPage

    options = ChromiumOptions()
    options.set_browser_path(browser_path)
    options.headless(True)
    options.set_argument("--no-sandbox")
    options.set_argument("--disable-dev-shm-usage")
    # 无头环境没有真实 GPU：允许 SwiftShader 软件渲染，否则 WebGL 直接不可用
    options.set_argument("--enable-unsafe-swiftshader")
    options.set_argument("--use-gl=angle")
    options.set_argument("--use-angle=swiftshader")
    options.set_argument("--window-size=1280,800")
    options.set_local_port(_free_port())

    page = ChromiumPage(options)
    try:
        return _drive(page, url, open_panel=open_panel)
    finally:
        try:
            page.quit()
        except Exception:
            # 退出失败不能掩盖真正的失败原因，但必须留下痕迹
            print("警告：浏览器未能正常退出，如系统变卡请手动结束 msedge/chrome 进程")


def _drive(page, url: str, *, open_panel: bool) -> tuple[list[str], dict]:
    # 在文档最开始挂钩 console.error / warn 与未捕获异常。
    # three 的着色器编译失败只走 console.error，不挂钩就一条都看不到。
    page.run_js(
        """
        if (!window.__bridgeLog) {
          window.__bridgeLog = [];
          const push = (level) => (...args) => {
            try {
              window.__bridgeLog.push(level + ': ' + args.map((a) =>
                typeof a === 'string' ? a : (a && a.message) ? a.message : String(a)).join(' '));
            } catch (e) { /* 忽略序列化失败 */ }
          };
          const originalError = console.error;
          const originalWarn = console.warn;
          console.error = (...args) => { push('error')(...args); originalError.apply(console, args); };
          console.warn = (...args) => { push('warn')(...args); originalWarn.apply(console, args); };
          window.addEventListener('error', (event) => {
            window.__bridgeLog.push('onerror: ' + (event.message || '') + ' @ ' + (event.filename || ''));
          });
          window.addEventListener('unhandledrejection', (event) => {
            window.__bridgeLog.push('rejection: ' + String(event.reason));
          });
        }
        """
    )

    page.get(url)
    page.wait.doc_loaded()

    # 登录页
    try:
        page.ele("@id=password", timeout=8).input(PASSWORD)
        page.ele("tag:button@@text():登 录", timeout=5).click()
    except Exception:
        # 已经登录或结构不同，继续走
        pass
    page.wait(2)

    # 进入舰桥并点「登舰」
    page.get(url.rstrip("/") + "/#/bridge")
    page.wait(3)
    try:
        page.ele("tag:button@@text():登舰", timeout=8).click()
    except Exception:
        pass
    page.wait(4)

    summary = page.run_js(
        """
        const canvas = document.querySelector('canvas.bridge-canvas');
        const overlay = document.querySelector('canvas.bridge-overlay');
        return JSON.stringify({
          hasCanvas: !!canvas,
          canvasSize: canvas ? [canvas.width, canvas.height] : null,
          hasOverlay: !!overlay,
          overlaySize: overlay ? [overlay.width, overlay.height] : null,
          fatal: !!document.querySelector('.bridge-fatal'),
          boot: !!document.querySelector('.boot'),
          hud: !!document.querySelector('.hud'),
          webgl: (() => {
            try {
              const c = document.createElement('canvas');
              const gl = c.getContext('webgl2') || c.getContext('webgl');
              return gl ? gl.getParameter(gl.VERSION) : null;
            } catch (e) { return 'error: ' + e.message; }
          })(),
        });
        """
    )

    # ---- 打开一座终端，验证「面板被投影到三维平面」这条链路真的跑起来了 ----
    #
    # 默认不跑：无头环境下模拟点击不稳定（而且它正是把浏览器实例拖死过一次的元凶）。
    # 需要时用 BRIDGE_SMOKE_OPEN_PANEL=1 打开。
    panel_info: dict = {"panelOpened": False, "openStep": "skipped"}
    if not open_panel:
        return _finish(page, summary, panel_info)

    try:
        # 用页内 JS 派发 click：无头环境下 DrissionPage 的元素定位经常点不中
        # （元素在 3D 画布之上、命中测试会落到 canvas），而这里要验的是渲染链路。
        # 舰桥工具条第一个按钮就是「终端总览」
        page.run_js("const b = document.querySelector('.bridge-dock button'); if (b) b.click();")
        page.wait(1.2)
        panel_info["openStep"] = "overlay-clicked"

        # 终端卡片：点第一座（指挥台），与「导航到面板」是同一条路径
        panel_info["cards"] = page.run_js(
            "const c = document.querySelectorAll('.ov-terminal'); if (c.length) c[0].click(); return c.length;"
        )
        page.wait(3)
        panel_info["openStep"] = "card-clicked"
        panel_info["panelOpened"] = True
    except Exception as exc:  # noqa: BLE001 - 冒烟脚本需要把失败原因带回报告
        panel_info["openError"] = f"{type(exc).__name__}: {exc}"[:200]

    if panel_info["panelOpened"]:
        raw_panel = page.run_js(
            """
            const host = document.querySelector('.panel-anchor');
            if (!host) return JSON.stringify({ anchorFound: false });
            const style = getComputedStyle(host);
            const rect = host.getBoundingClientRect();
            const body = host.querySelector('.panel-anchor-body');
            return JSON.stringify({
              anchorFound: true,
              hasMatrix: style.transform.startsWith('matrix3d('),
              inlineOpacity: host.style.opacity,
              transformOrigin: style.transformOrigin,
              renderedWidth: Math.round(rect.width),
              renderedHeight: Math.round(rect.height),
              // 面板实际落在屏幕内（而不是被投影到视野外）
              onScreen: rect.width > 40 && rect.height > 30 && rect.right > 0 && rect.bottom > 0
                && rect.left < window.innerWidth && rect.top < window.innerHeight,
              hasFrame: !!host.querySelector('.hologram'),
              lift: body ? getComputedStyle(body).fontSize : null,
            });
            """
        )
        try:
            panel_info.update(json.loads(str(raw_panel)))
        except json.JSONDecodeError:
            panel_info["anchorFound"] = False
    return _finish(page, summary, panel_info)


def _finish(page, summary, panel_info: dict) -> tuple[list[str], dict]:
    """收尾：读取控制台日志与页面摘要，拼成统一的状态字典"""
    raw_log = page.run_js("return JSON.stringify(window.__bridgeLog || []);")
    try:
        messages = json.loads(raw_log) if isinstance(raw_log, str) else []
    except json.JSONDecodeError:
        messages = []

    state: dict = {}
    try:
        state = json.loads(str(summary))
    except json.JSONDecodeError:
        state = {"rawSummary": str(summary)}
    state.update(panel_info)
    return [str(item) for item in messages], state


async def main() -> int:
    browser = _find_browser()
    if browser is None:
        print("未找到 Edge / Chrome，跳过渲染冒烟（这不是失败）。")
        return 0
    if os.environ.get("BRIDGE_RENDER_SMOKE") == "0":
        print("BRIDGE_RENDER_SMOKE=0，跳过。")
        return 0

    server = await _start_server()
    base = f"http://127.0.0.1:{server.bound_port}"
    failures: list[str] = []
    open_panel = os.environ.get("BRIDGE_SMOKE_OPEN_PANEL") == "1"
    try:
        messages, state = await asyncio.wait_for(
            asyncio.to_thread(_browse, browser, base + "/bridge/", open_panel=open_panel),
            timeout=BROWSER_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        print(f"浏览器在 {BROWSER_TIMEOUT_SECONDS}s 内没有完成，判定为失败。")
        messages, state = [], {"timeout": True}
    finally:
        await server.stop()

    print("页面状态：", json.dumps(state, ensure_ascii=False))
    print(f"控制台消息 {len(messages)} 条")
    for message in messages[:40]:
        print("  ·", message)

    def check(label: str, ok: bool) -> None:
        print(f"[{'OK  ' if ok else 'FAIL'}] {label}")
        if not ok:
            failures.append(label)

    check("进入 3D 场景（未落到渲染失败分支）", not state.get("fatal"))
    check("主画布已创建", bool(state.get("hasCanvas")))
    check("合成层画布已创建", bool(state.get("hasOverlay")))
    check("抬头显示器可见（已登舰）", bool(state.get("hud")))
    if state.get("panelOpened"):
        check("面板锚点存在于场景中", bool(state.get("anchorFound")))
        check("面板已写入 matrix3d 投影矩阵", bool(state.get("hasMatrix")))
        check("面板落在屏幕可见范围内（投影没飘走）", bool(state.get("onScreen")))
        check("终端机框已挂载", bool(state.get("hasFrame")))
    else:
        print("[SKIP] 未能通过界面打开面板，跳过投影链路检查")

    if state.get("webgl") is None:
        print("提示：无头环境没有 WebGL，着色器未能真正编译（跳过着色器判定）")
    for message in messages:
        if any(pattern.lower() in message.lower() for pattern in FATAL_PATTERNS):
            failures.append(f"控制台报错：{message[:160]}")

    print()
    if failures:
        print("舰桥渲染冒烟失败：")
        for item in failures:
            print(" -", item)
        return 1
    print("舰桥渲染冒烟通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
