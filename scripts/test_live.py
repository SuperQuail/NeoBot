"""真实环境测试脚本

连接 OneBot WebSocket (127.0.0.1:8091) ，持续接收消息：
- 文本回复：不调用真实 AI，统一回复"虚拟回复"
- 图片解析：调用真实视觉模型（SiliconFlow / Qwen3-VL）
- 回复意愿：使用真实配置计算
- 收到"测试中止"消息时结束测试

环境变量（可选，也可在 app/.env 中设置）:
  SILICONFLOW_APIKEY  — 硅基流动 API Key（用于图片解析）
  DeepSeek_APIKey     — DeepSeek API Key（文本模型 mock 时不需真实 key，占位即可）

用法:
  uv run python scripts/test_live.py
"""

from __future__ import annotations

import asyncio
import os
import re
import signal
import sys
import tempfile
import traceback
from pathlib import Path

from neobot_chat.providers import OpenAIProvider
from neobot_adapter.model.message import GroupMessage, PrivateMessage
from neobot_app.bootstrap import create_application
from neobot_app.runtime.application import ConnectionTimeoutError


class MockTextProvider:
    """Mock 文本 AI provider — 若 prompt 含图片描述，则返回描述；否则返回"虚拟回复" """

    async def chat(self, messages, tools=None):
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str) and "[图片：" in content:
                matches = re.findall(r"\[图片：(.+?)\]", content)
                if matches:
                    return {"role": "assistant", "content": matches[-1]}
        return {"role": "assistant", "content": "虚拟回复"}


def _patch_env_file() -> str:
    """确保 .env 中的 API Key 有值，返回原始内容用于恢复。

    因为 Windows 上环境变量大小写不敏感，.env 中的空值会覆盖我们预设
    的占位 key，导致 register_models() 校验失败。这里直接修改 .env 内容。
    """
    env_path = Path("app/.env")
    if not env_path.exists():
        return ""
    original = env_path.read_text(encoding="utf-8")
    modified = original
    if re.search(r"^DeepSeek_APIKey=\s*$", modified, flags=re.MULTILINE):
        modified = re.sub(
            r"^DeepSeek_APIKey=\s*$",
            "DeepSeek_APIKey=test-placeholder-key",
            modified,
            flags=re.MULTILINE,
        )
    siliconflow_key = os.environ.get("SiliconFlow_APIKey", "")
    if siliconflow_key and re.search(r"^SiliconFlow_APIKey=\s*$", modified, flags=re.MULTILINE):
        modified = re.sub(
            r"^SiliconFlow_APIKey=\s*$",
            f"SiliconFlow_APIKey={siliconflow_key}",
            modified,
            flags=re.MULTILINE,
        )
    if modified != original:
        env_path.write_text(modified, encoding="utf-8")
    return original


def _restore_env_file(original: str) -> None:
    """恢复 .env 文件原始内容"""
    if original:
        Path("app/.env").write_text(original, encoding="utf-8")


