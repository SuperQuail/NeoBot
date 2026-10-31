# 前端架构与开发约定

本文描述当前代码边界和维护方式。视觉、响应式和滚动规则见 [DESIGN.md](./DESIGN.md)，运行与验证命令见 [README.md](./README.md)。

## 依赖方向

`main → App → routes / auth / Layout → pages → api / data / hooks / notifications / components`。

基础组件、数据层和 hook 不反向引用 `App` 或业务页面。ESLint 阻止业务代码导入应用入口和已移除的旧通知组件。运行时模块直接导入实际实现，避免聚合入口意外加载整片业务代码；仅类型契约可以集中 `export type`。

| 边界       | 维护位置                                                     | 约定                                                                                           |
| ---------- | ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------- |
| 页面目录   | `app/routes.ts`                                              | 路由、分组导航、面包屑、滚动外壳与骨架类型只登记一处                                           |
| 鉴权       | `auth/AuthContext.ts`、`AuthProvider.tsx`、`RequireAuth.tsx` | 页面消费 hook，不依赖入口文件；服务端仍是授权裁决者                                            |
| HTTP       | `api/client.ts`、`endpoints.ts`                              | 会话、CSRF、401 与请求封装集中处理，页面不各写一套 fetch                                       |
| 契约       | `api/types.ts` 与 `api/types/`                               | 入口只导出类型；按 common / config / models / plugins / runtime / usage / chat / archives 归组 |
| 服务端状态 | `data/queryCore.ts`、`useQuery.ts`、`queryKeys.ts`           | 同一资源共用 key、缓存与轮询；失效由实际写操作触发                                             |
| 操作反馈   | `notifications/infoBar.ts`                                   | `notify(text, tone)` 用于简单结果，`infoBar(options)` 用于结构化摘要与详情                     |
| 通知显示   | `components/InfoBar.tsx`                                     | 全应用只挂一个宿主，管理计时、焦点、详情与动效                                                 |

## 状态与生命周期

- 服务端缓存、编辑草稿、UI 选择各有归属。缓存回读不能无条件覆盖草稿，派生状态优先在渲染中计算。
- 异步查询忽略过期响应。鉴权探测以最新请求为准，设置密码后的新状态不能被较慢的启动探测覆盖。
- `useMutation` 保持执行入口稳定，同时读取最新 action / 回调 / 失效配置；回调不捕获首次渲染的旧状态。
- 页内副作用由所属 hook 或父页持有。纯展示组件接受数据与语义回调，不暗中查询或保存。
- 路由匹配沿用 Router 的大小写、尾斜杠和编码规则。业务页 Suspense 以路径为 key，切换到骨架时立即卸载旧页，释放轮询和编辑守卫。
- 不用空列表或零数值掩盖读取失败。首次读取提供骨架或可重试错误，已有数据刷新失败时保留原内容与错误状态。
- 自动更新共用 `data/autoRefresh.ts` 时钟：同一订阅串行读取，页面隐藏或离线暂停，恢复可见/在线后补读已错过的周期；卸载后取消时钟和事件。查询缓存与自有状态页面复用同一行为，不再各写 `setInterval`。
- `useQuery({ enabled: false })` 暂停首读和轮询，保留缓存与已挂载表单。思索演示开启时暂停同插件的真实资源读取，关闭后恢复；演示不能通过卸载真实表单来暂停请求。
- 编辑页面通过 `hooks/useAutoRefresh.ts` 在无草稿、无保存操作时读回文档；焦点位于输入框、非法 JSON 草稿或弹窗交互时暂停。请求发出后开始输入、保存、切换目标或离开页面，都必须在回包落地前再次检查最新状态/编辑世代。不要仅在发请求前判断 dirty，更不能为了轮询先更新编辑基线或清空待填密钥。

## 领域模块

