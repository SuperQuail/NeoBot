---
flow: 22-storage-migrations
covers:
  - packages/storage/src/neobot_storage/
verified_against: 99836cd
verified_hash: 7c6d43b94868
---

# 22 存储与迁移

## 范围

`neobot_storage` 包（32 个 py 文件）：异步引擎与 PRAGMA、UoW 事务边界、15 张表、
27 个 Alembic 迁移、仓储层与锁重试。所有上层（档案、画像、用量、定时任务、头像）
都通过它读写 SQLite。

不在这里：档案的业务语义见 `07` / `07b`；用量与计费见 `23-billing-stats.md`；
头像三列的业务含义见 `20-avatar-files.md`。

## 流程

```mermaid
flowchart TD
    A["bootstrap: sqlite_url(DATA_DIR/neobot.db)"] --> B["create_engine(db_url)"]
    B --> C["_enable_wal_if_sqlite: PRAGMA journal_mode=WAL + busy_timeout=5000"]
    C --> D["run_migrations 走到最新版本"]
    D --> E{"迁移失败?"}
    E -- 是 --> F["启动失败（迁移前留可回滚快照）"]
    E -- 否 --> G["async_sessionmaker"]
    G --> H["业务: async with uow:"]
    H --> I["__aenter__ 建 session + 绑定各仓储"]
    I --> J["仓储方法执行语句"]
    J --> K["commit()：锁冲突显式失败"]
    K --> L{"database is locked?"}
    L -- 是 --> M["retry_on_lock **重放整个事务体**"]
    L -- 否 --> N["提交成功"]
    M --> H
    H --> O["__aexit__：异常则 rollback，然后 close"]
```

## 时序

```mermaid
sequenceDiagram
    autonumber
    participant BS as bootstrap
    participant EN as create_engine
    participant AL as alembic
    participant UOW as SqlAlchemyUnitOfWork
    participant DB as SQLite

    BS->>EN: create_engine(sqlite_url)
    EN->>DB: PRAGMA journal_mode=WAL
    EN->>DB: PRAGMA busy_timeout=5000
    BS->>AL: run_migrations(db_url)
    AL->>DB: 逐个版本 upgrade
    BS->>UOW: 构造工厂（make_uow_factory）
    UOW->>DB: 开启事务
    UOW->>DB: 仓储语句
    alt 提交撞锁
        UOW-->>UOW: commit 抛错（不自动重试）
        Note over UOW: 调用方用 retry_on_lock 重放整个事务体
    else 正常
        UOW->>DB: COMMIT
    end
```

## 细节

<details>
### 引擎：两个 PRAGMA 决定并发行为

```mermaid
flowchart TD
    A["create_engine(db_url)"] --> B{"后端是 sqlite?"}
    B -- 否 --> C["原样返回引擎"]
    B -- 是 --> D["注册 connect 事件"]
    D --> E["PRAGMA journal_mode=WAL"]
    D --> F["PRAGMA busy_timeout=5000"]
    E --> G{"执行失败?"}
    F --> G
    G -- 是 --> H["静默忽略（pass）"]
    G -- 否 --> I["生效"]
```

**WAL** 让「读不阻塞写」，**busy_timeout=5000** 让撞锁时最多等 5 秒再报错
（`engine.py:25-41`）。两个 PRAGMA 都包在 `try/except: pass` 里 ——
失败**不会**导致启动失败，表现为「偶发 database is locked」而不是「起不来」。
</details>

<details>
### UoW：进入即绑定仓储，退出必关会话

```mermaid
flowchart TD
    A["async with uow"] --> B["__aenter__: session = factory()"]
    B --> C["绑定 9 个仓储：messages/memories/profiles/archive/<br/>archive_snapshots/images/emojis/creator_images/scheduled_tasks"]
    C --> D["业务代码用 uow.xxx.method()"]
    D --> E["__aexit__(exc)"]
    E --> F{"有异常?"}
    F -- 是 --> G["rollback()"]
    F -- 否 --> H["不 rollback"]
    G --> I["session.close()"]
    H --> I
```

仓储**按需绑定**在 `__aenter__`（`uow.py:27-38`），一次进入拿到全部 9 个入口。
`__aexit__` 只在有异常时 `rollback`，两种情况都会 `close`（`:40-43`）——
漏掉 `async with` 手工管理 session 会泄漏连接。
</details>

<details>
### commit 的锁语义：为什么不允许「rollback 后重试 commit」

```mermaid
flowchart TD
    A["commit()"] --> B["session.commit()"]
    B --> C{"抛 database is locked?"}
    C -- 否 --> D["成功"]
    C -- 是 --> E["显式失败，向上抛"]
    E --> F["调用方 retry_on_lock 重放**整个事务体**"]
    F --> G["重新 __aenter__ + 重新执行语句 + commit"]
    H["错误做法：rollback 后重试 commit()"] --> I["已发往 DB 的 Core DML 随事务一起丢失"]
    I --> J["commit 返回成功但写入静默丢失"]
```

`uow.py:45-52` 的 docstring 是这条规则的**唯一权威说明**：仓库层大量使用
`session.execute(insert(...))`（Core DML，不经 ORM 身份映射），
所以「rollback 后重试 commit」会静默丢写。
正确用法见 `statistics/tracker.py`（把整个事务体放进 `retry_on_lock` 的工厂函数里）。
</details>

<details>
### 锁重试：异常链匹配与退避

