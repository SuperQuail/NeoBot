// StatCard.jsx —— 统计卡(带图标,对齐原版 stat-card)
export default function StatCard({ label, value, sub, accent, icon, iconAccent, children }) {
  return (
    <div className="card stat-card">
      {icon && <div className={'stat-icon' + (iconAccent ? ' accent' : '')}>{icon}</div>}
      <div className="stat-label">{label}</div>
      <div className="stat-value" style={accent ? { color: accent } : undefined}>
        {value ?? '—'}
      </div>
      {sub != null && <div className="stat-sub">{sub}</div>}
      {children}
    </div>
  );
}
