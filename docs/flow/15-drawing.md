---
flow: 15-drawing
covers:
  - app/src/neobot_app/drawing/
verified_against: 528fe18
verified_hash: 5ba359524368
---

# 15 绘画子系统：提交判据 · 参考图接口分派 · 落盘清理 · 通知回执

## 范围

本图覆盖 `app/src/neobot_app/drawing/` 这 5 个文件（2792 行）：

* `service.py`（2017 行）：`CreatorImageService`——生图请求组装、参考图解析、`/images/edits` 与
  `/images/generations` 分派、结果落盘与命名、图库/暂存区记录、失效清理、本地图片后处理；
* `manager.py`（653 行）：`BackgroundDrawingManager`——提交判据（未启用 / busy / cooldown）、
  冷却、任务容量、后台执行、通知投递与通知重试；
* `config.py`（63 行）：`DrawServiceConfig.from_schema` 与 `ImageGenerationError`；
* `tasks.py`（34 行）：`DrawTask` 数据结构；
* `__init__.py`：包导出。

**不画什么**（相邻图）：

* `skills/drawing_skill.py` 的工具定义与提示词（06-tools-skills）；
* `reply/tools.py` 的 `drawing__inspect_image`、`check_last_drawing`、
  `cancel_task(drawing_cooldown)` 与视觉工具隐藏规则（03b-reply-tools）；
* `image_pipeline.prepare_local_image_async`、`ImageStagingPool`、`file_server`、
  `media_sender`（14-emoji-image-parse、13-render-cards、20-avatar-files）；
* `[models.assignments].creator_image_models` 的配置与模型注册（05-llm-routing、01b-config-system）；
* `BackgroundNotificationHub` 的队列实现与消息队列镜像（03、16）。

**spec / 直觉与现实的差异**（逐条落到节点上）：

1. **没有绘图任务队列**：管线忙时 `submit` 直接回 `status=busy`，不排队、不合并、不覆盖；
   模型要自己稍后再试。
2. **没有任务级超时、没有取消接口**：能取消的只有冷却；在途生图只能等 httpx 超时或
   进程 `shutdown()`。`DrawTask.status` 的 `timeout` 只在关停与通知超时时写入。
3. **默认尺寸对不上**：代码 `DEFAULT_IMAGE_SIZE="512x512"`（`config.py:15`），工具提示词里
   写的是「未指定时默认 1024x1024」（`skills/drawing_skill.py:102`）。
4. **`draw_max_retries` 不是绘图重试次数**：它只控制**通知**重试；绘图本身失败从不自动重提。
5. **完全没有计费/用量记录**：本目录 0 处 `usage/billing/cost` 写入；生图走裸 httpx 不经过
   chat Provider；连图库自动描述调 `vision_provider.chat` 也没有 `record()`（详见细节块 11）。
6. **hub 存在时 `manager.poll_notification` 是死分支**：bootstrap 无条件创建
   `BackgroundNotificationHub`，orchestrator 命中 hub 分支后直接 `return`（`orchestrator.py:3818-3831`），
   `_notification_queues` 只有在 `notification_hub is None` 的旧装配下才会用到。
7. SPLIT-MAP 标注 `drawing/service.py` 为 1821 行，实际 2017 行（`wc -l` 口径）。

## 流程

