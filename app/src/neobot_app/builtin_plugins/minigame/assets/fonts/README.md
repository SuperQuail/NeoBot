# 字体资产来源与许可

本目录的字体只服务于**卡片渲染**（运行时 Chromium 把 HTML 渲染成 PNG），
通过 `neobot_contracts.ports.screenshot.FontFace` 以 data URI **内联进临时页**，
因此**部署侧不需要安装任何字体、也不需要前端工具链**。

---

## 1. Monocraft-Regular.ttf / Monocraft-Bold.ttf

- 来源：<https://github.com/IdreesInc/Monocraft> release `v4.2.1` 的 `Monocraft-ttf.zip`
- 作者：Idrees Hassan
- **许可：SIL Open Font License 1.1**（全文见 `LICENSE-Monocraft.txt`）
  - 允许商用、允许随软件分发与内嵌渲染；未修改字形，不涉及 OFL 的保留字体名条款。
- 用途：Minecraft 主题的**拉丁字母与数字**（完整字体，未子集化）。

> ⚠️ 真正的 Minecraft 官方字体是专有资产，**不得**进入本仓库；这里用的是开放许可的 MC 风格替代字体。

## 2. FusionPixel8px-zh_hans.woff2

- 来源：<https://github.com/TakWolf/fusion-pixel-font>（缝合像素字体）release `2026.09.01`
  的 `fusion-pixel-font-8px-proportional-ttf.woff2` 包内 `zh_hans` 变体
- **许可：SIL Open Font License 1.1**（全文见 `LICENSE-FusionPixel-OFL.txt`，另附 `LICENSE-FusionPixel.txt`）
- **大小：439 KB**（8px 像素字形，woff2 压缩后），完整未子集化。
- 用途：Minecraft 主题的**中日韩字形**。

### 为什么需要它

Monocraft **只有拉丁字形**。卡片内容大部分是中文，若只内嵌 Monocraft，中文会被 Chromium
回退到系统平滑字体，结果同一行里「拉丁是像素风、中文是平滑风」，观感割裂。
本机实测渲染对比见 `dev-test/font-check/pixel-fonts.png`（临时产物，不入库）。

### 推荐用法

```css
font-family: "Monocraft", "FusionPixel", <系统等宽回退>;
```

Chromium 会**逐字形回退**：拉丁/数字命中 Monocraft（MC 招牌字形），中日韩命中 FusionPixel。
像素字体请在**整数倍字号**下使用（8px 字体的 2 倍 = 16px、3 倍 = 24px），
并以 `-webkit-font-smoothing: none` / `font-smooth: never` 抑制抗锯齿以获得清晰像素边缘。
