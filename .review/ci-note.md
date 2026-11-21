补充（CI 现状，与本 PR 代码无关）：

- `PR 评审（阻断）`：发评审前是 **fail**（最后一次提交晚于最后一条评审），现在已 **pass**。
- `check`（QuailEgg PR）：红在**最后一步** `gh pr comment --edit-last -F plan.md` → `GraphQL: Resource not accessible by integration (addComment)`，是 bot 缺 PR 评论权限，不是 `qegg check --ci` 失败；建议管理员检查该 App 的 Pull requests / Issues 写权限。
- 其余检查（体积限制、分支流向、修复 PR 关联 issue、前端、CLI 模板验收、SDK 回归）全绿。
