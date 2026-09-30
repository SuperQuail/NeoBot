---
flow: 20-avatar-files
covers:
  - app/src/neobot_app/runtime/avatar_store.py
  - app/src/neobot_app/core/file_server.py
  - app/src/neobot_app/core/paths.py
  - app/src/neobot_app/image_pool.py
verified_against: 96da9ef
verified_hash: 49cbf82a3fe8
---

# 20 头像存储与文件服务

## 范围

三件与「文件」有关的基础设施：

* `AvatarStore`（557 行）：本体级头像存储 —— 三列落在 `user_data` 上，谁有资料行谁有头像；
* `core/file_server.py`（406 行）：本地文件服务器（启动、路由、鉴权、生命周期）；
* `image_pool.py` + `core/paths.py`：图片暂存池与数据目录路径解析。

不在这里：卡片的渲染与缓存见 `13-render-cards.md`（那里也讲图片暂存池的使用侧）；
图片下载与解析见 `14-emoji-image-parse.md`；面板的头像展示见 `09b-dashboard-api.md`。

## 流程

```mermaid
flowchart TD
    A["需要某用户头像"] --> B["AvatarStore.path_for(user_id)"]
    B --> C{"本地已有?"}
    C -- 是 --> D["get_data_uri 直接给 data URI"]
    C -- 否 --> E["maybe_refresh(user_id)"]
    E --> F{"在冷却中?"}
    F -- 是 --> F1["_in_cooldown：跳过下载"]
    F -- 否 --> G["_start_download 起后台任务"]
    G --> H["_fetch：_fetch_from_qq 拉头像"]
    H --> I["_validate 检查是不是图片"]
    I --> J{"通过?"}
    J -- 否 --> K["_record_failure 记失败 + 冷却"]
    J -- 是 --> L["_write_temp 原子写 + _record_success"]
    L --> M["写 user_data 三列"]
    M --> N["下次直接命中"]
    O["application.start"] --> P["file_server.start 监听端口"]
    P --> Q["请求进入：路由 + 鉴权"]
    Q --> R["返回文件或 404"]
```

## 时序

```mermaid
sequenceDiagram
    autonumber
    participant RQ as 调用方
    participant AS as AvatarStore
    participant AD as adapter(QQ)
    participant DB as user_data
    participant FS as file_server

    RQ->>AS: get_data_uri(user_id)
    AS->>AS: path_for + 本地命中判断
    alt 本地没有
        AS->>AS: maybe_refresh（含冷却判断）
        AS->>AD: 拉取头像
        AD-->>AS: 字节或失败
        AS->>AS: _validate + _write_temp
        AS->>DB: 记录三列（成功/失败+冷却）
    end
    AS-->>RQ: data URI 或 None
    Note over FS: 文件服务器独立于头像链路
```

## 细节

<details>
### 头像与 user_data 的耦合

```mermaid
flowchart TD
    A["user_data 有行"] --> B["= 认识该用户"]
    B --> C["avatar 三列可写"]
    C --> D["get_path / get_data_uri 可用"]
    E["没有行"] --> F["ensure_user_profile 先建行（18）"]
    F --> C
```

「有 `user_data` 行 = 认识该用户」是 spec(5) R33–R37 的实现口径：头像就存在 `user_data` 上，
所以**软重启复用同一个 `AvatarStore` 实例**（内存缓存与在途下载都不重建）。
反过来说：**删掉 `user_data` 行 = 头像也一起没了**，排查「头像消失」要先看资料行是否还在。
</details>

<details>
### 下载：冷却、校验与原子写

```mermaid
flowchart TD
    A["maybe_refresh(user_id)"] --> B{"enabled?"}
    B -- 否 --> C["直接返回 False"]
    B -- 是 --> D{"_in_cooldown?"}
    D -- 是 --> E["跳过（避免刷接口）"]
    D -- 否 --> F["_start_download 后台任务去重"]
    F --> G["_fetch -> _fetch_from_qq"]
    G --> H{"_looks_like_image?"}
    H -- 否 --> I["_record_failure(reason)"]
    H -- 是 --> J["_validate 尺寸/格式"]
    J --> K{"通过?"}
    K -- 否 --> I
    K -- 是 --> L["_write_temp 临时文件 + 原子替换"]
    L --> M["_record_success 写库"]
```

四个防呆点：**冷却**（`_in_cooldown`）、**去重**（同时多个调用只起一个下载）、
**内容校验**（`_looks_like_image` 看魔数，避免把 HTML 错误页存成头像）、
**原子写**（先写临时文件再替换，避免半截文件被当成头像）。
`_validate`（`:408`）返回错误字符串而不是抛异常，失败走 `_record_failure`。
</details>

<details>
### 清理与排空：expired / drain

