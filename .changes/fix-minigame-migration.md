---
type: fix
scope: bot
packages:
  python@neobot-app: patch
---

修复小游戏插件库 v2→v3 重建表用 SELECT * 按位置拷贝导致 mg_profile 的 user_name/score/best_score 等列错位的问题，v3 改为显式列清单拷贝。minigame 新增 Migration v4、streaming_parser 新增 Migration v3：借 data/qqbot/identities.json 把插件库里的旧 13 位合成号用户/群 ID 改写成官方 openid（积分/签到/运势/榜单/漂流瓶/流水、直播订阅/群设置），无映射或目标 openid 行已存在时保留旧数据、不删除。
