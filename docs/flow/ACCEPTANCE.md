# spec(13) 验收记录（A1–A8）

> 本文件是 spec(13) §5 验收口径的逐条实测记录。命令可复跑；数据来自本轮实测。

## A1 图数量与覆盖

- `docs/flow/` 下共 **30 张图**（spec 原计划 12 张；按模块规模审计扩到 30 张，依据见 SPLIT-MAP.md §2）。
- 每张图头部 `covers:` 声明的路径全部存在（由 `check_flow_diagrams.py` F1 逐条校验）。
- 验证：`uv run python scripts/flow/check_flow_diagrams.py --strict-drift` -> 阻断 0 项、警告 0 项。

## A2 全局图可走通

- `00-overview.md` 从「进程启动 cli:main」画到「自身发言入队 / 有界拆除」，范围段给出到 01/02/02b/02c/03/03b/04/05/10 的跳转。
- 6 个折叠细节块：装配顺序、启动 13 步（含 CLI 路径差异）、入站两道 dict 守卫、事件入口、队列不是分发器、停机与软重启。

## A3 单图规模

- mermaid 块总数 **363**，折叠细节块总数 **200+**（每图 5–12 个）。
- 检查口径：单块有效行 ≤120 为**阻断**；节点数 >40 仅提示（排版会让节点数虚高，行数才是客观上限）。
- 验证：F3 全部通过，最大块 26 节点 / 28 行。

## A4 可视化

- 本地：`uv run python scripts/flow/view_flow.py`（只读 HTTP 服务；细节默认折叠，可逐个展开/收起，也有展开全部）。
- 截图：`docs/flow/shots/` 共 34+ 张 PNG（每图收起态，另有展开态）。
- 离线：mermaid 运行时随仓库分发（`scripts/flow/vendor/mermaid.min.js`），不依赖 CDN。
- 导出：`view_flow.py --export` 生成自包含单文件 HTML，便于分享。

## A5 漂移检测

- 改 `covers:` 范围内任一 `*.py` 后，F2 报「图可能过期」并列出最近改动文件；`--strict-drift` 下为阻断。
- 验证：单测 `test_f2_warns_then_blocks_on_drift` 覆盖；本地默认只警告，CI 阻断。

## A6 坏样例阻断

- 缺 `covers` 路径 -> F1 阻断；缺必需章节/折叠块、`flow` 名与文件名不一致 -> F1/F3 阻断。
- 验证：单测 16 例覆盖（F1 三类、F3 四类、F2 两态、盖章幂等、哈希口径、真实目录健康检查）。

## A7 锚点可对账

- 自动核对：`uv run python scripts/flow/acceptance_anchors.py`
  - 图中 `文件:行号` 锚点共 **1372** 个；唯一命中且行号在范围内 **814** 个；
  - 同名文件多候选、经上下文路径或行号范围消歧后命中 **552** 个；**0 个错配**；
  - 未能解析 **6** 个，均为文档性引用（`packages/chat/.../models.py` 这类省略写法 2 个、逻辑组件名 2 个、非源文件引用 2 个），不是错误锚点；
  - 通过率 **99.56%**（可解析锚点 100% 落在文件行号范围内）。

## A8 「改了什么 -> 更新哪张图」

- `docs/flow/SPLIT-MAP.md` §1 覆盖全部 30 张图（文件链接 + 覆盖范围 + 最近核对提交）；§3 另有 100+ 条代码事实台账（W1–W59 + FINDINGS.md）。

## 可执行防线

| 防线 | 位置 | 行为 |
|---|---|---|
| F1/F3 | `.githooks/pre-commit` | 改了 `docs/flow/*.md` 才跑，阻断提交 |
| F1/F2/F3 | `.github/workflows/ci.yml` | `--strict-drift` 全阻断 |
| 逐块渲染校验 | CI「流程图逐块渲染校验」（continue-on-error） | 363 个 mermaid 块全部渲染通过 |
| 定向单测 | `app/tests/modules/test_flow_diagrams.py` | 16 例 |
| 锚点审计 | `scripts/flow/acceptance_anchors.py` | 1372 个锚点自动核对 |

复跑命令：

```powershell
uv run python scripts/flow/check_flow_diagrams.py --strict-drift
node scripts/flow/verify_flow_render.mjs
uv run python scripts/flow/acceptance_anchors.py
uv run pytest app/tests/modules/test_flow_diagrams.py -q
```
