# 前端与渲染约定

## 现状：零构建

卡片的"前端"就是 `templates/` 下的 6 个 **纯 HTML + 内联 CSS** 模板：

``
templates/
├── card_sakura.html / card_neon.html / card_minimal.html               # 开播与下播卡片
├── overview_sakura.html / overview_neon.html / overview_minimal.html   # 开播状态总览
└── fonts/FusionPixel8px-zh_hans.woff2 (+ OFL 许可)                      # 随包分发的中文字体
``

渲染路径：Python 侧把数据填进 `{{占位符}}`（`render.py`），交给宿主 `ctx.screenshots`（Chromium + CDP）出 PNG，再 `ctx.send_image` 发出。

模板里不允许出现：`<script>`、`@import`、任何 `http(s)://` 外链。原因是截图端口用 CDP `setDocumentContent` 把 HTML 写进 `about:blank`，**`file://` 与相对路径资源都加载不到**，所以：

- CSS 必须内联在模板的 `<style>` 里；
- 图片必须由渲染端转成 data URI 再填进去（头像、封面都是这么处理的）；
- 字体以 `FontFace` 交给截图端口，由端口生成 data URI 的 `@font-face`。

这一层没有 Node、没有任何构建步骤，改模板就是改 HTML，部署侧自然也不需要前端工具链。

## 面板直播订阅页

`web/subscriptions/` 是直接分发的原生 HTML / CSS / JavaScript 页面，由 `panel.py` 的 `plugin.view()` 注册，不需要 Node 构建。入口引用宿主 `_sdk.js` 和 `_ui.css`，自定义样式使用同步的主题令牌；页面不访问宿主 DOM、登录凭据或外部接口。

独立页面不提供折叠：桌面左侧选群、填写链接和识别，右侧显示通知卡片／文字预览；窄屏改为单列。下方直接展示本群设置、可按群筛选的订阅列表和监听健康。预览可切换图片、文字、适应宽度及原始尺寸，正文使用自然高度，只有预览和宽表格保留局部滚动。

群设置通过 `groups.settings.get/update` 读取和保存，显示继承状态；保存卡片风格、开播／下播 AI 回复与新订阅默认推送。修改后须先保存或放弃再切群、预览或订阅；刷新获得不同设置时旧预览失效。已有订阅的推送开关不被群默认值覆盖。群目录读取失败不能阻止本地订阅列表和健康状态读取，失败统一使用宿主 InfoBar。

接收群来自 `get_group_list`，机器人账号来自标准 `get_login_info`，不读取适配器未承诺的 `self_id` 属性。只有群目录非空时才查询账号；空群目录保持合法空结果，不能影响已有订阅管理。

`panel_guide.py` 的订阅教程从空群与空链接开始，`onGuideStep()` 逐步重建群、链接、设置、预览、列表和健康状态；异步旧章节回包不能覆盖新章节。`panel_form_guide.py` 提供完整配置表单的独立样例，演示填写、错误与修正、模拟保存和生效。所有教程均不调用真实写接口。

## 将来要引入真正的构建时

如果以后需要 React/Vite 这类工程，沿用 NeoBot 官方插件约定：

| 目录 | 内容 | 入库 | 分发 |
|---|---|---|---|
| `frontend/` | 源码，只有开发者需要 | 入库 | **不**分发 |
| `web/` | 构建产物（`index.html` + `assets/index-<hash>.{js,css}`） | **必须入库** | 分发 |

构建基线：`base: './'`（支持面板子路径部署）、`build.outDir = '../web'`、`assetsDir = 'assets'`、`sourcemap: false`。

**产物与源码必须在同一个 commit 内更新**，且 `node_modules/` 永不入库（NeoBot 面板安装插件走 GitHub 归档 zip，有压缩包 64MB / 解压 256MB / 条目 5000 的硬上限）。

## 接入与验收

页面只通过已声明的动作操作业务，读／管理权限和写锁由宿主校验；不再需要另行注册 `DashboardWebExtension`。入口、资源边界、主题、暂停和教程规则见 [插件设置界面](../../../../../../docs/04-功能文档/插件设置界面.md)。修改后重新导出契约，并验证桌面、窄屏、明暗主题、只读模式和教程回放；修改宿主前端时另行重建面板 `web/` 产物。

