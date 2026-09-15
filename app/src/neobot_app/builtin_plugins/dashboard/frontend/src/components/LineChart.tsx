// LineChart.tsx —— 带网格/Y轴刻度的折线图(移植自旧 botsPage.js 的 chartBuild)
// props: values(数组,可含 null 断点)、fmtTick(刻度格式化)
import { useEffect, useLayoutEffect, useRef, useState } from 'react';

const H = 140; // 高度仍固定
const PAD = { l: 40, r: 20, t: 20, b: 20 };
const DEFAULT_W = 600; // SSR / 首帧兜底宽度

// SSR 下 useLayoutEffect 会报警告，做个同构兜底
const useIsoLayoutEffect = typeof window !== 'undefined' ? useLayoutEffect : useEffect;

export type LineChartValue = number | string | null | undefined;

export interface LineChartProps {
  values?: LineChartValue[];
  fmtTick?: (value: number) => string;
}

/** 把任意刻度值收敛成数字，非数值返回 null（保持折线断点语义） */
const toNumber = (value: LineChartValue): number | null => {
  if (value == null || value === '') return null;
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
};

export default function LineChart({ values = [], fmtTick = (v) => String(Math.round(v)) }: LineChartProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(DEFAULT_W);

  // —— 关键：测量容器真实宽度 ——
  useIsoLayoutEffect(() => {
    const el = wrapRef.current;
    if (!el) return;

    const apply = (w: number) => {
      if (w > 0) setWidth(Math.round(w));
    };

    // 首帧先量一次（useLayoutEffect 中，paint 之前完成，不会闪）
    apply(el.getBoundingClientRect().width);

    if (typeof ResizeObserver === 'undefined') {
      // 极老环境兜底
      const onResize = () => apply(el.getBoundingClientRect().width);
      window.addEventListener('resize', onResize);
      return () => window.removeEventListener('resize', onResize);
    }

    const ro = new ResizeObserver((entries) => {
      apply(entries[0].contentRect.width);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // 保证 innerW 不为负
  const W = Math.max(PAD.l + PAD.r + 1, width);
  const innerW = W - PAD.l - PAD.r;
  const innerH = H - PAD.t - PAD.b;

  const numeric = values.map(toNumber);
  const valid = numeric.filter((v): v is number => v != null);

  // 公共 svg 属性：宽度跟随容器，高度固定，viewBox 用实测宽度
  const svgProps = {
    className: 'linechart',
    width: '100%',
    height: H,
    viewBox: `0 0 ${W} ${H}`,
    // 与 viewBox 比例一致时 meet 不会产生留白；显式写出便于阅读
    preserveAspectRatio: 'xMidYMid meet' as const,
    style: { display: 'block' as const },
  };

  if (valid.length === 0) {
    return (
      <div ref={wrapRef} style={{ width: '100%' }}>
        <svg {...svgProps}>
          <text x={W / 2} y={H / 2} textAnchor="middle" className="lc-empty-text">
            暂无数据
          </text>
        </svg>
      </div>
    );
  }

  const min = 0;
  const max = Math.max(1, ...valid) * 1.1;
  const n = numeric.length;
  const stepX = n > 1 ? innerW / (n - 1) : 0;

  const pts: Array<[number, number] | null> = numeric.map((v, i) => {
    if (v == null) return null;
    const x = PAD.l + i * stepX;
    const y = PAD.t + (1 - (v - min) / (max - min || 1)) * innerH;
    return [x, y];
  });

  // 折线(遇 null 断开)
  let dLine = '';
  let started = false;
  for (const p of pts) {
    if (p == null) {
      started = false;
      continue;
    }
    dLine += `${started ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)} `;
    started = true;
  }

  // 面积
  const vpts = pts.filter((p): p is [number, number] => p != null);
  let dArea = 'M' + vpts.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' L');
  dArea += ` L${vpts[vpts.length - 1][0].toFixed(1)},${H - PAD.b}`;
  dArea += ` L${vpts[0][0].toFixed(1)},${H - PAD.b} Z`;

  const yTicks = [0, max / 2, max];

  return (
    <div ref={wrapRef} style={{ width: '100%' }}>
      <svg {...svgProps}>
        <g className="lc-grid">
          {yTicks.map((v, i) => {
            const y = PAD.t + (1 - (v - min) / (max - min || 1)) * innerH;
            return (
              <g key={i}>
                <line x1={PAD.l} y1={y} x2={W - PAD.r} y2={y} />
                <text x={PAD.l - 6} y={y + 3} textAnchor="end">
                  {fmtTick(v)}
                </text>
              </g>
            );
          })}
        </g>
        <path className="lc-area" d={dArea} />
        <path className="lc-line" d={dLine.trim()} />
      </svg>
    </div>
  );
}
