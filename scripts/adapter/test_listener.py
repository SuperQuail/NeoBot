#!/usr/bin/env python3
"""
事件监听器测试

测试装饰器注册和事件分发功能。
"""
import asyncio
import threading
import time
import json
from typing import Dict, Any
import sys
import os

# 添加模块路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from neobot_adapter.receiver import AdapterCore, initialize_core
from neobot_adapter.listener import (
    on_message,
    on_notice,
    on_request,
    on_event,
    on_meta_event,
    setup_listeners,
    get_listener_manager,
    stop_listening,
    EventDispatcher
)


class MockCore(AdapterCore):
    """模拟适配器核心，用于测试"""
    
    def __init__(self, max_queue_size: int = 1000):
        """初始化模拟核心"""
        super().__init__(max_queue_size=max_queue_size)
        # 模拟事件循环运行
        self._mock_running = False
    
    def mock_event(self, event: Dict[str, Any]) -> None:
        """模拟接收到事件
        
        Args:
            event: 事件字典
        """
        try:
            self.message_queue.put_nowait(event)
        except Exception as e:
            print(f"放入事件失败: {e}")
    
    def start(self):
        """启动模拟核心（不实际启动WebSocket服务器）"""
        print("模拟核心已启动（不启动WebSocket服务器）")
        self._mock_running = True
    
    def stop(self):
        """停止模拟核心"""
        print("模拟核心已停止")
        self._mock_running = False


def test_decorator_registration():
    """测试装饰器注册功能"""
    print("\n=== 测试装饰器注册 ===")
    
    # 清除现有的监听器
    manager = get_listener_manager()
    manager.clear()
    manager.stop()
    
    # 创建模拟核心
    core = MockCore()
    
    # 设置监听器
    manager.core = core
    
    # 定义计数器
    counters = {
        'private_message': 0,
        'group_message': 0,
        'group_increase': 0,
        'friend_request': 0,
        'heartbeat': 0,
        'all_messages': 0
    }
    
    # 使用装饰器注册处理器
    @on_message(message_type="private")
    def handle_private_message(event: Dict[str, Any]) -> None:
        counters['private_message'] += 1
        print(f"处理私聊消息: {event.get('message_id')}")
    
    @on_message(message_type="group")
    def handle_group_message(event: Dict[str, Any]) -> None:
        counters['group_message'] += 1
        print(f"处理群聊消息: {event.get('message_id')}")
    
    @on_notice(notice_type="group_increase")
    def handle_group_increase(event: Dict[str, Any]) -> None:
        counters['group_increase'] += 1
        print(f"处理群成员增加: {event.get('group_id')}")
    
    @on_request(request_type="friend")
    def handle_friend_request(event: Dict[str, Any]) -> None:
        counters['friend_request'] += 1
        print(f"处理好友请求: {event.get('user_id')}")
    
    @on_meta_event(meta_event_type="heartbeat")
    def handle_heartbeat(event: Dict[str, Any]) -> None:
        counters['heartbeat'] += 1
        print(f"处理心跳: {event.get('self_id')}")
    
    @on_event(post_type="message")
    def handle_all_messages(event: Dict[str, Any]) -> None:
        counters['all_messages'] += 1
        print(f"处理所有消息: {event.get('post_type')}")
    
    # 检查处理器数量
    handlers = manager._handlers
    print(f"注册的处理器数量: {len(handlers)}")
    assert len(handlers) == 6, f"期望6个处理器，实际{len(handlers)}个"
    
    print("装饰器注册测试通过!")
    return core, counters


def test_event_filtering():
    """测试事件过滤功能"""
    print("\n=== 测试事件过滤 ===")
    
    manager = get_listener_manager()
    manager.clear()
    
    # 测试数据
    test_events = [
        {
            'post_type': 'message',
            'message_type': 'private',
            'message_id': 1001,
            'user_id': 123456
        },
        {
            'post_type': 'message',
            'message_type': 'group',
            'message_id': 1002,
            'group_id': 100001
        },
        {
            'post_type': 'notice',
            'notice_type': 'group_increase',
            'group_id': 100001,
            'user_id': 654321
        },
        {
            'post_type': 'request',
            'request_type': 'friend',
            'user_id': 987654
        },
        {
            'post_type': 'meta_event',
            'meta_event_type': 'heartbeat',
            'self_id': 123456
        }
    ]
    
    # 定义匹配计数器
    matches = {i: 0 for i in range(len(test_events))}
    
    # 注册通用处理器
    @on_event(post_type="message", message_type="private")
    def handle_private(event):
        if event.get('message_id') == 1001:
            matches[0] += 1
    
    @on_event(post_type="message", message_type="group")
    def handle_group(event):
        if event.get('message_id') == 1002:
            matches[1] += 1
    
    @on_event(post_type="notice", notice_type="group_increase")
    def handle_notice(event):
        if event.get('group_id') == 100001:
            matches[2] += 1
    
    @on_event(post_type="request", request_type="friend")
    def handle_request(event):
        if event.get('user_id') == 987654:
            matches[3] += 1
    
    @on_event(post_type="meta_event", meta_event_type="heartbeat")
    def handle_meta(event):
        if event.get('self_id') == 123456:
            matches[4] += 1
    
    # 手动分发事件
    for i, event in enumerate(test_events):
        manager._dispatch_sync(event)
    
    # 检查匹配结果
    for i, count in matches.items():
        assert count == 1, f"事件{i}应该匹配1次，实际匹配{count}次"
        print(f"事件{i}匹配成功")
    
    print("事件过滤测试通过!")