```mermaid
flowchart TD
    A["drawing 工具：DrawingSkill._handle_draw"] --> B["BackgroundDrawingManager.submit / manager.py:198"]
    B --> C{"background_enabled?<br/>draw_background_enabled 且 image_service 非空"}
    C -- 否 --> C1["ok=false：后台绘图未启用或服务未配置"]
    C -- 是 --> D{"_get_active_task 命中该管线 status=drawing?"}
    D -- 有 --> D1["ok=true status=busy：不排队直接拒绝"]
    D -- 无 --> E{"check_cooldown(pipeline_key) > 0?"}
    E -- 是 --> E1["ok=true status=cooldown + remaining_seconds"]
    E -- 否 --> F["建 DrawTask → _enforce_task_limit(20) → _set_cooldown(60s)"]
    F --> G["_spawn_bg_task(_run_draw) + 主协程 sleep(min(grace,3.0))"]
    G --> H{"宽限期内 task.status 已 failed?"}
    H -- 是 --> H1["cancel_cooldown + ok=false + error"]
    H -- 否 --> I["ok=true status=drawing 立即返回，不等绘图结果"]
    G --> J["CreatorImageService.generate_image / service.py:419"]
    J --> K{"有参考图 且 image_api in auto/edits?"}
    K -- 是 --> K1["_post_edits：POST /images/edits multipart"]
    K -- 否 --> L["POST /images/generations JSON，参考图放 reference_param"]
    K1 --> K2{"status in 400/404/405 且非显式 edits?"}
    K2 -- 是 --> L
    K2 -- 否 --> M["raise_for_status + _extract_image_bytes"]
    L --> M
    M -. 失败：抛 ImageGenerationError .-> P["status=failed + error JSON + cancel_cooldown"]
    M -- 成功 --> N["_save_image_bytes：tmp_ 命名 + sha256 + 写 .txt 描述"]
    N --> O["status=completed + image_id + record_payload"]
    O --> Q["_push_notification：hub.publish 或本地队列"]
    P --> Q
    Q --> R["orchestrator 注入 user 消息，模型按 next 调 image_send__send_image"]
```

## 时序

```mermaid
sequenceDiagram
    autonumber
    participant SK as DrawingSkill 工具面
    participant MG as BackgroundDrawingManager
    participant SV as CreatorImageService
    participant API as 生图 API
    participant DB as UoW creator_images
    participant HB as BackgroundNotificationHub
    participant OR as ReplyOrchestrator
    participant MD as 主模型
    SK->>MG: submit(pipeline_key, prompt, references, reference_id, provider)
    MG->>MG: 未启用 / busy / cooldown 三判据 → 建 DrawTask + _set_cooldown
    MG-->>SK: sleep min(grace,3.0) 后返回 status=drawing，不等绘图
    par 后台协程 _run_draw
        MG->>SV: generate_image(...)
        SV->>SV: resolve_model_name + payload 组装 + 参考图解析为 data URL
        SV->>API: POST /images/edits 或 /images/generations
        API-->>SV: b64_json 或 url；失败抛 ImageGenerationError 或 httpx 异常
        SV->>DB: _save_image_bytes + _upsert_record + commit
        SV-->>MG: CreatorImageRecord(image_id=tmp_xxx)
    end
    MG->>HB: publish(source=drawing, on_consumed=_mark_notified)
    HB->>OR: 无活跃管线时 start_background_reply，否则入 hub 队列
    OR->>HB: 每轮 _poll_background_notifications(pipeline_key)
    HB-->>OR: 通知 JSON（含 file_path 与 next 动作）
    OR->>MD: 追加 role=user 通知后继续本轮调用
    MD->>OR: 调 image_send__send_image(file_path, group_id 或 user_id)
    Note over MG,HB: 通知重试 30s × max_retries；仍未 poll 则 status=timeout 再推一条
    Note over MG,SV: 绘图本身失败只回执失败，不自动重提；重试只发生在通知层
```

## 细节

<details>
### 提交判据：三种拒绝与 3 秒宽限期

```mermaid
flowchart TD
    A["DrawingSkill._handle_draw / skills/drawing_skill.py:349"] --> B{"prompt 去空后非空?"}
    B -- 空 --> B1["ok=false：prompt 不能为空，不进管理器"]
    B -- 非空 --> C{"provider 参数非空?"}
    C -- 是 --> C1["manager.resolve_model_name；未知取值 ok=false + available_models"]
    C -- 否 --> D["manager.submit / drawing/manager.py:198"]
    C1 -- 解析成功 --> D
    D --> E{"background_enabled<br/>= draw_background_enabled 且 image_service 非空"}
    E -- 否 --> E1["ok=false：后台绘图未启用或服务未配置"]
    E -- 是 --> F{"_get_active_task(pipeline_key) 有 status=drawing?"}
    F -- 有 --> F1["ok=true status=busy + existing_task_id + 委托者/绘图要求"]
    F -- 无 --> G{"check_cooldown(pipeline_key) > 0?"}
    G -- 是 --> G1["ok=true status=cooldown + remaining_seconds"]
    G -- 否 --> H["建 DrawTask：task_id=draw_<uuid4 hex12>，status 默认 drawing"]
    H --> I["_enforce_task_limit：按 created_at 升序销毁非活跃旧任务"]
    I --> J["_set_cooldown：monotonic_seconds() + draw_cooldown_seconds(60)"]
    J --> K["_spawn_bg_task(_run_draw)，任务句柄进 _bg_tasks"]
    K --> L["await asyncio.sleep(min(startup_grace_seconds, 3.0))"]
    L --> M{"睡眠结束时 task.status == failed?"}
    M -- 是 --> M1["cancel_cooldown + ok=false + task.error"]
    M -- 否 --> M2["ok=true status=drawing + model/references + task_id"]
```

