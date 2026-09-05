import asyncio
import json
import os
import queue
import threading
import time
from typing import Any, Callable, Iterator, Optional

import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

from neobot_adapter.model.meta_event import Heartbeat, LifeCycle, LifeCycleSubType
from neobot_adapter.utils.logger import get_module_logger
from neobot_adapter.utils.parse import safe_parse_model

logger = get_module_logger("adapter_receiver")


def _env_ci(name: str) -> str | None:
    """大小写不敏感地读取环境变量。

    .env 文件中的键名由 load_env 原样写入 os.environ(保留用户大小写),
    而 os.getenv 大小写敏感,用户写成 NEOBOT_ADAPTER_PORT / 小写变体时
    会静默回落到默认值 —— 这里统一按大小写不敏感匹配,杜绝该坑。
    """
    target = name.casefold()
    for key, value in os.environ.items():
        if key.casefold() == target:
            return value
    return None


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

    def __init__(
        self,
        max_queue_size: int = 1000,
        heartbeat_timeout_multiplier: float = 2.0,
        packet_callback: Callable[[dict[str, Any]], None] | None = None,
        host: str | None = None,
        port: int | None = None,
    ):
        """初始化适配器核心

        Args:
            max_queue_size: 消息队列最大长度
            heartbeat_timeout_multiplier: 心跳超时倍数，超过 心跳间隔 * 该倍数 未收到心跳则告警
            host: 反向 WebSocket 监听地址；None 时读环境变量 NEO_BOT_ADAPTER_HOST，
                  缺省 0.0.0.0
            port: 反向 WebSocket 监听端口；None 时读环境变量 NEO_BOT_ADAPTER_PORT，
                  缺省 8080
        """
        self.host = host
        self.port = port
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._async_stop_event: Optional[asyncio.Event] = None
        self.message_queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._pending = {}  # echo -> asyncio.Future
        self.active_connections = set()
        self._connections_lock = asyncio.Lock()
        self._echo_to_conn = {}  # echo -> websocket
        self._conn_to_echo = {}  # websocket -> set of echo
        self._connection_established = threading.Event()  # 连接建立事件
        self._api_instance: Optional[Any] = None  # WebSocketAPI 实例缓存
        self._last_heartbeat_time: float = 0.0  # 上次心跳时间
        self._heartbeat_interval: float = 0.0  # 心跳间隔（秒）
        self._heartbeat_timeout_multiplier: float = heartbeat_timeout_multiplier
        self._heartbeat_checker_task: Optional[asyncio.Task] = None
        self._packet_callback = packet_callback

    def wait_for_connection(self, timeout: Optional[float] = None) -> bool:
        """等待直到有框架连接建立

        Args:
            timeout: 超时时间（秒），None 表示无限等待

        Returns:
            如果连接建立返回 True，超时返回 False
        """
        return self._connection_established.wait(timeout=timeout)

    def iter_messages(
        self, block: bool = True, timeout: Optional[float] = None
    ) -> Iterator[dict]:
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

    def stop(self, timeout: float = 8.0) -> bool:
        """在有限时间内停止接收线程。

        正常路径会立即唤醒接收循环；若第三方 WebSocket 实现在清理时卡住，
        则最终兜底取消其残留的事件循环任务，让守护线程保持隔离，
        避免阻塞应用永久无法退出。
        """
        logger.info("正在停止接收器...")
        self._stop_event.set()
        loop = self.loop
        async_stop_event = self._async_stop_event
        if loop is not None and loop.is_running() and async_stop_event is not None:
            loop.call_soon_threadsafe(async_stop_event.set)

        thread = self.thread
        if thread is None:
            return True
        thread.join(timeout=max(0.0, timeout))
        if thread.is_alive() and loop is not None and loop.is_running():
            logger.warning("接收器正常停止超时，正在取消残留任务")
            loop.call_soon_threadsafe(self._cancel_loop_tasks)
            thread.join(timeout=1.0)
        stopped = not thread.is_alive()
        if not stopped:
            logger.error("接收器停止兜底超时，后台守护线程将由进程退出时回收")
        else:
            self.thread = None
        return stopped

    def get_message(self, block: bool = True, timeout: Optional[float] = None):
        try:
            return self.message_queue.get(block=block, timeout=timeout)
        except queue.Empty:
            return None

    def _run_thread_target(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            try:
                self.loop.run_until_complete(self._run_server())
            except asyncio.CancelledError:
                logger.warning("接收器事件循环已由停止兜底取消")
        finally:
            self._async_stop_event = None
            self.loop.close()
            self.loop = None

    def _cancel_loop_tasks(self) -> None:
        current = asyncio.current_task(self.loop)
        for task in asyncio.all_tasks(self.loop):
            if task is not current and not task.done():
                task.cancel()

    async def _run_server(self):
        # 端口来源优先级:构造参数(配置系统) > 环境变量 > 默认。
        # 环境变量兼容链(均大小写不敏感):
        #   NEO_BOT_ADAPTER_*     反向 WS 规范键
        #   NEOBOT_ADAPTER_*      老版本无 Local 字样的键(配置迁移期)
        #   NEOBOT_LOCAL_ADAPTER_* local 专用键;生产环境长期用它配端口,
        #                           onebot 模式下回退读取,避免"配了 8091 实际监听 8080"
        host = (
            self.host
            or _env_ci("NEO_BOT_ADAPTER_HOST")
            or _env_ci("NEOBOT_ADAPTER_HOST")
            or _env_ci("NEOBOT_LOCAL_ADAPTER_HOST")
            or "0.0.0.0"
        )
        port = self.port
        if port is None:
            env_port = (
                _env_ci("NEO_BOT_ADAPTER_PORT")
                or _env_ci("NEOBOT_ADAPTER_PORT")
                or _env_ci("NEOBOT_LOCAL_ADAPTER_PORT")
            )
            port = int(env_port) if env_port else 8080
        self._async_stop_event = asyncio.Event()
        # 监听指定路径 /onebot；10MiB 帧上限以容纳 base64 大图等超 1MiB 默认上限的负载
        server = await websockets.serve(
            self._handle_client,
            host,
            port,
            max_size=10 * 2**20,
        )
        logger.info(f"反向 WebSocket 服务运行于 ws://{host}:{port}")
        try:
            if not self._stop_event.is_set():
                await self._async_stop_event.wait()
        finally:
            heartbeat_task = self._heartbeat_checker_task
            self._heartbeat_checker_task = None
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                await asyncio.gather(heartbeat_task, return_exceptions=True)

            # 关闭服务器（不再接受新连接）
            server.close()
            # 显式关闭所有活跃连接，避免 wait_closed 无限等待
            connections = list(self.active_connections)
            for ws in connections:
                ws.close_timeout = 1
            if connections:
                close_tasks = [
                    ws.close(1011, "Server shutting down") for ws in connections
                ]
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*close_tasks, return_exceptions=True),
                        timeout=2,
                    )
                except asyncio.TimeoutError:
                    logger.warning("活跃连接关闭超时，继续回收服务器")
            # 等待 handler 清理（最多 2 秒）
            try:
                await asyncio.wait_for(server.wait_closed(), timeout=2)
            except asyncio.TimeoutError:
                logger.warning("服务器关闭超时，强制退出")
            except Exception as exc:
                logger.warning(f"服务器关闭异常: {exc}")
            self.active_connections.clear()
            self._connection_established.clear()

    async def _handle_client(self, websocket):
        logger.info("框架已连接")
        async with self._connections_lock:
            self.active_connections.add(websocket)
            self._conn_to_echo[websocket] = set()
            # 标记连接已建立
            if not self._connection_established.is_set():
                self._connection_established.set()
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                except (json.JSONDecodeError, ValueError):
                    logger.warning("收到畸形 JSON 帧，已跳过")
                    continue
                if self._packet_callback is not None:
                    try:
                        self._packet_callback(data)
                    except Exception as exc:
                        logger.error(f"调试收包回调失败: {exc}")
                # 区分响应和事件
                if "echo" in data:
                    echo = data["echo"]
                    logger.debug(f"收到echo响应: echo={echo}")
                    await self._fulfill_echo(websocket, echo, data)
                else:
                    # 事件处理
                    await self._handle_event(websocket, data)
        except ConnectionClosedError as exc:
            logger.warning(f"框架连接异常断开（{exc}）")
        except ConnectionClosed:
            logger.info("框架连接断开")
        except Exception as e:
            logger.warning(f"处理异常: {type(e).__name__}: {e}")
        finally:
            await self._remove_connection(websocket)

    async def _fulfill_echo(self, websocket, echo: str, data: dict[str, Any]) -> None:
        """将 echo 响应回填给等待中的 future。

        对迟到/重复的 echo 必须幂等：future 可能已被超时取消或被连接回收
        清理，此时 set_result/set_exception 会抛 InvalidStateError —— 这里吞掉，
        绝不让回显处理协程异常退出（否则会触发 _handle_client 异常分支并
        回收连接，造成“没有活跃连接”连锁故障）。
        """
        async with self._connections_lock:
            fut = self._pending.get(echo)
            conn_echo_set = self._conn_to_echo.get(websocket)
        try:
            if fut is None:
                logger.debug(f"未匹配的 echo（已取消/清理）: {echo}")
                return
            if fut.cancelled():
                logger.debug(f"echo {echo} 对应的 future 已被取消，丢弃迟到响应")
                return
            if fut.done():
                logger.debug(f"echo {echo} 对应的 future 已完成，丢弃重复响应")
                return
            fut.set_result(data)
        except asyncio.InvalidStateError:
            logger.debug(f"echo {echo} future 状态非法，丢弃响应")
        except Exception as exc:
            logger.warning(f"回填 echo {echo} 失败: {exc}")
        else:
            async with self._connections_lock:
                self._echo_to_conn.pop(echo, None)
                conn_echo_set = self._conn_to_echo.get(websocket)
                if conn_echo_set and echo in conn_echo_set:
                    conn_echo_set.remove(echo)

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
                    fut.set_exception(ConnectionClosed(None, None))

    async def _handle_meta_event(self, event):
        """处理元事件，使用 Pydantic 模型解析"""
        post_type = event.get("post_type")
        if post_type != "meta_event":
            return

        meta_event_type = event.get("meta_event_type")
        if meta_event_type == "heartbeat":
            try:
                heartbeat = safe_parse_model(event, Heartbeat)
                self._last_heartbeat_time = time.monotonic()
                if heartbeat.interval and self._heartbeat_interval == 0.0:
                    self._heartbeat_interval = heartbeat.interval / 1000.0
                    logger.debug(f"心跳间隔: {self._heartbeat_interval}s")
                    # 收到第一次心跳后启动检测任务
                    if self._heartbeat_checker_task is None:
                        self._heartbeat_checker_task = asyncio.ensure_future(
                            self._check_heartbeat()
                        )
                        logger.debug("心跳检测任务已启动")
            except Exception as e:
                logger.error(f"心跳包解析失败: {e}, 原始数据: {event}")
        elif meta_event_type == "lifecycle":
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

    async def _check_heartbeat(self):
        """定期检查心跳是否超时"""
        try:
            while not self._stop_event.is_set():
                await asyncio.sleep(self._heartbeat_interval)
                if self._last_heartbeat_time == 0.0:
                    continue
                elapsed = time.monotonic() - self._last_heartbeat_time
                if (
                    elapsed
                    > self._heartbeat_interval * self._heartbeat_timeout_multiplier
                ):
                    logger.warning(f"心跳超时: 已 {elapsed:.1f}s 未收到心跳包")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"心跳检测任务异常: {e}")

    async def _call_action(self, websocket, action, params, timeout=20):
        echo = f"{action}_{id(params)}_{asyncio.get_event_loop().time()}"
        fut = asyncio.get_event_loop().create_future()
        self._pending[echo] = fut
        async with self._connections_lock:
            self._echo_to_conn[echo] = websocket
            if websocket not in self._conn_to_echo:
                self._conn_to_echo[websocket] = set()
            self._conn_to_echo[websocket].add(echo)
        try:
            request = {"action": action, "params": params, "echo": echo}
            logger.info(f"发送API请求: {request}")
            await websocket.send(json.dumps(request))
            response = await asyncio.wait_for(fut, timeout)
            logger.info(f"收到API响应: {response.get('status')}")
            # 根据 OneBot 协议规范，响应有 status 字段
            if response.get("status") == "ok":
                return response
            retcode = response.get("retcode")
            message = response.get("message") or response.get("wording") or ""
            logger.warning(f"API调用失败: {retcode} - {message}")
            return response
        except asyncio.TimeoutError:
            # 取消等待中的 future，使后续迟到 echo 被 _fulfill_echo 当作 cancelled 安全丢弃，
            # 而不是触发 InvalidStateError。降级到 WARNING：偶发取图/慢响应不应进入自修复判定。
            if not fut.done():
                fut.cancel()
            logger.warning(f"API 调用超时: {action}")
            return None
        finally:
            async with self._connections_lock:
                self._pending.pop(echo, None)
                self._echo_to_conn.pop(echo, None)
                conn_echo_set = self._conn_to_echo.get(websocket)
                if conn_echo_set and echo in conn_echo_set:
                    conn_echo_set.remove(echo)

    async def call_api(self, action, params, timeout=20, websocket=None):
        """调用 API 并等待响应"""
        if websocket is None:
            async with self._connections_lock:
                if not self.active_connections:
                    # 降级为 DEBUG：上游短暂断连时会被高频打出，属于偶发性而非系统异常，
                    # 不应进入自修复 Agent 的错误累积判定。
                    logger.debug("没有活跃连接，无法调用 API")
                    return None
                websocket = next(iter(self.active_connections))  # 选择第一个连接
        return await self._call_action(websocket, action, params, timeout)

    async def send_message(self, data, websocket=None):
        """通过一条活跃的 WebSocket 连接发送原始 OneBot 数据。"""
        if websocket is None:
            async with self._connections_lock:
                if not self.active_connections:
                    logger.debug("没有活跃连接，无法发送原始消息")
                    return False
                websocket = next(iter(self.active_connections))
        await websocket.send(json.dumps(data, ensure_ascii=False))
        return True

    def send_message_sync(self, data, websocket=None, timeout=5):
        """通过接收循环同步发送原始 OneBot 数据。"""
        if not self.loop or not self.loop.is_running():
            logger.error("事件循环未运行")
            return False
        future = asyncio.run_coroutine_threadsafe(
            self.send_message(data, websocket), self.loop
        )
        try:
            return bool(future.result(timeout))
        except Exception as exc:
            logger.error(f"发送原始消息失败: {exc}")
            return False

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