```mermaid
flowchart TD
    A["retry_on_lock(coro_factory, max_retries=3,<br/>base_delay=0.1, max_delay=2.0)"] --> B["调用 coro_factory()"]
    B --> C{"成功?"}
    C -- 是 --> D["返回结果"]
    C -- 否 --> E["_is_locked_error(exc)"]
    E --> F["_iter_exception_chain 沿 __cause__/__context__ 找"]
    F --> G{"链上任意一环含 locked 关键词?"}
    G -- 否 --> H["原样抛（不重试）"]
    G -- 是 --> I{"重试次数未用尽?"}
    I -- 否 --> J["抛出最后一次异常"]
    I -- 是 --> K["退避后重试（最多 max_delay 封顶）"]
    K --> B
```

匹配关键词是 `database is locked` / `database table is locked` / `locking protocol` / `deadlock`
（`_retry.py:11-17`）。**沿异常链匹配**是为了覆盖 `PendingRollbackError` 把原始 flush 异常
嵌在 message 里的情况（注释明确写了），同时避免对含 "rolled back" 的普通错误过度匹配。
</details>

<details>
### 15 张表与谁在写

```mermaid
flowchart LR
    subgraph 身份与消息
      T1["user_data"] --> W1["18 画像 / 20 头像"]
      T2["group_data"] --> W2["18 群资料"]
      T3["message_data"] --> W3["02c 消息落盘"]
      T4["event_data"] --> W4["事件记录"]
    end
    subgraph 记忆与档案
      T5["memory_data"] --> W5["07 记忆"]
      T6["archive_memories"] --> W6["07 档案"]
      T7["archive_snapshots"] --> W7["07b 压缩快照"]
    end
    subgraph 多媒体
      T8["images"] --> W8["14 图像解析"]
      T9["emojis"] --> W9["14 表情包"]
      T10["creator_images / creator_image_sequences"] --> W10["15 绘画"]
    end
    subgraph 任务与用量
      T11["scheduled_tasks / completed_scheduled_tasks"] --> W11["16 定时任务"]
      T12["model_usage_records"] --> W12["23 计费统计"]
      T13["maintenance_runs"] --> W13["沙箱维护（06）"]
    end
```

表名全部**小写复数**（迁移 `0002_lowercase_table_names` 统一过）。
`completed_scheduled_tasks` 上有 `task_uuid` 唯一约束（迁移 0021）——
这是「同一任务不会被重复标记完成」的数据库级保证（见 `16` 的去重）。
</details>

<details>
### 迁移链：27 个版本与不可逆操作

```mermaid
flowchart TD
    A["0001_initial_schema"] --> B["0002_lowercase_table_names"]
    B --> C["0003 archive_memories / 0004 images / 0005 profile_refresh"]
    C --> D["0006 emojis / 0007 creator_images / 0008 avatar_analysis"]
    D --> E["0009 emoji_use_count / 0010 favorability / 0011 image_source"]
    E --> F["0012 scheduled_tasks"]
    F --> G["0017 model_usage_records / 0018 cost_usd->cny"]
    G --> H["0019 cache_hit_tokens / 0020 bilibili_links"]
    H --> I["0021 unique task_uuid（含去重 DELETE，不可逆）"]
    I --> J["0022 maintenance_runs / 0023 gallery_no / 0024 sequences"]
    J --> K["0025 usage_cost_source / 0026 archive_snapshots / 0027 avatar_storage"]
```

两个要注意的点：

1. **编号有跳号**（0013-0016 不存在）：这是历史合并的结果，不要以为是文件丢失；
2. **存在不可逆迁移**（如 0021 里的去重 DELETE）——所以 bootstrap 在迁移前会留一份可回滚快照，
   失败时能人工恢复而不是只剩半个 schema。
</details>

<details>
### 备份与恢复入口

```mermaid
flowchart TD
    A["backup.py"] --> B["迁移前快照"]
    B --> C["失败时可人工恢复"]
    D["app/src/neobot_app/database/"] --> E["连接/初始化辅助"]
    E --> F["与 storage 包的分工：<br/>包内管 schema 与仓储，app 侧管生命周期接线"]
```

改 schema 的标准动作：**加迁移文件 -> 本地先跑一遍 -> 确认能升级也能回滚**。
直接改 `models.py` 而忘了迁移，表现为「新库正常、老库启动报缺列」。
</details>

## 关键状态

| 状态 | 谁置位 | 谁清理 | 失败时停在哪 |
|---|---|---|---|
| 引擎 PRAGMA | 引擎首次连接（connect 事件） | 连接关闭 | 执行失败被静默忽略，不阻断启动 |
| 会话 | `__aenter__` 创建 | `__aexit__` 关闭 | 异常路径先 rollback 再 close |
| 事务 | 仓储语句执行中 | `commit` / `rollback` | 锁冲突显式失败，由调用方重放整个事务体 |
| 迁移版本 | `run_migrations` | 不回退（除非人工） | 迁移失败 -> 启动失败（迁移前有快照） |
| 完成标记唯一性 | 迁移 0021 的唯一约束 | 约束长期有效 | 重复标记被数据库拒绝 |

## 易错点

* **不要「rollback 后重试 commit」**：会静默丢 Core DML 写入，必须重放整个事务体（`uow.py:45`）。
* **两个 PRAGMA 失败是静默的**：偶发 `database is locked` 而不是启动失败，排查时容易漏。
* **改 `models.py` 必须配迁移**：老库不会自动加列，表现为启动报缺列。
* **迁移编号有跳号（0013-0016 缺失）**：历史合并的结果，不是文件丢失。
* **存在不可逆迁移**：迁移前快照是唯一回退手段，别删它。
* **`async with uow` 是必须的**：手工管理 session 容易泄漏连接。
