# 创作者 Agent (Creator) — 参考图机制说明

## 目录结构

```
data/creator/
├── tmp/          # 临时图片，由 generate_image 生成
└── gallery/      # 图库图片，可作参考图使用
```

## 概述

创作者 Agent 负责图片生成、管理和发送。支持以图库中的图片作为**参考图**（参考构图/风格），让新生成的图片在其基础上创作。

## 参考图机制

### 流程

```
生成图片 → 加入图库 → 以图库图片为参考再生成 → 发送到群/私聊
```

### 涉及的 Tool

| Tool | 功能 | 参考图相关 |
|------|------|-----------|
| `generate_image` | 根据提示词生图 | 支持 `reference_id` 参数，指定图库图片编号作为参考 |
| `list_references` | 列出可作参考图的图库图片 | 返回编号供 `generate_image` 的 `reference_id` 使用 |
| `gallery_list` | 查看临时图片和图库图片 | — |
| `gallery_add` | 将临时图片加入图库 | 加入后即可作为参考图 |
| `gallery_replace` | 替换图库图片的内容 | — |
| `gallery_delete` | 删除图库图片 | — |
| `gallery_send` | 发送图片到群聊/私聊 | 只发图片本身，不附带文字 |

## 为图库图片添加文字描述（同名 .txt）

图库中的每张图片都可以附带一个**同名的 `.txt` 文件**来提供文字描述。系统在查看图库或使用参考图时会自动读取。

### 用法

在 `gallery/` 目录下，放一张图片和一个同名的 `.txt` 文件：

```
gallery/
├── g_0549c53b339a.png     # 图片
└── g_0549c53b339a.txt     # 同名的描述文件
```

`.txt` 文件内容就是该图片的描述文本，例如：

```
青山绿水田园风光，蓝天白云，以印象派风格绘制
```

### 效果

- 调用 `list_references` 或 `gallery_list` 查看图片时，会带上 `.txt` 中的描述
- 当 LLM 需要挑选合适的参考图时，描述文字能帮助它做出更精准的选择
- 描述在图片入库时自动读取；如果之后修改了 `.txt` 文件，下次查看时会即时更新

## 使用示例

### 1. 生成图片并加入图库

```
用户：画一张风景画
→ Agent 生成临时图片 tmp_xxxx
用户：这张不错，存起来
→ Agent 调用 gallery_add(image_id="tmp_xxxx")
```

### 2. 手动添加参考图（带描述）

将图片和描述文件放入 `gallery/` 目录后，重启 Bot 并让 Agent 查看：

```
用户：参考图库里那张田园风光画一张类似的
→ Agent 调用 list_references()
→ 看到编号 1，描述为"青山绿水田园风光…"
→ Agent 调用 generate_image(prompt="类似田园风光的画", reference_id=1)
```

### 3. 发送图片

```
用户：把画好的图发到这个群
→ Agent 调用 gallery_send(image_id="tmp_yyyy", group_id="123456789")
```

## 图片存储

| 来源 | 目录 | 特点 |
|------|------|------|
| `tmp` | `data/creator/tmp/` | 临时文件，可加入图库或直接发送 |
| `gallery` | `data/creator/gallery/` | 图库文件，可作参考图、可替换、可删除 |

- 图片 ID 前缀：`tmp_`（临时） / `g_`（图库）
- 支持格式：png / jpg / webp（自动检测）

## 参考图限制

- 只能以 **图库（gallery）** 图片作为参考图
- 临时图片（tmp）需要先 `gallery_add` 才能作参考
- 参考图编号由 `list_references` 按列表顺序生成（从 1 开始）
- 图库容量由配置文件 `agent.creator.gallery.capacity` 控制，默认 10

## 配置

在 `data/config.toml` 中：

```toml
[agent.creator]
enabled = true

[agent.creator.gallery]
capacity = 10  # 0 表示禁用图库管理

[agent.creator.emoji]
allow_add = true      # 是否允许 Creator Agent 增加表情包
allow_delete = false  # 是否允许 Creator Agent 删除表情包
```
