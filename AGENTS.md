# AGENTS.md

## Pull Request/Commit Message

> 本仓库用 **squash 合并**，仓库设置为 `PR_TITLE` + `PR_BODY`：
>
> - main 上的**标题 = PR 标题**（永远，与提交数无关）
> - main 上的**正文 = PR 描述**
> - **提交信息不进 main**（除非有人改用 rebase 合并）
>
> 所以：**标题写 PR 标题，正文写 PR 描述**——这两处就是永久历史，
> commit message 的规矩一字不差地适用。
>
> 合并对话框里会预填最终落地的那条 squash 信息，合并前看一眼——那是最后一次人工把关。

### 速查

```
fix(dashboard): 折线图宽度跟随容器

- viewBox 改按容器实测宽度计算，不再写死 600
- 移除按金额切换小数位的分支

验证：pnpm run verify 全绿；1440px / 820px 实测 viewBox 与渲染宽度一致
```

- 标题写 **PR 标题**：`<type>(<scope>): 一句话概括`，**不罗列子改动**
- 正文写 **PR 描述**：子改动逐条列，末尾写**真跑过**的验证
- 一个 PR 装多个改动没问题——标题概括，描述里列清即可
- 修了 issue 就在描述末尾写 `Closes #NN`（详见第 7 节）——贴链接**不算关联**

### 1. 标题

| 部分 | 要求 |
|---|---|
| `type` | 只能取 `feat` `fix` `docs` `refactor` `test` `chore` `perf` |
| `(scope)` | 模块或包名，小写，可省略；同一 PR 内保持一致 |
| 简述 | **动词开头的祈使句**，写「做了什么」，不写「动了哪些文件」 |

破坏性变更加 `!`，并在 body 写迁移步骤：

```
refactor(modloader)!: 插件 API 改为能力注册制
```

**硬性要求**

CI 用 [scripts/check_pr_title.py](scripts/check_pr_title.py) 校验 **PR 标题**
（见 [.github/workflows/pr-title.yml](.github/workflows/pr-title.yml)）；
提交信息不进 main，不在校验范围内，但**建议同样写合规**——仓库也允许 rebase 合并。

- 显示宽度 ≤ 72（中文/全角按 2 计）
- 结尾不加句号
- 不要自己加 `(#NN)`——squash 合并时 GitHub 会自动补
- 不用 `update`、`修复若干问题`、`优化代码` 这类空话

**简述用动词开头**（约定式提交的祈使语气）

`修复…` `添加…` `移除…` `重订…` `简化…` `支持…`。
不要用「让…」「关于…」「为了…」这类迂回说法——仓库历史里 30 条标题有 24 条是动词开头。

**概括，不是清单**

判据：标题里每个并列项，能不能独立成一条 body 条目？

```
❌ feat: 降低上手门槛 —— 出厂模型库改为空 + 面板接入模型教程 + 懒人安装包
   每一项都能独立成一条 → 这是清单，明细下沉 body

✅ fix: 修复取消、重启与配置相关的缺陷
   「取消、重启与配置」是领域词，读者靠它检索 → 可以留在标题里
```

一句话概括不出来时，按这个顺序降级，别硬编一个空主题：

1. 有共同主题 → `fix: 加固回复输出与重启稳定性`
2. 只有共同领域 → `fix: 修复取消、重启与配置相关的缺陷`
3. 连领域都不同 → `fix: 修复多处独立缺陷`，明细全交给 body

### 2. 描述

按改动风险选档，**拿不准往高一档写**。分档只决定填哪几段，不限制行数——该讲清楚的根因不要为了短而省。

| 档位 | 适用 | 必填段 |
|---|---|---|
| 轻 | `chore` `docs`、依赖、文案 | 变更、验证 |
| 中 | `feat` `refactor`、新配置、新接口 | 需求、实现、验证、行为变化 |
| 重 | bug 修复、并发与生命周期、破坏性变更、发版 | 现象、根因、修复、验证（+ 迁移） |

- **PR 描述**：按下面三档写全——**它就是 main 上的正文**
- **PR 标题**：概括（见第 1 节）——**它就是 main 上的标题**
- **提交信息**：不进 main，但仍要写清楚——评审时会看，而且仓库允许 rebase 合并，那时它会原样进历史
- 不要出现「见 PR 描述」「WIP」「临时提交」——这些话只在分支上有意义

### 3. 验证段

**只写真正执行过的命令和真实输出。**

- 好：`uv run pytest -m "…" → 4604 passed, 10 skipped, 0 failed`、`ruff 全绿`
- 没跑就写：`未验证：<原因>`
- 不允许推测，不允许把「应该能过」写成「已通过」，不允许编造测试数量或产物哈希

修 bug 尽量给「修复前 → 修复后」对照（现象、耗时、返回值、日志）。
引用代码写全 `app/src/neobot_app/xxx.py:123`，不写「相关文件」。

### 4. 提交前必须跑