```mermaid
flowchart TD
    A["cleanup_expired()"] --> B["扫目录找过期头像文件"]
    B --> C["删文件 + 清库字段"]
    C --> D["_maybe_schedule_cleanup 惰性排程"]
    E["停机"] --> F["drain(timeout=5.0)"]
    F --> G{"在途下载当前?"}
    G -- 是 --> H["等最多 5s"]
    G -- 否 --> I["立即返回"]
```

`drain`（`:512`）是停机路径的一部分：给在途下载最多 5 秒收尾，超时即放弃（不阻塞停机）。
`_maybe_schedule_cleanup`（`:490`）说明清理是**惰性触发**的 —— 长期没有头像访问就不会清理。
</details>

<details>
### 文件服务器：启动与失败语义

```mermaid
flowchart TD
    A["application.start: file_server.start()"] --> B{"端口可用?"}
    B -- 否 --> C["抛错 -> 启动回滚（01）"]
    B -- 是 --> D["监听 + 注册路由"]
    D --> E["请求：静态文件 / 目录列表"]
    E --> F{"路径合法?"}
    F -- 否 --> G["404 或 403"]
    F -- 是 --> H["返回文件"]
    I["停机"] --> J["file_server.stop 关闭监听"]
```

文件服务器是 `application.start` 的**第一步**（见 `01-startup-shutdown.md`），
端口占用会直接导致启动失败并触发回滚 —— 这是启动失败最常见的原因之一。
它服务于图片/音频等产物的外链，与面板（`09`）是两套 HTTP 服务。
</details>

<details>
### 图片暂存池：TTL 与磁盘文件的关系

```mermaid
flowchart TD
    A["StagedImage 入池"] --> B["记录 created_at / expires_at"]
    B --> C{"取用时 now - created_at > ttl?"}
    C -- 是 --> D["视为过期，不再给出"]
    C -- 否 --> E["给出引用"]
    D --> F["只删引用，**不删磁盘文件**"]
    E --> G["TTL 300s 硬编码（bootstrap/_runtime.py）"]
```

三处与直觉不符（FINDINGS 13-3，本图复核确认）：

1. `expires_at` **只写不读**：判定实际用 `now - created_at > ttl`；
2. TTL 300s **硬编码**，配置层没有 `image_pool` / `ttl_seconds` 这两个键；
3. 池**只删引用不删磁盘文件** —— 磁盘占用要靠别的清理链路（见 `16` 的 temp_cleaner）。
</details>

<details>
### 路径解析：DATA_DIR 与目录布局

```mermaid
flowchart LR
    A["core/paths.py: get_data_dir()"] --> B["DATA_DIR"]
    B --> C["avatars/ 头像文件"]
    B --> D["browser/ 浏览器 profile"]
    B --> E["plugins/ 第三方插件"]
    B --> F["plugins_data/<插件>/config.toml"]
    B --> G["Billing/ 计价脚本"]
    B --> H["logs/ 日志"]
    B --> I["neobot.db 主库"]
```

`get_data_dir()` 是**唯一**的数据目录来源；注意 `agent.browser.data_dir` 是死配置
（FINDINGS 12-1），浏览器数据实际固定落在 `DATA_DIR/browser`。
写新功能时用 `get_data_dir()`，别自己拼相对路径。
</details>

## 关键状态

| 状态 | 谁置位 | 谁清理 | 失败时停在哪 |
|---|---|---|---|
| 头像文件 | `_write_temp` + `_record_success` | `cleanup_expired` | 校验不过不落地，只记失败与冷却 |
| 下载冷却 | `_record_failure` | 冷却窗口自然过期 | 冷却期内不再发起下载 |
| 在途下载 | `_start_download`（去重） | 任务结束 / `drain` | 停机时最多等 5s |
| 文件服务监听 | `file_server.start` | `file_server.stop` | 端口占用 -> 启动回滚 |
| 暂存池引用 | 入池 | TTL 到期 / 显式移除 | 只删引用，磁盘文件另行清理 |

## 易错点

* **头像寄生在 `user_data`**：删资料行会连头像一起丢；软重启必须复用 `AvatarStore` 实例。
* **下载有冷却与去重**：头像「长时间没更新」可能是冷却中，不是坏了。
* **暂存池 TTL 不可配**：300s 硬编码，且 `expires_at` 是死字段（判定用 `created_at`）。
* **暂存池不删磁盘文件**：磁盘占用要靠 temp_cleaner 等链路，别指望池子自清。
* **文件服务器端口占用会让启动失败**：这是 `start()` 第一步，报错信息会指向端口。
* **`agent.browser.data_dir` 是死配置**：浏览器数据固定用 `DATA_DIR/browser`（FINDINGS 12-1）。
