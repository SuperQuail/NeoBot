# NeoBot

## 安装

> 完整的部署步骤（uv / pip / 源码安装、数据目录、NapCat 反向 WebSocket 配置）见 [部署说明](docs/08-部署说明.md)。

### 环境要求

- Python 3.13 或更高版本
- 操作系统：Windows / Linux / macOS

### 安装方式

```bash
pip install neobot-app
```

### 首次运行

```bash
# 首次运行（会自动生成配置文件）
neobot

# 编辑 .env 文件填入 API 密钥
# 编辑 data/config.toml 设置机器人 QQ 号

# 启动 OneBot 框架（如 NapCat）
# 然后再次运行 NeoBot
neobot
```

首次运行会自动生成必要的配置文件和目录结构。编辑好配置后，NeoBot 会等待 OneBot 框架连接，连接成功后即可在 QQ 上使用。

建议在虚拟环境中安装，避免与其他 Python 项目冲突：

```bash
python -m venv neobot-env
# Windows
neobot-env\Scripts\activate
# Linux / macOS
source neobot-env/bin/activate

pip install neobot-app
```

## 网页面板

NeoBot 只有一个网页面板，由**官方内置插件 `dashboard`** 提供（源码在 `app/src/neobot_app/builtin_plugins/dashboard/`，前端产物随包分发，使用面板不需要 Node.js）。

- 默认**开启**并监听 `0.0.0.0:9981`（即默认对网络开放）；只在本机使用可把 `host` 改为 `127.0.0.1`。
- 用**面板密码**登录：未设置密码时不允许外网访问，只能在本机打开面板按提示设置，或由超级管理员在 QQ 私聊发送 `/set_password <新密码>`（留空自动生成）。密码以 PBKDF2 哈希保存在 `plugins_data/dashboard/auth.json`，修改后旧会话立即失效。
- 端口被占用时从 `dashboard.port` 起最多向后尝试 10 个端口，并在启动日志打印告警。
- 页面包含：仪表盘（运行概览/系统资源/消息趋势/最近日志）、插件管理（官方与第三方分组、启停、热重载能力标注、安装/更新/卸载、在线配置、下载代理）、配置管理（`config.toml` 表单/TOML 编辑、`.env` 编辑、一键添加 API 供应商、模型库、模型分配、撤销/历史/恢复默认、热重载标记）、用量统计（金额与 Token 图表）、系统状态（进程资源/宿主服务/后台任务/模型用量）、机器人详情、日志。
- **密钥只写不读**：`.env` 与第三方插件配置中的 API Key / Token 只显示「已设置 / 未设置」，留空表示不修改，保存后也无法再读回明文。

```toml
[dashboard]
enabled = true
host = "0.0.0.0"      # 对网络开放；127.0.0.1 仅本机
port = 9981
manage_plugins = true # 关闭后面板内所有写操作变为只读
allow_remote_manage = true  # 关闭后远程只能查看，改配置/管插件仅限本机
```

公网使用时建议通过 HTTPS 反向代理访问，并在确认 HTTPS 生效后将 `secure_cookies` 设为 `true`；只有可信反向代理正确覆盖客户端地址头时才应开启 `trust_proxy_headers`。若外部无法建立 TCP 连接，请放行操作系统和云平台防火墙中的面板端口（Windows 可执行 `neobot firewall-open`，需管理员权限）。

面板内支持「重载运行时配置」（等价于 `config.reload`）与「重启 NeoBot」；构建期组件（运行中的 LLM Provider、关键词规则、TTS/表情包等）需要重启后生效。

## 开发文档

完整的开发文档（功能说明、架构设计、配置参考、开发指南）见 [docs/](docs/README.md)：

- [项目概览](docs/01-项目概览.md) — 项目定位、功能总览、技术栈与目录结构
- [快速开始](docs/02-快速开始.md) — 安装、配置、连接 OneBot、网页面板
- [架构设计](docs/03-架构设计.md) — 分层架构、事件处理流水线、依赖注入
- [功能文档](docs/04-功能文档/) — 聊天回复 / Agent / 记忆 / 技能 / 图像 / 浏览器 / 搜索 / 定时任务 / 沙箱 / 网页面板 / 统计
- [配置参考](docs/05-配置参考.md) — `data/config.toml` 完整配置项说明
- [开发指南](docs/06-开发指南.md) — 开发环境、测试、代码规范
- [插件开发](docs/07-插件开发.md) — 插件系统入门（详细 API 见 [packages/modloader/README.md](packages/modloader/README.md)）

## 贡献方式

请查看 [贡献指南](CONTRIBUTING.md) 了解如何贡献代码。

## 项目规范

- [语义化版本](https://semver.org/lang/zh-CN/)
- [约定式提交](https://www.conventionalcommits.org/zh-hans/v1.0.0/)