要点：`provider` 在工具层**先校验后提交**，未知取值不会白跑一次任务并吃掉冷却（注释就写在
`drawing_skill.py:370`）。宽限期是「启动期失败不占冷却」的窗口，代码把配置值再夹到 3.0 秒，
所以 `startup_grace_seconds` 配大于 3 也不会有更长窗口；宽限期失败直接回
`{"ok": false, "error": ...}`（`manager.py:263-265`）。`min(grace, 3.0)` 是提交路径上唯一的等待，
它**不保证**绘图已经开始——生图 HTTP 在后台协程里。
</details>

<details>
### 并发、容量、超时与取消：四个「没有」

```mermaid
flowchart TD
    A["提交并发上限 / manager.py:99"] --> A1["每管线：_get_active_task 只认 status=drawing → 同时最多 1 个"]
    A1 --> A2["跨管线：无全局信号量、无并发上限，N 个会话可同时打生图 API"]
    A2 --> A3["忙时不排队：submit 直接回 busy，任务根本不创建"]
    A3 --> B["保留容量 / manager.py:106"]
    B --> B1["draw_max_tasks_per_pipeline=20；按 created_at 升序删非活跃任务"]
    B1 --> B2["status=drawing 的任务永不被删；limit<=0 时函数直接 return"]
    B2 --> C["超时：任务级没有超时，只有 HTTP/IO 超时"]
    C --> C1["每个模型一个 AsyncClient：timeout=settings.timeout_seconds，connect=min(timeout,10)"]
    C1 --> C2["Adapter call_api / send / media_sender：asyncio.wait_for 30s"]
    C2 --> C3["_parse_local_image 视觉描述：asyncio.wait_for 60s"]
    C3 --> C4["远端图片下载：_read_limited 上限 100 MiB，无总时长预算"]
    C4 --> D["取消：没有接口能取消在途绘图"]
    D --> D1["可取消的只有冷却：cancel_draw_cooldown / cancel_task(drawing_cooldown)"]
    D1 --> D2["shutdown()：drawing 任务改 timeout + bg_task.cancel + gather(return_exceptions=True)"]
    D2 --> D3["shutdown 不清 _tasks（只清 _bg_tasks 与 _notification_queues）"]
```

`_tasks` 是**内存字典**：进程重启即全部丢失，没有任何持久化（`DrawTask` 不落库）。
因此 `check_last_drawing` 在重启后必然回 `found=false`。`shutdown()` 由
`runtime/application.py:243/465` 与 `orchestrator.py:950` 挂进停机/回滚步骤。
</details>

<details>
### 参数组装：payload 的每个字段从哪里来

```mermaid
flowchart TD
    A["generate_image / service.py:419"] --> B["prompt.strip()；空 → ValueError"]
    B --> C["resolve_model_name(model) → 注册名；_client_for 取模型与 AsyncClient"]
    C --> D["payload = {model: registered.model_name, prompt, image_size}"]
    D --> E["payload.update(registered.settings.extra_body or {})"]
    E --> F{"negative_prompt 非空?"}
    F -- 是 --> F1["payload[negative_prompt]"]
    F -- 否 --> G{"seed is not None?"}
    F1 --> G
    G -- 是 --> G1["payload[seed]"]
    G -- 否 --> H["image_size 缺省 DEFAULT_IMAGE_SIZE=512x512 / config.py:15"]
    G1 --> H
    H --> I["参考图解析 → resolved_data_urls"]
    I --> J["image_api = settings.image_api 规范化，非法值回落 auto"]
    J --> K["reference_param = settings.image_reference_param 或 image"]
    K --> L["manager 落盘时 image_source = <requester>要求<requirements> / manager.py:290"]
```

