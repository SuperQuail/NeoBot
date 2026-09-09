// Sparkline.jsx —— 消息趋势迷你折线图(移植自旧 overview.js 的 buildSparkPaths)
const W = 240;
const H = 56;
const PAD = 6;

export default function Sparkline({ series = [] }) {
  const counts = series.map((s) => s.count || 0);
  if (counts.length < 2) {
    return <div className="spark-empty">暂无数据</div>;
  }
  const max = Math.max(1, ...counts);
  const usable = H - PAD * 2;
  const pts = counts.map((c, i) => {
    const x = (i / (counts.length - 1)) * W;
    const y = PAD + (1 - c / max) * usable;
    return [x.toFixed(1), y.toFixed(1)];
  });
  const line = 'M' + pts.map(([x, y]) => `${x},${y}`).join(' L');
  const area = line + ` L${W},${H} L0,${H} Z`;

  return (
    <svg className="spark" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
      <path className="spark-area" d={area} />
      <path className="spark-line" d={line} />
    </svg>
  );
}
