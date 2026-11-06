# 检查与发布

## GitHub Actions

- `.github/workflows/ci.yml`：PR 的 Python 静态检查/测试、前端 lint/类型/测试/构建及入库产物一致性检查；同时可由发布工作流复用。
- `.github/workflows/pr-title.yml`：PR 标题规范检查（`scripts/check_pr_title.py`）。仓库 squash 设置为 `PR_TITLE` + `PR_BODY`，PR 标题会成为目标分支上的提交标题，因此按 commit message 规范阻断：格式、长度、`(#NN)`、空话、「主题 —— 明细」清单写法；「疑似罗列」只警告，加 `--strict` 才阻断。
- `.github/workflows/publish.yml`：**release 推送**后通过 GitHub API 确认该提交来自 `main → release` 的合并 PR，直接推送不发布。也可在 Actions 页面手动对 release 触发（`workflow_dispatch`）：手动触发是对 release 的显式发布动作，仅当 ref 就是 release 时才可信，从其他分支手动触发一律跳过。两种情况都会先重跑 CI，通过后才检测版本、构建和上传。
- 发布流程结束后自动创建 Git tag 与 GitHub Release：tag 使用 PyPI 规范化版本（`2.0.2-a13` → `v2.0.2a13`），版本含预发布标识时标记为 Pre-release，Release 正文由 GitHub 自动生成（对比上一个 Release）。已存在同名 Release 时跳过，可安全重跑；对 release 手动触发也可用于补齐当前版本的 tag/Release（该版本已在 PyPI 时上传步骤跳过，但仍会补建 Release）。
- CI 和发布流程只读检查源码版本及锁文件，不自动改版本、不更新锁文件，也不提交源码；唯一的写操作是创建 Git tag 与 GitHub Release（workflow 中的 `github-release` job 使用 `contents: write`）。

### 分支与发布流程（2026-10-26 起）

- 日常 PR → `dev`；发布候选 `dev → main`；正式发布 `main → release`。
- 版本号在 `dev` 上提升（见下节，8 个 `pyproject.toml` + `uv.lock`），随 `dev → main` 带入；
  `main → release` 的 PR 版本必须高于 release 当前版本，CI 用 `scripts/check_release_bump.py` 阻断未提升的 PR；
  合并到 `release` 后才触发发布。

### 首次配置

1. 创建 GitHub environment `pypi`（可配置审批、仅允许 `release` 分支部署）。
2. 在该 environment 或仓库 Secrets 中添加 `UV_PUBLISH_TOKEN`，需有全部 7 个工作区发布包的上传权限。根项目 `neobot` 没有 build-system，不上传。

### 手动更新版本

1. 在 **`dev` 分支**（发布准备，`dev → main` 之前）运行 `python scripts/versions.py <新版本>`，脚本会把以下 8 个 `pyproject.toml` 的 `project.version` 更新为一致且递增的 SemVer 版本，并同步 `app/pyproject.toml` 里 6 条内部子包 pin（issue #72）；主分支保护禁止直推，因此不要在 release PR 里提交版本：
   - `pyproject.toml`
   - `app/pyproject.toml`
   - `packages/adapter/pyproject.toml`
   - `packages/chat/pyproject.toml`
   - `packages/contracts/pyproject.toml`
   - `packages/memory/pyproject.toml`
   - `packages/modloader/pyproject.toml`
   - `packages/storage/pyproject.toml`
2. 在仓库根目录手动执行 `uv lock`，将更新后的 `uv.lock` 与上述版本变更一起提交到同一 PR。CI 使用锁定依赖，发布流程只执行 `uv lock --check`，锁文件过期会失败。
3. 该 PR 合并到 `release` 后自动检测是否需要发布；普通 dev/main PR 无需修改版本。

### SemVer 校验