async def main() -> None:
    # ── 环境变量 ───────────────────────────────────────────
    for key, val in [
        ("NEO_BOT_ADAPTER_HOST", "127.0.0.1"),
        ("NEO_BOT_ADAPTER_PORT", "8091"),
        ("DeepSeek_URL", "https://api.deepseek.com"),
        ("SiliconFlow_URL", "https://api.siliconflow.cn/v1"),
    ]:
        if key not in os.environ:
            os.environ[key] = val

    env_original = _patch_env_file()

    try:
        application = create_application()
    finally:
        pass

    orchestrator = application._reply_orchestrator

    # ── 替换文本 provider 为 mock ──────────────────────────
    orchestrator._provider = MockTextProvider()

    # ── 诊断：替换 _run 为带详细异常输出的版本 ─────────────────
    # _original_run 内部已 catch 所有 Exception，所以外层无法捕获。
    # 只能替换整个方法，在 catch 块里同时输出到文件。
    from neobot_app.reply.orchestrator import ReplyOrchestrator as _RO
    from neobot_app.reply.event import ReplyState

    _diag_file = Path(tempfile.gettempdir()) / "neobot_test_diag.txt"

    async def _debug_run(self, event, queue, queue_key):
        try:
            if event.mode == "agent":
                await self._run_agent_mode(event, queue, queue_key)
            else:
                await self._run_common_mode(event, queue, queue_key)
            self._logger.info(
                "ReplyEvent completed",
                event_id=event.event_id,
                mode=event.mode,
                reply_preview=event.generated_text[:80] if event.generated_text else "",
            )
        except asyncio.CancelledError:
            event.error = "cancelled"
            self._logger.warning("ReplyEvent cancelled", event_id=event.event_id)
            raise
        except Exception as exc:
            try:
                event.transition(ReplyState.FAILED)
            except RuntimeError:
                pass
            event.error = f"{type(exc).__name__}: {exc}"
            # 写入诊断文件
            tb = traceback.format_exc()
            diag_msg = (
                f"[{event.event_id}] mode={event.mode}\n"
                f"  error: {event.error}\n"
                f"  traceback:\n{tb}\n"
            )
            try:
                with _diag_file.open("a", encoding="utf-8") as f:
                    f.write(diag_msg)
                print(f"[诊断] 异常已写入 {_diag_file}", file=sys.stderr)
            except Exception:
                print(f"[诊断] {diag_msg}", file=sys.stderr)
            self._logger.error(
                "ReplyEvent failed",
                event_id=event.event_id,
                mode=event.mode,
                error=event.error,
            )

    _RO._run = _debug_run

    # ── 注入真实视觉模型 provider（图片解析） ──────────────
    try:
        vision_api_key = input("请输入 SiliconFlow API Key（直接回车跳过）: ").strip()
    except (EOFError, OSError):
        vision_api_key = ""
    if not vision_api_key:
        vision_api_key = os.environ.get("SiliconFlow_APIKey", "").strip()
    if vision_api_key:
        vision_provider = OpenAIProvider(
            api_key=vision_api_key,
            model="Qwen/Qwen3-VL-8B-Instruct",
            base_url="https://api.siliconflow.cn/v1",
        )
        orchestrator._image_parse_service._vision_provider = vision_provider

        # 诊断：拦截 vision provider 的 chat 调用，捕获真实异常
        _original_vision_chat = vision_provider.chat

        async def _diag_vision_chat(messages, tools=None):
            try:
                return await _original_vision_chat(messages, tools=tools)
            except Exception as exc:
                diag_msg = f"[视觉模型异常] {type(exc).__name__}: {exc}\n{traceback.format_exc()}\n"
                try:
                    with _diag_file.open("a", encoding="utf-8") as f:
                        f.write(diag_msg)
                    print(f"[诊断] 视觉模型异常已写入 {_diag_file}", file=sys.stderr)
                except Exception:
                    print(f"[诊断] {diag_msg}", file=sys.stderr)
                raise

        vision_provider.chat = _diag_vision_chat

        # 打印图片解析结果到控制台
        from neobot_app.image.parser import ImageParseService as _IPS
        _original_parse_single = _IPS._parse_single_image

        async def _print_parse_single(self, segment):
            description = await _original_parse_single(self, segment)
            if description and not description.startswith("[图片解析失败"):
                print(f"[图片解析] {description}", file=sys.stderr)
            return description

        _IPS._parse_single_image = _print_parse_single
    else:
        print("[警告] 未设置 SiliconFlow_APIKey，图片解析将无法工作")

    # ── 测试中止消息检测 ───────────────────────────────────
    adapter = application.adapter

    def _is_stop_message(raw_text: str) -> bool:
        return "测试中止" in raw_text or "测试终止" in raw_text or "测试结束" in raw_text

    @adapter.on.message(private=True)
    async def _check_private_stop(event: PrivateMessage):
        if event.raw_message and _is_stop_message(event.raw_message):
            print(f"\n[测试] 收到私聊中止消息: {event.raw_message}")
            application.request_stop()

    @adapter.on.message(group=True)
    async def _check_group_stop(event: GroupMessage):
        if event.raw_message and _is_stop_message(event.raw_message):
            print(f"\n[测试] 收到群聊中止消息: {event.raw_message}")
            application.request_stop()

    # ── 信号处理 ───────────────────────────────────────────
    loop = asyncio.get_running_loop()

    def _request_stop() -> None:
        application.request_stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            pass

    # ── 启动信息 ───────────────────────────────────────────
    print("=" * 60)
    print("NeoBot 真实环境测试")
    print("WebSocket:       127.0.0.1:8091")
    print("文本回复模式:    虚拟回复 (不调用文本 AI)")
    visual_label = "SiliconFlow Qwen3-VL-8B" if vision_api_key else "未配置"
    print(f"图片解析:        {visual_label}")
    print("回复意愿:        真实计算")
    print("中止指令:        发送包含「测试中止 / 测试终止 / 测试结束」的消息")
    print("=" * 60)

    # ── 运行 ───────────────────────────────────────────────
    try:
        await application.start()
        # start 完成后所有配置已加载完毕，可以安全恢复 .env
        _restore_env_file(env_original)

        await application._shutdown_event.wait()
    except ConnectionTimeoutError as exc:
        print(f"错误: {exc}")
    finally:
        _restore_env_file(env_original)
        await application.stop()
        print("测试结束")


if __name__ == "__main__":
    asyncio.run(main())
