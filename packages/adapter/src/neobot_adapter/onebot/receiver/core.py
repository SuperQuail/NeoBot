import asyncio
import hmac
import json
import queue
import threading
import time
from http import HTTPStatus
from typing import Any, Callable, Iterator, Optional
from urllib.parse import parse_qs, urlparse

import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

from neobot_adapter.model.meta_event import Heartbeat, LifeCycle, LifeCycleSubType
from neobot_adapter.onebot.receiver.settings import ReverseWsSettings
from neobot_adapter.utils.logger import get_module_logger
from neobot_adapter.utils.parse import safe_parse_model

logger = get_module_logger("adapter_receiver")


def _extract_access_token(headers: Any, path: str) -> Optional[str]:
    """按 OneBot 11 鉴权规范从握手中取出 access token。

    反向 WebSocket 由框架（客户端）在握手请求头里带
    ``Authorization: Bearer <access_token>``；同时兼容 query 参数
    ``?access_token=``（规范对 HTTP / 正向 WebSocket 给出的兜底形式，
    部分框架对反向 WS 也只提供填 URL 的入口）。
    """
    authorization = None
    if headers is not None:
        try:
            authorization = headers.get("Authorization")
        except Exception:
            authorization = None
    if authorization:
        parts = str(authorization).split(None, 1)
        if len(parts) == 2 and parts[0].casefold() == "bearer":
            return parts[1].strip()
        # 宽容处理只填 token、未带 Bearer 前缀的框架
        return str(authorization).strip()

    raw_path = str(path or "")
    if "?" in raw_path:
        values = parse_qs(urlparse(raw_path).query).get("access_token") or []
        if values and str(values[0]).strip():
            return str(values[0]).strip()
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
        access_token: str = "",
    ):
        """初始化适配器核心

        Args:
            max_queue_size: 消息队列最大长度
            heartbeat_timeout_multiplier: 心跳超时倍数，超过 心跳间隔 * 该倍数 未收到心跳则告警
            host: 反向 WebSocket 监听地址；None 时读环境变量 NEO_BOT_ADAPTER_HOST，
                  缺省 0.0.0.0
            port: 反向 WebSocket 监听端口；None 时读环境变量 NEO_BOT_ADAPTER_PORT，
                  缺省 8080
            access_token: 反向 WebSocket 握手鉴权的 access token（OneBot 11 规范）。
                  留空表示不校验（与历史行为一致）
        """
        self.host = host
        self.port = port
        self.access_token = str(access_token or "").strip()
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
        # 生命周期的串行化闸门：start/stop 由控制面调用，必须与接收线程的
        # 启停临界区互斥，否则「停止 → 改配置 → 重启」序列会与在途启停交错。
        self._lifecycle_lock = threading.Lock()
        # 最近一次实际生效的监听设置（服务未运行时为 None）。
        self._active_settings: Optional[ReverseWsSettings] = None

    def resolve_settings(self) -> ReverseWsSettings:
        """把当前字段解析为实际监听设置（构造参数 > 环境变量 > 默认值）。

        每次调用都重新解析，因此运行期修改 host/port/access_token 后，
        下一次启动接收线程即生效。
        """
        return ReverseWsSettings.resolve(
            host=self.host,
            port=self.port,
            access_token=self.access_token,
        )

    @property
    def settings(self) -> ReverseWsSettings:
        """当前解析后的监听设置（供状态展示与重配比较）。"""
        return self.resolve_settings()

    def apply_settings(self, settings: ReverseWsSettings) -> None:
        """写入新的监听设置（仅改字段，不触碰运行中的接收线程）。

        实际的「停下旧服务 → 用新设置重启」由控制面按需编排。
        """
        self.host = settings.host
        self.port = settings.port
        self.access_token = settings.access_token

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
        with self._lifecycle_lock:
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
        with self._lifecycle_lock:
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
                self._active_settings = None
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
        # 监听设置的解析规则（构造参数 > 环境变量 > 默认值）由 ReverseWsSettings
        # 统一负责，本方法只使用解析结果。
        settings = self.resolve_settings()
        self._active_settings = settings
        self._async_stop_event = asyncio.Event()
        warning = settings.security_warning()
        if warning is not None:
            logger.warning(warning)
        # 路径（文档约定 /onebot）由框架自己配置，服务端不限制；
        # 10MiB 帧上限以容纳 base64 大图等超 1MiB 默认上限的负载。
        serve_kwargs: dict[str, Any] = {"max_size": 10 * 2**20}
        if settings.token_enabled:
            # OneBot 11 鉴权：反向 WebSocket 由框架（客户端）在握手请求头中
            # 携带 Authorization: Bearer <access_token>，服务端在此校验。
            serve_kwargs["process_request"] = self._authorize_handshake
        server = await websockets.serve(
            self._handle_client,
            settings.host,
            settings.port,
            **serve_kwargs,
        )
        logger.info(f"反向 WebSocket 服务运行于 {settings.describe()}")
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

    async def _authorize_handshake(self, *args: Any) -> Any:
        """反向 WebSocket 握手鉴权（OneBot 11 规范的 access token 校验）。

        仅在本端配置了 access token 时注册为 ``process_request`` 钩子；
        未配置时连接行为与历史版本完全一致。

        兼容 websockets 两代 API：
        - 新版 asyncio 实现：``process_request(connection, request)``
          拒绝时返回 ``connection.respond(...)``；
        - 旧版 legacy 实现：``process_request(path, request_headers)``
          拒绝时返回 ``(status, headers, body)``。
        """
        if not self.access_token:
            return None

        connection: Any = None
        headers: Any = None
        path = ""
        if len(args) == 2 and hasattr(args[1], "headers"):
            connection, request = args
            headers = request.headers
            path = getattr(request, "path", "") or ""
        else:
            path = args[0] if args else ""
            headers = args[1] if len(args) > 1 else None

        supplied = _extract_access_token(headers, path)
        if supplied is not None and hmac.compare_digest(supplied, self.access_token):
            return None

        logger.warning("反向 WebSocket 握手被拒绝：access token 缺失或不匹配")
        if connection is not None:
            return connection.respond(HTTPStatus.UNAUTHORIZED, "unauthorized\n")
        return (HTTPStatus.UNAUTHORIZED, [], b"unauthorized\n")

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

    async def _call_action(self, websocket, action, params, timeout=20, wait_response=True):
        echo = f"{action}_{id(params)}_{asyncio.get_event_loop().time()}"
        if not wait_response:
            # 只把请求写上线，不等回执：回复管线不应被上游 echo 的往返延迟阻塞。
            # 代价是拿不到 message_id，也看不到 retcode；发送失败只能靠上游连接
            # 状态与心跳发现（实测发送几乎不会失败）。
            try:
                request = {"action": action, "params": params, "echo": echo}
                logger.info(f"发送API请求(不等待回执): {request}")
                await websocket.send(json.dumps(request))
            except Exception as exc:
                logger.warning(f"发送API请求失败(不等待回执): {action} - {exc}")
                return None
            return {
                "status": "ok",
                "retcode": 0,
                "echo": echo,
                "wording": "已发送(未等待回执)",
            }
        fut = asyncio.get_event_loop().create_future()
        self._pending[echo] = fut
        async with self._connections_lock:
            self._echo_to_conn[echo] = websocket
            if websocket not in self._conn_to_echo:
                self._conn_to_echo[websocket] = set()
            self._conn_to_echo[websocket].add(echo)
        try:
            request = {"action": action, "params": params, "echo": echo}
            # 高频恒定日志：降为 DEBUG。DEBUG 仍会落盘与进入面板缓冲（sink 等级为 DEBUG），
            # 但不再污染 INFO 级别的业务日志；失败/超时分支保留 WARNING 作为诊断主线。
            logger.debug(f"发送API请求: {request}")
            await websocket.send(json.dumps(request))
            response = await asyncio.wait_for(fut, timeout)
            logger.debug(f"收到API响应: {response.get('status')}")
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

    async def call_api(self, action, params, timeout=20, websocket=None, wait_response=True):
        """调用 API；wait_response=False 时只发请求不等回执。"""
        if websocket is None:
            async with self._connections_lock:
                if not self.active_connections:
                    # 降级为 DEBUG：上游短暂断连时会被高频打出，属于偶发性而非系统异常，
                    # 不应进入自修复 Agent 的错误累积判定。
                    logger.debug("没有活跃连接，无法调用 API")
                    return None
                websocket = next(iter(self.active_connections))  # 选择第一个连接
        return await self._call_action(
            websocket, action, params, timeout, wait_response=wait_response
        )

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
