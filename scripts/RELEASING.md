# 检查与发布

## GitHub Actions

- `.github/workflows/ci.yml`：PR 的 Python 静态检查/测试、发布版本逻辑测试、前端 lint/类型/测试/构建及入库产物一致性检查；同时可由发布工作流复用。
- `.github/workflows/publish.yml`：main 推送后通过 GitHub API 确认该提交来自合并 PR（支持 merge/squash/rebase），直接推送不发布。对合并提交重新运行 CI，通过后才检测版本、构建和上传。
- pnpm Action 显式读取前端目录的 `package.json`，不再在仓库根目录寻找 `packageManager`。Node 使用 22，setup-node 使用 v6。

### 首次配置

1. 创建 GitHub environment `pypi`（可配置审批、仅允许 main 部署）。
2. 在该 environment 或仓库 Secrets 中添加 `UV_PUBLISH_TOKEN`，需有全部 7 个工作区发布包的上传权限。根项目 `neobot` 没有 build-system，不上传。
3. 允许发布 job 的 `GITHUB_TOKEN` 写入 main：工作流会提交版本和 `uv.lock`。若分支保护不允许机器人直接提交，需要先调整发布权限/规则，否则工作流会在上传前失败；不会强推或绕过保护。

### 版本策略

`scripts/prepare_release.py` 查询每个可发布包的 PyPI release 历史（含预发布），统一更新根项目和所有工作区成员的 `project.version`。

- 本地版本必须一致。如果本地版本高于全部已发布版本，使用本地版本。
- 否则取本地/PyPI 最大版本并递增：如 `1.0.0a22` → `1.0.0a23`；稳定版 `1.2.3` → `1.2.4`。不自动把 alpha 转成正式版。
- 不支持 dev/post/local 版本时直接失败，避免错误递增。PyPI 只有 404 视为新包；网络错误、鉴权/服务错误、无效响应均中止，不猜测版本。
- 更新 `uv.lock`，完成前端和 Python 构建/发布预检后，先提交版本再上传。并发 main 更新导致非快进推送时会中止，绝不覆盖新提交。
- 上传使用 `uv publish --check-url`，跳过已存在的文件。版本回写使用 GITHUB_TOKEN，不会递归触发新工作流。

若上传部分失败，可在包含已回写版本的最新 main 上运行下面的本地发布脚本，补齐同一版本缺失文件。不要盲目重跑旧提交：旧运行的版本回写可能因 main 已前进而被拒绝。多个 main 推送的等待运行受 GitHub concurrency 队列规则影响，最新合并会包含前面合并的代码。

## 本地发布

要求已安装 uv、Node 22 和前端 `package.json` 指定的 pnpm。

```powershell
# 无需 token，不上传；依然执行完整构建并联网检查 PyPI 已有文件
./scripts/publish.ps1 -DryRun

# 上传当前仓库版本（本地脚本不会自动改版本）
$env:UV_PUBLISH_TOKEN = '你的 PyPI API token'
./scripts/publish.ps1
```

脚本可从任意目录调用；依次执行 `pnpm install --frozen-lockfile`（本仓库对应 `npm ci` 的操作）、lint、typecheck、test、build，再清理 dist、构建全部 Python 包并发布。任何步骤失败都会中止。`dist/` 是本次构建的输出目录。
