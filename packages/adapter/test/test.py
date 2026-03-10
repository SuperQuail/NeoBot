#!/usr/bin/env python3
"""
适配器核心测试文件。

这个文件演示了如何使用 neobot_adapter 的适配器核心功能。
测试向 QQ 号 3331347593 发送私聊消息。

使用方法：
1. 确保适配器已安装：在 packages/adapter 目录下执行 `uv pip install -e .`
2. 运行测试：`uv run python test.py`
3. 确保 OneBot 协议框架已启动并配置了反向 WebSocket 连接到 ws://localhost:8091
"""

import asyncio
import os
import time
import sys
from pathlib import Path

# 添加父目录到 Python 路径，以便导入模块
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from neobot_adapter.receiver import (
    initialize_core,
    get_core,
    start_core,
    stop_core,
    is_core_initialized,
)
from neobot_adapter.request.websocket import get_default_api


def test_sync_api():
    """同步 API 调用测试"""
    print("=== 同步 API 调用测试 ===")
    
    try:
        # 检查是否已初始化
        if is_core_initialized():
            print("适配器核心已初始化")
        else:
            print("初始化适配器核心...")
            initialize_core(max_queue_size=1000)
        
        # 启动适配器核心
        print("启动适配器核心...")
        start_core()
        
        # 等待连接建立（最多 30 秒）
        print("等待 OneBot 框架连接...")
        core = get_core()
        connected = core.wait_for_connection(timeout=30)
        
        if not connected:
            print("错误: 连接超时，请确保 OneBot 框架已启动并配置了反向 WebSocket 连接到 ws://localhost:8091")
            return False
        
        print("连接已建立")
        
        # 使用核心实例直接调用 API
        print("使用核心实例发送私聊消息...")
        result = core.call_api_sync(
            "send_private_msg",
            {
                "user_id": 918206897,
                "message": "测试消息：这是一条来自适配器核心的同步测试消息",
                "auto_escape": False,
            },
            timeout=10,
        )
        
        if result:
            print(f"消息发送成功: {result}")
        else:
            print("消息发送失败")
        
        # 等待 2 秒
        time.sleep(2)
        
        # 使用 WebSocketAPI 包装器调用 API
        print("使用 WebSocketAPI 包装器发送私聊消息...")
        api = get_default_api()
        result2 = api.send_private_msg_sync(
            user_id=918206897,
            message="测试消息：这是一条来自 WebSocketAPI 的同步测试消息",
            auto_escape=False,
            timeout=10,
        )
        
        if result2:
            print(f"消息发送成功: {result2}")
        else:
            print("消息发送失败")
        
        # 等待 2 秒
        time.sleep(2)
        
        print("同步 API 调用测试完成")
        return True
        
    except Exception as e:
        print(f"同步测试出错: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_async_api():
    """异步 API 调用测试"""
    print("\n=== 异步 API 调用测试 ===")
    
    try:
        # 检查是否已初始化
        if not is_core_initialized():
            print("错误: 适配器核心未初始化，请先运行同步测试")
            return False
        
        core = get_core()
        
        # 等待连接建立
        if not core.wait_for_connection(timeout=5):
            print("错误: 连接未建立")
            return False
        
        print("连接已建立，开始异步测试")
        
        # 使用核心实例直接调用异步 API
        print("使用核心实例发送私聊消息（异步）...")
        result = await core.call_api(
            "send_private_msg",
            {
                "user_id": 918206897,
                "message": "测试消息：这是一条来自适配器核心的异步测试消息",
                "auto_escape": False,
            },
            timeout=10,
        )
        
        if result:
            print(f"消息发送成功: {result}")
        else:
            print("消息发送失败")
        
        # 等待 2 秒
        await asyncio.sleep(2)
        
        # 使用 WebSocketAPI 包装器调用异步 API
        print("使用 WebSocketAPI 包装器发送私聊消息（异步）...")
        api = get_default_api()
        result2 = await api.send_private_msg(
            user_id=918206897,
            message="测试消息：这是一条来自 WebSocketAPI 的异步测试消息",
            auto_escape=False,
            timeout=10,
        )
        
        if result2:
            print(f"消息发送成功: {result2}")
        else:
            print("消息发送失败")
        
        print("异步 API 调用测试完成")
        return True
        
    except Exception as e:
        print(f"异步测试出错: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_message_queue():
    """消息队列功能测试"""
    print("\n=== 消息队列功能测试 ===")
    
    try:
        if not is_core_initialized():
            print("错误: 适配器核心未初始化")
            return False
        
        core = get_core()
        
        print("获取消息队列中的消息（非阻塞模式，最多等待 5 秒）...")
        
        # 非阻塞方式获取消息
        for i in range(10):
            msg = core.get_message(block=False)
            if msg:
                print(f"收到消息 {i+1}: {msg}")
            else:
                print(f"队列为空，等待 1 秒...")
                time.sleep(1)
        
        print("消息队列测试完成")
        return True
        
    except Exception as e:
        print(f"消息队列测试出错: {e}")
        return False


def main():
    """主测试函数"""
    os.environ['NEO_BOT_ADAPTER_HOST'] = "127.0.0.1"
    os.environ['NEO_BOT_ADAPTER_PORT'] = "8091"
    print("适配器核心测试开始")
    print("=" * 50)
    
    success = True
    
    # 运行同步测试
    if not test_sync_api():
        success = False
        print("同步测试失败，跳过后续测试")
    else:
        # 运行异步测试
        if asyncio.run(test_async_api()):
            print("异步测试成功")
        else:
            success = False
            print("异步测试失败")
        
        # 运行消息队列测试
        if test_message_queue():
            print("消息队列测试成功")
        else:
            success = False
            print("消息队列测试失败")
    
    # 停止适配器核心
    print("\n停止适配器核心...")
    try:
        stop_core()
        print("适配器核心已停止")
    except Exception as e:
        print(f"停止适配器核心时出错: {e}")
        success = False
    
    print("=" * 50)
    if success:
        print("所有测试通过！")
        return 0
    else:
        print("部分测试失败")
        return 1


if __name__ == "__main__":
    # 注意：在实际运行前，请确保：
    # 1. OneBot 协议框架（如 go-cqhttp）已启动
    # 2. 配置了反向 WebSocket 连接到 ws://localhost:8091
    # 3. 机器人账号 3331347593 可用
    # 4. 适配器已安装：在 packages/adapter 目录下执行 `uv pip install -e .`
    
    print("测试说明：")
    print("1. 请确保 OneBot 框架已启动并配置了反向 WebSocket 连接到 ws://localhost:8091")
    print("2. 测试将向 QQ 号 3331347593 发送私聊消息")
    print("3. 如果该账号不是您的机器人，请修改代码中的 user_id")
    print("4. 按 Enter 键继续测试，或按 Ctrl+C 取消")
    
    try:
        input()
    except KeyboardInterrupt:
        print("\n测试取消")
        sys.exit(0)
    
    sys.exit(main())