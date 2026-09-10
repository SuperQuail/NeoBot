// components/SidebarTooltip.tsx —— 已废弃
//
// 侧栏悬浮提示已改为纯 CSS 实现，见 styles/theme.css 中 .nav-item[data-tooltip] 的规则。
// 保留此文件只是为了让 Layout 的 import 不报错，可以随时连同 import 一起删掉。
//
// 为什么放弃 JS 版（两个都实测踩过）：
//   1) 绝对定位摆到侧栏右侧 → 顶层 .app 的 overflow:hidden 把越界部分裁掉（只露半个字）；
//   2) JS 算坐标 + position:fixed → 一旦 CSS 与 JS 缓存版本错位（新 JS 配旧 CSS），
//      浮层没有 fixed 规则，就作为 static 的 flex 子元素被排到侧栏最底部，
//      表现为「tooltip 跑到图标下面去了」。
// 纯 CSS 版不依赖 JS 时序，也不存在这种错位。
export default function SidebarTooltip() {
  return null;
}