def test_async_handlers():
    """测试异步处理器"""
    print("\n=== 测试异步处理器 ===")
    
    manager = get_listener_manager()
    manager.clear()
    
    async_flag = {'processed': False}
    
    @on_message(message_type="private")
    async def async_private_handler(event):
        async_flag['processed'] = True
        print(f"异步处理私聊消息: {event.get('message_id')}")
    
    # 创建模拟事件
    test_event = {
        'post_type': 'message',
        'message_type': 'private',
        'message_id': 9999
    }
    
    # 由于没有运行事件循环，我们需要手动调用异步处理器
    # 这里我们只测试装饰器是否正常注册
    handlers = manager._handlers
    assert len(handlers) == 1, f"期望1个处理器，实际{len(handlers)}个"
    
    handler = handlers[0]
    assert handler.is_async, "处理器应该是异步的"
    
    print("异步处理器注册测试通过!")


def test_priority():
    """测试处理器优先级"""
    print("\n=== 测试处理器优先级 ===")
    
    manager = get_listener_manager()
    manager.clear()
    
    execution_order = []
    
    @on_message(priority=1)
    def low_priority_handler(event):
        execution_order.append('low')
    
    @on_message(priority=10)
    def high_priority_handler(event):
        execution_order.append('high')
    
    @on_message(priority=5)
    def medium_priority_handler(event):
        execution_order.append('medium')
    
    # 创建测试事件
    test_event = {
        'post_type': 'message',
        'message_type': 'private'
    }
    
    # 分发事件
    manager._dispatch_sync(test_event)
    
    # 检查执行顺序（优先级高的先执行）
    expected_order = ['high', 'medium', 'low']
    assert execution_order == expected_order, \
        f"期望顺序 {expected_order}，实际顺序 {execution_order}"
    
    print(f"执行顺序: {execution_order}")
    print("处理器优先级测试通过!")


def test_event_dispatcher():
    """测试事件分发器高级API"""
    print("\n=== 测试事件分发器 ===")
    
    # 创建事件分发器
    core = MockCore()
    dispatcher = EventDispatcher(core)
    
    # 清除现有处理器
    dispatcher.clear_handlers()
    
    # 定义计数器
    counters = {
        'dispatcher_messages': 0,
        'dispatcher_notices': 0
    }
    
    # 使用分发器API注册处理器
    @dispatcher.handle_message(message_type="private")
    def dispatcher_message_handler(event):
        counters['dispatcher_messages'] += 1
        print(f"分发器处理消息: {event.get('message_id')}")
    
    @dispatcher.handle_notice(notice_type="group_increase")
    def dispatcher_notice_handler(event):
        counters['dispatcher_notices'] += 1
        print(f"分发器处理通知: {event.get('group_id')}")
    
    # 创建测试事件
    message_event = {
        'post_type': 'message',
        'message_type': 'private',
        'message_id': 8888
    }
    
    notice_event = {
        'post_type': 'notice',
        'notice_type': 'group_increase',
        'group_id': 100001
    }
    
    # 立即分发事件
    dispatcher.dispatch(message_event)
    dispatcher.dispatch(notice_event)
    
    # 检查计数器
    assert counters['dispatcher_messages'] == 1, "消息处理器应该被调用1次"
    assert counters['dispatcher_notices'] == 1, "通知处理器应该被调用1次"
    
    print("事件分发器测试通过!")


def test_integration():
    """测试集成功能"""
    print("\n=== 测试集成功能 ===")
    
    # 创建模拟核心
    core = MockCore()
    
    # 设置监听器
    manager = get_listener_manager()
    manager.clear()
    manager.core = core
    manager.start()
    
    # 定义计数器
    counters = {
        'received_events': 0,
        'private_messages': 0
    }
    
    # 注册处理器
    @on_message(message_type="private")
    def integration_handler(event):
        counters['received_events'] += 1
        counters['private_messages'] += 1
        print(f"集成测试收到私聊消息: {event.get('user_id')}")
    
    # 模拟一些事件
    test_events = [
        {
            'post_type': 'message',
            'message_type': 'private',
            'user_id': 111111,
            'message': 'Hello'
        },
        {
            'post_type': 'message',
            'message_type': 'private',
            'user_id': 222222,
            'message': 'World'
        },
        {
            'post_type': 'notice',
            'notice_type': 'friend_add',
            'user_id': 333333
        }
    ]
    
    # 将事件放入队列
    for event in test_events:
        core.mock_event(event)
    
    # 等待事件被处理（监听器在后台线程运行）
    time.sleep(0.5)
    
    # 停止监听器
    manager.stop()
    
    # 检查结果
    assert counters['private_messages'] == 2, f"应该处理2条私聊消息，实际处理{counters['private_messages']}条"
    assert counters['received_events'] == 2, f"应该收到2个事件，实际收到{counters['received_events']}个"
    
    print(f"处理结果: 私聊消息 {counters['private_messages']}/2, 总事件 {counters['received_events']}/2")
    print("集成测试通过!")


def main():
    """运行所有测试"""
    print("开始测试事件监听器...")
    
    try:
        # 测试1: 装饰器注册
        core, counters = test_decorator_registration()
        
        # 测试2: 事件过滤
        test_event_filtering()
        
        # 测试3: 异步处理器
        test_async_handlers()
        
        # 测试4: 优先级
        test_priority()
        
        # 测试5: 事件分发器
        test_event_dispatcher()
        
        # 测试6: 集成测试
        test_integration()
        
        print("\n" + "="*50)
        print("所有测试通过! (✓)")
        print("="*50)
        
        # 清理
        manager = get_listener_manager()
        manager.clear()
        manager.stop()
        
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())