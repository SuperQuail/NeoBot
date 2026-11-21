---
type: fix
scope: commands
packages:
  python@neobot-app: patch
  python@neobot-adapter: patch
  python@neobot-modloader: patch
---

修复 a13 通配符/身份重建的已知问题：权限检查先于 at_args 报错；self 只在声明槽位识别；多槽只填可用目标；/linkqq 按注入槽位剥离目标；PluginCommand 透传 at_args。身份重建要求 DB 证据（同一 openid 收到多个真实 QQ 旧行），aux 快照与 core 快照配对，先回滚再拍启动备份，异常时回滚 core/agent/插件/aliases，无快照时清空映射；回滚后同启动完成身份迁移。补对应回归测试。
