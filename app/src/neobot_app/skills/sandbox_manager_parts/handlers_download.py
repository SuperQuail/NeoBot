"""下载文件的处理函数与受限读取/重定向跟随。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from typing import Any

from .common import _json, MAX_DOWNLOAD_BYTES, MAX_DOWNLOAD_REDIRECTS

if TYPE_CHECKING:
    from ..sandbox_manager_skill import SandboxManagerSkill

async def _read_download_limited(response: Any) -> bytes:
    """分块读取下载响应体，超过上限即中止。"""
    content_length = response.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError:
            declared = 0
        if declared > MAX_DOWNLOAD_BYTES:
            raise ValueError(f"文件过大（{declared} 字节），超过上限 {MAX_DOWNLOAD_BYTES} 字节")
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > MAX_DOWNLOAD_BYTES:
            raise ValueError(f"文件过大，超过上限 {MAX_DOWNLOAD_BYTES} 字节，下载已中止")
        chunks.append(chunk)
    return b"".join(chunks)


async def _download_with_redirects(client: Any, url: str) -> bytes:
    """流式下载并手动跟随重定向，每跳重新做 SSRF 校验。"""
    from neobot_app.utils.ssrf import validate_public_url_async

    current_url = url
    for _ in range(MAX_DOWNLOAD_REDIRECTS + 1):
        response = await client.get(current_url)
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("location")
            if not location:
                raise ValueError(f"重定向响应缺少 Location（{response.status_code}）")
            import httpx
            current_url = str(httpx.URL(current_url).join(location))
            if not await validate_public_url_async(current_url):
                raise ValueError("重定向目标不允许下载（内网/非公网地址）")
            continue
        response.raise_for_status()
        return await _read_download_limited(response)
    raise ValueError(f"重定向次数超过限制（{MAX_DOWNLOAD_REDIRECTS} 次）")


async def _handle_download_file(self: SandboxManagerSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    url = str(args.get("url", "")).strip()
    save_name = str(args.get("save_name", "")).strip()
    chat_flow_id = str(args.get("chat_flow_id", "")).strip()
    if not url or not save_name or not chat_flow_id:
        return _json({"ok": False, "error": "缺少必要参数 url/save_name/chat_flow_id"})

    timeout_seconds = int(args.get("timeout_seconds", 300) or 300)
    timeout_seconds = max(1, min(timeout_seconds, 1800))

    from neobot_app.utils.ssrf import validate_public_url_async

    if not await validate_public_url_async(url):
        return _json({"ok": False, "error": "禁止下载内网/非公网地址"})

    try:
        import httpx
        async with httpx.AsyncClient(timeout=float(timeout_seconds), follow_redirects=False) as client:
            data = await _download_with_redirects(client, url)

        # 检查沙箱总容量
        remaining = self._sandbox.check_capacity(len(data))
        if remaining is not None and remaining < 0:
            current = self._sandbox.get_total_size()
            max_mb = self._sandbox.max_total_size / (1024 * 1024)
            current_mb = current / (1024 * 1024)
            return _json({
                "ok": False,
                "error": (
                    f"沙箱空间不足：当前 {current_mb:.0f}MB / 上限 {max_mb:.0f}MB，"
                    f"下载需要 {len(data) / (1024*1024):.1f}MB"
                ),
            })

        path = self._sandbox.resolve_path(save_name, chat_flow_id)
        await self._sandbox.write_file(path, data)
        return _json({"ok": True, "path": str(path), "size": len(data)})
    except ValueError as e:
        return _json({"ok": False, "error": str(e)})
    except Exception as e:
        return _json({"ok": False, "error": f"下载失败: {e}"})
