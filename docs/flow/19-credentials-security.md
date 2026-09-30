---
flow: 19-credentials-security
covers:
  - app/src/neobot_app/credentials/
  - app/src/neobot_app/panel_auth.py
  - app/src/neobot_app/panel_web.py
verified_against: 528fe18
verified_hash: 93e3c1dafcc7
---

# 19 凭据、面板鉴权与安全边界

## 范围

两个**完全不同**的「认证」以及仓库的密钥防线：

* `credentials/`：**不是 API Key 仓库**，而是「聊天动作口令」——危险动作前要管理员在群里发一串码；
* `panel_auth.py` / `panel_web.py`：网页面板的登录鉴权与静态资源鉴权判定；
* 钥匙真正的来源与脱敏规则（`.env` -> EnvConfig -> RegisteredModel.api_key）、
  密钥扫描脚本与 pre-commit/CI 防线。

不在这里：面板中间件与端点的完整鉴权流见 `09-dashboard.md` / `09b-dashboard-api.md`；
沙箱路径裁决见 `06-tools-skills.md`；日志脱敏的落地见 `23-billing-stats.md`。

## 流程

```mermaid
flowchart TD
    A["AI 或用户请求危险动作"] --> B{"该动作需要凭据?"}
    B -- 否 --> C["直接执行（受权限树约束）"]
    B -- 是 --> D{"已有活跃凭据?"}
    D -- 是 --> E["get(code) 校验 + 未过期"]
    E --> F{"有效?"}
    F -- 是 --> G["consume 消费"]
    G --> H["动作执行"]
    F -- 否 --> I["回固定文案：不要重试，先请求凭据"]
    D -- 否 --> I
    I --> J["管理员在群里发码"]
    J --> K["try_issue(chat_flow, code, issuer_id)"]
    K --> L{"签发者级别够?"}
    L -- 否 --> M["拒绝 + _record_issue_failure"]
    L -- 是 --> N{"该会话签发失败 >= 5 次?"}
    N -- 是 --> O["is_issue_blocked：冷却中"]
    N -- 否 --> P["create：生成码 + 设时限"]
    P --> Q["_clear_issue_failures"]
    Q --> D
    R["面板请求"] --> S["panel_auth 登录态判定"]
    S --> T{"通过?"}
    T -- 否 --> U["401 / 403"]
    T -- 是 --> V["进入端点"]
```

## 时序

```mermaid
sequenceDiagram
    autonumber
    participant AG as AI/用户
    participant CM as CredentialManager
    participant AD as 管理员
    participant ACT as 危险动作
    participant PA as panel_auth

    AG->>CM: has_active(chat_flow, action)?
    CM-->>AG: False
    AG-->>AD: 提示需要凭据
    AD->>CM: try_issue(chat_flow, code, issuer_id)
    CM->>CM: 校验级别 + 失败计数
    CM-->>AD: 签发结果（码 + 时限）
    AG->>CM: get(code) + consume
    CM-->>AG: 有效则放行
    AG->>ACT: 执行
    PA->>PA: 面板侧独立判定登录态
```

## 细节

<details>
### 凭据生命周期：create / get / consume / revoke / cleanup

```mermaid
flowchart TD
    A["create(action, chat_flow, ...)"] --> B["required_level = ACTION_REQUIRED_LEVEL.get(action)"]
    B --> C["_clamp_duration 夹紧时长"]
    C --> D["_generate_code 生成码"]
    D --> E["登记 Credential(code, expires_at, chat_flow)"]
    E --> F["get(code) 取用"]
    F --> G{"is_expired?"}
    G -- 是 --> H["视为无效"]
    G -- 否 --> I{"一次性凭据已用过?"}
    I -- 是 --> J["视为无效（USED）"]
    I -- 否 --> K["有效"]
    K --> L["consume 消费：one_time 立刻置 USED"]
    L --> M["revoke(code) 主动吊销"]
    M --> N["cleanup() 清理过期项"]
```

四种状态要分清（`credentials/service.py`）：**不存在 / 已过期 / 已消费（一次性）/ 有效**。
`is_expired`（`model.py:72`）只看时间；`consume`（`service.py:199`）负责把一次性凭据置为已用。
`cleanup`（`:239`）是清理入口，但不保证被周期调用 —— 长期不清理不会导致功能错误（`get` 会判过期），
只是内存里会留垃圾项。
</details>

<details>
### try_issue：级别校验 + 失败冷却

```mermaid
flowchart TD
    A["try_issue(chat_flow, code, issuer_id)"] --> B{"该会话在冷却中?"}
    B -- 是 --> C["拒绝：is_issue_blocked"]
    B -- 否 --> D["校验签发者级别"]
    D --> E{"级别够?"}
    E -- 否 --> F["_record_issue_failure：失败计数 +1"]
    F --> G{"failures >= _ISSUE_MAX_FAILURES=5?"}
    G -- 是 --> H["进入冷却（约 300s）"]
    G -- 否 --> I["返回失败，允许再试"]
    E -- 是 --> J["create 签发"]
    J --> K["_clear_issue_failures 清零"]
```

