// LineChart.tsx —— 带网格/Y轴刻度的折线图(移植自旧 botsPage.js 的 chartBuild)
// props: values(数组,可含 null 断点)、fmtTick(刻度格式化)
//
// 悬停：鼠标进入绘图区时按最近的数据点画一条竖直参考线 + 高亮点，
// 并在光标旁弹出「x 轴标签 + 数值」的详细提示（labels / name / fmtValue），
// 另可用 extraRows 追加该点的其它指标（用量页就是把同一时间档的调用 / Token / 花费一起列出）。
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
  /** 每个数据点的 x 轴标签（悬停提示里显示）；缺省时显示 `#序号` */
  labels?: string[];
  /** 悬停提示里的数值格式化；缺省与 fmtTick 相同 */
  fmtValue?: (value: number) => string;
  /** 数据列名称（悬停提示的第一行与无障碍描述里使用） */
  name?: string;
  /**
   * 悬停提示里、主数值之外的附加明细（如该时间桶的调用次数 / 其它 Token 口径）。
   * 只在真正悬停时调用，参数是数据点序号。
   */
  extraRows?: (index: number) => Array<{ label: string; value: string }>;
}

interface HoverState {
  index: number;
  /** 光标相对容器的像素坐标（提示框据此定位） */
  px: number;
  py: number;
  /** 光标的视口纵坐标：提示框还要避开视口的上下边缘 */
  vy: number;
}

/** 把任意刻度值收敛成数字，非数值返回 null（保持折线断点语义） */
const toNumber = (value: LineChartValue): number | null => {
  if (value == null || value === '') return null;
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
};

