# NeoBot 网页面板前端

React + TypeScript 前端，随官方 `dashboard` 插件分发。源码在本目录，产物输出到 `../web/` 并入库；使用面板不需要安装 Node.js。

开始开发前阅读：

- [ARCHITECTURE.md](./ARCHITECTURE.md)：模块边界、状态归属、接口与新增功能流程。
- [DESIGN.md](./DESIGN.md)：视觉令牌、控件、滚动、响应式与界面验收。
- [网页面板功能文档](../../../../../../docs/04-功能文档/网页面板.md)：产品行为、权限、部署与禁止抓取规则。

## 安装与运行

```bash
pnpm install --frozen-lockfile
pnpm run dev             # 默认 5173；API 代理到本机 9981
```

Windows PowerShell 可以使用 `pnpm.cmd`。开发代理必须保留 `changeOrigin: false`，否则登录接口的 Origin / Host 同源校验会失败。修改 `NEOBOT_API_TARGET` 只影响开发环境，生产资源不携带代理地址。

## 统一验证

```bash
pnpm run verify
```

验证依次执行格式检查、零警告 ESLint、TypeScript、全部前端测试、演示接口契约测试和生产构建；任一步失败立即返回非零退出码。组件测试使用两个 worker，避免同时运行的浏览器与开发服务造成过度并发。

独立命令用于定位问题，不替代提交前完整验证：

```bash
pnpm run format          # 只格式化本前端，不影响仓库 Python 文件
pnpm run format:check
pnpm run lint
pnpm run typecheck
pnpm run test
pnpm run test:preview    # 随机回环端口上的演示 HTTP 契约，不占用 18881
pnpm run build           # 重建 ../web；不要手工编辑构建产物
```

改动前端源码后，源码与重建的 `web/` 必须一起提交。生成的锁文件与分发资源不手工格式化。

## 自动更新

业务页面默认自动更新，节奏集中在 `src/data/queryKeys.ts`：日志正文增量为 1.5 秒，资源、运行状态、最近日志与聊天流为 5 秒，机器人与概览为 10 秒，插件列表为 20 秒，服务、分析及编辑文档为 30 秒，用量与消息趋势为 60 秒。已有差异化排行周期继续按该文件定义。

时钟共用 `data/autoRefresh.ts`：隐藏/离线暂停，回来后补读，同一订阅不重叠请求。自有状态编辑器使用 `useAutoRefresh`；有草稿、待填密钥、保存操作、输入焦点、非法 JSON 或弹窗时暂停替换文档，回包再次检查编辑世代和原始保存版本。自动读取不触发写入、草稿确认或成功通知；失败保留旧内容和重试入口。

## 隔离演示

两个终端均在本目录运行：

```powershell
# 终端一：所有读写仅发生在虚构内存数据中
node scripts/preview-api.mjs

# 终端二
$env:NEOBOT_API_TARGET = 'http://127.0.0.1:18881'
pnpm run dev -- --host 127.0.0.1
```

演示密码为 `neobot-demo`。夹具只监听回环地址，不启动机器人、不读取真实配置或密码；重启会重置内存写入。启动参数 `--scenario=long`、`--scenario=empty`、`--scenario=readonly` 分别用于长内容、空态与只读检查。夹具实现按职责放在 `scripts/preview/`，不参与生产构建。

隔离插件列表包含默认停用的虚构 `speaking_schedule`，初始配置为 `timezone = "Asia/Shanghai"`、空默认窗口与空覆盖范围。可在插件原配置表单中添加窗口、拖动滑块、输入精确分钟并保存；数组只写入当前演示服务内存，启用状态不会随配置保存变化。`test:preview` 覆盖该数组保存、版本冲突和服务间隔离契约，不能代替真实 Bot 的时段门禁验收。

界面验收覆盖 390px / 1366px / 1920px、明暗主题、正常 / 长内容 / 空态 / 只读；具体项目见 [DESIGN.md](./DESIGN.md#验收清单)。记录结果时区分隔离演示与真实实例，不把虚构接口验证写成真实保存或运行操作验收。

## 代码入口

| 位置                                            | 职责                                                 |
| ----------------------------------------------- | ---------------------------------------------------- |
| `src/App.tsx` / `src/app/routes.ts`             | 应用装配与唯一业务页面目录                           |
| `src/auth/`                                     | 鉴权上下文、探测与登录门禁                           |
| `src/api/` / `src/data/`                        | HTTP 契约、会话/CSRF、缓存与轮询                     |
| `src/notifications/` / `components/InfoBar.tsx` | 通知发布与唯一展示宿主                               |
| `src/components/ui/`                            | 按钮、页头、选择器、确认、骨架等基础组件             |
| `src/components/schema/`                        | 动态配置字段与集合编辑                               |
| `src/pages/`                                    | 页面入口；领域子目录存放编排 hook、展示与纯工具      |
| `src/hooks/` / `src/utils/`                     | 编辑守卫、动效偏好等共享能力与纯函数                 |
| `src/styles/`                                   | 设计令牌与按职责分组的全局样式；仅由 `main.tsx` 引入 |
| `src/test/`                                     | 用户行为回归、环境适配与统一 mock                    |

Motion 负责业务页与通用组件动效，GSAP 仅随登录路由加载；增强编辑器使用按需加载的 CodeMirror。字体本地分发，不请求外部字体服务。依赖版本以 `package.json` 和 `pnpm-lock.yaml` 为准。
