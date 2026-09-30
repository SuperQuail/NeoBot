# 全链路流程图（spec(13) 实现）

> 这里是 **NeoBot 全链路流程图系统**的入口：分文件 Mermaid 图 + 可折叠细节 + 本地可视化 +
> 「改代码必须同步改图」的可执行检查。
>
> **先读 [REFERENCE.md](./REFERENCE.md)**：所有图的格式、粒度与自检流程都在那里。
> 粒度对照物：[02b-willing-probability.md](./02b-willing-probability.md)（把概率算到小数点）。

## 1. 怎么用

| 想干什么 | 怎么做 |
|---|---|
| 看渲染后的图（推荐） | \`uv run python scripts/flow/view_flow.py\` —— 浏览器打开，细节默认折叠，按需展开 |
| 只看某一页并截图 | \`node scripts/flow/shoot_flow.mjs <图名>\` —— 产物在 \`docs/flow/shots/\` |
| 导出可分享的单文件 HTML | \`uv run python scripts/flow/view_flow.py --export docs/flow/_site\` |
| 改完代码后同步图 | 改图 -> \`uv run python scripts/flow/check_flow_diagrams.py --update\` -> 提交 |
| 体检所有图 | \`uv run python scripts/flow/check_flow_diagrams.py\`（CI 用 \`--strict-drift\`） |

## 2. 图清单与拆分依据

> 完整清单（每张图的 covers 与状态）在 [SPLIT-MAP.md](./SPLIT-MAP.md)；
> 写图核出的代码事实（每张图一节）在 [FINDINGS.md](./FINDINGS.md)。
> 本文件只讲用法、检查规则与更新约定。

## 3. 检查规则（F1/F2/F3）

| 规则 | 内容 | 阻断性 |
|---|---|---|
| **F1 锚点存在** | 图头 \`covers:\` 的每条路径必须真实存在；\`flow\` 必须等于文件名 | CI + pre-commit 阻断 |
| **F2 漂移检测** | \`verified_hash\` 与 covers 范围内 \`*.py\` 的内容哈希不一致 => 「图可能过期」 | 本地警告、CI \`--strict-drift\` 阻断 |
| **F3 结构完整** | 必须含 范围/流程/时序/细节/关键状态/易错点；至少 1 个 flowchart + 1 个 sequenceDiagram + 1 个折叠细节块；单块 ≤25 节点 / ≤120 行 | CI + pre-commit 阻断 |

哈希口径（工具自动盖章，别手写）：covers 范围内所有 \`*.py\` 按相对路径排序 ->
逐文件 sha256 取前 16 位 -> \`路径:短哈希\` 拼行 -> 整体 sha256 取前 12 位。

