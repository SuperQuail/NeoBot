"""面板里的 B站扫码登录：轻量单页 + 进程内登录状态机。

页面与脚本挂在面板同一端口、同一 base_path 下；二维码由 BilibiliService
的 login_with_qr(on_qr/on_status) 生成，前端轮询状态。接口仍由面板鉴权
中间件保护，并遵守 dashboard.allow_remote_manage 的本机/远程限制。
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
from typing import Any


class BilibiliQrLoginFlow:
    """一次扫码登录的进程内状态：二维码 PNG、扫码状态与后台轮询任务。"""

    def __init__(self, service_provider: Any) -> None:
        self._service_provider = service_provider
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[bool] | None = None
        self._state = "idle"
        self._message = ""
        self._qr_png = ""
        self._qr_url = ""

    def snapshot(self) -> dict[str, Any]:
        try:
            service = self._service_provider()
        except Exception:
            service = None
        status = getattr(service, "status", None) if service is not None else None
        info = status() if callable(status) else {}
        info = info if isinstance(info, dict) else {}
        logged_in = bool(getattr(service, "available", False))
        return {
            "service_available": service is not None,
            "logged_in": logged_in,
            "uid": info.get("uid") or 0,
            "uname": str(info.get("uname") or ""),
            "state": "success" if logged_in else self._state,
            "message": self._message,
            "qr_png": self._qr_png,
            "qr_url": self._qr_url,
            "running": self._task is not None and not self._task.done(),
        }

    async def start(self) -> dict[str, Any]:
        """启动一次扫码登录；已在扫码时先取消旧任务。"""
        async with self._lock:
            await self._cancel()
            service = self._service_provider()
            if service is None:
                raise RuntimeError("B站服务未注册，无法扫码登录")
            self._qr_png = ""
            self._qr_url = ""
            if getattr(service, "available", False):
                self._state = "success"
                self._message = "B站已登录"
                return self.snapshot()
            self._state = "pending"
            self._message = "正在申请二维码…"
            self._task = asyncio.create_task(self._run(service))
            return self.snapshot()

    async def close(self) -> None:
        async with self._lock:
            await self._cancel()

    async def _cancel(self) -> None:
        task = self._task
        self._task = None
        if task is None or task.done():
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _run(self, service: Any) -> bool:
        try:
            ok = await service.login_with_qr(on_qr=self._on_qr, on_status=self._on_status)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._state = "error"
            self._message = f"扫码登录失败：{type(exc).__name__}: {exc}"
            return False
        if ok:
            self._state = "success"
            # 成功但落盘失败等 warning 由 service 写进 error，一并展示。
            self._message = self._service_error(service) or "登录成功"
        elif self._state not in {"expired", "error"}:
            self._state = "expired"
            self._message = self._service_error(service) or "登录未完成"
        return bool(ok)

    @staticmethod
    def _service_error(service: Any) -> str:
        """服务记录的最近错误/警告文本；读不到时返回空串。"""
        try:
            info = service.status()
        except Exception:
            return ""
        return str(info.get("error") or "").strip() if isinstance(info, dict) else ""

    def _on_qr(self, login: Any) -> None:
        self._qr_url = str(getattr(login, "url", "") or "")
        png = getattr(login, "png_bytes", None)
        if png:
            self._qr_png = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
        self._state = "pending"
        self._message = "请用 B站 App 扫码登录"

    def _on_status(self, result: Any) -> None:
        self._state = str(getattr(result, "state", "") or self._state)
        message = str(getattr(result, "message", "") or "").strip()
        if message:
            self._message = message


LOGIN_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>B站扫码登录 · NeoBot 面板</title>
<style>
body { margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
  background: #f5f6f8; color: #1f2329; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
main { width: min(92vw, 380px); box-sizing: border-box; padding: 28px; border-radius: 16px;
  background: #fff; box-shadow: 0 12px 36px rgba(0, 0, 0, .08); text-align: center; }
h1 { margin: 0 0 18px; font-size: 18px; }
#qr { width: 220px; height: 220px; margin: 0 auto 14px; box-sizing: border-box;
  display: flex; align-items: center; justify-content: center; overflow: hidden;
  border: 1px solid #e5e7eb; border-radius: 12px; background: #fff; }
#qr img { width: 100%; height: 100%; object-fit: contain; }
#qr.placeholder { padding: 20px; color: #8a919f; font-size: 13px; }
#status { min-height: 22px; margin: 0 0 18px; font-size: 14px; line-height: 1.5; color: #4e5969; }
button { padding: 10px 22px; border: 0; border-radius: 10px; background: #00a1d6;
  color: #fff; font-size: 14px; cursor: pointer; }
button:disabled { opacity: .55; cursor: default; }
a { display: block; margin-top: 14px; color: #8a919f; font-size: 13px; text-decoration: none; }
a:hover { color: #00a1d6; }
a.qr-link { display: inline; margin: 0; color: #00a1d6; }
</style>
</head>
<body>
<main>
  <h1>B站扫码登录</h1>
  <div id="qr" class="placeholder">正在准备二维码…</div>
  <p id="status" role="status">读取登录状态…</p>
  <button id="refresh" type="button" disabled>刷新二维码</button>
  <a href="../">← 返回面板</a>
</main>
<script src="login.js" defer></script>
</body>
</html>
"""

