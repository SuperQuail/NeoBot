---
type: feat
scope: config
packages:
  python@neobot-app: minor
---

配置版本升到 0.11.0：schema 默认 adapter.mode=official（新部署）；0.10→0.11 迁移为未显式配置 mode 的老配置补 onebot，显式选择保留；无 version 字段的更老配置同样按升级语义补 onebot。
