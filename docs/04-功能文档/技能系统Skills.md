# 技能系统（Skills）

Skill 是 NeoBot 给 LLM 扩展能力的核心机制：每个 Skill 以 OpenAI function-calling 格式暴露一组工具，模型在对话中按需调用。工具名自动加 `{skill_name}__` 前缀（如 `browser__navigate`），避免命名冲突。

## 工作机制

- **注册**：[`app/src/neobot_app/skills/base.py`](../../app/src/neobot_app/skills/base.py) 的 `SkillManager` 负责注册、聚合与路由；[`skills/__init__.py`](../../app/src/neobot_app/skills/__init__.py) 的 `build_all_skills()` 在启动时注册全部内置 Skill（支持 `agent.skill.disabled_skills` 黑名单）。
- **协议**：每个 Skill 继承 `SkillModule`，实现 `name`、`description`、`get_tools()`、`execute()`；可选 `instructions`（注入系统提示词的说明）、`session_tools`（Session 模式工具：提交后立即返回，后台执行完成后通知）、`reset()`（跨会话状态复位）。
- **注入**：Skill 工具定义随提示词注入主 Agent（[`packages/chat/skills/inject.py`](../../packages/chat/src/neobot_chat/skills/inject.py)），模型调用时经 SkillManager 分发到对应 Skill 的 `execute()`。
- **会话模式**：耗时工具（绘图等）以 Session 模式运行，模型提交后立即返回，完成后通过通知系统告知。

## 内置技能清单（30+）

### 记忆与画像
| Skill | 能力 |
|---|---|
| `archive_crud` | 档案增删改查（user/group/item 档案） |
| `archive_skill` | 档案读取 |
| `user_profile` | 用户画像查询/更新（含头像分析） |
| `favorability` | 好感度查询 |
| `adaptive_prompt` | 自适应提示词读写（Agent 永久记忆） |
| `chat_history` | 聊天历史读取 |

### 社交与管理
| Skill | 能力 |
|---|---|
| `group_management` | 群管理（加群/退群/成员管理等） |
| `friend_management` | 好友管理 |
| `forward_message` | 消息转发 |
| `cross_chat` | 跨会话消息传递 |
| `gift` | 送礼互动 |
| `birthday` | 生日提醒 |

### 图像与创作
| Skill | 能力 |
|---|---|
| `drawing` | 绘图（生图，后台任务） |
| `gallery` | 图库管理 |
| `emoji_management` | 表情包管理（增删/列表） |
| `sticker` | 贴纸/表情发送 |
| `image_send` | 图片发送 |
| `image_pool` | 图片池管理 |
| `image_parse` | 图片解析（视觉识别） |

### 浏览器与网络
| Skill | 能力 |
|---|---|
| `browser` | 浏览器操作（导航/点击/输入/截图等） |
| `browser_network` | 网络请求拦截与读取 |
| `browser_video` | 视频获取 |

### 任务与文件
| Skill | 能力 |
|---|---|
| `reminder` | 提醒（定时） |
| `background_trigger` | 后台触发 |
| `file_storage` | 文件存储（沙箱内读写） |
| `sandbox_manager` | 沙箱管理 |
| `sandbox_maintenance` | 沙箱持久化维护 |
| `balance` | 余额查询 |
| `agents`（agent_delegation） | 子 Agent 委托 |
| `willingness` | 回复意愿设置 |

> 以上清单随版本演进，最新列表以 [`app/src/neobot_app/skills/__init__.py`](../../app/src/neobot_app/skills/__init__.py) 为准。

## 开发自定义 Skill

1. 创建 `SkillModule` 子类，实现 4 个核心方法
2. 在 [`skills/__init__.py`](../../app/src/neobot_app/skills/__init__.py) 的 `build_all_skills()` 中注册（或通过插件系统注册）
3. 通过 `agent.skill.disabled_skills` 可黑名单禁用

示例见 `packages/modloader/example_plugins/` 与 Skill 测试 `app/tests/modules/skills/`。

## 相关配置

- `agent.skill.disabled_skills`：禁用的 skill 名称列表（黑名单），空列表表示全部启用
- `agent.file_operation.enabled`：是否启用文件操作 Agent

## 相关代码文件

| 文件 | 说明 | 关键类/函数 |
|---|---|---|
| [skills/base.py](../../app/src/neobot_app/skills/base.py) | Skill 核心：SkillModule 协议与 SkillManager | `SkillModule`、`SkillManager`、`SkillExecutionToken` |
| [skills/__init__.py](../../app/src/neobot_app/skills/__init__.py) | 全部内置 Skill 的注册工厂 | `build_all_skills` |
| [chat/skills/inject.py](../../packages/chat/src/neobot_chat/skills/inject.py) | 将 Skill 工具定义注入 Agent 状态/提示词 | `inject_skills`、`build_skill_preprocessor` |
| [chat/skills/registry.py](../../packages/chat/src/neobot_chat/skills/registry.py) | 插件 Markdown Skill 的注册表 | `Skill`、`SkillRegistry` |
| [config/schemas/bot.py](../../app/src/neobot_app/config/schemas/bot.py) | Skill 全局配置（禁用列表） | `AgentSkill` |

> 各内置 Skill 的实现文件见 [技能清单](#内置技能清单30) 对应的 `skills/*.py`（如 [drawing_skill.py](../../app/src/neobot_app/skills/drawing_skill.py)、[browser_skill.py](../../app/src/neobot_app/skills/browser_skill.py)）。