工具面只暴露 `prompt / negative_prompt / image_size / reference_id / references / seed /
requester / requirements / provider`（`drawing_skill.py:157-182`），风格与尺寸都靠 `image_size`
字符串与提示词表达，没有独立的 style 字段。`extra_body` 是模型级兜底：会被**展开进顶层**，
所以配置里能覆盖 `model` 之外的任意键。
</details>

<details>
### 参考图解析：一个数字、七种前缀、两条兜底

```mermaid
flowchart TD
    A["generate_image：reference_id 与 references"] --> B{"reference_id 非 None?"}
    B -- 是 --> B1["_get_reference_by_gallery_no；查不到抛 LookupError 图库编号不存在"]
    B1 --> B2["_image_data_url(file_path, mime_type)"]
    B -- 否 --> C["逐项 _resolve_reference(ref, conv_id) / service.py:1587"]
    C --> D{"裸数字 > 0?"}
    D -- 是 --> D1["按图库固定编号 gallery_no 取图（不看列表顺序）"]
    D -- 否 --> E{"含冒号前缀?"}
    E --> E1["gallery/g/image/img：数字按编号，其余按 image_id"]
    E --> E2["pool：image_pool.get(conv_id, key)；未配置 RuntimeError，缺 conv_id ValueError"]
    E --> E3["e/emoji：EmojiService.get_entry 编号 → data URL"]
    E --> E4["url：validate_public_url_async 必须公网，否则 ValueError"]
    E --> E5["file：_resolve_creator_path 必须落在 data/creator 内，越界 PermissionError"]
    E --> E6["chat：msg:idx 走 get_msg → base64，固定包成 image/png"]
    E --> F{"裸 http(s):// ?"}
    F -- 是 --> F1["_download_as_data_url：SSRF 校验 + 100 MiB 上限"]
    F -- 否 --> F2["按 image_id 查库；查不到抛 LookupError 并列出全部可接受格式"]
```

前缀解析与 `resolve_source_to_path`（`service.py:1673`，供图片暂存池 `put` 用）是**两套独立实现**：
前者产出 data URL、后者产出本地路径，能接受的前缀集合不同（后者没有 `pool`/`image` 别名，
`url:` 分支会落盘到 `creator/tmp/pool_url_<md5前12>.<ext>`）。
</details>

<details>
### /images/edits 还是 /images/generations：分派、字段名与回退

```mermaid
flowchart TD
    A["references 解析出 resolved_data_urls"] --> B{"image_api 是 auto 或 edits?"}
    B -- 否 --> G["POST /images/generations（JSON）"]
    B -- 是 --> C{"每张参考图都是 base64 data URL?"}
    C -- 否 --> G
    C -- 是 --> C1["_post_edits → POST /images/edits（multipart）"]
    C1 --> C2["data：model/prompt/size=image_size；其余标量透传，非标量 json.dumps"]
    C2 --> C3["files：单张字段 image，多张重复 image[]，文件名 reference_N + 扩展名"]
    C3 --> D{"响应 status 是 400/404/405?"}
    D -- 否 --> H["交给统一出口 raise_for_status + _extract_image_bytes"]
    D -- 是 --> E{"image_api == edits 显式指定?"}
    E -- 是 --> H
    E -- 否 --> G
    G --> G1["参考图字段用 reference_param；长度>1 或以 s 结尾 → 数组，否则单个字符串"]
    G1 --> H
```

`edits` 用 `size`、`generations` 用 `image_size`——两个端点参数名不同，这是有意为之（中转站
普遍只认 `image_size`）。回退只覆盖 400/404/405：`401/403/429/5xx` 一律不重试、直接抛
`ImageGenerationError`，错误体里带 `response_body` 供 agent 诊断。
</details>

<details>
### 失败分级：抛什么、怎么序列化、谁重试

