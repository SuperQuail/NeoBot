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
- 调试控制台提供运行概览、服务健康、队列、异步任务、实时日志、调试记录和脱敏诊断导出。它默认关闭，可按需对外监听。

首次打开本机管理员控制台时会要求创建强密码。若首选端口被占用，NeoBot 会从该端口开始自动尝试最多 100 个端口，实际地址会写入启动日志。

控制台密码文件位于 NeoBot 数据目录下的 `console/auth.json`。开发环境的默认完整路径为 `app/data/console/auth.json`；设置了 `NEOBOT_DATA_DIR` 时则位于该目录下。控制台不提供网页密码修改功能。忘记密码时点击登录页的“忘记密码？”可查看实际文件位置，然后停止 NeoBot、删除该文件、重新启动，并从本机重新设置密码。

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

## 贡献方式

请查看 [贡献指南](CONTRIBUTING.md) 了解如何贡献代码。

## 项目规范

- [语义化版本](https://semver.org/lang/zh-CN/)
- [约定式提交](https://www.conventionalcommits.org/zh-hans/v1.0.0/)
