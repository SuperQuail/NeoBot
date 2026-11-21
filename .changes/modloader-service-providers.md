---
type: fix
scope: modloader
packages:
  python@neobot-modloader: patch
---

修复插件服务依赖的两条遗留缺陷：停用的高优先级提供者不再占住服务名，使用方自动回落到下一个可用提供者，停用/恢复时保持运行；注册失败不再留下幽灵提供者，声明只在注册成功后写入，失败后可立即重试。另补 load_registered 跳过原因日志、插件升级工具识别宿主服务，并把服务模块纳入 08b 流程图。
