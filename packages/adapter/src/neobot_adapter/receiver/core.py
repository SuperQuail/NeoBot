import os
import queue
import json
from typing import Optional, Iterator, AsyncIterator, Any
from neobot_adapter.utils.env import get_websocket_url, get_websocket_host, get_websocket_port
from neobot_adapter.utils.logger import get_module_logger
from neobot_adapter.utils.parse import safe_parse_model
from neobot_adapter.model.meta_event import Heartbeat, LifeCycle, LifeCycleSubType
from neobot_adapter.model.basic import PostMetaEventType, PostType
import asyncio
import threading
import websockets

logger = get_module_logger("adapter_receiver")


class AdapterCore:
    """适配器核心类，负责 WebSocket 反向连接和消息处理

    功能：
    1. 启动反向 WebSocket 服务器监听连接
    2. 接收和处理来自框架的事件和响应
    3. 提供 API 调用功能发送请求到框架
    4. 管理消息队列和连接状态

    使用方式：
        通过 OneBotAdapter 创建和管理，不要直接实例化

        adapter = OneBotAdapter(max_queue_size=1000)
        await adapter.start()
        connected = adapter.wait_for_connection(timeout=10)
    """
    def __init__(self, max_queue_size: int = 1000):
        """初始化适配器核心

        Args:
            max_queue_size: 消息队列最大长度
        """
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.message_queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._pending = {}  # echo -> asyncio.Future
        self.active_connections = set()
        self._connections_lock = asyncio.Lock()
        self._echo_to_conn = {}  # echo -> websocket
        self._conn_to_echo = {}  # websocket -> set of echo
        self._connection_established = threading.Event()  # 连接建立事件
        self._api_instance: Optional[Any] = None  # WebSocketAPI 实例缓存

    def wait_for_connection(self, timeout: Optional[float] = None) -> bool:
        """等待直到有框架连接建立

        Args:
            timeout: 超时时间（秒），None 表示无限等待

        Returns:
            如果连接建立返回 True，超时返回 False
        """
        return self._connection_established.wait(timeout=timeout)

    def iter_messages(self, block: bool = True, timeout: Optional[float] = None) -> Iterator[dict]:
        """返回一个迭代器，持续从队列中获取消息

        Args:
            block: 是否阻塞等待新消息
            timeout: 每次获取消息的超时时间

        Yields:
            消息字典
        """
        while True:
            msg = self.get_message(block=block, timeout=timeout)
            if msg is None:
                if not block:
                    break
                continue
            yield msg

    @property
    def api(self):
        """获取 WebSocketAPI 实例"""
        if self._api_instance is None:
            from neobot_adapter.request.websocket import WebSocketAPI
            self._api_instance = WebSocketAPI(self)
        return self._api_instance

    def start(self):
        if self.thread and self.thread.is_alive():
            logger.error("接收器已在运行")
            return
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._run_thread_target, daemon=True)
        self.thread.start()
        logger.info("接收器已启动")

    def stop(self):
        logger.info("正在停止接收器...")
        self._stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                logger.warning("接收器停止超时，后台线程仍未退出")
            else:
                self.thread = None

    def get_message(self, block: bool = True, timeout: Optional[float] = None):
        try:
            return self.message_queue.get(block=block, timeout=timeout)
        except queue.Empty:
            return None

    def _run_thread_target(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._run_server())
        finally:
            self.loop.close()
            self.loop = None

    async def _run_server(self):
        host = os.getenv("NEO_BOT_ADAPTER_HOST", "0.0.0.0")
        port = int(os.getenv("NEO_BOT_ADAPTER_PORT", 8080))
        # 监听指定路径 /onebot
        async with websockets.serve(self._handle_client, host, port):
            logger.info(f"反向 WebSocket 服务运行于 ws://{host}:{port}")
            # 等待停止信号
            while not self._stop_event.is_set():
                await asyncio.sleep(1)

    async def _handle_client(self, websocket):
        logger.info(f"框架已连接")
        async with self._connections_lock:
            self.active_connections.add(websocket)
            self._conn_to_echo[websocket] = set()
            # 标记连接已建立
            if not self._connection_established.is_set():
                self._connection_established.set()
        try:
            async for message in websocket:
                data = json.loads(message)
                # 区分响应和事件
                if "echo" in data:
                    echo = data["echo"]
                    logger.debug(f"收到echo响应: echo={echo}")
                    if echo in self._pending:
                        self._pending[echo].set_result(data)
                        # 移除echo映射
                        async with self._connections_lock:
                            self._echo_to_conn.pop(echo, None)
                            conn_echo_set = self._conn_to_echo.get(websocket)
                            if conn_echo_set and echo in conn_echo_set:
                                conn_echo_set.remove(echo)
                    else:
                        logger.warning(f"未匹配的 echo: {echo}")
                else:
                    # 事件处理
                    await self._handle_event(websocket, data)
        except websockets.exceptions.ConnectionClosed:
            logger.info("框架连接断开")
        except Exception as e:
            logger.error(f"处理异常: {e}")
        finally:
            await self._remove_connection(websocket)

    async def _handle_event(self, websocket, event):
        # 放入队列（原始事件）
        try:
            self.message_queue.put_nowait(event)
        except queue.Full:
            logger.warning("队列满，丢弃事件")
        # 处理元事件
        await self._handle_meta_event(event)

    async def _remove_connection(self, websocket):
        async with self._connections_lock:
            self.active_connections.discard(websocket)
            echo_set = self._conn_to_echo.pop(websocket, set())
            for echo in echo_set:
                self._echo_to_conn.pop(echo, None)
                fut = self._pending.pop(echo, None)
                if fut and not fut.done():
                    fut.set_exception(websockets.exceptions.ConnectionClosed(0, ''))

    async def _handle_meta_event(self, event):
        """处理元事件，使用 Pydantic 模型解析"""
        post_type = event.get('post_type')
        if post_type != 'meta_event':
            return

        meta_event_type = event.get('meta_event_type')
        if meta_event_type == 'heartbeat':
            try:
                heartbeat = safe_parse_model(event, Heartbeat)
                logger.info(
                    f"心跳包: 机器人 {heartbeat.self_id}, "
                    f"时间 {heartbeat.time}, 间隔 {heartbeat.interval}ms, "
                    f"状态 {heartbeat.status}"
                )
            except Exception as e:
                logger.error(f"心跳包解析失败: {e}, 原始数据: {event}")
        elif meta_event_type == 'lifecycle':
            try:
                lifecycle = safe_parse_model(event, LifeCycle)
                logger.info(
                    f"生命周期: 机器人 {lifecycle.self_id}, "
                    f"时间 {lifecycle.time}, 子类型 {lifecycle.sub_type}"
                )
                if lifecycle.sub_type == LifeCycleSubType.disable:
                    logger.warning(f"机器人 {lifecycle.self_id} 已禁用")
                elif lifecycle.sub_type == LifeCycleSubType.enable:
                    logger.info(f"机器人 {lifecycle.self_id} 已启用")
                elif lifecycle.sub_type == LifeCycleSubType.connect:
                    logger.info(f"机器人 {lifecycle.self_id} 连接建立")
            except Exception as e:
                logger.error(f"生命周期解析失败: {e}, 原始数据: {event}")
        else:
            logger.info(f"未知元事件类型: {meta_event_type}, 数据: {event}")

    async def _call_action(self, websocket, action, params, timeout=5):
        echo = f"{action}_{id(params)}_{asyncio.get_event_loop().time()}"
        fut = asyncio.get_event_loop().create_future()
        self._pending[echo] = fut
        async with self._connections_lock:
            self._echo_to_conn[echo] = websocket
            if websocket not in self._conn_to_echo:
                self._conn_to_echo[websocket] = set()
            self._conn_to_echo[websocket].add(echo)
        try:
            request = {
                "action": action,
                "params": params,
                "echo": echo
            }
            logger.info(f"发送API请求: {request}")
            await websocket.send(json.dumps(request))
            response = await asyncio.wait_for(fut, timeout)
            logger.info(f"收到API响应: {response.get('status')}")
            # 根据 OneBot 协议规范，响应有 status 字段
            if response.get("status") == "ok":
                # 返回完整的响应数据，包括 data、retcode、message 等
                # 注意：即使 data 为 None 或空字典，也表示调用成功
                return response
            else:
                logger.warning(f"API调用失败: {response.get('retcode')} - {response.get('message')}")
                return None
        except asyncio.TimeoutError:
            logger.error(f"API 调用超时: {action}")
            return None
        finally:
            async with self._connections_lock:
                self._pending.pop(echo, None)
                self._echo_to_conn.pop(echo, None)
                conn_echo_set = self._conn_to_echo.get(websocket)
                if conn_echo_set and echo in conn_echo_set:
                    conn_echo_set.remove(echo)

    async def call_api(self, action, params, timeout=5, websocket=None):
        """调用 API 并等待响应"""
        if websocket is None:
            async with self._connections_lock:
                if not self.active_connections:
                    logger.error("没有活跃连接，无法调用 API")
                    return None
                websocket = next(iter(self.active_connections))  # 选择第一个连接
        return await self._call_action(websocket, action, params, timeout)

    def call_api_sync(self, action, params, timeout=5, websocket=None):
        """同步调用 API"""
        if not self.loop or not self.loop.is_running():
            logger.error("事件循环未运行")
            return None
        future = asyncio.run_coroutine_threadsafe(
            self.call_api(action, params, timeout, websocket), self.loop
        )
        try:
            return future.result(timeout + 1)  # 额外等待1秒
        except Exception as e:
            logger.error(f"调用 API 失败: {e}")
            return None