```mermaid
flowchart TD
    A["generate_image / process_image 抛出"] --> B{"异常类型"}
    B -- ValueError --> B1["prompt 为空 / 下载超限 / 图库重复哈希 / 非法 operation"]
    B -- LookupError --> B2["图库编号或 image_id 不存在 / 本地引用不可解析 / 图片段无图"]
    B -- PermissionError --> B3["file: 越界 / 表情包增删被配置禁止"]
    B -- ImageGenerationError --> B4["HTTP 状态码错误或响应体解析失败，带 error_info"]
    B -- httpx 或 TimeoutError --> B5["连接失败、读超时、代理错误"]
    B --> C["_run_draw except Exception / manager.py:311"]
    C --> C1["task.status=failed"]
    C1 --> C2["_serialize_draw_error：ImageGenerationError 直接 str(JSON)"]
    C2 --> C3["其余：error_type+message；HTTPStatusError 追加 status_code/response_body/request_url"]
    C3 --> C4["cancel_cooldown(pipeline_key)：失败一定释放冷却"]
    C4 --> C5["_on_failed → 通知；绝不自动重提绘图"]
    C5 --> D["重试只发生在通知层：max_attempts = draw_max_retries + 1"]
    D --> D1["30s 后队列空才补一条 draw_result_retry（attempt=1）"]
    D1 --> D2["再 30s 仍未被 poll：status=timeout + draw_result_timeout 通知"]
```

文件级失败语义对照：**抛异常**＝上表；**降级**＝`image_api` 非法值回落 `auto`、`edits` 404 回退
`generations`（400/404/405）、无视觉模型时描述写占位符；**丢弃**＝hub 队列满时丢最旧通知、超限时删最旧非活跃
任务；**重试**＝只有通知层有重试。
</details>

<details>
### 结果落盘、命名与描述：tmp_xxx / g_xxx 与 .txt 伴生文件

```mermaid
flowchart TD
    A["_save_image_bytes / service.py:1220"] --> B{"source != tmp?"}
    B -- 是 --> B1["sha256 → get_by_hash；命中即 ValueError 拒绝重复入库"]
    B -- 否 --> C
    B1 --> C["image_id = tmp_<uuid4 hex12> 或 g_<uuid4 hex12>"]
    C --> D["_detect_suffix：JPEG/PNG/WEBP 魔数，其余回落 png"]
    D --> E["目录 tmp → data/creator/tmp，gallery → data/creator/gallery；写字节"]
    E --> F["_upsert_record：mimetypes 猜 mime + PIL 读原图宽高"]
    F --> G["_resolve_description：四层回退"]
    G --> H["显式描述非空 → 直接写同名 .txt"]
    G --> H1["读 sidecar .txt"]
    H1 --> H2["读数据库已有 description 并回写 .txt"]
    H2 --> H3["_parse_local_image 视觉描述；无视觉模型写 [未配置视觉模型]，异常写 [解析失败]"]
    H3 --> I["_allocate_gallery_no：仅 gallery 源分配，已有编号复用不重签"]
    I --> J["uow.commit → CreatorImageRecord(image_id/source/file_path/...) "]
```

`_record_payload`（`service.py:1918`）决定回执字段：`image_id/source/file_path/prompt/
description/mime_type/width/height`；`description` 在 DB 为空时会现读 .txt。图库编号是
**高水位消耗品**：删除与重命名都不回填，编号只增不复用（`_allocate_gallery_no` 注释）。
`gallery_rename` 会连带改 .txt，DB 改名失败时把文件改回去（`service.py:846-854`）。
</details>

<details>
### 清理策略：12 小时过期、哈希去重、停机清空 tmp

```mermaid
flowchart TD
    A["_start_cleanup_task / service.py:327"] --> A1["自动入口只有 list_images / count_images 懒启动；start() 全仓无调用点"]
    A1 --> B["_cleanup_loop：每 6h 一轮，异常只记 error 不退出循环"]
    B --> B1["_cleanup_stale_records：tmp/gallery 目录内按哈希去重，保留 mtime 最新"]
    B1 --> B2["删旧文件 + 同名 .txt；不删 keeper"]
    B2 --> B3["数据库记录：文件在但路径变了 → rename；文件不在但磁盘有同 resolved 路径 → rename；否则 delete"]
    B3 --> C["_sync_image_sidecars：磁盘上没记录的图片补登记，image_source=部署者提供并分配编号"]
    C --> D["_cleanup_expired_tmp_files：cutoff = now - 12h，按 mtime 判过期"]
    D --> D1["文件不存在时 mtime 记 0.0 → 视为过期，只删记录"]
    D1 --> D2["删文件 + .txt + delete(image_id)，最后 commit"]
    D2 --> E["close()：停清理任务 → cleanup_tmp 清空 tmp 全部文件 + delete_by_source(tmp)"]
```

