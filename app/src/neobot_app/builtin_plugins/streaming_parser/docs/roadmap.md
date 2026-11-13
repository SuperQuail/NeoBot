# 移植路线图

协议来源：[ikenxuan/amagi](https://github.com/ikenxuan/amagi)（TypeScript，多平台 Web 接口 SDK）。
本插件只移植 **B 站** 部分，优先直播间。

## 落地状态（v0.2.0）

**P0 已全部落地**：三个直播接口封装、短号 ↔ 真实房间号互转、开播/下播轮询与跳变判定、
卡片推送（3 风格 + 随包字体）、开播状态总览图、`/直播监听` 一族命令与 `/config`，
以及渲染不可用时的纯文本降级。测试见仓库 `tests/`（含模板契约测试）。

实现过程中由真实流量补充、参考项目未记录的点：

- `live_time` 的负数哨兵值 `-62170012800`（.NET DateTime.MinValue 秒数），必须归一化为「无开播时间」；
- `getRoomInfoOld` 的 `data` 可能是空对象，模型要容忍字段缺失；
- 直播接口沿用 `Referer: https://www.bilibili.com/` 也能跑通，但改成 `https://live.bilibili.com/{room_id}` 更贴近真实前端；
- 截图的 `file://` 与相对资源一律加载不到（CDP setDocumentContent 落在 about:blank），CSS 与图片必须内联；
- 内嵌中日韩 woff2 时 `wait_for_fonts=True` 会抛 FontLoadError，必须保留「不等字体校验」的降级。

**P1 未做**：WBI 签名器只有原型与向量验证（`research/`），尚未接线到正式代码；视频弹幕、评论、动态等同理。

**P2 未做**：直播间弹幕长连接。参考项目在这一点上是空白，协议需另行调研。

## 参考项目的能力边界（实测结论）

| 能力 | amagi 是否实现 | 说明 |
|---|---|---|
| uid → 直播状态/房间号 | 是（HTTP） | `room/v1/Room/getRoomInfoOld?mid=` |
| 短号/房间号 → 真实房间号 + 开播状态 | 是（HTTP） | `room/v1/Room/room_init?id=` |
| 直播间展示信息（标题/封面/人气/分区） | 是（HTTP） | `room/v1/Room/get_info?room_id=` |
| WBI 签名（`w_rid` / `wts`） | 是，但直播三接口**不用** | 只有评论/用户空间/动态用 |
| 视频（点播）弹幕 protobuf 解码 | 是（HTTP `seg.so`） | 与直播间无关 |
| **直播间弹幕 WebSocket 长连接** | **否，零实现** | 无 `getDanmuInfo`、无 16 字节包头、无 brotli |
| `buvid3` / `buvid4` 生成 | 否 | 只在 WS 鉴权里成为必需项 |

三个直播接口的共同特征：GET、无请求体、**无签名**、匿名可访问，端点声明
`retryOn: ["RISK_CONTROL"]` —— 即 `-412` 退避重试 1s/2s/4s，最多 4 次尝试。

## P0 — 直播间解析（最小可用集合）

1. HTTP 客户端与请求头基线：UA、`Referer`、`Origin`、超时 10s。
   amagi 对直播接口沿用 `Referer: https://www.bilibili.com/`；本插件改用更贴近真实前端的
   `https://live.bilibili.com/{room_id}`（这是改进项，不是复刻）。
2. 三个房间接口的 Python 封装 + 参数校验（`room_id` 宽容地 `str()` 化）。
3. ID 互转：`short_id → room_id`、`room_id → short_id`、`uid → roomid`。
4. 开播轮询：`getRoomInfoOld` 最省流，命中 `liveStatus == 1` 再取详情。
5. 错误判定与重试：`code == 0` 成功；`-412` 退避重试；`-101` 凭据失效；
   `-404` 不存在；空响应体视为 cookie 失效；非 JSON 文本视为反爬页。
   **改进项**：把 `-352`（风控校验失败）与 `-509`（请求过于频繁）也纳入退避重试，
   amagi 把它们落到了「不重试的未知错误」。
6. `live_time` 双形态归一化：`room_init` 返回数字时间戳，
   `get_info` 返回字符串 `YYYY-MM-DD HH:mm:ss`。

## P1 — 扩展能力

- WBI 签名器（mixinKeyEncTab 64 项表 + md5 + `/nav` 密钥 30 分钟 TTL 缓存），
  仅评论/用户空间/动态接口需要。
- Cookie 透传与 `csrf`（`bili_jct`）取值。
- 视频弹幕 protobuf 分段拉取与解析。

## P2 — 直播间弹幕长连接

`getDanmuInfo` 取 `token` + `host_list` → `wss://{host}:{wss_port}/sub` 建连 →
鉴权包（需 `uid` + `buvid`，因此还要先解决 buvid 获取）→ 30s 心跳 →
16 字节包头解析 → `protover=3` 时 brotli 解压 → 解析 `DANMU_MSG` 等 `cmd`。

协议规格需另行调研（参考项目在此处是空白走廊），Python 侧需引入
`brotli` / `websockets` 依赖。