版本格式遵循 [SemVer 2.0.0](https://semver.org/lang/zh-CN/)，由 `scripts/semver_validation.py` 统一校验：

- 必须是 `X.Y.Z`，可带 `-先行版本` 和 `+编译信息`；主/次/修订号及纯数字先行标识符不得有前导零。
- 拒绝 `1.0`、`v1.2.3`、`1.0.0a23`、`01.2.3`、`1.0.0-alpha.01`、空标识符、空白和非 ASCII 字符。
- 可手动运行 `python scripts/versions.py 1.0.0-alpha.24` 批量更新工作区版本，并同步 app 的 6 条内部 pin。目标版本在文件扫描、确认和写入之前校验；非法则退出且不改文件。该脚本不会由 CI 自动调用，也不会更新锁文件。
- SemVer 合法不等于 PyPI 可发布。例如 `1.0.0+build.01` 和任意先行标签可以通过手动版本脚本的 SemVer 校验，但发布入口还要求兼容 PyPI/PEP 440；不兼容会单独报错，绝不自动删改版本信息。

### 版本检测与上传

`scripts/prepare_release.py --base-ref <推送前的提交>` 比较根项目当前版本与推送前版本；推送时 GitHub Actions 传入 `github.event.before`。手动触发没有该值：留空表单时改用 `--publish-missing`，完全忽略 Git 基线，只按 PyPI 判断（7 个包缺当前版本就发布，全部已有则跳过）；确实需要按某条历史提交比较时，再在触发表单里填写 `base_ref`（提交 SHA 或 tag）。脚本只检测，不修改任何项目文件，并通过 `GITHUB_OUTPUT` 输出原始 SemVer `version` 和 `publish=true/false`。

- 先校验全部工作区版本的 SemVer 格式及 PyPI 兼容性；任一非法都会报错停止，不查询 PyPI、不上传，即使版本未变也不放行。PyPI 历史版本和 Git 基线仅作 PEP 440 比较，允许历史的规范化拼写。
- 根版本未变（推送或显式填了 `base_ref` 时才会比较）：不查询 PyPI，输出 `publish=false`；跳过发布凭据检查、发布 job 的 Node/pnpm 安装、构建和上传，合并 PR 的 CI 门禁仍运行。
- 手动触发且留空 `base_ref`：跳过 Git 基线比较，直接看 PyPI——7 个包都已有当前版本则 `publish=false`，缺任意一个则 `publish=true` 补齐发布（适合重发一个已合并、但当时发布失败的版本）。
- 根版本有变：要求 8 个项目版本一致，且相较推送前版本递增；手动目标版本若低于 PyPI 已有版本也会失败。校验失败立即中止。所有版本均由维护者手动选择，脚本不会自动递增。
- PyPI 已有全部 7 个包的当前版本：输出 `publish=false`，跳过上传。部分包缺失当前版本：输出 `publish=true`，构建并补齐发布；`uv publish --check-url` 跳过已存在的文件。
- PyPI 的 PEP 440 规范化仅用于版本比较和构建/发布，例如 `1.0.0-alpha.23` 对应 `1.0.0a23`；不会回写或改变仓库中的 SemVer 拼写。
- PyPI 只有 404 视为新包；网络错误、鉴权/服务错误或无效响应均中止，不猜测版本。

若上传部分失败，且仍有包缺失当前版本，可重跑该版本变更对应的工作流，或在 Actions 页面手动对 release 触发补齐发布：留空 `base_ref` 即按 PyPI 缺失情况补发，不需要知道版本变更提交是哪一个。若所有包的当前版本均已建立，但个别 wheel/sdist 文件缺失，自动流程会跳过，需使用下方本地 `publish.ps1` 补齐同一版本的文件。后续无版本变更的 PR 不会触发补发。不要用旧版本运行覆盖新发布；多个 release 推送的等待运行仍受 GitHub concurrency 队列规则影响。

# 检查与发布

## Q Egg 发布流程

仓库发布由 [QuailEgg](https://github.com/SuperQuail/QuailEgg) 驱动，配置在 `.quailegg.toml`，采用 dev 上的 PR 发布模式。

- 日常 PR 合入 `dev`；修改 `app/` 或 `packages/*` 时用 `qegg commit` 写一条 `.changes/<slug>.md`（或手写合法记录，字段见 `.changes/README.md`）。
- 合并到 dev 后 [`.github/workflows/qegg-release.yml`](../.github/workflows/qegg-release.yml) 运行 `qegg release --yes`：
  - 有变更记录时：按记录计算下一版本，同步 8 个 `pyproject.toml` 与 `uv.lock`，生成 `CHANGELOG.md`，创建/刷新发布 PR（分支 `qegg-release`，目标 `dev`）。
  - 合并发布 PR 后：同一工作流再次运行，构建并发布 7 个 Python 包到 PyPI，创建 Git tag 与 GitHub Release。
- 预发布：`qegg pre alpha|beta|rc` 写入 `.quailegg/pre-release.lock`；下一次发布生成对应渠道版本，预发布不写 `CHANGELOG.md`、不消费记录；`qegg pre exit` 后回到稳定版。
- 发布 job 使用受保护的 `pypi` environment（已允许 `dev` 部署），`UV_PUBLISH_TOKEN` 来自 environment/repo secret；不要在仓库里提交 token。
- 发布前校验由 `[verify].commands` 执行：`uv run ruff check .` 与全量 pytest（排除 browser/network/slow/llm）。
- 中断恢复：用 `qegg resume`（CI 或本地），或按 Actions 运行记录重跑；**不要手工创建 tag/Release、不要手改版本号**。
- 旧的 `publish.yml`（main→release）已移除；`scripts/versions.py`、`scripts/prepare_release.py`、`scripts/publish.ps1` 仅保留为历史/本地兜底，不再参与自动发布。
- 分支模型：发布不再经过 `main`/`release`；这两个分支仅为历史保留，后续可清理。`dev` 是唯一发布入口。

## 本地发布

