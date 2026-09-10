// LineChart.jsx —— 带网格/Y轴刻度的折线图(移植自旧 botsPage.js 的 chartBuild)
// props: values(数组,可含 null 断点)、fmtTick(刻度格式化)
const W = 600;
const H = 140;
const PAD = { l: 40, r: 20, t: 20, b: 20 };

export default function LineChart({ values = [], fmtTick = (v) => Math.round(v) }) {
  const innerW = W - PAD.l - PAD.r;
  const innerH = H - PAD.t - PAD.b;

  const numeric = values.map((v) => (v == null || isNaN(v) ? null : Number(v)));
  const valid = numeric.filter((v) => v != null);

  if (valid.length === 0) {
    return (
      <svg className="linechart" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
        <text x={W / 2} y={H / 2} textAnchor="middle" className="lc-empty-text">
          暂无数据
        </text>
      </svg>
    );
  }

  const min = 0;
  const max = Math.max(1, ...valid) * 1.1;
  const n = numeric.length;
  const stepX = n > 1 ? innerW / (n - 1) : 0;

  const pts = numeric.map((v, i) => {
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
  const vpts = pts.filter((p) => p != null);
  let dArea = 'M' + vpts.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' L');
  dArea += ` L${vpts[vpts.length - 1][0].toFixed(1)},${H - PAD.b}`;
  dArea += ` L${vpts[0][0].toFixed(1)},${H - PAD.b} Z`;

  const yTicks = [0, max / 2, max];

  return (
    <svg className="linechart" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
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
  );
}