| 页面     | 编排与纯数据                                        | 展示边界                                                   |
| -------- | --------------------------------------------------- | ---------------------------------------------------------- |
| 系统状态 | `system/useSystemState.ts`、`systemPresentation.ts` | `SystemPanels` 与维护弹窗                                  |
| 快捷部署 | `deploy/useDeployEditor.ts`、`deployModel.ts`       | 五步内容集中在 `DeployStepPanel`                           |
| 聊天流   | 父页管理查询、历史选择与跟随最新                    | 会话列表、快速预览、完整提示词、历史与详情弹窗             |
| 档案     | 父页管理筛选、版本、草稿、删除与压缩轮询            | 浏览列表、正文编辑、工具与详情弹窗                         |
| 日志     | `Logs` 管理增量缓冲、筛选与跟随；`logs/logPresentation` 统一上下文搜索与导出 | 行内展开字段、调用位置与异常，沿日志正文滚动 |
| 配置     | `pages/config/` 各面板管理自己的编辑会话            | `ConfigTreePanel` 绑定 Schema 字段                         |
| 插件     | 父页管理列表、选择、权限与操作                      | `PluginListPanel`、`PluginEditorPanel` 使用显式 props 契约 |

官方 `speaking_schedule` 的表单由 `pages/plugins/SpeakingScheduleForm.tsx` 展示默认及会话覆盖，`ScheduleWindowEditor.tsx` 负责星期、精确时间和两端滑块，`speakingScheduleModel.ts` 负责纯时间转换及周周期重叠校验。只通过现有 `onChangeField` 修改父页草稿，不自行查询或保存；`Plugins` 在现有保存入口应用相同校验，TOML 仍交由后台校验。嵌套可选字段 `next_day` / 覆盖 `windows` 在显示时使用后台默认值，不因读取改写草稿；字段修改保留未涉及的额外字段。其它插件及第三方同名插件继续使用 `SchemaForm`。保存版本、409、重读、撤销、模式切换与只读沿用原编辑会话。

拆分以状态和业务职责为依据，不按行数机械切分，也不把每个简单字段单独建文件。仅在多个调用点有同一稳定职责时提升为共享能力；领域独有的格式与数据转换留在对应目录。

### 插件配置与思索说明书

`PluginEditorPanel` 使用同一组「配置表单 / TOML / 插件页面」模式，未声明页面时隐藏最后一项。配置复用 `SchemaForm` 固定控件与 TOML 编辑器；开发者只通过模型声明类型、标题、说明、约束及有限文本提示。业务交互由 `plugin.view()` 的 sandbox iframe 承载，不再解析业务设置布局 DSL。

`PluginSettingsViews` 直接呈现所有已声明页面，不提供折叠；单页不重复标题，多页使用标题与分隔线。首次访问且上下文可用时才挂载，切回配置或打开说明书只暂停，不销毁原输入。配置草稿未保存或仍在编辑时，插件页面提示返回配置，并暂停真实操作。选中插件的配置、契约与页面资源共用 2 秒更新节奏；配置连同 schema 安全同步。页面资源 revision 改变后重建 iframe 与桥接会话，暂停或页面持有焦点时先保留原窗口，恢复后应用最新资源集合；相同资源轮询保留输入与会话。宿主持有已展示页面的最后有效契约，最后一页删除或契约暂态不可用同样经过该安全边界；实时可用状态与权限立即生效，保留窗口不延长业务授权。底部保存区只属于配置路径；业务动作和页面配置保存通过 `usePluginSettingsAccess` 接入原权限与写锁。

`Plugins` 的列表失败和 `PluginEditorPanel` 的运行、依赖、配置与草稿暂停反馈统一发布到全局 InfoBar，恢复动作放在详情中；侧栏保留最后成功读取的列表，不插入错误卡片。详情反馈依赖具体诊断值而非轮询对象身份，避免重复通知；重新读取使用最新编辑状态并保留草稿确认规则。

`PluginHtmlPreview` 为教程和动作结果提供无脚本权限的隔离预览，缩放、原图和文字查看由组件管理，样式归 `styles/plugin-html-preview.css`。`PluginConfigScene` 通过 `pluginConfigSamples` 递归清除真实 value/items、敏感默认值与样例；普通配置目标复用单字段控件，带 `form` 的目标复用完整 `SchemaForm`，按每步独立快照展示初始、填写、本地数值校验和模拟保存，样式归 `styles/plugin-form-tutorial.css`。不调用配置或动作写接口。

