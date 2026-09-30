---
flow: 18-user-profiles
covers:
  - app/src/neobot_app/user_profiles.py
  - app/src/neobot_app/favorability.py
verified_against: 08faa3f
verified_hash: c1da25b84be6
---

# 18 用户画像与好感度

## 范围

`UserProfileService`（871 行）与 `favorability`（52 行）：
用户/群资料的获取与刷新、QQ 资料段的拼装、群成员列表渲染、好感度的读写与钳制。
不在这里：档案（archive memory）本身的读写与压缩见 `07` / `07b`；
面板的档案页见 `09b`；头像存储见 `20-avatar-files.md`。

## 流程

```mermaid
flowchart TD
    A["事件管道: 命中用户相关能力"] --> B["ensure_user_profile(user_id)"]
    B --> C{"库里已有?"}
    C -- 否 --> D["_refresh_user_profile 调 adapter 拉资料"]
    C -- 是 --> E{"_needs_refresh?"}
    E -- 是 --> F["刷新（带依赖超时）"]
    E -- 否 --> G["直接用缓存"]
    D --> H["_merge_observed_fields 合并观测到的字段"]
    F --> H
    G --> I["_build_user_fields"]
    H --> I
    I --> J["_build_qq_profile_segment 拼资料段"]
    J --> K["提示词侧使用（24）"]
    L["好感度变更请求"] --> M["update_favorability / update_user_favorability"]
    M --> N["clamp_favorability 钳制到 -1000..1000"]
    N --> O{"重试次数用尽?"}
    O -- 是 --> P["_FAVORABILITY_UPDATE_ATTEMPTS=12 次后放弃"]
    O -- 否 --> Q["写库"]
```

## 时序

```mermaid
sequenceDiagram
    autonumber
    participant EP as EventPipeline
    participant UPS as UserProfileService
    participant AD as adapter(QQ)
    participant DB as SQLite
    participant PB as PromptBuilder

    EP->>UPS: ensure_user_profile(user_id)
    UPS->>DB: 查 user_data
    alt 缺失或过期
        UPS->>AD: 拉取用户资料（带依赖超时）
        AD-->>UPS: 资料或失败
        UPS->>DB: 合并写入
    end
    PB->>UPS: render_group_member_list / render_friend_info
    UPS-->>PB: 文本段
    EP->>UPS: update_favorability(delta)
    UPS->>UPS: clamp 到 -1000..1000
    UPS->>DB: 写入（最多重试 12 次）
```

## 细节

<details>
### 资料获取：缺则拉、旧则刷

```mermaid
flowchart TD
    A["ensure_user_profile(user_id)"] --> B["get_user 查库"]
    B --> C{"有记录?"}
    C -- 否 --> D["_refresh_user_profile"]
    C -- 是 --> E["_needs_refresh(profile)"]
    E -- 是 --> D
    E -- 否 --> F["直接返回"]
    D --> G["_adapter_call 带依赖超时"]
    G --> H{"调用成功?"}
    H -- 否 --> I["记日志，保留旧资料"]
    H -- 是 --> J["_merge_observed_fields 合并"]
    J --> K["写库"]
```

`_adapter_call`（`user_profiles.py:63`）是**统一的依赖调用包装**：加超时、记日志、失败不抛。
`_needs_refresh`（`:575`）决定什么时候重新拉 —— 它只看资料里的时间戳字段。
拉取失败时**保留旧资料**（不清空），所以「资料是旧的」通常意味着 adapter 一直在失败。
</details>

<details>
### 群成员列表：从队列观测 + 按需刷新

```mermaid
flowchart TD
    A["render_group_member_list(group_id)"] --> B["_collect_group_members_from_queue"]
    B --> C{"队列里有成员消息?"}
    C -- 是 --> D["用观测到的成员拼列表"]
    C -- 否 --> E["拉群成员列表"]
    D --> F["_get_bot_group_role 判 bot 角色"]
    E --> F
    F --> G["render_bot_group_admin_status"]
    G --> H["拼成提示词用的文本段"]
```

