# 网页面板前端（dashboard/frontend）

NeoBot 面板的前端源码。构建产物输出到上一级 `web/`，**随包分发并入库**，因此使用面板不需要 Node.js。

## 技术栈

- React 18 + **TypeScript**（`strict: true`）
- Vite 5 + `@tailwindcss/vite`（Tailwind CSS v4，CSS-first 配置）
- 类名合并：`clsx` + `tailwind-merge`（统一走 `src/utils/cn.ts`）
- 图标：`lucide-react`（统一走 `src/components/Icon.tsx`）
- 测试：Vitest + Testing Library（jsdom）
- 包管理器：**pnpm**（`pnpm-lock.yaml` 必须提交）

## 常用命令

```bash
pnpm install            # 安装依赖
pnpm run dev            # 本地开发（默认 5173，代理 /api 与 /image 到 9981）
pnpm run lint           # ESLint（0 error 才允许提交）
pnpm run typecheck      # tsc --noEmit（strict）
pnpm run test           # Vitest 单元测试
pnpm run build          # 构建到 ../web
pnpm run verify         # 上面四件事一次跑完
```

## 约定（改代码前请先读）

1. **改了 `src/**` 必须重新 `pnpm run build` 并提交 `../web/` 的产物**。CI 的 `frontend` job 会构建后比对 `git diff -- web/`，不一致直接失败；`.githooks/pre-commit` 也会给出提醒。
2. **样式迁移期双轨制**：`src/styles/theme.css` / `panel.css` 是既有样式（类名仍在使用），`src/styles/tailwind.css` 通过 `@theme inline` 把同一批 CSS 变量桥接成 Tailwind 工具类（`bg-brand` / `text-muted` …）。新代码优先用工具类；覆盖组件默认样式一律用 `cn()`。
3. **层级只能取自令牌**：`--z-sidebar/--z-header/--z-panel/--z-dropdown/--z-tooltip/--z-modal/--z-toast`，不要新增魔法数字。
4. **滚动契约**：body 永不滚动；`.content` 是通用页面的滚动容器，工作区（两栏）页必须用 `WorkspaceLayout`，滚动发生在 `workspace-scroll` 上。
5. **数据获取走 query 层**：`src/data/useQuery.ts` + `queryKeys.ts`。同一份数据在全应用共享一个 key（例如 `/api/system` 的 `QK.system`），不要各页各自 `setInterval` 轮询。
6. **接口返回类型以 `src/api/types.ts` 为准**，它对应 `../api.py` 的响应结构；后端改字段先改这里，TS 会把所有受影响调用点标出来。
7. **图标只用 `src/components/Icon.tsx` 或 lucide 组件**，不要新增手写内联 `<svg>`（图表类 `LineChart`/`Sparkline` 例外）。
8. **错误提示用 `<InlineAlert>`、按钮用 `<Button>`、表单行用 `<FormField>`**（`src/components/ui/`），不要各页重写一遍结构。
9. **开发服务器代理必须保留浏览器 Host**：`vite.config.ts` 的 `/api`、`/image` 代理写成对象形式并显式 `changeOrigin: false`。后端对 `/api/auth/login`、`/api/auth/setup` 会校验 `Origin` 与 `Host` 同源（防 CSRF），而字符串简写会被 Vite 展开成 `{ target, changeOrigin: true }` 把 Host 改写成 `localhost:9981`，导致开发模式登录恒定 403「跨站请求已被拒绝」。

## 目录结构

```
src/
  api/          client.ts（鉴权/CSRF/401）· endpoints.ts（接口封装）· types.ts（契约类型）
  components/   布局与通用组件；ui/ 下是基础件（Button/InlineAlert/FormField）
  data/         queryCore.ts（缓存/去重/失效）· useQuery.ts（React 绑定）· queryKeys.ts（key 与轮询周期）
  pages/        Dashboard/Plugins/ConfigManager/System/Usage/Bots/Logs/Login
                config/ 与 plugins/ 下是按面板/视图拆出的子组件
  styles/       tailwind.css（基座+令牌桥接）· theme.css · panel.css · workspace.css · plugins.css
  test/         Vitest 用例与 setup
  utils/        cn.ts（类名合并）· format.ts · paths.ts
```
