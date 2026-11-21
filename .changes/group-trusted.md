---
type: feat
scope: bot
packages:
  python@neobot-app: minor
---

user_identity 支持 kind=user/group 的映射；管理员命令 /linkqq（trusted）与 /linkgroup 可写可信身份，agent 工具只写展示映射、不参与权限；权限检查只认 trusted 映射，并内置开放平台默认开发者 9000000000001 为超级管理员；提示词/群名单展示真实群号。
