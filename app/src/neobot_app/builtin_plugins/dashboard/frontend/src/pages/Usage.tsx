// Usage.jsx —— API 消耗（金额 / Token）图表
import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../api/endpoints';
import type { UsagePayload, UsageTotals } from '../api/types';
import Icon from '../components/Icon';
import LineChart from '../components/LineChart';
import StatCard from '../components/StatCard';

const RANGES = [
  { key: '24h', label: '近 24 小时', hours: 24, bucket: 'hour' },
  { key: '7d', label: '近 7 天', hours: 24 * 7, bucket: 'hour' },
  { key: '30d', label: '近 30 天', hours: 24 * 30, bucket: 'day' },
];

function fmtCost(value?: number | null): string {
  const num = Number(value || 0);
  if (num === 0) return '¥0';
  if (num < 0.01) return '¥' + num.toFixed(6);
  if (num < 1) return '¥' + num.toFixed(4);
  return '¥' + num.toFixed(2);
}

function fmtTokens(value?: number | null): string {
  const num = Number(value || 0);
  if (num >= 1_000_000) return (num / 1_000_000).toFixed(2) + ' M';
  if (num >= 1_000) return (num / 1_000).toFixed(1) + ' K';
  return String(num);
}

function shortLabel(at?: string | null, bucket?: string): string {
  if (!at) return '';
  if (bucket === 'day') return at.slice(5);
  return at.slice(5, 13).replace('T', ' ');
}

export default function Usage() {
  const [range, setRange] = useState('24h');
  const [data, setData] = useState<UsagePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const active = RANGES.find((item) => item.key === range) || RANGES[0];

  const read = useCallback(async () => {
    setLoading(true);
    const result = await api.seriesUsage(active.hours, active.bucket);
    setLoading(false);
    if (!result.ok) {
      setError(result.error || '读取用量数据失败');
      return;
    }
    setError('');
    setData(result.data);
  }, [active.hours, active.bucket]);

  useEffect(() => {
    read();
  }, [read]);

  const points = data?.points || [];
  const totals: UsageTotals = data?.totals || {};
  const bucket = data?.bucket || active.bucket;
  const costSeries = useMemo(() => points.map((item) => Number(item.cost_cny || 0)), [points]);
  const inputSeries = useMemo(() => points.map((item) => Number(item.input_tokens || 0)), [points]);
  const outputSeries = useMemo(() => points.map((item) => Number(item.output_tokens || 0)), [points]);
  const labels = useMemo(() => points.map((item) => shortLabel(item.at, bucket)), [points, bucket]);

  return (
    <div className="page usage-page">
      <div className="config-tabs cfg-top-tabs">
        <div role="tablist" aria-label="时间范围">
          {RANGES.map((item) => (
            <button
              key={item.key}
              role="tab"
              aria-selected={range === item.key}
              className={range === item.key ? 'active' : ''}
              onClick={() => setRange(item.key)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div className="spacer" />
        <span className="muted small">金额单位：CNY（按模型价格表计算）</span>
        <button className="btn" disabled={loading} onClick={read}>
          <Icon name="refresh" /> {loading ? '读取中…' : '刷新'}
        </button>
      </div>

      {error && <div className="workspace-error" role="alert">{error}</div>}
      {data && data.available === false && (
        <div className="workspace-empty">
          <Icon name="settings" />
          <h3>暂无用量数据</h3>
          <p>数据库未就绪或还没有产生 API 调用记录。</p>
        </div>
      )}

      {data?.available && (
        <>
          <div className="stats-grid">
            <StatCard label="总花费" value={fmtCost(totals.cost_cny)} sub={active.label} />
            <StatCard label="API 调用" value={fmtTokens(totals.calls)} sub={active.label} />
            <StatCard label="输入 Token" value={fmtTokens(totals.input_tokens)} sub={active.label} />
            <StatCard label="输出 Token" value={fmtTokens(totals.output_tokens)} sub={active.label} />
          </div>

          <section className="card">
            <div className="card-head">
              <h3>花费趋势</h3>
              <span className="muted small">{points.length} 个数据点</span>
            </div>
            <LineChart values={costSeries} fmtTick={(v) => fmtCost(v)} />
            <div className="chart-axis">{labels.map((label, index) => (
              <span key={index}>{label}</span>
            ))}</div>
          </section>

          <section className="card">
            <div className="card-head"><h3>Token 趋势</h3><span className="muted small">输入 / 输出</span></div>
            <LineChart values={inputSeries} fmtTick={(v) => fmtTokens(v)} />
            <p className="muted small">输入 Token</p>
            <LineChart values={outputSeries} fmtTick={(v) => fmtTokens(v)} />
            <p className="muted small">输出 Token</p>
          </section>

          <div className="usage-tables">
            <section className="card">
              <div className="card-head">
                <h3>按模型</h3>
                <span className="muted small">{(data.models || []).length} 个</span>
              </div>
              <table className="model-table">
                <thead>
                  <tr><th>模型</th><th>供应商</th><th>调用</th><th>输入</th><th>输出</th><th>花费</th></tr>
                </thead>
                <tbody>
                  {(data.models || []).map((item) => (
                    <tr key={item.provider_name + '/' + item.model_name}>
                      <td><code>{item.model_name}</code></td>
                      <td>{item.provider_name}</td>
                      <td>{fmtTokens(item.calls)}</td>
                      <td>{fmtTokens(item.input_tokens)}</td>
                      <td>{fmtTokens(item.output_tokens)}</td>
                      <td>{fmtCost(item.cost_cny)}</td>
                    </tr>
                  ))}
                  {(data.models || []).length === 0 && <tr><td colSpan={6} className="muted">暂无数据</td></tr>}
                </tbody>
              </table>
            </section>

            <section className="card">
              <div className="card-head">
                <h3>按调用模块</h3>
                <span className="muted small">{(data.modules || []).length} 个</span>
              </div>
              <table className="model-table">
                <thead>
                  <tr><th>模块</th><th>调用</th><th>输入</th><th>输出</th><th>花费</th></tr>
                </thead>
                <tbody>
                  {(data.modules || []).map((item) => (
                    <tr key={item.module_name}>
                      <td><code>{item.module_name}</code></td>
                      <td>{fmtTokens(item.calls)}</td>
                      <td>{fmtTokens(item.input_tokens)}</td>
                      <td>{fmtTokens(item.output_tokens)}</td>
                      <td>{fmtCost(item.cost_cny)}</td>
                    </tr>
                  ))}
                  {(data.modules || []).length === 0 && <tr><td colSpan={5} className="muted">暂无数据</td></tr>}
                </tbody>
              </table>
            </section>
          </div>
        </>
      )}
    </div>
  );
}
