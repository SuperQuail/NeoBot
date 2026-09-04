# NeoBot

## 安装

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

## 内置控制台

NeoBot 内置两个随主进程启停的控制台：

- 本机管理员控制台默认开启并固定监听 `127.0.0.1`，首选端口为 `9891`。可在其中管理配置和 API 密钥。
- 调试控制台提供运行概览、聊天时间线、AI 输入/输出、后台任务、服务健康、实时日志、调试记录和脱敏诊断导出。它默认关闭，可按需对外监听。

首次打开任一控制台时会要求创建密码，密码不限制长度、字符或格式。若首选端口被占用，NeoBot 会从该端口开始自动尝试最多 100 个端口，实际地址会写入启动日志。

控制台密码文件位于 NeoBot 数据目录下的 `console/auth.json`。开发环境的默认完整路径为 `app/data/console/auth.json`；设置了 `NEOBOT_DATA_DIR` 时则位于该目录下。控制台不提供网页密码修改功能。忘记密码时点击登录页的“忘记密码？”可查看实际文件位置，然后停止 NeoBot、删除该文件、重新启动并设置新密码。

公网调试控制台可在 `data/config.toml` 中开启：

```toml
[console]
enabled = true
host = "0.0.0.0"
port = 9981
admin_enabled = true
admin_port = 9891
port_search_limit = 100
session_timeout_minutes = 60
secure_cookies = false
trust_proxy_headers = false
```

公网使用时建议通过 HTTPS 反向代理访问，并在确认 HTTPS 生效后将 `secure_cookies` 设为 `true`。只有可信反向代理正确覆盖客户端地址头时才应开启 `trust_proxy_headers`。

`host = "0.0.0.0"` 表示监听所有网卡；通过公网 IP 直连时无需开启代理请求头信任。若外部仍无法建立 TCP 连接，请放行操作系统和云平台防火墙中的实际控制台端口（端口被占用时会从 9981 起向后选择）。管理员控制台始终仅监听本机。

管理员控制台支持“保存并重载”或单独“重启 Bot 核心”。该操作会完整关闭当前核心后重新读取配置并创建新实例；记忆保存阶段不设置总超时，页面会持续等待控制台恢复。

## 开发文档

完整的开发文档（功能说明、架构设计、配置参考、开发指南）见 [docs/](docs/README.md)：

- [项目概览](docs/01-项目概览.md) — 项目定位、功能总览、技术栈与目录结构
- [快速开始](docs/02-快速开始.md) — 安装、配置、连接 OneBot、内置控制台
- [架构设计](docs/03-架构设计.md) — 分层架构、事件处理流水线、依赖注入
- [功能文档](docs/04-功能文档/) — 聊天回复 / Agent / 记忆 / 技能 / 图像 / 浏览器 / 搜索 / 定时任务 / 沙箱 / 控制台 / 统计
- [配置参考](docs/05-配置参考.md) — `data/config.toml` 完整配置项说明
- [开发指南](docs/06-开发指南.md) — 开发环境、测试、代码规范
- [插件开发](docs/07-插件开发.md) — 插件系统入门（详细 API 见 [packages/modloader/README.md](packages/modloader/README.md)）

## 贡献方式

请查看 [贡献指南](CONTRIBUTING.md) 了解如何贡献代码。

## 项目规范

- [语义化版本](https://semver.org/lang/zh-CN/)
- [约定式提交](https://www.conventionalcommits.org/zh-hans/v1.0.0/)
