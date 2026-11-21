---
type: fix
scope: reply
packages:
  python@neobot-app: patch
---

反引号包住的方括号/圆括号命令（`[ -f config.toml ]`、`(cd /tmp && make)`）不再被误判成注记：反引号照常去掉、命令整段不再被空格拆条；正文自带 U+E000/U+E001 时占位符不再串号，未闭合与单行三反引号围栏不再把裸反引号发给用户。