LOGIN_SCRIPT = """(function () {
  "use strict";
  var API = "../api/bilibili/login/";
  var qrBox = document.getElementById("qr");
  var statusText = document.getElementById("status");
  var button = document.getElementById("refresh");
  var csrf = "";
  var timer = 0;
  var LABELS = {
    pending: "等待扫码…",
    scanned: "已扫码，请在手机上确认",
    success: "登录成功",
    expired: "二维码已失效，请刷新",
    error: "登录失败"
  };

  function setStatus(text, isError) {
    statusText.textContent = text;
    statusText.style.color = isError ? "#d4380d" : "";
  }

  function placeholder(text) {
    qrBox.className = "placeholder";
    qrBox.textContent = text;
  }

  function renderQr(dataUrl) {
    qrBox.className = "";
    qrBox.textContent = "";
    var img = document.createElement("img");
    img.alt = "B站登录二维码";
    img.src = dataUrl;
    qrBox.appendChild(img);
  }

  async function readJson(response) {
    var payload = {};
    try { payload = await response.json(); } catch (error) { payload = {}; }
    if (!response.ok || payload.ok === false) {
      var failure = new Error(payload.error || ("HTTP " + response.status));
      failure.status = response.status;
      throw failure;
    }
    return payload;
  }

  function stopPolling() {
    if (timer) { window.clearInterval(timer); timer = 0; }
  }

  function apply(state) {
    if (state.logged_in) {
      stopPolling();
      placeholder("已登录");
      var who = state.uname
        ? "B站已登录：" + state.uname + "（UID " + state.uid + "）"
        : "B站账号已登录";
      setStatus(who);
      return;
    }
    if (state.qr_png) {
      renderQr(state.qr_png);
    } else if (state.running) {
      placeholder("正在申请二维码…");
    } else if (state.state === "expired") {
      placeholder("二维码已失效");
    }
    setStatus(state.message || LABELS[state.state] || "等待操作…",
      state.state === "error" || state.state === "expired");
    if (state.qr_url && !state.qr_png) {
      statusText.appendChild(document.createElement("br"));
      var link = document.createElement("a");
      link.className = "qr-link";
      link.href = state.qr_url;
      link.textContent = "打开登录链接";
      statusText.appendChild(link);
    }
  }

  async function poll() {
    try {
      var state = await readJson(await fetch(API + "status", { cache: "no-store" }));
      apply(state);
      if (state.logged_in || state.state === "expired" || state.state === "error") {
        stopPolling();
      }
    } catch (error) {
      if (error.status === 401) {
        stopPolling();
        setStatus("请先登录网页面板，再刷新本页。", true);
      } else {
        setStatus("读取状态失败：" + error.message, true);
      }
    }
  }

  async function start() {
    stopPolling();
    button.disabled = true;
    placeholder("正在申请二维码…");
    setStatus("正在申请二维码…");
    try {
      var state = await readJson(await fetch(API + "start", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: "{}"
      }));
      apply(state);
      if (!state.logged_in) { timer = window.setInterval(poll, 2000); }
    } catch (error) {
      placeholder("无法生成二维码");
      if (error.status === 401) {
        setStatus("请先登录网页面板，再刷新本页。", true);
      } else {
        setStatus("生成二维码失败：" + error.message, true);
      }
    } finally {
      button.disabled = false;
    }
  }

  async function main() {
    try {
      var me = await readJson(await fetch("../api/auth/me", { cache: "no-store" }));
      csrf = me.csrf_token || "";
      var state = await readJson(await fetch(API + "status", { cache: "no-store" }));
      apply(state);
      if (state.logged_in) { return; }
      if (state.running) { timer = window.setInterval(poll, 2000); return; }
      await start();
    } catch (error) {
      button.disabled = false;
      if (error.status === 401) {
        setStatus("请先登录网页面板，再刷新本页。", true);
      } else {
        setStatus("初始化失败：" + error.message, true);
      }
    }
  }

  button.addEventListener("click", start);
  main();
})();
"""
