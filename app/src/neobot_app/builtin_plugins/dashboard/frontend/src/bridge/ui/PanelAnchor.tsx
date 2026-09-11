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
  type PanelPlane,
  panelPlaneFromScreen,
  projectPanel,
} from '../three/projector';
import type { PanelCompositor } from '../three/composite';
import { HOLO_ACCENT, HOLO_ACCENT_ALT } from './tokens';
import type { Station } from '../core/types';
import { PANEL_LAYOUT, panelWorldSize } from './panelSizing';

export interface PanelAnchorProps {
  station: Station;
  /** 提供当前相机：用 getter 而不是传值，避免每帧触发重渲染 */
  getCamera: () => PerspectiveCamera | null;
  /** 提供视口尺寸（CSS 像素） */
  getViewport: () => { width: number; height: number };
  /** 面板可见度（0~1，由引擎按碰撞盒算出）：被挡住时面板整体暗下去 */
  getVisibility: (plane: PanelPlane) => number;
  /** 合成器：负责遮挡与全息辉光；为 null 时退化成纯 CSS 效果 */
  compositor: PanelCompositor | null;
  /** 置 true 播放收起动画 */
  closing?: boolean;
  children: ReactNode;
}

/** 面板中心相对屏幕中心抬高（米）：悬在终端上方，不挡住屏幕本身 */
const PANEL_RISE = 0.38;
/** 向玩家一侧浮出的距离（米） */
const PANEL_FORWARD = 0.42;

/** 元素像素尺寸 = 米数 × 这个系数（与 projector 的换算必须一致） */
const PX_PER_METER = PIXELS_PER_METER;
/** 展开/收起动画时长（秒）；与 bridge.tsx 里延时卸载的时间保持一致 */
const REVEAL_SECONDS = 0.26;
/**
 * 可见度采样的间隔（帧）。
 *
 * 遮挡本身是纯 CPU 的线段求交（几百个包围盒 × 20 条线段，微秒级），不降频也
 * 跑得动；这里仍然每 6 帧算一次，是因为遮挡只会随走动缓慢变化，没必要每帧算，
 * 中间几帧沿用上一次的结果。
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
  getVisibility,
  compositor,
  closing = false,
  children,
}: PanelAnchorProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const revealRef = useRef(0);
  const closingRef = useRef(closing);
  const dockRef = useRef<{
    transform: string;
    opacity: number;
  } | null>(null);
  closingRef.current = closing;

  // World size never depends on the camera: this remains a station-bound projection.
  const plane = useMemo(
    () =>
      ({
        ...panelPlaneFromScreen(station.screen, station.screenYaw, station.screenSize, {
          rise: PANEL_RISE,
          forward: PANEL_FORWARD,
        }),
        ...panelWorldSize(station.screenSize.width),
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
      if (!host) return;
      const hide = () => {
        host.style.opacity = '0';
        host.style.visibility = 'hidden';
        host.dataset.interactive = 'false';
        host.setAttribute('inert', '');
        dockRef.current = null;
        compositor?.clear();
      };
      if (!camera) { hide(); return; }
      const viewport = getViewport();
      if (viewport.width < 2 || viewport.height < 2) { hide(); return; }

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

      if (projected === null) {
        host.dataset.interactive = 'false';
        host.setAttribute('inert', '');
        const dock = dockRef.current;
        if (dock) {
          host.style.transform = dock.transform;
          host.style.opacity = (eased * dock.opacity).toFixed(3);
        } else {
          hide();
        }
        if (eased === 0) hide();
        compositor?.clear();
        return;
      }

      /**
       * 面板跑到相机背后（转过头 / 走出终端所在的方向）：保留上一次的 transform
       * 以便转回来时立刻归位，但**必须隐藏**。
       *
       * 早期这里和「收起动画」共用一条分支，于是隐藏时仍按上一次的透明度显示 ——
       * 玩家转身走开几十米后，面板会像一块 HUD 一样钉在屏幕上不动（实测人已经
       * 在中央枢纽，主机机柜的面板还挂在画面中央、77% 不透明度）。
       */
      if (projected.behind) {
        hide();
        return;
      }

      // matrix3d 已经包含透视（第 4 行是同次项 w），不需要 perspective()，
      // 也不需要 perspective-origin —— 后者默认在元素中心，只会把画面对错位。
      host.style.transform = projected.transform;

      // ---- 遮挡响应（降频采样）----
      // 引擎按碰撞盒算出「相机到面板的连线有多少条没被挡住」，纯 CPU、不碰 GPU。
      if (frame % VISIBILITY_INTERVAL === 0) {
        const visibility = getVisibility(plane);
        occlusionFade = 0.25 + 0.75 * visibility;
      }

      // 距离越远越淡：投影在空气里衰减，但保留下限，别让远处的面板直接消失
      const falloff = Math.min(
        1,
        Math.max(MIN_DISTANCE_FALLOFF, 1 - (projected.distance - 3) / 6),
      );
      const opacity = eased * falloff * occlusionFade;
      host.style.opacity = opacity.toFixed(3);
      host.style.visibility = opacity > 0.01 ? 'visible' : 'hidden';
      host.dataset.interactive = opacity > 0.01 ? 'true' : 'false';
      host.toggleAttribute('inert', opacity <= 0.01);
      dockRef.current = {
        transform: projected.transform,
        opacity: falloff * occlusionFade,
      };

      // 辉光要跟着面板一起淡：传进去的是最终不透明度，而不是只有展开量，
      // 否则面板已经暗下去了、全息光却还亮着贴在墙上。
      compositor?.draw(
        { quad: projected.quad, reveal, opacity, accent: HOLO_ACCENT, accent2: HOLO_ACCENT_ALT },
        viewport.width,
        viewport.height,
      );
    };

    raf = requestAnimationFrame(tick);
    return () => {
      if (raf) cancelAnimationFrame(raf);
      compositor?.clear();
    };
  }, [plane, getCamera, getViewport, getVisibility, compositor]);

  return (
    <div
      ref={hostRef}
      className="panel-anchor"
      style={{
        width: `${plane.width * PX_PER_METER}px`,
        height: `${plane.height * PX_PER_METER}px`,
        '--panel-layout-width': `${PANEL_LAYOUT.width}px`,
        '--panel-layout-height': `${PANEL_LAYOUT.height}px`,
        '--panel-layout-scale': plane.width * PX_PER_METER / PANEL_LAYOUT.width,
      } as React.CSSProperties}
      data-station={station.id}
    >
      {/* 全息外发光与扫描线：DOM 层负责「看起来是投影」，遮挡由合成层负责 */}
      <div className="panel-anchor-holo" aria-hidden="true" />
      <div className="panel-anchor-body">{children}</div>
    </div>
  );
}
