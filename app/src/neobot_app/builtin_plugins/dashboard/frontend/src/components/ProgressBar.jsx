// ProgressBar.jsx —— CPU/内存/磁盘占用条(对应旧 system.js 的 setBar)
export default function ProgressBar({ label, text, pct }) {
  const w = Math.min(100, Math.max(0, pct || 0));
  const tone = w >= 90 ? 'err' : w >= 70 ? 'warn' : 'ok';
  return (
    <div className="bar-row">
      <div className="bar-head">
        <span className="bar-label">{label}</span>
        <span className="bar-text">{text}</span>
      </div>
      <div className="bar-track">
        <div className={'bar-fill ' + tone} style={{ width: w.toFixed(1) + '%' }} />
      </div>
    </div>
  );
}
