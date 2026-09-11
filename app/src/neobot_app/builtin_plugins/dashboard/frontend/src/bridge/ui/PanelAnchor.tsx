// PanelAnchor.tsx —— 把面板「按相机投影」贴到终端屏幕上
//
// 这是「面板融入场景」的核心：每一帧把面板的 transform 设成 view·plane 矩阵，
// 交给 CSS 的 matrix3d 做与 WebGL **逐像素一致**的透视投影；同时驱动
// 「从屏幕里浮出来」的展开动画，并把合成层要用的参数（四边形、展开量）交给它做遮挡。
//
// 分工：
//   · 本组件只改 style，不参与 React 重渲染 —— 每帧 setState 会把面板内容
//     一起重渲染，日志那种滚动列表会卡死；
//   · 投影数学在 three/projector.ts，遮挡合成在 three/composite.ts；
//   · 收起动画由 closing 属性触发，动画结束回调 onExited 让父级真正卸载。

import { useEffect, useMemo, useRef, type ReactNode } from 'react';
import type { PerspectiveCamera } from 'three';
import {
  PIXELS_PER_METER,
  panelPlaneFromScreen,
  perspectiveDistance,
  projectPanel,
} from '../three/projector';
import type { PanelCompositor } from '../three/composite';
import { HOLO_ACCENT, HOLO_ACCENT_ALT } from './tokens';
import type { Station } from '../core/types';

export interface PanelAnchorProps {
  station: Station;
  /** 提供当前相机：用 getter 而不是传值，避免每帧触发重渲染 */
  getCamera: () => PerspectiveCamera | null;
  /** 提供视口尺寸（CSS 像素） */
  getViewport: () => { width: number; height: number };
  /** 合成器：负责遮挡与全息辉光；为 null 时退化成纯 CSS 效果 */
  compositor: PanelCompositor | null;
  /** 置 true 播放收起动画 */
  closing?: boolean;
  children: ReactNode;
}

/**
 * 面板相对终端屏幕的放大倍率。
 *
 * 屏幕本身只有 0.8~1.6m 宽，原样贴上去字号小到不可读；放大 2.4 倍后面板
 * 约 2~3.8m 宽，玩家站在交互距离（2.5~3.4m）时读起来正好，同时仍然明显
 * 挂在终端那一侧、需要转头去看——这才是「场景里的面板」。
 */
const PANEL_SCALE = 2.4;
/** 面板中心相对屏幕中心抬高（米）：悬在终端上方，不挡住屏幕本身 */
const PANEL_RISE = 0.62;
/** 向玩家一侧浮出的距离（米） */
const PANEL_FORWARD = 0.42;

/** 元素像素尺寸 = 米数 × 这个系数（与 projector 的换算必须一致） */
const PX_PER_METER = PIXELS_PER_METER;
/**
 * 字号补偿的上下限。元素被投影缩放了 renderedWidth / elementWidth 倍，
 * 字号乘上它的倒数就能让屏幕上的字号基本恒定；夹在区间内避免极端视距下溢出。
 */
const MIN_LIFT = 0.6;
const MAX_LIFT = 2.4;
/** 展开/收起动画时长（秒）；与 bridge.tsx 里延时卸载的时间保持一致 */
const REVEAL_SECONDS = 0.26;
/**
 * 可见度采样的间隔（帧）。
 *
 * 采样内部是 readRenderTargetPixels —— **GPU 同步回读**，每帧做会让 CPU 一直
 * 等 GPU 完成，实测直接把页面卡死。遮挡变化本来就慢，每 6 帧一次完全够用。
 */
const VISIBILITY_INTERVAL = 6;
/**
 * 距离淡出的下限。
 *
 * 早期把最远处压到 0.3，结果「在舰桥一端打开另一端的终端」时面板淡到看不见，
 * 玩家以为功能坏了。最远处保留 0.55：仍然明显是远景，但一眼能看到那里有块投影。
 */
const MIN_DISTANCE_FALLOFF = 0.55;

