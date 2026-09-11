# NeoBot 星舰 · 前端

这是官方 `starship` 插件的前端工程：three.js 第一人称 3D 星舰，把网页面板的
8 个菜单做成舰上的全息终端。

## 构建

产物输出到上一级目录的 `web/`，随插件包一起分发，**部署方不需要 Node 工具链**：

```bash
pnpm install
pnpm build        # 等价于 vite build，输出 ../web
```

开发时用面板已经跑起来的实例做后端代理：

```bash
pnpm dev          # http://localhost:5174/game/
```

`vite.config.ts` 里把 `/game`、`/api` 代理到面板端口（默认 9981）。

## 目录

| 路径 | 作用 |
| --- | --- |
| `src/core/` | 渲染循环之外的通用设施：输入、碰撞、玩家控制器、HUD、音频、动作接口 |
| `src/world/` | 飞船：甲板网格、几何与碰撞生成、舱室家具 |
| `src/space/` | 舰外太空：星空、行星、小行星流、过往飞船、跃迁特效 |
| `src/ui/` | 终端框架：全息屏、Canvas 控件库、文本输入、终端运行时 |
| `src/terminals/` | 各菜单终端与小游戏站点（新增终端在这里注册） |
| `src/minigames/` | 小游戏框架与玩法实现 |
| `src/net/` | 控制台 `/api/*` 与游戏 `/game/api/*` 客户端 |

## 增加一个小游戏（两条路）

1. **只加玩法**：在 `src/minigames/` 新建模块，实现 `MinigameModule`
   （`screen` 模式画在全息屏上 / `world` 模式接管相机），调用
   `registerMinigame(...)`，并在 `src/minigames/index.ts` 里 import 一次；
2. **连元数据一起加**：在插件Python侧的 `minigames.py` 注册目录条目，
   或由其它插件调用星舰插件的能力 `minigame.register`。

服务端会校验成绩上限并持久化到插件自己的 SQLite 数据库。
