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

## 贡献方式

请查看 [贡献指南](CONTRIBUTING.md) 了解如何贡献代码。

## 项目规范

- [语义化版本](https://semver.org/lang/zh-CN/)
- [约定式提交](https://www.conventionalcommits.org/zh-hans/v1.0.0/)