常量在 `service.py:88-89`：`_CLEANUP_INTERVAL_SECONDS = 6*3600`、`_TMP_MAX_AGE_SECONDS = 12*3600`。
手工往 `creator/tmp` 或 `creator/gallery` 目录丢图后，靠 `_sync_image_sidecars` 补登记：
它会给没有记录的图片生成 `g_xxx`/`tmp_xxx` 记录、写 .txt 描述并分配图库编号
（`_cleanup_stale_records` 只处理已有记录，不做磁盘扫描登记）。
</details>

<details>
### 多模型分派：注册名、客户端与选择解析

```mermaid
flowchart TD
    A["bootstrap：agent.creator.enabled=True 才建服务 / bootstrap/__init__.py:865"] --> B["model_names = models.creator_image_model_names = assignments.image_keys()"]
    B --> C{"model_names 为空?"}
    C -- 是 --> C1["ValueError：至少需要一个生图模型注册名（构造即失败）"]
    C -- 否 --> D["逐个 get_registered_model(key)：缺 key 抛 ValidationError"]
    D --> E["默认模型 = 列表第一个；default_model_name 只读"]
    E --> F["每模型一个 httpx.AsyncClient：base_url 去尾斜杠 + Authorization Bearer + 自身超时"]
    F --> G["trust_env = model.use_system_proxy：False 时忽略系统代理"]
    G --> H["resolve_model_name 顺序：同名 → 纯数字当序号 → 描述/供应商/模型名全等 → 子串 → ValueError"]
    H --> I["available_models() → 工具面 provider 枚举；只有 1 个模型时不生成该参数"]
    I --> J["creator_image_models 只在 creator 启用时注册进全局 registry / loader/manager.py:320"]
```

`null`（未指定）与空串都解析为默认模型；**纯数字是 0 基序号**，不是图库编号——同一串数字
在 `references` 里是图库编号、在 `provider` 里是序号，这是最容易读错的一处。
`manager.resolve_model_name` 只是转调 `service.resolve_model_name`（服务未注入时返回空串）。
</details>

<details>
### 通知投递与工具面回执：从 image_id 到用户看到图

```mermaid
flowchart TD
    A["_on_completed / _on_failed / manager.py:423"] --> B{"task.image_id 非空?"}
    B -- 空 --> B1["转 failed：绘图完成但未获取到图片ID"]
    B -- 非空 --> C["_notification_payload：JSON 化 ok/kind/status/task_id/message + record_payload + next"]
    B1 --> C
    C --> D{"notification_hub 非空?"}
    D -- 是 --> D1["hub.publish(source=drawing, on_consumed=_mark_notified)"]
    D1 --> D2{"hub 立刻起了新管线?"}
    D2 -- 是 --> D3["_consume 触发回调 → 该管线非活跃任务 notified=True"]
    D2 -- 否 --> D4["入 hub 队列（上限 100，满则丢最旧）+ 启动通知重试定时器"]
    D -- 否 --> E{"orchestrator.is_pipeline_key_active?"}
    E -- 否 --> E1["start_background_reply 成功 → notified=True"]
    E -- 是 --> E2["入 _notification_queues 本地 asyncio.Queue"]
    E1 -- 失败 --> E2
    D4 --> F["orchestrator 轮询：注入 role=user 通知 + hub 镜像的消息队列条目"]
    E2 --> F
    D3 --> F
    F --> G["next：reply_to_user / send_image(image_send__send_image) / gallery__gallery_add 可选"]
    G --> H["发送后 ReplySender 把本地图片登记成 tmp_xxx 索引，模型可再取回查看"]
```

`next` 里的工具名与参数是**给模型照抄的**（`manager.py:372-414`）：群聊填 `group_id`、私聊填
`user_id`，两者都取自 `task.conversation_id`；失败分支明确写了「不要在未询问用户的情况下
自动重新提交绘图」。主模型侧还有两个查询口：`check_background_tasks` 合并
`get_pipeline_status`（冷却 + 活跃任务 + 最近 5 条），`check_last_drawing` 走 `get_last_draw_info`
（只回最近一条非 drawing 任务，含 `record_payload` 与错误）。
</details>

<details>
### 安全、成本与观测：密钥从哪来、什么完全没记录

