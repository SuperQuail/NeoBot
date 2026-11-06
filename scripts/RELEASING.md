# 检查与发布

## QuailEgg 发布流程

仓库发布由 [QuailEgg](https://github.com/SuperQuail/QuailEgg) 驱动，配置在 `.quailegg.toml`，采用 `dev` 上的 PR 发布模式。

### 日常改动

- 功能/修复 PR 提到 `dev`；修改 `app/` 或 `packages/*` 时用 `qegg commit` 写一条 `.changes/<slug>.md`（或手写合法记录，字段见 `.changes/README.md`）。
- `.changes/` 记录决定下一版本与 CHANGELOG；没有记录的代码改动不会进入版本说明（发布前请检查 `qegg plan`）。
- PR 上 `QuailEgg PR` 工作流会运行 `qegg check --ci` 并张贴发版计划；它当前是**非阻断**检查，分支保护尚未把它设为必需。

### 发布流程（自动）

1. 合并到 `dev` 后 [`.github/workflows/qegg-release.yml`](../.github/workflows/qegg-release.yml) 运行 `qegg release --yes`。
2. 有变更记录时：按记录计算下一版本，同步 8 个 `pyproject.toml` 与 `uv.lock`，生成 `CHANGELOG.md`，创建/刷新发布 PR（分支 `qegg-release` → `dev`）。
3. 发布 PR 由 `github-actions[bot]` 创建，**不会触发常规 CI 检查**；合并需要管理员绕过分支保护（仓库管理员操作），或后续改用 PAT/GitHub App。
4. 合并发布 PR 后，同一工作流再次运行：`[verify].commands` 通过后构建并发布 7 个 Python 包到 PyPI，创建 Git tag 与 GitHub Release。

### 预发布

- `qegg pre alpha|beta|rc` 写入 `.quailegg/pre-release.lock`，下一次发布生成对应渠道版本（当前为 `alpha`）。
- 预发布不写 `CHANGELOG.md`、不消费变更记录；`qegg pre exit` 后下一次发布为稳定版。
- tag 使用 PyPI 规范化拼写，例如 `2.1.0-a1` → `v2.1.0a1`，GitHub Release 标记为 Pre-release。

### 发布前校验

`[verify].commands`（在 bump 前执行）：
1. `uv sync --all-packages --locked`
2. `uv run ruff check .`
3. `uv run pytest --strict-markers -m "not browser and not network and not slow and not llm"`

### 凭据与环境

- 发布 job 使用受保护的 `pypi` environment（已允许 `dev` 部署）；`UV_PUBLISH_TOKEN` 来自仓库/environment secret。
- 不要在仓库里提交 token；不要手工创建 tag/Release 或手改版本号。

### 中断恢复

- 优先从失败运行对应的 `dev` 合并提交重跑 `qegg-release`；`qegg resume` 只读本地 `.quailegg/state/`（CI 上不保留），不能在 CI 续跑。
- 上传部分失败时，Q Egg 会按 PyPI 已存在版本跳过；缺个别 wheel/sdist 可本地 `scripts/publish.ps1` 补齐同一版本，不要覆盖已发布版本。

### 旧流程（仅历史/本地兜底）

- `publish.yml`（main→release）已删除；`scripts/versions.py`、`scripts/prepare_release.py`、`scripts/publish.ps1` 不再参与自动发布。
- `main`/`release` 分支仅历史保留，发布不再经过它们。
