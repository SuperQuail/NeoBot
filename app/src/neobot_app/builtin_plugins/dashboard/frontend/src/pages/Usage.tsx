// Usage.jsx —— API 消耗（金额 / Token）图表 + 计费来源（spec(4) Part A）
import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../api/endpoints';
import type { UsagePayload, UsageRecordItem, UsageTotals } from '../api/types';
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
  if (Math.abs(num) < 0.01) return '¥' + num.toFixed(6);
  if (Math.abs(num) < 1) return '¥' + num.toFixed(4);
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

/** 来源口径：内建固定计费 / 脚本: xxx / 兜底: 原因（与后端 cost_source 闭集一致）。 */
function sourceLabel(source?: string | null): string {
  const text = String(source || 'builtin');
  if (text.startsWith('script:')) return '脚本: ' + (text.slice(7) || '未命名');
  if (text.startsWith('fallback:')) return '兜底: ' + (text.slice(9) || 'unknown');
  return '固定计费';
}

function sourceTagClass(source?: string | null): string {
  const text = String(source || 'builtin');
  if (text.startsWith('script:')) return 'tag info';
  if (text.startsWith('fallback:')) return 'tag err';
  return 'tag';
}

export default function Usage() {
  const [range, setRange] = useState('24h');
  const [data, setData] = useState<UsagePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [records, setRecords] = useState<UsageRecordItem[] | null>(null);
  const [detailIndex, setDetailIndex] = useState(-1);
  const [detailItem, setDetailItem] = useState<UsageRecordItem | null>(null);

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

  // 来源列表：只取最近若干条，分项（cost_detail）展开时才按需再取一次
  const readRecords = useCallback(async () => {
    const result = await api.usageRecords(active.hours, 20, false);
    if (!result.ok || !result.data) return;
    setRecords(result.data.items || []);
    setDetailIndex(-1);
    setDetailItem(null);
  }, [active.hours]);

  useEffect(() => {
    read();
  }, [read]);

  useEffect(() => {
    readRecords();
  }, [readRecords]);

  const points = data?.points || [];
  const totals: UsageTotals = data?.totals || {};
  const bucket = data?.bucket || active.bucket;
  const costSeries = useMemo(() => points.map((item) => Number(item.cost_cny || 0)), [points]);
  const inputSeries = useMemo(() => points.map((item) => Number(item.input_tokens || 0)), [points]);
  const outputSeries = useMemo(() => points.map((item) => Number(item.output_tokens || 0)), [points]);
  const labels = useMemo(() => points.map((item) => shortLabel(item.at, bucket)), [points, bucket]);

  // 分项按需取：默认视图不查 cost_detail，只有点「展开」才带 detail=1 再查一次
  const toggleRow = async (index: number) => {
    if (detailIndex === index) {
      setDetailIndex(-1);
      setDetailItem(null);
      return;
    }
    setDetailIndex(index);
    setDetailItem(records && records[index] ? records[index] : null);
    const result = await api.usageRecords(active.hours, 20, true);
    if (!result.ok || !result.data) return;
    setDetailItem((result.data.items || [])[index] || null);
  };

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
        <span className="muted small">金额单位：CNY（按模型绑定的计价脚本或价格表计算）</span>
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

          <section className="card">
            <div className="card-head">
              <h3>最近调用（计费来源）</h3>
              <span className="muted small">{(records || []).length} 条 · 金额为负表示冲抵</span>
            </div>
            <table className="model-table">
              <thead>
                <tr>
                  <th>时间</th><th>模块</th><th>模型</th><th>来源</th><th>金额</th><th>分项</th>
                </tr>
              </thead>
              <tbody>
                {(records || []).map((item, index) => (
                  <Fragment key={(item.at || '') + ':' + index}>
                    <tr>
                      <td className="muted small">{shortLabel(item.at, 'hour')}</td>
                      <td><code>{item.module}</code></td>
                      <td><code>{item.model_name}</code></td>
                      <td>
                        <span className={sourceTagClass(item.cost_source) + ' usage-source-tag'}>
                          {sourceLabel(item.cost_source)}
                        </span>
                      </td>
                      <td className={item.negative ? 'usage-cost-negative' : ''}>
                        {fmtCost(item.cost_cny)}
                        {item.negative && <span className="muted small"> · 冲抵</span>}
                      </td>
                      <td>
                        <button type="button" className="usage-detail-toggle" onClick={() => toggleRow(index)}>
                          {detailIndex === index ? '收起' : '展开'}
                        </button>
                      </td>
                    </tr>
                    {detailIndex === index && (
                      <tr>
                        <td colSpan={6} className="muted small">
                          {detailItem?.cost_detail?.components &&
                          Object.keys(detailItem.cost_detail.components).length > 0 ? (
                            Object.entries(detailItem.cost_detail.components).map(([name, value]) => (
                              <span key={name} className="usage-detail-part">
                                {name}: {fmtCost(value)}
                              </span>
                            ))
                          ) : (
                            <span>无分项（固定计费或脚本未返回 components）</span>
                          )}
                          {detailItem?.cost_detail?.note && <div>说明：{detailItem.cost_detail.note}</div>}
                          {detailItem?.cost_detail?.error && <div>错误：{detailItem.cost_detail.error}</div>}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
                {(records || []).length === 0 && (
                  <tr><td colSpan={6} className="muted">暂无数据</td></tr>
                )}
              </tbody>
            </table>
          </section>
        </>
      )}
    </div>
  );
}
