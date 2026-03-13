# 贡献指南

感谢你对 NeoBot 的关注！我们欢迎所有形式的贡献。

## Pull Request 流程

### 1. Fork 并克隆仓库

```bash
git clone https://github.com/your-username/NeoBot.git
cd NeoBot
```

### 2. 创建分支

```bash
git checkout -b feat/your-feature-name
```

分支命名规范：
- `feat/` - 新功能
- `fix/` - 修复问题
- `docs/` - 文档更新
- `refactor/` - 代码重构
- `test/` - 测试相关
- `chore/` - 构建/工具配置

### 3. 开发与提交
> [!INFO]
> 请确保安装下列内容:
> - [uv](https://docs.astral.sh/uv/getting-started/installation/)
> - [smif](https://semifold.noctisynth.org/zh/guide/start/quick-start/index)

```bash
# 安装依赖
uv sync --all-packages

# 进行开发...

# 提交更改
# 如果修改了 app/**, packages/** , pyproject.toml 需运行 smif commit
smif commit

# 否则直接提交
git add .
git commit -m "feat: 添加新功能描述"
```

提交信息遵循 [约定式提交](https://www.conventionalcommits.org/zh-hans/)：
```
<type>(<scope>): <subject>

<body>
```

### 4. 推送并创建 PR

在 GitHub 上创建 Pull Request，填写：
- 标题
- 变更说明
- 相关 issue 编号（如有）

## 开发规范

- 添加必要的注释
- 确保代码可以正常运行
- 重大变更请先开 issue 讨论

## 需要帮助？

- 查看现有 [Issues](https://github.com/SuperQuail/NeoBot/issues)
- 查看已合并的 [Pull Requests](https://github.com/SuperQuail/NeoBot/pulls?q=is%3Apr+is%3Amerged)

再次感谢你的贡献！
