# 检查与发布

## QuailEgg 发布流程

仓库发布由 [QuailEgg](https://github.com/SuperQuail/QuailEgg) 驱动，配置在 `.quailegg.toml`，采用 `main` 上的 PR 发布模式：

- `main`：默认分支与发布基线，日常功能/修复 PR 提到这里；
- `release`：发布分支，由 QuailEgg 每次从 `main` 重建并强制推送，**不要手工提交**；
- `dev`：普通分支，长期开发时可用，不再默认、不再参与发布。

### 生成文件（不要手改）

`.github/workflows/qegg-release.yml`、`qegg-pr.yml`、`qegg-status.yml` 都由 `qegg init` 生成。
需要定制前置步骤时改 `.quailegg.toml` 的 `[release.workflow]` / `[pr.workflow]` / `[status.workflow]`
（`runner`、`timeout_minutes`、`steps` 或 `yaml`、`env`），再重新生成：

```bash
qegg init --dry-run --force --no-input --no-hook --no-add-packages --qegg-version v0.13.0
qegg init --force --no-input --no-hook --no-add-packages --qegg-version v0.13.0
```

> 两类字段作用不同：
>
> - `runner` / `timeout_minutes` / `env` 改的是**整个 job**（`runs-on`、`timeout-minutes`、job 级 env），
>   不属于「追加步骤」。
> - `steps` / `yaml` 只把自定义步骤**插入**到「安装 QuailEgg 之后、`qegg check` / `qegg release` 之前」；
>   内置的 checkout、setup-go、各生态 setup（由 `[publish].registries` 推导，为空时回退各包 resolver，
>   再回退检测到的生态）、QuailEgg 安装照常渲染。
>
> 插入的步骤排在 `qegg check` / `qegg release` 之前，因此能通过 `$GITHUB_ENV`、`$GITHUB_PATH` 影响它们——
> 下面的 `UV_PYTHON` 与 uv shim 就是这么生效的。也正因如此，工具链 setup 已经在模板里，
> 不要为了「补 uv」往 `[pr.workflow]` 里重复写一遍。

`env` 与 `yaml` 互斥：同时设置会报 `… is only used by steps; set env inside the yaml block`。

当前配置的 `[release.workflow].yaml` 里有两条前置 step：固定 `UV_PYTHON=3.14`（onnxruntime 没有 cp315 wheel），
以及把 uv workspace 的 `uv build` 输出固定到各包目录（qegg 随后在该目录 `uv publish`）。qegg 也支持
`[release.workflow].steps` 写纯命令，本仓库没有使用。改完配置后要提交生成文件的 diff，不要手改生成文件。

已知限制（由生成模板决定，不在仓库内手改）：

- 生成工作流使用 qegg 模板内置的 action 版本（`checkout@v4`、`setup-uv@v5`），落后于手写工作流，
  且用可变大版本 tag；而 `plugin-ci.yml`、`plugin-sdk-validation.yml`、`video-frame-validation.yml`
  已钉到 SHA（`ci.yml`、`pr-gates.yml` 等仍是可变 tag）。升级版本或改钉 SHA 都得改 QuailEgg 模板并发版，
  仓库内不要手改生成文件。
- `qegg-pr` 的 Preview 步骤对 fork PR 会因只读 token 失败（非阻断检查）。
- `qegg-pr` 的 job 没有中文名，非阻断性质只在分支保护里体现。
- 升级 qegg 版本时要连 `--qegg-version` 一起改，生成文件里的安装步骤会跟着变（当前固定 `v0.13.0`）。

### 日常改动

- 功能/修复 PR 提到 `main`；修改 `app/` 或 `packages/*` 时用 `qegg commit` 写一条 `.changes/<slug>.md`（或手写合法记录，字段见 `.changes/README.md`）。
- `.changes/` 记录决定下一版本与 CHANGELOG；没有记录的代码改动不会进入版本说明（发布前请检查 `qegg plan`）。
- 提到 `main` 的 PR 上，`QuailEgg PR` 工作流会运行 `qegg check --ci` 并评论发版计划；它当前是**非阻断**检查（该工作流只监听 base 为 `main` 的 PR）。

### 发布流程（自动）

1. 合并到 `main` 后 [`.github/workflows/qegg-release.yml`](../.github/workflows/qegg-release.yml) 运行 `qegg release --yes`。
2. 有变更记录时：按记录计算下一版本，同步 8 个 `pyproject.toml`、`app` 的内部 pin 与 `uv.lock`，生成 `CHANGELOG.md`，创建/刷新发布 PR（`release` → `main`）。
3. 发布 PR 由 `github-actions[bot]` 创建，平台不会为它正常启动检查；合并时由仓库管理员强制合并：
   ```bash
   gh pr merge <发布PR号> --squash --admin
   ```
   **不要**为了让它变绿而手改生成的工作流，也**不要把** `QuailEgg PR` 设为必需检查。
4. 合并发布 PR 后，同一工作流再次运行：`[verify].commands` 通过后构建并发布 7 个 Python 包到 PyPI，创建 Git tag 与 GitHub Release，并把 `release` 分支拉平到 `main`。

**发版时确认 uv shim 生效**：`[release.workflow].yaml` 里的 shim 把 `uv build` 输出改到各包目录的 `dist/`。
若发布日志出现「在成员目录 `uv publish` 找不到产物」或产物集中到仓库根 `dist/`，说明 shim 没生效——
先修 `.quailegg.toml` 并重新生成，不要在生成的工作流里补步骤。

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

- 发布 job 使用受保护的 `pypi` environment（部署分支允许 `main`）；`UV_PUBLISH_TOKEN` 来自仓库/environment secret。
- 不要在仓库里提交 token；不要手工创建 tag/Release，也不要手改版本号或 `uv.lock`。

### 中断恢复

- 优先从失败运行对应的 `main` 合并提交重跑 `qegg-release`；`qegg resume` 只读本地 `.quailegg/state/`（CI 上不保留），不能在 CI 续跑。
- 上传部分失败时，Q Egg 会按 PyPI 已存在版本跳过，重跑同一流程即可补齐；不要覆盖已发布版本。
- 本地排查：`qegg status`、`qegg plan`、`qegg release --dry-run`。

### 历史

- 旧的 `publish.yml`（`main` → `release` 触发 PyPI）与 `scripts/versions.py`、`prepare_release.py`、`publish.ps1`、`check_release_bump.py` 已删除，可从 git 历史查看。
