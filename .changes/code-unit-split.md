---
type: fix
scope: reply
packages:
  python@neobot-app: patch
---

反引号包住的行内代码/命令在分句前替换成占位符，整段不再被空格切断、空格也不丢；还原时去掉两侧反引号，引用型内容（`cancel`、`*(note)*`）保留反引号。系统提示词同步要求发命令时用反引号标注。
