import { useState } from 'react';
import type { SeriesPoint } from '../api/types';
import { fmtNum } from '../utils/format';
import LineChart from './LineChart';

export default function MessageTrendCard({ series = [] }: { series?: SeriesPoint[] }) {
  const [days, setDays] = useState(30);
  const points = series.slice(-days);
  const valid = points.filter((point) => point.count != null && Number.isFinite(point.count));
  const total = valid.reduce((sum, point) => sum + (point.count || 0), 0);
  const peak = valid.reduce((max, point) => Math.max(max, point.count || 0), 0);
  return (
    <section className="card monitor-card message-trend-card" aria-label="消息趋势">
      <div className="monitor-card-head">
        <h3>消息趋势</h3>
        <div className="monitor-range" aria-label="消息趋势时间范围">
          {[7, 30].map((range) => (
            <button key={range} aria-pressed={range === days} onClick={() => setDays(range)}>
              {range} 天
            </button>
          ))}
        </div>
      </div>
      <div className="trend-metrics">
        <div className="trend-primary">
          <strong>{valid.length ? fmtNum(total) : '—'}</strong>
          <span>条消息</span>
        </div>
        <dl>
          <div>
            <dt>日均</dt>
            <dd>{valid.length ? fmtNum(Math.round(total / valid.length)) : '—'}</dd>
          </div>
          <div>
            <dt>单日峰值</dt>
            <dd>{valid.length ? fmtNum(peak) : '—'}</dd>
          </div>
        </dl>
      </div>
      <div className="monitor-chart">
        <LineChart
          fit
          showXAxis
          name="消息数量"
          values={points.map((point) => point.count ?? null)}
          labels={points.map((point, index) => point.date || point.at || `采样 ${index + 1}`)}
          fmtTick={(value) => (value >= 10000 ? `${Math.round(value / 1000)}k` : fmtNum(Math.round(value)))}
          fmtValue={(value) => `${fmtNum(value)} 条`}
        />
      </div>
      <div className="trend-caption">
        <span className="chart-legend">
          <i />
          每日消息
        </span>
        <span>{valid.length ? `${valid.length} 天有记录` : '等待消息记录'}</span>
      </div>
    </section>
  );
}
