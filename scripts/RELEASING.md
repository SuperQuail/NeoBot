# 检查与发布

## GitHub Actions

- `.github/workflows/ci.yml`：PR 的 Python 静态检查/测试、前端 lint/类型/测试/构建及入库产物一致性检查；同时可由发布工作流复用。
- `.github/workflows/publish.yml`：main 推送后通过 GitHub API 确认该提交来自合并 PR，直接推送不发布。对合并提交重新运行 CI，通过后才检测版本、构建和上传。
- CI 和发布流程只读检查源码版本及锁文件，不自动改版本、不更新锁文件，也不提交或推送代码；无需 main 写权限。

### 首次配置

1. 创建 GitHub environment `pypi`（可配置审批、仅允许 main 部署）。
2. 在该 environment 或仓库 Secrets 中添加 `UV_PUBLISH_TOKEN`，需有全部 7 个工作区发布包的上传权限。根项目 `neobot` 没有 build-system，不上传。

### 手动更新版本

1. 在同一个 PR 中手动把以下 8 个 `pyproject.toml` 的 `project.version` 更新为一致且递增的 SemVer 版本，例如 `1.0.0-alpha.23`：
   - `pyproject.toml`
   - `app/pyproject.toml`
   - `packages/adapter/pyproject.toml`
   - `packages/chat/pyproject.toml`
   - `packages/contracts/pyproject.toml`
   - `packages/memory/pyproject.toml`
   - `packages/modloader/pyproject.toml`
   - `packages/storage/pyproject.toml`
2. 在仓库根目录手动执行 `uv lock`，将更新后的 `uv.lock` 与上述版本变更一起提交到同一 PR。CI 使用锁定依赖，发布流程只执行 `uv lock --check`，锁文件过期会失败。
3. 合并 PR 后自动检测是否需要发布；普通代码 PR 无需修改版本。

### SemVer 校验

版本格式遵循 [SemVer 2.0.0](https://semver.org/lang/zh-CN/)，由 `scripts/semver_validation.py` 统一校验：

- 必须是 `X.Y.Z`，可带 `-先行版本` 和 `+编译信息`；主/次/修订号及纯数字先行标识符不得有前导零。
- 拒绝 `1.0`、`v1.2.3`、`1.0.0a23`、`01.2.3`、`1.0.0-alpha.01`、空标识符、空白和非 ASCII 字符。
- 可手动运行 `python scripts/versions.py 1.0.0-alpha.24` 批量更新工作区版本。目标版本在文件扫描、确认和写入之前校验；非法则退出且不改文件。该脚本不会由 CI 自动调用，也不会更新锁文件。
- SemVer 合法不等于 PyPI 可发布。例如 `1.0.0+build.01` 和任意先行标签可以通过手动版本脚本的 SemVer 校验，但发布入口还要求兼容 PyPI/PEP 440；不兼容会单独报错，绝不自动删改版本信息。

### 版本检测与上传

`scripts/prepare_release.py --base-ref <推送前的提交>` 比较根项目当前版本与推送前版本；GitHub Actions 传入 `github.event.before`。脚本只检测，不修改任何项目文件，并通过 `GITHUB_OUTPUT` 输出原始 SemVer `version` 和 `publish=true/false`。

- 先校验全部工作区版本的 SemVer 格式及 PyPI 兼容性；任一非法都会报错停止，不查询 PyPI、不上传，即使版本未变也不放行。PyPI 历史版本和 Git 基线仅作 PEP 440 比较，允许历史的规范化拼写。
- 根版本未变：不查询 PyPI，输出 `publish=false`；跳过发布凭据检查、发布 job 的 Node/pnpm 安装、构建和上传，合并 PR 的 CI 门禁仍运行。
- 根版本有变：要求 8 个项目版本一致，且相较推送前版本递增；手动目标版本若低于 PyPI 已有版本也会失败。校验失败立即中止。所有版本均由维护者手动选择，脚本不会自动递增。
- PyPI 已有全部 7 个包的当前版本：输出 `publish=false`，跳过上传。部分包缺失当前版本：输出 `publish=true`，构建并补齐发布；`uv publish --check-url` 跳过已存在的文件。
- PyPI 的 PEP 440 规范化仅用于版本比较和构建/发布，例如 `1.0.0-alpha.23` 对应 `1.0.0a23`；不会回写或改变仓库中的 SemVer 拼写。
- PyPI 只有 404 视为新包；网络错误、鉴权/服务错误或无效响应均中止，不猜测版本。

若上传部分失败，且仍有包缺失当前版本，可重跑该版本变更对应的工作流补齐发布。若所有包的当前版本均已建立，但个别 wheel/sdist 文件缺失，自动流程会跳过，需使用下方本地 `publish.ps1` 补齐同一版本的文件。后续无版本变更的 PR 不会触发补发。不要用旧版本运行覆盖新发布；多个 main 推送的等待运行仍受 GitHub concurrency 队列规则影响。

## 本地发布

要求已安装 uv、Node 22 和前端 `package.json` 指定的 pnpm。先按上述流程手动更新版本和锁文件。

```powershell
# 检查锁文件，不修改它
uv lock --check

# 无需 token，不上传；执行完整构建并联网检查 PyPI 已有文件
./scripts/publish.ps1 -DryRun

# 上传当前仓库版本，不自动改版本
$env:UV_PUBLISH_TOKEN = '你的 PyPI API token'
./scripts/publish.ps1
```

发布脚本可从任意目录调用；首先运行 `prepare_release.py --check-only` 离线校验所有版本，失败即停止（`-DryRun` 同样校验）；然后依次执行 `pnpm install --frozen-lockfile`、lint、typecheck、test、build，再清理 `dist/`、构建全部 Python 包并发布。任何步骤失败都会中止。`dist/` 是本次构建的输出目录。