```mermaid
flowchart TD
    A["密钥来源：RegisteredModel.api_key（.env → EnvConfig），只进 AsyncClient 请求头"] --> A1["日志只记 status 与 body[:500]，Authorization 永不落日志"]
    A1 --> B["用户可控 URL 用 _public_client：无凭据，防 API Key 外发"]
    B --> B1["url: 前缀与裸 http(s) 走 validate_public_url_async，非公网直接拒绝"]
    B1 --> B2["chat 图片段 URL 不查 SSRF，只用 is_local_or_private_url 决定是否绕过系统代理"]
    B2 --> C["file:// 与裸本地路径：looks_like_image 内容校验 + 100 MiB 上限"]
    C --> C1["file: 参考图必须落在 data/creator 内，越界 PermissionError"]
    C1 --> D["表情包增删受 allow_emoji_add / allow_emoji_delete 控制，关闭即 PermissionError"]
    D --> E["成本：drawing 目录内 0 处 usage/billing/cost 写入"]
    E --> E1["生图是裸 httpx，不经过 chat Provider，因此绕开 23 的用量统计"]
    E1 --> E2["图库自动描述走 vision_provider.chat，也没有 record；agent:image_parse 是合法模块名却无写入点"]
    E2 --> F["历史事故：scripts/test_drawing_*.py 曾硬编码密钥，已从远端历史清除"]
    F --> F1[".githooks/pre-push 与 CI hygiene job 拒绝这些文件重新入库"]
```

观测点（排查第一手线索）：日志 logger 名 `app.creator_image` / `app.drawing`；关键事件
「生图接口返回错误状态码」「生图接口返回数据解析失败」「后台绘图任务失败」「推送绘图完成通知」
「绘图通知超时」「后台绘图任务超出上限已自动销毁」「creator 过期临时图片已清理」。
任务回执里的 `error` 字段就是 `_serialize_draw_error` 的 JSON 字符串。
</details>

## 关键状态

| 状态 / 字段 | 谁置位 | 谁清理 | 失败时停在哪 |
|---|---|---|---|
| `DrawTask.status` = drawing | `submit` 建任务时默认值 | `_run_draw` 改 completed/failed；`shutdown` 与通知重试改 timeout | 卡在 `drawing` 只可能是进程在途或已崩溃；无任务级超时兜底 |
| `DrawTask.status` = completed | `_run_draw` 拿到 record 后 | 无（任务只是记录） | `image_id` 为空会被 `_on_completed` 改回 failed |
| `DrawTask.status` = failed | `_run_draw` except 分支 | 无 | error 是 JSON 字符串，最终随通知交给模型 |
| `DrawTask.status` = timeout | `_retry_notification` 结束仍未被 poll；`shutdown()` 对在途任务 | 无 | 通知链路失败停在这里；图片其实已生成 |
| `DrawTask.notified` / `notification_count` | `_mark_notified`（轮询取出或 hub 消费回调）；重试循环自增 | 随任务被 `_enforce_task_limit` 删除而消失 | 到达 `max_attempts` 仍未 notified → timeout |
| `_cooldowns[pipeline_key]` | `submit` 里 `_set_cooldown`（提交前） | `cancel_cooldown`：宽限期失败、`_run_draw` 失败、`cancel_draw_cooldown`、自愈钩子、`shutdown` | 成功后**不清理**，靠 60s 自然到期 |
| `_tasks` / `_bg_tasks` / `_notification_queues` | `submit` / `_spawn_bg_task` / `_push_notification` | `_enforce_task_limit`、`shutdown`（后两者整体清空） | 内存态，重启即丢；无持久化 |
| `creator_images` 行 + 磁盘文件 | `_save_image_bytes` → `_upsert_record` | `gallery_delete`、`_cleanup_expired_tmp_files`、`_cleanup_stale_records`、`cleanup_tmp` | 文件缺失的记录在下一轮清理被删；`_list_image_records` / `_search_single` 已先按 `is_file()` 过滤 |
| `creator_images.gallery_no` | `_allocate_gallery_no`（仅 gallery 源，高水位 +1） | 删除记录后**不回填**，编号留空洞 | 引用失效编号 → `LookupError 图库编号不存在` |
| 同名 `.txt` 伴生描述 | `_resolve_description` / `_sync_image_sidecars` | 随图片删除（unlink + with_suffix） | 写入的是占位符时，之后会被当成正式描述读回 |
| hub 通知队列 | `hub.publish` | `hub.poll`；空闲 1800s 惰性清理；满 100 丢最旧 | 无活跃管线且启动失败 → 留在队列等轮询 + 通知重试 |

