---
type: feat
scope: logging
packages:
  python@neobot-app: patch
---

消息入队后的唯一 INFO 明细日志（event=message.enqueued）带上意愿判定结果（probability / should_reply / reasons）与会话、消息预览；被@、屏蔽、睡眠、私聊延迟、意愿服务缺失各分支都有明确原因。入站「收到消息」摘要降为 DEBUG，避免同一消息两条 INFO。
