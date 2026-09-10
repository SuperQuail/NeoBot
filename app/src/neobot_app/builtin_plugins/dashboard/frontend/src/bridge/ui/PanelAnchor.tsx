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

import { useEffect, useRef, useState, type ReactNode } from 'react';
import type { PerspectiveCamera } from 'three';
import {
  PIXELS_PER_METER,
  panelPlaneFromStation,
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
 * 面板在世界里的物理尺寸（米）。
 *
 * 终端屏幕本身只有 0.8~1.6m 宽，照搬会让字号小到不可读；这里按「人凑到终端前
 * 2~3 米看」的可读视距设计，取 2.15×1.38m —— 在 2m 处大约占屏幕宽度的八成，
 * 既有「贴在终端上」的透视感，又不至于看不清。
 */
const PANEL_WIDTH_M = 2.15;
const PANEL_HEIGHT_M = 1.38;
/**
 * 元素像素尺寸 = 米数 × PIXELS_PER_METER（定义在 projector，两处必须一致）。
 * 取 150 是让 2m 视距下的缩放比接近 1（内容按设计字号 1:1 呈现）；
 * 更远时元素被缩小，同时由 --panel-lift 反向补偿字号——两者相乘保证
 * **屏幕上的字号恒定在一个可读区间**。
 */
const PX_PER_METER = PIXELS_PER_METER;
/** 字号补偿的上下限：太低就不再放大（避免远处内容溢出面板） */
const MIN_LIFT = 0.6;
const MAX_LIFT = 2.4;
/** 面板中心相对站位的偏移：抬到 1.5m 高、向玩家一侧浮出 0.55m */
const PANEL_CENTER_HEIGHT = 1.5;
const PANEL_FORWARD = 0.55;
/** 展开/收起动画时长（秒）；与 bridge.tsx 里延时卸载的时间保持一致 */
const REVEAL_SECONDS = 0.26;
/** 凑到这个距离以内就接管全屏（设定说法：贴到终端前） */
const TAKEOVER_DISTANCE = 1.75;

export default function PanelAnchor({
  station,
  getCamera,
  getViewport,
  compositor,
  closing = false,
  children,
}: PanelAnchorProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [fullscreen, setFullscreen] = useState(false);
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

  useEffect(() => {
    let raf = 0;

    const plane = panelPlaneFromStation(station.anchor, station.facing, {
      height: PANEL_CENTER_HEIGHT,
      forward: PANEL_FORWARD,
      width: PANEL_WIDTH_M,
      heightMeters: PANEL_HEIGHT_M,
    });

    const tick = () => {
      raf = requestAnimationFrame(tick);
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

      // ---- 遮挡响应 ----
      // 面板钻进舱壁/货箱时整体变淡并略微收缩透视，观感上像投影被挡住而衰减，
      // 比让 DOM 直接浮在墙上自然。（逐像素裁剪需要每帧把遮罩读回 DOM，
      // 同步 PNG 编码会吃掉整个帧预算，因此这里用 8×8 的可见度统计量代替。）
      const visibility = compositor?.sampleVisibility(projected.quad, viewport.width, viewport.height) ?? 1;
      const occlusionFade = 0.25 + 0.75 * visibility;

      // 距离越远越淡：投影在空气里衰减，同时暗示「凑近看」
      const falloff = Math.min(1, Math.max(0.3, 1 - (projected.distance - 1.2) / 6));
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
      const elementWidth = PANEL_WIDTH_M * PX_PER_METER;
      const lift = Math.min(MAX_LIFT, Math.max(MIN_LIFT, elementWidth / Math.max(1, renderedWidth)));
      host.style.setProperty('--panel-lift', lift.toFixed(3));

      compositor?.draw(
        { quad: projected.quad, reveal, opacity: eased, accent: HOLO_ACCENT, accent2: HOLO_ACCENT_ALT },
        viewport.width,
        viewport.height,
      );

      // 凑近接管全屏：状态变化很少，setState 开销可忽略
      const near = projected.distance < TAKEOVER_DISTANCE;
      setFullscreen((current) => (current === near ? current : near));
    };

    raf = requestAnimationFrame(tick);
    return () => {
      if (raf) cancelAnimationFrame(raf);
      compositor?.clear();
    };
  }, [station, getCamera, getViewport, compositor]);

  return (
    <div
      ref={hostRef}
      className={`panel-anchor${fullscreen ? ' panel-anchor-full' : ''}`}
      style={{
        width: `${PANEL_WIDTH_M * PX_PER_METER}px`,
        height: `${PANEL_HEIGHT_M * PX_PER_METER}px`,
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