## 易错点

1. **busy 不是排队**：`submit` 在管线已有 `drawing` 任务时直接回 `status=busy`，不创建任务、
   不进任何队列，冷却也不刷新。模型必须自己稍后再提交。
2. **`draw_max_retries` 重试的是通知不是绘图**：默认 1 → 首次通知后 30s 补一条
   `draw_result_retry`，再 30s 置 `timeout` 并发 `draw_result_timeout`。绘图失败从不自动重提。
3. **默认尺寸对不上文档**：`DEFAULT_IMAGE_SIZE="512x512"`（`config.py:15`），而工具提示词写
   「未指定时默认 1024x1024」（`skills/drawing_skill.py:102`）。调模型别信提示词这一句。
4. **冷却先设后跑**：`_set_cooldown` 在启动后台任务之前执行；失败会在两处被清（宽限期分支
   与 `_run_draw` 的 except），但**成功**保留满 60s。用户问「刚画完为什么不能再画」时看这里。
5. **hub 存在时 manager 的队列与 `poll_notification` 不可达**：bootstrap 无条件建 hub，
   orchestrator 命中 hub 分支即返回。排障要看 `BackgroundNotificationHub` 的队列与
   `on_consumed` 回调，而不是 `_notification_queues`。
6. **哈希去重会真删文件**：`_cleanup_stale_records` 在同一目录内按哈希保留 mtime 最新者，
   删掉其余文件与记录。手工复制过图片的部署会在 6h 后「少图」。
7. **占位描述会被持久化**：无视觉模型时写 `[未配置视觉模型]`、描述失败写 `[解析失败]`，
   都落进 `.txt`；而 `_read_sidecar_description` 优先读该文件，于是占位符变成正式描述。
8. **`close()` 清空 tmp**：正常停机后所有 `tmp_xxx` 文件与记录消失，历史消息里的
   `tmp_xxx` 引用失效（`file:` 退化路径还可能越出 `data/creator` 被 `PermissionError` 拒）。
9. **清理循环是懒启动的**：`CreatorImageService.start()` 全仓无调用点，6h 循环只在第一次
   `list_images`/`count_images` 后才启动；纯生图不列图库的部署只有停机时清 tmp。
10. **图库容量是 check-then-act**：`_ensure_gallery_capacity` 先 `count` 再写，并发导入可越过
    `gallery.capacity`（默认 10）；`gallery_add` 本身也不做哈希查重（只有 `_save_image_bytes`
    对非 tmp 源查重），同一张图可以先 `gallery_add` 再 `import_chat_image` 成两份。
11. **显式 `image_api=edits` 时没有回退**：400/404/405 直接 `raise_for_status` 报错；只有
    `auto` 才回退 `generations`。中转站不认 `/images/edits` 时改配置而不是改代码。
12. **绘图调试脚本禁止硬编码密钥**：`scripts/test_drawing_*.py`、`scripts/test_image_reference.py`
    曾带硬编码密钥，2026-09-11 已从远端历史彻底清除（force-push 重写）；
    `.githooks/pre-push` 与 CI hygiene job 会拒绝这些文件名重新入库。密钥唯一来源是
    `RegisteredModel.api_key`（`.env → EnvConfig`，SPLIT-MAP W59：`credentials/` 不是密钥仓库）。
13. **生图与图库自动描述都不计费**：本目录零处 `usage/billing/cost`；生图走裸 httpx 绕过
    chat Provider，`_parse_local_image` 虽走 `vision_provider.chat` 也没有 `record()`。
    `statistics/tracker.py:29` 的 `agent:image_parse` 是**没有写入点的合法模块名**，
    别把它当成已有的统计口径。
14. **面板看不到后台绘图**：`dashboard/api.py:788` 用 `getattr(drawing_manager, "list_active")`
    探测，而 `BackgroundDrawingManager` 没有这个方法 → `payload["background"]` 静默为空
    （相邻图 09b 的范围，改动时记得同步）。