export default function PanelAnchor({
  station,
  getCamera,
  getViewport,
  compositor,
  closing = false,
  children,
}: PanelAnchorProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const revealRef = useRef(0);
  const closingRef = useRef(closing);
  const dockRef = useRef<{
    transform: string;
    perspective: number;
    principalX: number;
    principalY: number;
    opacity: number;
  } | null>(null);
  closingRef.current = closing;

  // 面板尺寸由「屏幕尺寸 × 倍率」决定，是常量，不必每帧重算
  const plane = useMemo(
    () =>
      panelPlaneFromScreen(station.screen, station.screenYaw, station.screenSize, {
        scale: PANEL_SCALE,
        rise: PANEL_RISE,
        forward: PANEL_FORWARD,
      }),
    [station],
  );

  useEffect(() => {
    let raf = 0;
    /** 帧计数：可见度采样要降频（见下），用一个自增计数控制 */
    let frame = 0;
    /** 上一次算出的遮挡淡出系数，采样帧之间复用 */
    let occlusionFade = 1;

    const tick = () => {
      raf = requestAnimationFrame(tick);
      frame += 1;
      const host = hostRef.current;
      const camera = getCamera();
      if (!host || !camera) return;
      const viewport = getViewport();
      if (viewport.width < 2 || viewport.height < 2) return;

      // ---- 展开量：0→1 展开，1→0 收起 ----
      const step = 1 / 60 / REVEAL_SECONDS;
      const wantClosing = closingRef.current;
      revealRef.current = wantClosing
        ? Math.max(0, revealRef.current - step)
        : Math.min(1, revealRef.current + step);
      const reveal = revealRef.current;
      const eased = 1 - Math.pow(1 - reveal, 3);
      host.style.transformOrigin = '0 0';

      // 收起时不再跟随相机：面板留在原地淡出，避免「追着镜头飞走」的怪感
      const projected = wantClosing
        ? null
        : projectPanel(camera, plane, viewport.width, viewport.height, eased * 0.12);

      if (projected === null || projected.behind) {
        const dock = dockRef.current;
        if (dock) {
          host.style.transform = `perspective(${dock.perspective.toFixed(2)}px) ${dock.transform}`;
          host.style.perspectiveOrigin = `${dock.principalX.toFixed(1)}px ${dock.principalY.toFixed(1)}px`;
          host.style.opacity = (eased * dock.opacity).toFixed(3);
        } else {
          host.style.opacity = '0';
        }
        compositor?.clear();
        return;
      }

      const perspective = perspectiveDistance(camera, viewport.height);
      host.style.transform = `perspective(${perspective.toFixed(2)}px) ${projected.transform}`;
      // 视角原点必须显式设置：CSS 默认在元素中心，而面板元素很大，
      // 用默认值会让透视往元素中心收，与 WebGL 相机对不上。
      host.style.perspectiveOrigin = `${projected.principalX.toFixed(1)}px ${projected.principalY.toFixed(1)}px`;

      // ---- 遮挡响应（降频采样）----
      // sampleVisibility 内部是 readRenderTargetPixels，属于 **GPU 同步回读**：
      // 每帧调用会让 CPU 一直等 GPU，实测直接把页面卡死。遮挡变化本来就慢，
      // 每 VISIBILITY_INTERVAL 帧采一次完全够用，其余帧复用上次结果。
      if (frame % VISIBILITY_INTERVAL === 0) {
        const visibility =
          compositor?.sampleVisibility(projected.quad, viewport.width, viewport.height) ?? 1;
        occlusionFade = 0.25 + 0.75 * visibility;
      }

      // 距离越远越淡：投影在空气里衰减，但保留下限，别让远处的面板直接消失
      const falloff = Math.min(
        1,
        Math.max(MIN_DISTANCE_FALLOFF, 1 - (projected.distance - 1.2) / 6),
      );
      const opacity = eased * falloff * occlusionFade;
      host.style.opacity = opacity.toFixed(3);
      dockRef.current = {
        transform: projected.transform,
        perspective,
        principalX: projected.principalX,
        principalY: projected.principalY,
        opacity: falloff * occlusionFade,
      };

      // ---- 字号补偿 ----
      // 元素被投影缩放了 renderedWidth / elementWidth 倍；把字号乘上它的倒数，
      // 屏幕上的字号就基本恒定。夹在 [MIN_LIFT, MAX_LIFT] 内避免极端视距下溢出。
      const renderedWidth = Math.hypot(
        projected.quad[1].x - projected.quad[0].x,
        projected.quad[1].y - projected.quad[0].y,
      );
      const elementWidth = plane.width * PX_PER_METER;
      const lift = Math.min(MAX_LIFT, Math.max(MIN_LIFT, elementWidth / Math.max(1, renderedWidth)));
      host.style.setProperty('--panel-lift', lift.toFixed(3));

      compositor?.draw(
        { quad: projected.quad, reveal, opacity: eased, accent: HOLO_ACCENT, accent2: HOLO_ACCENT_ALT },
        viewport.width,
        viewport.height,
      );
    };

    raf = requestAnimationFrame(tick);
    return () => {
      if (raf) cancelAnimationFrame(raf);
      compositor?.clear();
    };
  }, [plane, getCamera, getViewport, compositor]);

  return (
    <div
      ref={hostRef}
      className="panel-anchor"
      style={{
        width: `${plane.width * PX_PER_METER}px`,
        height: `${plane.height * PX_PER_METER}px`,
        // 字号补偿倍数，每帧由投影循环写入
        '--panel-lift': 1,
      } as React.CSSProperties}
      data-station={station.id}
    >
      {/* 全息外发光与扫描线：DOM 层负责「看起来是投影」，遮挡由合成层负责 */}
      <div className="panel-anchor-holo" aria-hidden="true" />
      <div className="panel-anchor-body">{children}</div>
    </div>
  );
}
