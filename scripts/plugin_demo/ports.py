"""演示专用外部端口，不访问 QQ、直播平台或远程图片。"""

from __future__ import annotations

import base64
from io import BytesIO
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from PIL import Image, ImageDraw


class DemoAdapter:
    connected = True
    self_id = 10001

    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def call_api(self, action: str, params: dict | None = None, timeout: float = 5.0) -> dict:
        if action == "get_group_list":
            data = [{"group_id": 100100, "group_name": "演示交流群"}, {"group_id": 100200, "group_name": "通知测试群"}]
        elif action == "get_login_info":
            data = {"user_id": self.self_id, "nickname": "NeoBot 本地演示"}
        elif action == "get_version_info":
            data = {"app_name": "离线演示适配器", "app_version": "1.0"}
        else:
            data = {}
        return {"status": "ok", "retcode": 0, "data": data}

    async def send(self, conversation, message):
        self.messages.append({"conversation": str(conversation), "message": message})
        return "demo-message"

    async def send_group_msg(self, group_id: int, message):
        return await self.send(f"group:{group_id}", message)

    async def send_private_msg(self, user_id: int, message):
        return await self.send(f"private:{user_id}", message)


def _picture() -> bytes:
    image = Image.new("RGB", (640, 360), "#173347")
    draw = ImageDraw.Draw(image)
    for index, height in enumerate((70, 125, 185, 90, 155, 215, 120, 75)):
        x = 90 + index * 58
        draw.rounded_rectangle((x, 265 - height, x + 24, 265), radius=10, fill="#7dd3c0")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


DEMO_PICTURE = _picture()
DEMO_PICTURE_URI = "data:image/png;base64," + base64.b64encode(DEMO_PICTURE).decode()


class DemoLiveTransport:
    """返回真实 Bilibili 客户端能解析的合成 HTTP 响应。"""

    async def request(self, *, method: str, url: str, headers: dict, timeout: float):
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        room = int(query.get("room_id", query.get("id", ["900001"]))[0])
        if parsed.path.endswith("room_init"):
            data = {"room_id": room, "short_id": 0, "uid": 900100, "live_status": 1, "live_time": 0}
        elif parsed.path.endswith("get_info"):
            data = {
                "room_id": room,
                "uid": 900100,
                "title": "夜航电台 · 插件思索演示",
                "live_status": 1,
                "online": 1280,
                "area_name": "演示分区",
                "user_cover": "demo://cover",
                "live_time": 0,
            }
        elif parsed.path.endswith("getRoomInfoOld"):
            data = {"liveStatus": 1, "roomStatus": 1, "roomid": 900001, "title": "夜航电台"}
        elif parsed.path.endswith("/card"):
            data = {"card": {"mid": 900100, "name": "夜航电台（演示）", "face": "demo://avatar"}}
        else:
            raise ValueError("演示传输没有声明该平台接口")
        return SimpleNamespace(status=200, body={"code": 0, "message": "0", "data": data}, url=url, headers={})

    async def aclose(self) -> None:
        pass


async def demo_image_download(url: str, headers: dict, timeout: float):
    if not url.startswith("demo://"):
        raise ValueError("演示图片只允许本地合成资源")
    return 200, DEMO_PICTURE
