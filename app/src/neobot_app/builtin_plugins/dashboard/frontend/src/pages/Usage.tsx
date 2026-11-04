import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api/endpoints';
import type { UsagePayload, UsageRecordItem } from '../api/types';
import AnalyticsTable from '../components/AnalyticsTable';
import LineChart from '../components/LineChart';
import Modal from '../components/Modal';
import Button from '../components/ui/Button';
import EmptyState from '../components/ui/EmptyState';
import PageHeader from '../components/ui/PageHeader';
import { PanelSkeleton } from '../components/ui/PageSkeleton';
import { POLL } from '../data/queryKeys';
import { useAutoRefresh } from '../hooks/useAutoRefresh';
import InlineAlert from '../components/ui/InlineAlert';
import { aggregateAmount, fmtCost, pendingCalls } from '../utils/usageCost';

const RANGES = [
  { key: '24h', label: '近 24 小时', hours: 24, bucket: 'hour' },
  { key: '7d', label: '近 7 天', hours: 168, bucket: 'hour' },
  { key: '30d', label: '近 30 天', hours: 720, bucket: 'day' },
];
function fillTimeGaps(points: NonNullable<UsagePayload['points']>, bucket: string) {
  const parse = (at = '') => Date.parse(at.length === 19 ? at + 'Z' : at);
  const first = parse(points[0]?.at);
  const last = parse(points.at(-1)?.at);
  const step = (bucket === 'day' ? 24 : 1) * 3_600_000;
  if (!Number.isFinite(first) || !Number.isFinite(last) || last < first || last - first > 720 * 3_600_000) {
    return points;
  }
  const byTime = new Map(points.map((point) => [parse(point.at), point]));
  const filled: typeof points = [];
  for (let time = first; time <= last; time += step) {
    filled.push(byTime.get(time) || { at: new Date(time).toISOString(), calls: 0 });
  }
  return filled;
}
const TABLES = [
  { key: 'models', label: '按模型' },
  { key: 'modules', label: '按调用模块' },
  { key: 'records', label: '最近调用' },
] as const;
const COMPONENT_NAMES: Record<string, string> = {
  cache_hit: '缓存命中输入',
  cache_miss: '缓存未命中输入',
  output: '输出',
};
const fmtExact = (value?: number) => value?.toLocaleString('zh-CN') ?? '—';
const MODULE_NAMES: Record<string, string> = {
  'agent:memory': '档案总结',
  'agent:chat_interaction': '聊天互动',
  'agent:image_parse': '图片理解',
  'agent:willingness': '发言意愿',
  reply_agent: 'Agent 回复',
  reply_common: '普通回复',
  memory_compaction: '记忆压缩',
};
const moduleLabel = (value?: string) => (value && (MODULE_NAMES[value] || value)) || '—';
const recordAmount = (item: UsageRecordItem) =>
  item.cost_source === 'unpriced' || item.unverified_zero ? '—' : fmtCost(item.cost_cny);

function fmtTokens(value?: number | null): string {
  const num = Number(value || 0);
  if (num >= 1_000_000_000) return (num / 1_000_000_000).toFixed(2) + ' B';
  if (num >= 1_000_000) return (num / 1_000_000).toFixed(2) + ' M';
  if (num >= 1_000) return (num / 1_000).toFixed(1) + ' K';
  return String(num);
}
function hoverLabel(at?: string | null, bucket?: string): string {
  if (!at) return '';
  return bucket === 'day' ? at.slice(0, 10) : at.slice(0, 16).replace('T', ' ');
}
function sourceLabel(source?: string | null): string {
  const text = String(source || 'builtin');
  if (text === 'unpriced') return '未配置价格';
  if (text === 'partial') return '部分待核价';
  if (text.startsWith('script:')) return '脚本: ' + (text.slice(7) || '未命名');
  if (text.startsWith('fallback:')) return '兜底: ' + (text.slice(9) || 'unknown');
  return '固定计费';
}
function sourceTagClass(source?: string | null): string {
  return source?.startsWith('script:') ? 'tag info' : source?.startsWith('fallback:') ? 'tag err' : 'tag';
}
// 列表会继续写入，取分项时按记录内容匹配，不能沿用旧列表下标。
function recordKey(item: UsageRecordItem): string {
  return JSON.stringify([
    item.at,
    item.module,
    item.provider_name,
    item.model_name,
    item.input_tokens,
    item.output_tokens,
    item.cache_hit_tokens,
    item.cache_miss_tokens,
    item.cost_cny,
    item.cost_source,
  ]);
}