`_ISSUE_MAX_FAILURES = 5`（`service.py:26`）与冷却窗口是**防爆破**设计：
失败 5 次后该会话在冷却期内无法再尝试签发。
注意冷却键是 **chat_flow**（会话维度）不是全局 —— 一个群被冷却不影响其它群。
</details>

<details>
### ACTION_REQUIRED_LEVEL：动作到级别的映射

```mermaid
flowchart LR
    A["ACTION_REQUIRED_LEVEL: dict[str, int]"] --> B["按动作名取所需级别"]
    B --> C{"动作不在表里?"}
    C -- 是 --> D["用 DEFAULT_REQUIRED_LEVEL"]
    C -- 否 --> E["用表里的级别"]
    D --> F["required_level_for(action)"]
    E --> F
```

`credentials/model.py:23` 是唯一映射表，`required_level_for`（`service.py:263`）是唯一读法。
新增危险动作**必须**同时加表项与调用点，否则会落到 `DEFAULT_REQUIRED_LEVEL` —— 表现为
「该拦的没拦」。回执文案里明确写了「不要重试」（见 FINDINGS 06 节的凭据语义）。
</details>

<details>
### 面板鉴权与凭据的边界（两个「认证」）

```mermaid
flowchart LR
    subgraph 面板侧
      A["panel_auth：登录态 / 会话 Cookie"] --> B["server 中间件（09）"]
      B --> C["_require_manage 二次校验（09b）"]
    end
    subgraph 聊天侧
      D["credentials：动作口令"] --> E["危险动作放行"]
    end
    A -.互不替代.-> D
```

两者**不通兑**：拿到面板登录态不等于能在群里执行危险动作；反之亦然。
`panel_web.py` 只负责静态资源/Web 扩展的鉴权判定（哪些路径公开、哪些需要登录），
真正的中间件在 `server.py:448`（见 `09-dashboard.md`）。
</details>

<details>
### 钥匙真正的来源：.env -> EnvConfig -> RegisteredModel

```mermaid
flowchart TD
    A[".env 文件"] --> B["EnvConfig.get_api_platform_config(平台名)"]
    B --> C["读 <平台名>_URL 与 <平台名>_APIKey"]
    C --> D{"两者都有?"}
    D -- 否 --> E["该模型不注册"]
    D -- 是 --> F["RegisteredModel(api_key=...)"]
    F --> G["provider._build_headers 注入 Authorization"]
    G --> H["请求真正发出"]
```

**这里才是 API Key**，不是 `credentials/`。环境变量名大小写不敏感（`EnvConfig` 查 `os.environ`）。
面板侧对密钥有三条脱敏路径：结构化 config 载荷给空串 + `secrets_set`、TOML 原文给占位符、
只读会话隐藏 `source/raw` —— 但 `.env` 恒为掩码（`09c` 记录了两个占位符样式）。
本图与文档**不记录任何真实密钥值**。
</details>

<details>
### 密钥防线：扫描脚本 + pre-commit + CI

```mermaid
flowchart TD
    A["scripts/check_secrets.py --staged"] --> B{"命中疑似密钥?"}
    B -- 是 --> C["pre-commit 阻断提交"]
    B -- 否 --> D["放行"]
    E["CI hygiene job"] --> F["扫描历史里被清除的调试脚本"]
    F --> G{"命中?"}
    G -- 是 --> H["CI 失败并提示移除提交"]
    G -- 否 --> I["通过"]
    J[".secretsignore"] --> K["登记确认无害的占位符"]
```

历史事故：`scripts/test_drawing_*.py` 等曾带硬编码密钥，已从远端历史彻底清除，
`.githooks/pre-push` 与 CI hygiene job 各有一道兜底（见 `.githooks/pre-push` 注释）。
**新增调试脚本前先读这两个文件** —— 它们列了禁止回流的文件清单。
</details>

## 关键状态

| 状态 | 谁置位 | 谁清理 | 失败时停在哪 |
|---|---|---|---|
| 凭据项 | `create` | `consume` / `revoke` / `cleanup` | 过期与已消费都按无效处理 |
| 签发失败计数 | `_record_issue_failure` | `_clear_issue_failures`（成功签发时） | 达 5 次进入冷却，冷却按 chat_flow 维度 |
| 面板登录态 | `panel_auth` 登录 | 登出/过期（前端登出不调后端，见 09c） | 未登录 401 / 无权限 403 |
| 密钥 | `.env` + `EnvConfig` | 改 `.env` 需 reload 才重建注册表 | 平台名/密钥缺一即不注册该模型 |

## 易错点

* **`credentials/` 不是 API Key 仓库**：排查「密钥无效」不要进这个模块（FINDINGS W59）。
* **凭据不是重试型错误**：无凭据时每次同样失败，必须先 `credential__request`；
  一次性凭据一消费就 USED，时限凭据持续有效不消费（FINDINGS 06 节）。
* **签发冷却按会话**：一个群被冷却不影响其它群，但同一群内所有动作一起被挡。
* **新增危险动作必须登记 `ACTION_REQUIRED_LEVEL`**：漏登记会落到默认级别，表现为「该拦的没拦」。
* **面板登录态与凭据不通兑**：两套体系独立判定。
* **密钥只从 `.env` 来**：面板保存后需要 reload 才让注册表用上新密钥。