export default function LineChart({
  values = [],
  fmtTick = (v) => String(Math.round(v)),
  labels,
  fmtValue,
  name,
  extraRows,
}: LineChartProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(DEFAULT_W);
  const [hover, setHover] = useState<HoverState | null>(null);
  // 提示框实测尺寸：用它决定往上还是往下弹、以及贴左 / 贴右 / 居中
  const [tipSize, setTipSize] = useState({ w: 0, h: 0 });
  const formatValue = fmtValue || fmtTick;

  useIsoLayoutEffect(() => {
    const el = tipRef.current;
    if (!el) return;
    const w = el.offsetWidth;
    const h = el.offsetHeight;
    setTipSize((prev) => (prev.w === w && prev.h === h ? prev : { w, h }));
  });

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
  const n = numeric.length;
  const stepX = n > 1 ? innerW / (n - 1) : 0;

  /** 数据点序号 → 绘图区 x 坐标（与 pts 同一口径） */
  const xOf = (index: number) => PAD.l + index * stepX;

  // 公共 svg 属性：宽度跟随容器，高度固定，viewBox 用实测宽度
  const ariaLabel = (() => {
    const series = name ? name + '折线图' : '折线图';
    if (valid.length === 0) return series + '：暂无数据';
    const peak = Math.max(...valid);
    const lastIndex = (() => {
      for (let i = numeric.length - 1; i >= 0; i -= 1) if (numeric[i] != null) return i;
      return -1;
    })();
    const last = lastIndex >= 0 ? formatValue(numeric[lastIndex] as number) : '—';
    return (
      series +
      '：共 ' +
      n +
      ' 个数据点，最新 ' +
      last +
      '，峰值 ' +
      formatValue(peak)
    );
  })();

  const svgProps = {
    className: 'linechart',
    width: '100%',
    height: H,
    viewBox: `0 0 ${W} ${H}`,
    // 与 viewBox 比例一致时 meet 不会产生留白；显式写出便于阅读
    preserveAspectRatio: 'xMidYMid meet' as const,
    style: { display: 'block' as const },
    role: 'img' as const,
    'aria-label': ariaLabel,
  };

  /** 鼠标位置 → 最近的数据点序号（viewBox 坐标换算，兼容被缩放的容器） */
  const handleMove = (event: React.MouseEvent<HTMLDivElement>) => {
    const el = wrapRef.current;
    if (!el || n === 0) return;
    const rect = el.getBoundingClientRect();
    if (!(rect.width > 0)) return;
    const px = event.clientX - rect.left;
    const py = event.clientY - rect.top;
    const scale = rect.width / W;
    const vx = px / scale;
    const raw = stepX > 0 ? Math.round((vx - PAD.l) / stepX) : 0;
    const index = Math.min(n - 1, Math.max(0, raw));
    setHover({ index, px, py, vy: event.clientY });
  };

  const clearHover = () => setHover((current) => (current === null ? current : null));

  if (valid.length === 0) {
    return (
      <div ref={wrapRef} className="lc-wrap" style={{ width: '100%' }}>
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

  const pts: Array<[number, number] | null> = numeric.map((v, i) => {
    if (v == null) return null;
    const x = xOf(i);
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

  // 悬停：数值刷新后旧序号可能越界，一律以当前长度为准
  const hoverIndex = hover && hover.index < n ? hover.index : null;
  const hoverValue = hoverIndex === null ? null : numeric[hoverIndex];
  const hoverPoint = hoverIndex === null ? null : pts[hoverIndex];

  // 提示框：按光标的像素位置定位，用**实测尺寸**决定往上/往下弹与贴左/贴右/居中
  let tip: {
    style: React.CSSProperties;
    label: string;
    value: string;
    rows: Array<{ label: string; value: string }>;
  } | null = null;
  if (hover && hoverIndex !== null) {
    const chartW = Math.max(1, width);
    const half = tipSize.w / 2;
    const tx = hover.px < half ? '0' : hover.px > chartW - half ? '-100%' : '-50%';
    // 竖直：默认贴光标上方（不挡悬停的那个点）；上方放不下整块提示就翻到下方；
    // 上下都放不下（提示比可视区还高）时仍取上方。这样无论图表贴近视口顶部还是底部，
    // 提示都不会被裁掉半个或直接跑到屏幕外。
    const h = tipSize.h;
    const viewH = typeof window === 'undefined' ? 0 : window.innerHeight;
    const roomAbove = hover.vy - 10 - h;
    const roomBelow = viewH - (hover.vy + 14 + h);
    const below = roomAbove < 0 && roomBelow >= 0;
    tip = {
      style: {
        left: Math.min(Math.max(hover.px, 0), chartW),
        top: below ? hover.py + 14 : hover.py - 10,
        transform: `translate(${tx}, ${below ? '0' : '-100%'})`,
      },
      label: labels?.[hoverIndex] || '#' + hoverIndex,
      value: hoverValue == null ? '无数据' : formatValue(hoverValue),
      rows: extraRows ? extraRows(hoverIndex) : [],
    };
  }

  return (
    <div
      ref={wrapRef}
      className="lc-wrap"
      style={{ width: '100%' }}
      onMouseMove={handleMove}
      onMouseLeave={clearHover}
    >
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
        {hoverIndex !== null && (
          <g className="lc-cursor">
            <line
              className="lc-guide"
              x1={xOf(hoverIndex)}
              y1={PAD.t}
              x2={xOf(hoverIndex)}
              y2={H - PAD.b}
            />
            {hoverPoint && <circle className="lc-dot" cx={hoverPoint[0]} cy={hoverPoint[1]} r={3.5} />}
          </g>
        )}
      </svg>
      {tip && (
        <div className="lc-tooltip" role="tooltip" ref={tipRef} style={tip.style}>
          <span className="lc-tooltip-name">{name || '数值'}</span>
          <span className="lc-tooltip-label">{tip.label}</span>
          <span className="lc-tooltip-value">{tip.value}</span>
          {tip.rows.map((row) => (
            <span className="lc-tooltip-row" key={row.label}>
              <span className="lc-tooltip-row-label">{row.label}</span>
              <span className="lc-tooltip-row-value">{row.value}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