成员列表**优先用消息队列里观测到的成员**（`_collect_group_members_from_queue`，`:406`），
只有队列信息不足时才去拉全量 —— 这是省 adapter 调用的设计。
`render_group_owner_text` / `render_specific_members` / `render_friend_info` 是另外三个渲染入口，
共同服务于提示词的可读性（`24-prompt-chatflow.md`）。
</details>

<details>
### 好感度：钳制与重试

```mermaid
flowchart TD
    A["update_favorability(delta)"] --> B{"delta 来自配置?"}
    B -- 是 --> C["读 favorability.max_change_per_summary"]
    B -- 否 --> D["用调用方给定值"]
    C --> E["clamp_favorability(min=-1000, max=1000)"]
    D --> E
    E --> F["写库（乐观更新）"]
    F --> G{"冲突/失败?"}
    G -- 否 --> H["成功"]
    G -- 是 --> I{"重试 < 12?"}
    I -- 是 --> F
    I -- 否 --> J["放弃并记日志"]
```

`FAVORABILITY_MIN=-1000` / `FAVORABILITY_MAX=1000`（`favorability.py:29-30`）是硬边界，
`favorability_to_text` 负责把数值转成可读文案。
`_FAVORABILITY_UPDATE_ATTEMPTS = 12`（`user_profiles.py:25`）说明这是一条**会重试**的写路径 ——
排查「好感度没变」时要看是不是 12 次都撞了锁。
</details>

<details>
### 配置键名不一致（已知坑）

```mermaid
flowchart LR
    A["schema: favorability.max_change_per_summary / min_value / max_value"] --> C{"谁在读"}
    B["技能侧: favorability_max_change / favorability_min / favorability_max"] --> C
    C -- 技能侧 --> D["键名不匹配 -> 恒回落默认 ±5 / ±1000"]
    C -- 提示词侧 --> E["读到配置值"]
```

这是 FINDINGS 07b-9 记录的同一处不一致：**技能侧读的键名与 schema 不匹配**，
所以工具侧钳制恒为默认（±5 / ±1000），而总结提示词里写的是配置值 ——
改配置会让两边口径分叉。修之前不要按「配置说了算」推断工具行为。
</details>

<details>
### 档案注入：用户档案段与长度上限

```mermaid
flowchart TD
    A["_fetch_user_archive(user_id)"] --> B["读档案（07）"]
    B --> C["_user_archive_max_chars 截断"]
    C --> D["拼进资料段"]
```

用户档案被拼进提示词时有独立长度上限（`_user_archive_max_chars`，`:393`），
与档案系统自己的 `max_chars=500` 不是同一个值（同 07-2 的「两个 max_chars」问题）。
</details>

## 关键状态

| 状态 | 谁置位 | 谁清理 | 失败时停在哪 |
|---|---|---|---|
| 用户资料行 | `ensure_user_profile` / `_refresh_user_profile` | 不清理（长期存在） | 拉取失败保留旧资料，只记日志 |
| 资料刷新时机 | `_needs_refresh` 按时间戳判定 | 刷新后新时间戳覆盖 | 时间戳不动就一直不刷 |
| 好感度值 | `update_(user_)favorability` | 不清理 | 钳制到 ±1000；写冲突最多重试 12 次 |
| 群成员观测缓存 | 消息队列（见 02c） | 队列容量驱逐 | 队列空时回落全量拉取 |

## 易错点

* **拉取失败不清空旧资料**：资料「看起来没更新」时先查 adapter 调用日志，而不是查库。
* **好感度配置有两套键名**：技能侧读的键名与 schema 不一致（FINDINGS 07b-9），
  工具侧钳制恒为默认值 —— 改配置不会改变工具行为。
* **群成员列表优先吃队列观测**：成员列表不全是拉取失败，可能只是队列里没有该成员的消息。
* **好感度写路径会重试 12 次**：高并发下写失败是「重试耗尽」而不是「没触发写」。
* **档案注入有独立长度上限**：与档案系统的 `max_chars` 不同源，改一个不影响另一个。
