---
type: refactor
scope: modloader
packages:
  python@neobot-modloader: patch
  python@neobot-app: patch
---

插件版本号只认 plugin.toml：Plugin(version=...) 保留但不再生效，单文件插件版本固定 0.1.0。
