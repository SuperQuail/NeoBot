"""测试 WebSocket 反向连接是否正常工作。

模拟 OneBot 框架连接到 NeoBot 的反向 WebSocket 服务器，
发送一个生命周期事件，验证连接和消息传递。

用法: uv run python scripts/test_ws_connection.py
"""

import asyncio
import json
import time

import websockets


async def test_connection(host: str = "127.0.0.1", port: int = 8080):
    uri = f"ws://{host}:{port}"
    print(f"[1/4] 尝试连接 {uri} ...")

    try:
        async with websockets.connect(uri) as ws:
            print(f"[2/4] 连接成功!")

            # 模拟 OneBot 框架发送 lifecycle connect 事件
            lifecycle_event = {
                "time": int(time.time()),
                "self_id": 10001,
                "post_type": "meta_event",
                "meta_event_type": "lifecycle",
                "sub_type": "connect",
            }
            await ws.send(json.dumps(lifecycle_event))
            print(f"[3/4] 已发送 lifecycle connect 事件")

            # 模拟心跳
            heartbeat_event = {
                "time": int(time.time()),
                "self_id": 10001,
                "post_type": "meta_event",
                "meta_event_type": "heartbeat",
                "interval": 5000,
                "status": {"online": True, "good": True},
            }
            await ws.send(json.dumps(heartbeat_event))
            print(f"[3/4] 已发送 heartbeat 事件")

            # 模拟一条群消息
            group_msg = {
                "time": int(time.time()),
                "self_id": 10001,
                "post_type": "message",
                "message_type": "group",
                "sub_type": "normal",
                "message_id": 12345,
                "group_id": 888888,
                "user_id": 999999,
                "message": "测试消息",
                "raw_message": "测试消息",
                "sender": {
                    "user_id": 999999,
                    "nickname": "测试用户",
                    "card": "测试群名片",
                },
            }
            await ws.send(json.dumps(group_msg))
            print(f"[3/4] 已发送群消息事件")

            # 等待看看服务端是否发来 API 请求
            print(f"[4/4] 等待 5 秒观察服务端响应...")
            try:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(msg)
                    print(f"  <- 收到服务端请求: {json.dumps(data, ensure_ascii=False, indent=2)}")

                    # 如果是 API 调用，返回一个成功响应
                    if "echo" in data:
                        resp = {
                            "status": "ok",
                            "retcode": 0,
                            "data": None,
                            "echo": data["echo"],
                        }
                        await ws.send(json.dumps(resp))
                        print(f"  -> 已回复 echo={data['echo']}")
            except asyncio.TimeoutError:
                print(f"  (5 秒内无更多服务端请求)")

            print("\n测试完成 — 连接正常工作!")

    except ConnectionRefusedError:
        print(f"连接被拒绝 — 服务器未在 {uri} 监听")
        print("请先启动 NeoBot: uv run python Bot.py")
    except Exception as e:
        print(f"连接失败: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(test_connection())
