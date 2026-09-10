"""舰桥端到端冒烟：用真实面板进程取回 3D 控制台的入口、静态资源与接口。

用法（仓库根目录）：
    .venv/Scripts/python.exe scripts/bridge_smoke.py

只启动 dashboard 插件本身（不拉起 QQ 适配器），因此可以在开发机上离线跑。
退出码非 0 表示舰桥资源或接口有问题。
"""

from __future__ import annotations

import asyncio
import re
import sys
import tempfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "adapter" / "src"))

from neobot_app.builtin_plugins.dashboard.config import DashboardConfig  # noqa: E402
from neobot_app.builtin_plugins.dashboard.server import DashboardServer  # noqa: E402
from neobot_app.panel_auth import get_panel_password_store  # noqa: E402


class _Logger:
    def info(self, *_args, **_kwargs) -> None: ...
    def warning(self, *_args, **_kwargs) -> None: ...
    def exception(self, *_args, **_kwargs) -> None: ...


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="bridge-smoke-"))
    config_path = tmp / "config.toml"
    config_path.write_text('version = "0.5.0"\n[dashboard]\nenabled = true\n', encoding="utf-8")
    env_path = tmp / ".env"
    env_path.write_text("", encoding="utf-8")
    data_dir = tmp / "data"
    password = "bridge-smoke-pass"
    get_panel_password_store(data_dir / "auth.json").set_password(password)

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
    base = f"http://127.0.0.1:{server.bound_port}"
    failures: list[str] = []

    def check(label: str, condition: bool, detail: str = "") -> None:
        status = "OK  " if condition else "FAIL"
        print(f"[{status}] {label}{(' — ' + detail) if detail and not condition else ''}")
        if not condition:
            failures.append(label)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            entry = await client.get(f"{base}/bridge/")
            check("舰桥入口返回 HTML", entry.status_code == 200 and "text/html" in entry.headers.get("content-type", ""))
            check("入口不被缓存", entry.headers.get("cache-control") == "no-store")

            scripts = re.findall(r'src="(/bridge/[^"]+\.js)"', entry.text)
            check("入口引用 /bridge/ 下的脚本", len(scripts) >= 1, f"scripts={scripts}")
            for src in scripts:
                asset = await client.get(base + src)
                check(
                    f"脚本 {src} 可下载且 MIME 正确",
                    asset.status_code == 200 and "javascript" in asset.headers.get("content-type", ""),
                )

            styles = re.findall(r'href="(/bridge/[^"]+\.css)"', entry.text)
            for href in styles:
                asset = await client.get(base + href)
                check(f"样式 {href} 可下载", asset.status_code == 200 and "css" in asset.headers.get("content-type", ""))

            missing = await client.get(f"{base}/bridge/assets/nope.js")
            check("缺失资源返回 404（不回 HTML）", missing.status_code == 404)

            csp = entry.headers.get("content-security-policy", "")
            check("CSP 放行 blob worker", "worker-src 'self' blob:" in csp, csp)
            check("CSP 未放开 unsafe-eval", "unsafe-eval" not in csp)

            login = await client.post(f"{base}/api/auth/login", json={"password": password})
            check("登录成功", login.status_code == 200, login.text[:200])
            token = login.json().get("token", "")

            overview = await client.get(f"{base}/bridge/api/overview", headers={"X-Token": token})
            check("带前缀的接口可用", overview.status_code == 200, overview.text[:200])

            system = await client.get(f"{base}/bridge/api/system", headers={"X-Token": token})
            check("系统遥测可用（舰况数据源）", system.status_code == 200 and "cpu_percent" in system.text)

            no_csrf = await client.post(f"{base}/bridge/api/auth/logout", headers={"X-Token": token})
            check("带前缀的写操作仍要 CSRF", no_csrf.status_code == 403)

            traversal = await client.get(f"{base}/bridge/assets/..%2f..%2fserver.py")
            check("拒绝路径穿越", traversal.status_code in {403, 404})
    finally:
        await server.stop()

    print()
    if failures:
        print(f"舰桥冒烟失败 {len(failures)} 项：{', '.join(failures)}")
        return 1
    print("舰桥冒烟全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