`PluginManualEntry` 提供唯一的“使用说明”入口，直接打开思索说明书。`PluginViewFrame` 在内联布局中接收经过会话校验的高度消息，跟随外层正文滚动；思索舞台保持独立尺寸。`public/assets/plugin-view-ui.css` 经页面根下 `_ui.css` 分发，提供宿主一致的控件和布局；`_sdk.js` 自动应用并持续同步主题令牌与 `color-scheme`，自定义样式必须消费同一主题机制。接入见 [插件设置界面](../../../../../../docs/04-功能文档/插件设置界面.md)。设置和说明共用契约、页面元信息缓存。iframe 按服务端返回的 URL（包含页面 revision）创建独立会话，更新时销毁旧桥接；不透明来源不能读取宿主 DOM、登录凭据或 CSRF。

公开入口 `public/assets/plugin-view-sdk.js` 和配套 `.d.ts` 提供 `window.NeoBotPlugin`。`pluginViewBridge` 验证当前 iframe 窗口、协议版本、请求 ID 与会话标识；动作仅能来自当前插件契约，并经过当前权限和统一写入锁。`getConfig` / `saveConfig(values, revision)` 复用当前插件的配置 API，按原规则校验版本与敏感字段，不传配置源码或磁盘路径。通知统一进入 InfoBar，导航只接受稳定目标 ID。

说明作者声明 `target`、中文说明、可选 `chapter` / `example`、配置专用 `form` 和 `demo.actions` / `demo.config`。素材页面通过 `registerAnchor(id, element)` 报告实际几何位置，目标写成 `view.<页面ID>.<锚点ID>`，无需编写坐标或播放脚本。页面订阅 `onGuideStep`，按独立样例快照重建全部演示状态，不定位或改写宿主中的真实配置草稿。

SDK 上报锚点在 iframe 及各级滚动容器中的可见范围，观察目标与祖先尺寸，并在滚动后更新；不可见或已卸载目标不再上报。思索模式不在 iframe 中绘制外扩 outline，所有场景由 `PluginPonderStage` 通过 `ponderGeometry` 在舞台内统一绘制高亮与指针。真实页面定位仍使用控件内描边，不改变其布局尺寸。

内联真实页面获得键盘焦点时，SDK 在浏览器完成自身滚动后报告焦点矩形。桥接仅接受当前窗口与会话的有效范围，演示和暂停期间不处理；`pluginViewFocus` 再检查焦点仍位于当前 iframe，只调整所属 `.workspace-scroll` 正文。不能调用跨层 `scrollIntoView` 移动固定标题或工具栏，迟到的请求不能拉回用户已经移走的焦点。

`PluginPonderScreen` 提供整屏模式、返回焦点与无障碍隔离，不复用业务弹窗外框；`PluginPonderPlayer` 编排舞台、分章时间线、字幕和键盘导航。`usePonderPlayback` 默认手动阅读，显式播放后按正文及命令场景计算时钟，暂停与页面隐藏保留剩余时长；切换说明只重置教程内容，不重挂整屏容器。`PluginPonderContents` 只消费同一份教程声明，在舞台区域提供可搜索全文；打开时暂停，选择步骤返回舞台并恢复目录按钮焦点，不增加业务查询或侧栏。舞台按内容复用实际配置控件、命令样例或隔离的同一设置页面；未映射入口的动作和资源只展示用途与结果，不虚构按钮。演示动作只返回声明样例，配置只读，不执行完成检查。打开说明时真实页面保留但暂停，关闭时归还暂停状态。真实设置写入由 `usePluginSettingsAccess` 接入父级操作锁，配置 revision、草稿和权限继续生效；只读列表不占用写锁。关闭或切换素材清理消息监听、锚点观察器与在途响应。

## 编辑与写操作

