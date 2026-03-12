#!/usr/bin/env python3
"""
简单示例：使用适配器核心的基本流程。

这个示例展示了如何初始化、启动和使用适配器核心。
"""
import asyncio
import sys
from pathlib import Path

# 添加父目录到 Python 路径，以便导入模块
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from neobot_adapter.receiver import (
    initialize_core,
    get_core,
    start_core,
    stop_core,
)
from neobot_adapter.request.websocket import get_default_api


async def main():
    """主函数：演示适配器核心的基本使用流程"""
    
    print("=== 适配器核心使用示例 ===")
    
    try:
        # 1. 初始化适配器核心
        print("1. 初始化适配器核心...")
        core = initialize_core(max_queue_size=1000)
        
        # 2. 启动适配器核心（启动 WebSocket 服务器）
        print("2. 启动适配器核心...")
        start_core()
        
        # 3. 等待连接建立
        print("3. 等待 OneBot 框架连接...")
        connected = core.wait_for_connection(timeout=30)
        
        if not connected:
            print("错误: 连接超时！")
            print("请确保 OneBot 框架已启动并配置了反向 WebSocket 连接到 ws://localhost:8091")
            return
        
        print("连接已建立！")
        
        # 4. 使用核心实例调用 API
        print("4. 使用核心实例发送私聊消息...")
        result = await core.call_api(
            "send_private_msg",
            {
                "user_id": 3331347593,  # 替换为你的机器人 QQ 号
                "message": "你好！这是一条测试消息。",
                "auto_escape": False,
            },
            timeout=10,
        )
        
        if result:
            print(f"消息发送成功: {result}")
        else:
            print("消息发送失败")
        
        # 5. 使用 WebSocketAPI 包装器
        print("5. 使用 WebSocketAPI 包装器发送群聊消息...")
        api = get_default_api()
        
        result2 = await api.send_group_msg(
            group_id=123456789,  # 替换为你的群号
            message="这是一条群聊测试消息！",
            auto_escape=False,
            timeout=10,
        )
        
        if result2:
            print(f"群聊消息发送成功: {result2}")
        else:
            print("群聊消息发送失败")
        
        # 6. 监听消息（示例：监听 10 秒）
        print("6. 监听消息 10 秒...")
        print("   按 Ctrl+C 提前结束监听")
        
        try:
            start_time = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - start_time < 10:
                # 非阻塞方式获取消息
                msg = core.get_message(block=False)
                if msg:
                    print(f"收到消息: {msg}")
                
                # 等待一小段时间
                await asyncio.sleep(0.1)
        except KeyboardInterrupt:
            print("\n监听被用户中断")
        
        print("7. 示例完成！")
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 8. 停止适配器核心
        print("8. 停止适配器核心...")
        try:
            stop_core()
            print("适配器核心已停止")
        except Exception as e:
            print(f"停止适配器核心时出错: {e}")


if __name__ == "__main__":
    print("注意：")
    print("1. 请确保 OneBot 框架已启动并配置了反向 WebSocket 连接到 ws://localhost:8091")
    print("2. 请将代码中的 user_id 和 group_id 替换为实际值")
    print("3. 按 Enter 键开始示例，或按 Ctrl+C 取消")
    
    try:
        input()
    except KeyboardInterrupt:
        print("\n示例取消")
        sys.exit(0)
    
    asyncio.run(main())