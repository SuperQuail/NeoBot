---
type: fix
scope: modloader
packages:
  python@neobot-modloader: patch
---

插件 PyPI 依赖安装命令显式带 `--python <当前解释器>`（uv 不再因宿主 cwd 是数据目录而找不到目标环境）；面板安装/重载插件时先读 `plugin.toml` 装缺失依赖再导入模块，顶层 import 第三方库的插件不再因导入早于安装而永远装不上。