```bash
uv run ruff check .            # CI 的门禁就是这一条
uv run pytest -m "not browser and not network and not slow and not llm"
uv lock --check                # 改过依赖时

# 标题自查（CI 也会校验；它将成为 main 上的提交标题）
python scripts/check_pr_title.py --title "<PR 标题>" --strict
```

- 改过前端源码：在对应 frontend 目录跑 `pnpm run verify`，并提交重建后的 `web/` 产物
- 自己改过的文件保持 `ruff format` 干净即可
- **不要顺手全量重排**：全仓库 `ruff format --check` 目前过不了（存量文件未统一格式化），重排会让 diff 无法审

### 5. 注意事项

下面每一条都是**禁止项**，不是建议：

- **禁止**直推 main，**禁止** force push 他人分支，**禁止** amend 或 rebase 别人的提交
- **禁止**为了让检查通过而改 CI 门禁、放宽断言、删除或跳过失败用例、用 `xfail` 掩盖失败
- **禁止**夹带与本 PR 无关的重构或格式化
- **禁止**提交 `.env`、密钥、token、真实用户数据（占位符要登记到 `.secretsignore`）
- **禁止**从历史里恢复已删除的调试脚本——CI hygiene job 会阻断，那些文件历史上带过硬编码密钥
- **禁止**擅自改版本号或 `uv.lock`——只在发版 PR 里按 [scripts/RELEASING.md](scripts/RELEASING.md) 做
- **禁止**留 AI 署名、工具痕迹或 `Generated with …`

### 6. 别忘了同步

- 新增/变更功能 → 更新 `docs/04-功能文档/` 对应文件
- 新增配置项 → 更新 `docs/05-配置参考.md`
- 改前端源码 → 重建并提交 `web/`（CI 会比对产物，不一致直接失败）
- 涉及版本 → 同一个 PR 内更新 8 个 `pyproject.toml` 与 `uv.lock`

### 7. 关联 issue

**本 PR 在修某个 issue 时，必须在 PR 描述里用关闭关键字把它关联上。**

只有关键字才算关联。在描述里贴一句 `https://github.com/…/issues/59` 或写「相关 issue：见 #59」
**不算**：GitHub 不会记录关系，issue 侧看不到这个 PR，合并时也不会自动关闭。

在 PR 描述末尾加一段。**每个 issue 都要带自己的关键字**——官方口径是
「多 issue 就对每个 issue 用完整写法」，别写成 `Closes #59, #60`（第二个没有关键字）：

```markdown
## 关联 issue（合并时自动关闭）

Closes #59
Closes #60
```

同一行也行，但每个都要带关键字，例如 `Resolves #10, resolves #123`。

支持的关键字（大小写不敏感，后面可跟冒号）：`close` `closes` `closed`
`fix` `fixes` `fixed` `resolve` `resolves` `resolved`。

| 关键字 | 语义 | 什么时候用 |
|---|---|---|
| `Closes`/`Fixes`/`Resolves` | 合并时**自动关闭**该 issue | 本 PR 确实修完了这个 issue——**默认用这个** |
| `Refs`/`Related to` | 只建立关联，**不关闭** | 只做了部分工作、或只是相关但未修完 |

> 注意：`Refs` 不在 GitHub 的关闭关键字表里，它只建立引用关系，不会关闭 issue——
> 这正是「分步修完、最后一步才 Closes」需要的语义。

省事与把关：

- 用 `gh` 建 PR 时把这段直接写进 `--body-file`；**不要**先建空描述再补——
  关联是随描述一起落地的。
- 合并前看一眼 PR 侧栏的 **Development / Linked issues**：那里列出了 issue，
  才说明关联真的生效了。用下面的命令核对：

```bash
gh api graphql -f query='{ repository(owner:"OWNER",name:"REPO") {
  pullRequest(number: PR) { closingIssuesReferences(first:10) { totalCount nodes { number } } } } }'
```

- `totalCount` 必须等于你打算关闭的 issue 数；对不上就是关键字没写对。
- **PR 描述与 issue 不是一对一**：一个 PR 修多个 issue 就写多个 `Closes`；
  一个 issue 被多个 PR 分步修完，只有**最后一个**写 `Closes`，前面的写 `Refs`。
- 关**别的仓库**的 issue 要写全限定名：`Closes owner/repo#123`。
- 关闭关键字只在**目标分支 = 仓库默认分支**（本仓库是 `main`）时生效；
  指向其它分支时关键字被直接忽略——既不建立关联，合并也不会关 issue。
- 没有对应 issue 的改动（文档、依赖、纯内部重构）不必硬凑一个——**别为此新建 issue**。

> 依据：[GitHub Docs — Linking a pull request to an issue](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue)

---

**规范来源**：[CONTRIBUTING.md](CONTRIBUTING.md)（分支命名、PR 流程）、
[docs/06-开发指南.md](docs/06-开发指南.md)（代码规范、测试约定）、
[scripts/RELEASING.md](scripts/RELEASING.md)（版本与发布）。

本节只写 AI 需要额外遵守的部分，不重复上述文档；与本节冲突时以本节为准。