- `useEditorGuard` 发布 dirty / busy，页内离开用 `confirmAction()`，关闭或刷新使用原生 beforeunload。
- UI 权限未知或只读时禁止写入，但保留查看入口；前端禁用不代替后端授权。不得把公开登录状态当作写入授权。
- 保留配置 revision、档案 version、409 冲突恢复与危险操作确认。部署配置与密钥部分成功时分别更新基线，失败部分继续保留供重试。
- 新字段、恢复默认、数组增删排序、JSON 与快捷保存都必须执行相同权限和 busy 判定。
- 共享增强编辑器通过 `language` 区分 TOML 与纯文本。保留源文、注释、选区、撤销记录和异步加载接力；只读显式传递给 CodeMirror，不能依赖 fieldset 禁用 contenteditable。
- 字段 JSON 的非法草稿保留在当前字段内，不写入配置值；目前它尚未计入页面 dirty，离开或切分区前需修正。
- 本体、插件与提示词保存前的校验和备份仍由对应后端流程保证；界面重构不得绕过。

## 反馈、控件与样式

操作反馈只用全局 InfoBar：同一时间一条简短摘要，详情按需打开，错误、冲突和需重启消息可持续访问。缺少变更前后值时只显示路径与原因，不显示 `undefined → undefined`。原位错误仅用于真正阻塞的读取状态或字段校验。

业务页面复用 `PageHeader`、`Button`、`SelectControl`、`PageSkeleton` / `PanelSkeleton`；不为已有自动更新的页面保留常驻刷新按钮，失败区域提供重试，人工重新读取文档保留草稿确认。页头 API 只有标题、操作和显式 children，没有被忽略的说明参数。后台任务复用 `TaskStatusList`，只展示实际返回的状态、数量和进度。

所有全局 CSS 由 `main.tsx` 按既定顺序引入，令牌是唯一颜色、字体、尺寸与层级来源。业务规则回到所属文件，不在其它业务样式末尾叠补丁，也不以更高权重掩盖旧布局。新增样式职责须同步 [DESIGN.md](./DESIGN.md#样式职责)。

动效保持一次编排和可清理的生命周期：普通业务页使用 Motion，登录使用 GSAP，共享减少动态效果偏好；轮询文本与编辑器 DOM 更新不反复入场，不为退出动画保留旧的可写页面。

## 新增或调整功能

1. 确定领域与状态归属，先对齐 `api/types/` 和后端真实契约，再在 `endpoints.ts` 封装接口。
2. 新资源在 `queryKeys.ts` 登记；复用已有查询，不重复建立轮询。新业务页在 `app/routes.ts` 登记一次。
3. 编排 hook / 父页负责权限、请求、草稿和恢复；展示组件通过 props 接收数据与回调。
4. 使用现有控件与样式 owner，补充首次读取、刷新失败、空态、只读、busy 和窄屏状态。
5. 为真实分支和故障恢复写行为测试。测试 mock 路径与生产导入保持一致，内部 TS 模块使用无扩展名导入。
6. 更新功能文档或配置参考，执行完整 `verify` 并提交重建的 `web/`。验证记录区分隔离夹具、真实实例与未验证项。

## 验证边界

`pnpm run verify` 沿用仓库既有的 lint、类型、前端测试与构建流程。隔离演示接口可单独运行 `pnpm run test:preview`，格式可单独运行 `pnpm run format:check`；本轮不调整 CI 工作流或原有门禁。生成的锁文件和分发资源不手工重排。

测试环境的 matchMedia、滚动与原生 top-layer selector 适配仅补齐 jsdom 缺失能力，不改变产品实现。行为测试应覆盖草稿保留、过期响应、部分失败、权限变化和组件卸载；不要把纯样式快照或实现细节断言当作真实交互验收。

隔离演示只使用 `scripts/preview/` 的虚构内存状态与固定图片白名单；不访问真实 Bot、配置或认证文件。真实实例的登录、写入、冲突、轮询和运行操作必须单独记录环境与可观察结果。