export default function Usage() {
  const [range, setRange] = useState('24h');
  const [data, setData] = useState<UsagePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [records, setRecords] = useState<UsageRecordItem[]>([]);
  const [recordsError, setRecordsError] = useState('');
  const [recordsLoading, setRecordsLoading] = useState(true);
  const [table, setTable] = useState<(typeof TABLES)[number]['key']>('models');
  const [view, setView] = useState('cost');
  const [tokenKind, setTokenKind] = useState<'input' | 'output'>('input');
  const [detailItem, setDetailItem] = useState<UsageRecordItem | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const [billingHelp, setBillingHelp] = useState(false);
  const seriesRequest = useRef(0);
  const recordsRequest = useRef(0);
  const detailRequest = useRef(0);
  const active = RANGES.find((item) => item.key === range) || RANGES[0];
  const closeDetail = useCallback(() => {
    detailRequest.current += 1;
    setDetailItem(null);
    setDetailError('');
    setDetailLoading(false);
  }, []);
  const read = useCallback(async () => {
    const request = ++seriesRequest.current;
    setLoading(true);
    try {
      const result = await api.seriesUsage(active.hours, active.bucket);
      if (request !== seriesRequest.current) return;
      if (!result.ok || !result.data) {
        setError(result.error || '读取用量数据失败');
        return;
      }
      setError('');
      setData(result.data);
    } catch {
      if (request === seriesRequest.current) setError('读取用量数据失败，请刷新重试');
    } finally {
      if (request === seriesRequest.current) setLoading(false);
    }
  }, [active.hours, active.bucket]);
  const readRecords = useCallback(async () => {
    const request = ++recordsRequest.current;
    setRecordsLoading(true);
    try {
      const result = await api.usageRecords(active.hours, 20, false);
      if (request !== recordsRequest.current) return;
      if (!result.ok || !result.data || result.data.available === false) {
        setRecordsError(result.error || result.data?.error || '读取最近调用失败');
        return;
      }
      setRecordsError('');
      setRecords(result.data.items || []);
    } catch {
      if (request === recordsRequest.current) setRecordsError('读取最近调用失败，请刷新重试');
    } finally {
      if (request === recordsRequest.current) setRecordsLoading(false);
    }
  }, [active.hours]);
  useEffect(() => {
    setData(null);
    setError('');
    setRecords([]);
    setRecordsError('');
    closeDetail();
    void Promise.all([read(), readRecords()]);
    return () => {
      seriesRequest.current += 1;
      recordsRequest.current += 1;
      detailRequest.current += 1;
    };
  }, [read, readRecords, closeDetail]);
  useAutoRefresh(() => Promise.all([read(), readRecords()]), {
    enabled: !loading && !recordsLoading,
    interval: POLL.usage,
    pauseWhileEditing: false,
  });

  const bucket = data?.bucket || active.bucket;
  const points = useMemo(() => fillTimeGaps(data?.points || [], bucket), [data, bucket]);
  const totals = data?.totals || {};
  const unpriced = totals.unpriced_calls || 0;
  const unverified = totals.unverified_zero_calls || 0;
  const partial = totals.partial_calls || 0;
  const partialCost = pendingCalls(totals) > 0;
  const summaryCost = aggregateAmount(totals);
  const hasPricedCalls = summaryCost !== '—';
  const costSeries = useMemo(
    () =>
      points.map((item) =>
        !hasPricedCalls || aggregateAmount(item) === '—' ? null : Number(item.cost_cny || 0),
      ),
    [points, hasPricedCalls],
  );
  const costPeak = costSeries.reduce<number | null>(
    (peak, value) => (value === null ? peak : Math.max(peak ?? value, value)),
    null,
  );
  const inputSeries = useMemo(() => points.map((item) => Number(item.input_tokens || 0)), [points]);
  const outputSeries = useMemo(() => points.map((item) => Number(item.output_tokens || 0)), [points]);
  const labels = useMemo(() => points.map((item) => hoverLabel(item.at, bucket)), [points, bucket]);
  const bucketRows = useMemo(
    () =>
      points.map((item) => [
        { label: '调用', value: fmtTokens(item.calls) },
        { label: '输入 Token', value: fmtTokens(item.input_tokens) },
        { label: '输出 Token', value: fmtTokens(item.output_tokens) },
        { label: '花费', value: aggregateAmount(item) },
        ...(item.cache_hit_tokens == null
          ? []
          : [{ label: '缓存命中', value: fmtExact(item.cache_hit_tokens) }]),
        ...(pendingCalls(item) ? [{ label: '费用待核对', value: fmtExact(pendingCalls(item)) }] : []),
      ]),
    [points],
  );
  const rowsOf = useCallback((index: number) => bucketRows[index] || [], [bucketRows]);
  const fmtAxis = (label: string) =>
    active.hours === 24 ? label.slice(11, 16) : label.slice(5, 10).replace('-', '/');
  const period = points.length ? `${labels[0]} — ${labels[labels.length - 1]}` : active.label;
  const tokenSeries = tokenKind === 'input' ? inputSeries : outputSeries;
  const tokenTotal = tokenKind === 'input' ? totals.input_tokens : totals.output_tokens;
  const tokenName = tokenKind === 'input' ? '输入 Token' : '输出 Token';

  const showDetail = async (item: UsageRecordItem) => {
    const request = ++detailRequest.current;
    setDetailItem(item);
    setDetailError('');
    setDetailLoading(true);
    try {
      const result = await api.usageRecords(active.hours, 20, true);
      if (request !== detailRequest.current) return;
      if (!result.ok || !result.data || result.data.available === false) {
        setDetailError(result.error || result.data?.error || '读取计费分项失败，请重试');
        return;
      }
      const match = result.data.items?.find((candidate) => recordKey(candidate) === recordKey(item));
      if (match) setDetailItem(match);
      else setDetailError('这条记录已移出最近调用列表，请刷新列表后查看。');
    } catch {
      if (request === detailRequest.current) setDetailError('读取计费分项失败，请重试');
    } finally {
      if (request === detailRequest.current) setDetailLoading(false);
    }
  };

  return (
    <div className="page page--viewport analytics-page usage-page" data-view={view}>
      <PageHeader title="用量统计" />
      <div className="analytics-toolbar">
        <div className="analytics-segments" role="group" aria-label="时间范围">
          {RANGES.map((item) => (
            <button
              key={item.key}
              type="button"
              aria-pressed={range === item.key}
              onClick={() => setRange(item.key)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <button type="button" className="analytics-help" onClick={() => setBillingHelp(true)}>
          CNY · 计费说明
        </button>
      </div>
      {error && (
        <InlineAlert
          tone="error"
          title={error}
          actions={
            <Button size="sm" disabled={loading} onClick={() => void read()}>
              重试读取
            </Button>
          }
        />
      )}
      {loading && !data && <PanelSkeleton className="card" label="正在读取用量数据…" rows={5} />}
      {data?.available === false && (
        <EmptyState icon="settings" title="暂无用量数据">
          <p>{data.error || '数据库未就绪或还没有产生 API 调用记录。'}</p>
        </EmptyState>
      )}
      {data?.available && (
        <>
          <dl className="analytics-summary">
            <div>
              <dt>
                {partialCost ? '已计价金额' : '总花费'} <span>CNY</span>
              </dt>
              <dd>{summaryCost}</dd>
              {partialCost && (
                <small>
                  {unpriced > 0 && <span>{unpriced} 次未计价</span>}
                  {unpriced > 0 && partial > 0 && ' · '}
                  {partial > 0 && <span>{partial} 次部分待核价</span>}
                  {(unpriced > 0 || partial > 0) && unverified > 0 && ' · '}
                  {unverified > 0 && <span>{unverified} 次历史零金额待核对</span>}
                </small>
              )}
            </div>
            <div>
              <dt>API 调用</dt>
              <dd>
                {fmtTokens(totals.calls)} <small>次</small>
              </dd>
            </div>
            <div>
              <dt>输入 Token</dt>
              <dd>{fmtTokens(totals.input_tokens)}</dd>
            </div>
            <div>
              <dt>输出 Token</dt>
              <dd>{fmtTokens(totals.output_tokens)}</dd>
            </div>
          </dl>
          <div className="analytics-mobile-views analytics-segments" role="group" aria-label="用量视图">
            {[
              ['cost', '花费'],
              ['tokens', 'Token'],
              ['details', '明细'],
            ].map(([key, label]) => (
              <button type="button" key={key} aria-pressed={view === key} onClick={() => setView(key)}>
                {label}
              </button>
            ))}
          </div>
          <div className="usage-workbench">
            <section className="card analytics-card usage-cost-chart" aria-label="花费趋势">
              <div className="analytics-card-head">
                <h3>花费趋势</h3>
                <span>按{bucket === 'day' ? '天' : '小时'}汇总</span>
              </div>
              <div className="analytics-chart-summary">
                <strong>{summaryCost}</strong>
                <span>
                  峰值 <b>{costPeak === null ? '—' : fmtCost(costPeak)}</b>
                </span>
              </div>
              {points.length ? (
                <div className="analytics-chart">
                  <LineChart
                    fit
                    showXAxis
                    xTickFormatter={fmtAxis}
                    values={costSeries}
                    labels={labels}
                    name="花费"
                    fmtTick={fmtCost}
                    leftPadding={86}
                    extraRows={rowsOf}
                  />
                </div>
              ) : (
                <div className="analytics-chart-empty">
                  <EmptyState compact title="还没有花费记录">
                    调用模型后，这里会显示每个时间段的花费。
                  </EmptyState>
                </div>
              )}
              <div className="analytics-chart-caption">
                <span className="chart-legend">
                  <i />
                  已计价净花费 · 含冲抵
                </span>
                <span title={period}>{period}</span>
              </div>
            </section>
            <section
              className="card analytics-card usage-token-chart"
              data-token={tokenKind}
              aria-label="Token 趋势"
            >
              <div className="analytics-card-head">
                <h3>Token 趋势</h3>
                <div
                  className="analytics-segments analytics-segments--small"
                  role="group"
                  aria-label="Token 类型"
                >
                  <button
                    type="button"
                    aria-pressed={tokenKind === 'input'}
                    onClick={() => setTokenKind('input')}
                  >
                    输入
                  </button>
                  <button
                    type="button"
                    aria-pressed={tokenKind === 'output'}
                    onClick={() => setTokenKind('output')}
                  >
                    输出
                  </button>
                </div>
              </div>
              <div className="analytics-chart-summary">
                <strong>{fmtTokens(tokenTotal)}</strong>
                <span>
                  峰值 <b>{fmtTokens(tokenSeries.length ? Math.max(...tokenSeries) : 0)}</b>
                </span>
              </div>
              {points.length ? (
                <div className="analytics-chart">
                  <LineChart
                    key={tokenKind}
                    fit
                    showXAxis
                    xTickFormatter={fmtAxis}
                    values={tokenSeries}
                    labels={labels}
                    name={tokenName}
                    fmtTick={fmtTokens}
                    leftPadding={66}
                    extraRows={rowsOf}
                  />
                </div>
              ) : (
                <div className="analytics-chart-empty">
                  <EmptyState compact title="还没有 Token 记录">
                    输入与输出会分别统计，悬停数据点可查看完整用量。
                  </EmptyState>
                </div>
              )}
              <div className="analytics-chart-caption">
                <span className="chart-legend">
                  <i />
                  {tokenName}
                </span>
                <span>{points.length} 个时间段 · 悬停查看详情</span>
              </div>
            </section>
            <section className="card analytics-card usage-details" aria-label="用量明细">
              <div className="analytics-card-head">
                <div className="analytics-table-tabs" role="group" aria-label="用量明细类型">
                  {TABLES.map((item) => (
                    <button
                      key={item.key}
                      type="button"
                      aria-pressed={table === item.key}
                      onClick={() => setTable(item.key)}
                    >
                      {item.label}
                      {item.key === 'records' && recordsError && (
                        <span className="analytics-records-error">读取失败</span>
                      )}
                    </button>
                  ))}
                </div>
                <span>{table === 'records' ? '最近 20 次 · 金额为负表示冲抵' : active.label}</span>
              </div>
              {table === 'models' && (
                <AnalyticsTable
                  key={`models-${range}`}
                  items={data.models || []}
                  label="按模型的用量明细"
                  columns={['模型 / 供应商', '调用', '输入 Token', '输出 Token', '花费']}
                  className="analytics-aggregate-table"
                  renderRow={(item, index) => (
                    <tr key={index}>
                      <td>
                        <strong title={item.model_name}>{item.model_name || '—'}</strong>
                        <span title={item.provider_name}>{item.provider_name || '—'}</span>
                      </td>
                      <td>{fmtTokens(item.calls)}</td>
                      <td>{fmtTokens(item.input_tokens)}</td>
                      <td>{fmtTokens(item.output_tokens)}</td>
                      <td>
                        {aggregateAmount(item)}
                        {pendingCalls(item) > 0 && <span>{pendingCalls(item)} 次待核价</span>}
                      </td>
                    </tr>
                  )}
                />
              )}
              {table === 'modules' && (
                <AnalyticsTable
                  key={`modules-${range}`}
                  items={data.modules || []}
                  label="按调用模块的用量明细"
                  columns={['调用模块', '调用', '输入 Token', '输出 Token', '花费']}
                  className="analytics-aggregate-table"
                  renderRow={(item, index) => (
                    <tr key={index}>
                      <td>
                        <strong title={item.module_name}>{moduleLabel(item.module_name)}</strong>
                      </td>
                      <td>{fmtTokens(item.calls)}</td>
                      <td>{fmtTokens(item.input_tokens)}</td>
                      <td>{fmtTokens(item.output_tokens)}</td>
                      <td>
                        {aggregateAmount(item)}
                        {pendingCalls(item) > 0 && <span>{pendingCalls(item)} 次待核价</span>}
                      </td>
                    </tr>
                  )}
                />
              )}
              {table === 'records' && (
                <>
                  {recordsError && (
                    <InlineAlert
                      tone="warning"
                      title={recordsError}
                      actions={
                        <Button size="sm" disabled={recordsLoading} onClick={() => void readRecords()}>
                          重试读取
                        </Button>
                      }
                    />
                  )}
                  <AnalyticsTable
                    key={`records-${range}`}
                    items={records}
                    label="最近调用明细"
                    columns={['时间 / 模块', '模型', '输入 / 命中', '输出', '金额 / 来源', '分项']}
                    className="analytics-records-table"
                    empty={recordsLoading ? '正在读取最近调用…' : '当前时间范围内没有调用记录'}
                    renderRow={(item, index) => (
                      <tr key={index}>
                        <td>
                          <strong>{hoverLabel(item.at)}</strong>
                          <span title={item.module}>{moduleLabel(item.module)}</span>
                        </td>
                        <td>
                          <span className="analytics-cell-text" title={item.model_name}>
                            {item.model_name || '—'}
                          </span>
                        </td>
                        <td>
                          <strong>{fmtExact(item.input_tokens)}</strong>
                          <span title="缓存命中输入 Token">{fmtExact(item.cache_hit_tokens)}</span>
                        </td>
                        <td>{fmtExact(item.output_tokens)}</td>
                        <td className={item.negative || Number(item.cost_cny) < 0 ? 'analytics-credit' : ''}>
                          <strong>{recordAmount(item)}</strong>
                          <span className="analytics-cell-text" title={sourceLabel(item.cost_source)}>
                            {item.unverified_zero ? '历史零金额待核对' : sourceLabel(item.cost_source)}
                          </span>
                          {(item.negative || Number(item.cost_cny) < 0) && <span>冲抵</span>}
                        </td>
                        <td>
                          <Button size="sm" variant="ghost" onClick={() => void showDetail(item)}>
                            查看分项
                          </Button>
                        </td>
                      </tr>
                    )}
                  />
                </>
              )}
            </section>
          </div>
        </>
      )}
      <Modal
        open={!!detailItem}
        title="调用计费详情"
        onClose={closeDetail}
        className="analytics-detail-modal"
      >
        {detailItem && (
          <>
            <div className="usage-detail-total">
              <strong className={Number(detailItem.cost_cny) < 0 ? 'analytics-credit' : ''}>
                {recordAmount(detailItem)}
              </strong>
              <span className={sourceTagClass(detailItem.cost_source)}>
                {detailItem.unverified_zero ? '历史零金额待核对' : sourceLabel(detailItem.cost_source)}
              </span>
              {(detailItem.negative || Number(detailItem.cost_cny) < 0) && (
                <span className="analytics-credit">冲抵</span>
              )}
            </div>
            <dl className="usage-detail-meta">
              <div>
                <dt>时间</dt>
                <dd>{hoverLabel(detailItem.at)}</dd>
              </div>
              <div>
                <dt>调用模块</dt>
                <dd>{moduleLabel(detailItem.module)}</dd>
              </div>
              <div>
                <dt>模型</dt>
                <dd>{detailItem.model_name || '—'}</dd>
              </div>
              <div>
                <dt>供应商</dt>
                <dd>{detailItem.provider_name || '—'}</dd>
              </div>
              <div>
                <dt>输入 Token</dt>
                <dd>{fmtExact(detailItem.input_tokens)}</dd>
              </div>
              <div>
                <dt>输出 Token</dt>
                <dd>{fmtExact(detailItem.output_tokens)}</dd>
              </div>
              <div>
                <dt>缓存命中输入</dt>
                <dd>{fmtExact(detailItem.cache_hit_tokens)}</dd>
              </div>
              <div>
                <dt>缓存未命中输入</dt>
                <dd>
                  {detailItem.cache_miss_tokens === 0 &&
                  (detailItem.input_tokens || 0) > (detailItem.cache_hit_tokens || 0)
                    ? '未记录'
                    : fmtExact(detailItem.cache_miss_tokens)}
                </dd>
              </div>
            </dl>
            <div className="usage-detail-breakdown">
              <h4>计费分项</h4>
              {detailLoading ? (
                <p className="muted">正在读取分项…</p>
              ) : detailError ? (
                <>
                  <InlineAlert tone="warning" title={detailError} />
                  <Button size="sm" onClick={() => void showDetail(detailItem)}>
                    重试
                  </Button>
                </>
              ) : (
                <>
                  {Object.keys(detailItem.cost_detail?.components || {}).length ? (
                    <dl>
                      {Object.entries(detailItem.cost_detail?.components || {}).map(([name, value]) => (
                        <div key={name}>
                          <dt>{COMPONENT_NAMES[name] || name}</dt>
                          <dd>
                            {detailItem.cost_detail?.unpriced_components?.includes(name)
                              ? '待核价'
                              : fmtCost(value)}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  ) : (
                    <p className="muted">这条记录没有保存计费分项。</p>
                  )}
                  {detailItem.cost_detail?.note && <p>说明：{detailItem.cost_detail.note}</p>}
                  {detailItem.cost_detail?.error && (
                    <InlineAlert tone="warning" title={`错误：${detailItem.cost_detail.error}`} />
                  )}
                </>
              )}
            </div>
          </>
        )}
      </Modal>
      <Modal open={billingHelp} title="计费说明" onClose={() => setBillingHelp(false)}>
        <p>
          金额单位为 CNY。未计价时，请在模型配置中检查每百万 Token
          单价。历史零金额保留原值，负金额表示退款或冲抵。 输入 Token
          包含缓存命中，档案总结等后台模型调用单独记账。
        </p>
        <p>
          最近调用保留当前时间范围内最近 20
          条记录。打开「查看分项」后，再读取该次调用的脚本分项、说明或计费错误。
        </p>
      </Modal>
    </div>
  );
}
