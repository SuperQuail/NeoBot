#!/usr/bin/env python3
"""
适配器核心测试文件。

这个文件演示了如何使用 neobot_adapter 的适配器核心功能。
测试向 QQ 号 3331347593 发送私聊消息。

使用方法：
1. 确保适配器已安装：在 packages/adapter 目录下执行 `uv pip install -e .`
2. 运行测试：`uv run python adapter.py`
3. 确保 OneBot 协议框架已启动并配置了反向 WebSocket 连接到 ws://localhost:8091
"""

import asyncio
import os
import time
import sys
from pathlib import Path

import requests
from neobot_adapter.utils.logger import get_module_logger
from neobot_adapter.model import notice
from neobot_adapter.model.message import Message, GroupMessage
from neobot_adapter.utils.parse import safe_parse_model
from neobot_adapter.request import private,group,message

logger = get_module_logger('测试脚本')
i = 10989

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
from neobot_adapter.listener import (
    on_message,
    on_notice,
    on_request,
    on_event,
    on_meta_event,
    setup_listeners,
    get_listener_manager,
    stop_listening,
)


def test_sync_api() -> bool:
    """同步 API 调用测试

    Returns:
        测试是否成功
    """
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


async def test_async_api() -> bool:
    """异步 API 调用测试

    Returns:
        测试是否成功
    """
    print("\n=== 异步 API 调用测试 ===")

    try:
        # 检查是否已初始化
        if not is_core_initialized():
            print("初始化适配器核心...")
            initialize_core(max_queue_size=1000)

        # 启动适配器核心
        print("启动适配器核心...")
        start_core()

        # 等待连接建立（最多 30 秒）
        print("等待 OneBot 框架连接...")
        core = get_core()
        if not core.wait_for_connection(timeout=30):
            print("错误: 连接超时，请确保 OneBot 框架已启动并配置了反向 WebSocket 连接到 ws://localhost:8091")
            return False
        
        print("连接已建立，开始异步测试")
        await asyncio.sleep(3)
        
        # result = await private.friend_poke(918206897)
        # logger.info(f"friend_poke调用结果：{result}")
        # result = await private.send_like(918206897, 1)
        # logger.info(f"send_like调用结果：{result}")
        # result = await private.set_friend_remark(918206897, "摸鱼")
        # logger.info(f"set_friend_remark调用结果：{result}")
        # result = await private.get_stranger_info(918206897)
        # logger.info(f"get_stranger_info调用结果：{result}")
        # result = await group.set_group_card(1016011262, 2603391440, "梦梦")
        # logger.info(f"set_group_card调用结果：{result}")
        # result = await group.set_group_ban(1016011262,694326339,1)
        # logger.info(f"set_group_ban调用结果：{result}")
        #group_id = [1060107693,1035121335,618084902,725620862,234450817]
        # for i in [1016011262]:
        #     result = await message.send_group_record_msg(i,"file://D:/Creator/Music/弥音/世末歌者.mp3")
        #     logger.info(f"set_group_whole_ban调用结果：{result}")
        # for i in [1016011262]:
        #     result = await message.send_group_msg(i,"喵喵喵")
        #     logger.info(f"set_group_whole_ban调用结果：{result}")
        logger.level("INFO")
        for t in range(2):
            for i in [1016011262]:
                start = time.perf_counter()
                result = await message.get_group_msg_history( i,0,1)
                end1 = time.perf_counter()
                logger.info(f"第{t}次调用耗时：{end1-start}")
        # result = await message.send_group_record_msg(1016011262,"file://D:/Creator/Music/弥音-TTS/我会说话了哦.wav")
        # logger.info(f"send_group_record_msg调用结果：{result}")
        # result = await message.send_group_dice_msg(1016011262)
        # logger.info(f"send_group_dice_msg调用结果：{result}")
        # result = await message.send_group_music_msg(1016011262, "163", 1389028405)
        # logger.info(f"send_group_music_msg调用结果：{result}")

    except Exception as e:
        print(f"异步测试出错: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_message_queue() -> bool:
    """消息队列功能测试

    Returns:
        测试是否成功
    """
    print("\n=== 消息队列功能测试 ===")

    start_core()
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



def run_continuous_listener() -> int:
    """运行持续监听模式

    初始化适配器核心，设置事件监听器，持续监听并记录所有事件。

    Returns:
        退出代码：0 表示成功，1 表示失败
    """
    os.environ['NEO_BOT_ADAPTER_HOST'] = "127.0.0.1"
    os.environ['NEO_BOT_ADAPTER_PORT'] = "8091"

    print("=== 持续监听模式 ===")
    print("初始化适配器核心...")

    try:
        # 初始化适配器核心
        if not is_core_initialized():
            initialize_core(max_queue_size=1000)

        # 启动适配器核心
        start_core()

        # 等待连接建立
        print("等待 OneBot 框架连接...")
        core = get_core()
        connected = core.wait_for_connection(timeout=30)

        if not connected:
            print("错误: 连接超时，请确保 OneBot 框架已启动并配置了反向 WebSocket 连接到 ws://localhost:8091")
            return 1

        print("连接已建立")

        # 设置事件监听器
        print("设置事件监听器...")
        setup_listeners(core)

        # 注册事件处理器，使用 info 级别 logger 记录所有事件
        # @on_event()
        # def log_all_events(event: dict) -> None:
        #     """记录所有事件"""
        #     post_type = event.get('post_type', 'unknown')
        #     event_type = event.get('message_type') or event.get('notice_type') or event.get('request_type') or event.get('meta_event_type') or 'unknown'
        #     logger.info(f"收到事件: post_type={post_type}, type={event_type}, data={event}")
        #
        # @on_message(message_type="private")
        # def log_private_message(event: dict) -> None:
        #     """记录私聊消息"""
        #     user_id = event.get('user_id')
        #     message = event.get('message', '')
        #     logger.info(f"私聊消息: 用户={user_id}, 内容={message}")


        @on_message(message_type="group")
        async def log_group_message(event: dict) -> None:
            """记录群聊消息"""
            # group_id = event.get('group_id')
            # user_id = event.get('user_id')
            # message = event.get('message', '')
            # logger.info(f"群聊消息: 群={group_id}, 用户={user_id}, 内容={message}")
            tempMessage = safe_parse_model(event, GroupMessage)
            id = tempMessage.message_id
            if tempMessage.group_id == 1016011262 and tempMessage.user_id == 1807980091:
                result = await message.set_msg_emoji_like( id,12951)
                # i+=1
                logger.info(f"set_msg_emoji_like调用结果：{result}")



        @on_notice()
        def log_notice(event: dict) -> None:
            """记录通知事件"""
            notice_type = event.get('notice_type', 'unknown')
            logger.info(f"通知事件: type={notice_type}, data={event}")
            if event.get('sub_type') == notice.PokeSubType.poke.value:
                event = safe_parse_model(event, notice.GroupPoke)
                logger.info(f"群 {event.group_id} 的 {event.target_id} 被{event.user_id}戳了")

        @on_request()
        def log_request(event: dict) -> None:
            """记录请求事件"""
            request_type = event.get('request_type', 'unknown')
            logger.info(f"请求事件: type={request_type}, data={event}")

        @on_meta_event()
        def log_meta_event(event: dict) -> None:
            """记录元事件"""
            meta_event_type = event.get('meta_event_type', 'unknown')
            logger.info(f"元事件: type={meta_event_type}, data={event}")

        print("事件监听器已启动，开始监听事件...")
        print("按 Ctrl+C 停止监听")
        print("-" * 50)

        # 保持主线程运行，直到收到中断信号
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n收到中断信号，停止监听...")

        # 清理资源
        print("停止事件监听器...")
        stop_listening()

        print("停止适配器核心...")
        stop_core()

        print("持续监听模式结束")
        return 0

    except Exception as e:
        logger.error(f"持续监听模式出错: {e}", exc_info=True)
        return 1


def main() -> int:
    """主测试函数"""
    os.environ['NEO_BOT_ADAPTER_HOST'] = "127.0.0.1"
    os.environ['NEO_BOT_ADAPTER_PORT'] = "8091"
    print("适配器核心测试开始")
    print("=" * 50)
    
    success = True
    
    # 运行同步测试

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
    
    print("请选择测试模式：")
    print("1. 标准测试模式（发送测试消息并检查功能）")
    print("2. 持续监听模式（监听并记录所有事件）")
    print("输入 1 或 2 后按 Enter：", end="")

    try:
        choice = input().strip()
    except KeyboardInterrupt:
        print("\n测试取消")
        sys.exit(0)
    
    if choice == "1":
        print("\n=== 标准测试模式 ===")
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
    elif choice == "2":
        print("\n=== 持续监听模式 ===")
        print("测试说明：")
        print("1. 请确保 OneBot 框架已启动并配置了反向 WebSocket 连接到 ws://localhost:8091")
        print("2. 将监听并记录所有事件，按 Ctrl+C 停止")
        print("3. 按 Enter 键开始监听，或按 Ctrl+C 取消")

        try:
            input()
        except KeyboardInterrupt:
            print("\n测试取消")
            sys.exit(0)

        sys.exit(run_continuous_listener())
    else:
        print(f"\n无效选择: '{choice}'，请输入 1 或 2")
        sys.exit(1)
