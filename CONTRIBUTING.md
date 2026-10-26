# 贡献指南
> [!TIP]
> 开始前请确保已安装下列内容:
> - [uv](https://docs.astral.sh/uv/getting-started/installation/)

感谢你对 NeoBot 的关注！我们欢迎所有形式的贡献。

## 分支模型

- **`dev`**：默认分支，功能/修复 PR 默认提到这里；
- **`main`**：发布候选，只接收来自 `dev` 的 PR；
- **`release`**：发布分支，只接收来自 `main` 的 PR；`main → release` 的 PR 必须提升版本号
  （8 个 `pyproject.toml` 统一提升并更新 `uv.lock`），合并后自动触发 PyPI 发布。

功能分支从 `dev` 切出，禁止跨级 PR（功能分支直接提到 `main`/`release` 会被 CI 拦下）。
## Pull Request 流程

### 1. Fork 并克隆仓库

```bash
git clone https://github.com/your-username/NeoBot.git
cd NeoBot
```

### 2. 创建分支

```bash
git switch dev
git switch -c feat/your-feature-name
```

分支命名规范：
- `feat/` - 新功能
- `fix/` - 修复问题
- `docs/` - 文档更新
- `refactor/` - 代码重构
- `test/` - 测试相关
- `chore/` - 构建/工具配置

### 3. 开发与提交

```bash
# 安装依赖
uv sync --all-packages

# 进行开发...

# 提交修改
git add .
git commit -m "feat: 添加新功能描述"
```

### 4. 推送并创建 PR

在 GitHub 上创建 Pull Request（默认目标是 `dev`），填写：
- 标题
- 变更说明
- 关联 issue（如有）：用关闭关键字写进描述，例如 `Closes #59`。
  只贴 `#59` 或 issue 链接**不算关联**——GitHub 不会记录关系，合并时也不会自动关闭。
  多个 issue 要各自带关键字（`Closes #59` 与 `Closes #60` 各一行，或
  `Resolves #10, resolves #123`）。详见 [AGENTS.md](AGENTS.md) 第 7 节。

PR 创建后还要过 **CI 硬门禁**（[.github/workflows/pr-gates.yml](.github/workflows/pr-gates.yml)）：

- 单个代码文件本次新增 ≥ 500 行给警告、≥ 800 行直接红（拆分文件/PR，不要压行）；
- PR 下必须有评审评论（允许 AI/自评），且最后一次 review 必须晚于最后一次 commit；
  推送新提交后旧评论失效，需要重新评审。AI 自评必须由独立子代理完成、不带开发上下文；
- 发现 bug 或 CI 因 bug 变红：**先发 issue**，修复 PR 描述里用 `Closes #NN` 关联；
  标题以 `fix` 开头的 PR 没关联 issue 会直接红；
- PR 流向必须是 `功能分支 → dev`、`dev → main`、`main → release`；
  `main → release` 还必须提升版本号并更新 `uv.lock`。

## 开发规范

- 添加必要的注释
- 确保代码可以正常运行
- 重大变更请先开 issue 讨论

## 需要帮助？

- 查看现有 [Issues](https://github.com/SuperQuail/NeoBot/issues)
- 查看已合并的 [Pull Requests](https://github.com/SuperQuail/NeoBot/pulls?q=is%3Apr+is%3Amerged)

再次感谢你的贡献！
