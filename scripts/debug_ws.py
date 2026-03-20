"""调试脚本 — 直接打印 WebSocket 收到的所有原始数据。

用法: uv run python scripts/debug_ws.py
"""

import asyncio
import json
import signal

import websockets


async def main():
    host = "0.0.0.0"
    port = 8080

    async def handle(ws):
        print(f"[连接] 客户端已连接: {ws.remote_address}")
        try:
            async for raw in ws:
                print(f"[原始数据] {raw}")
                try:
                    data = json.loads(raw)
                    print(f"[解析] post_type={data.get('post_type')}, "
                          f"message_type={data.get('message_type')}, "
                          f"meta_event_type={data.get('meta_event_type')}")
                    if data.get("post_type") == "message":
                        print(f"  message_id={data.get('message_id')}")
                        print(f"  user_id={data.get('user_id')}")
                        print(f"  group_id={data.get('group_id')}")
                        print(f"  raw_message={data.get('raw_message')}")
                        print(f"  message={data.get('message')}")
                        print(f"  sender={data.get('sender')}")
                except json.JSONDecodeError as e:
                    print(f"[JSON解析失败] {e}")
                print()
        except websockets.exceptions.ConnectionClosed as e:
            print(f"[断开] code={e.code}, reason={e.reason}")

    async with websockets.serve(handle, host, port):
        print(f"调试 WebSocket 服务器运行于 ws://{host}:{port}")
        print("等待 OneBot 框架连接...\n")

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        await stop.wait()

    print("\n已停止")


if __name__ == "__main__":
    asyncio.run(main())
