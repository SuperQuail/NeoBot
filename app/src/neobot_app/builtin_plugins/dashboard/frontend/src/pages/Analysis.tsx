import { useState, type CSSProperties } from 'react';
import { ArrowLeft, ChevronRight, Info } from 'lucide-react';
import { api } from '../api/endpoints';
import type { AgentPromptReport, PromptPartReport } from '../api/types';
import { useQuery } from '../data/useQuery';
import { POLL, QK } from '../data/queryKeys';
import { fmt1, fmtNum } from '../utils/format';
import Modal from '../components/Modal';
import MonitorList from '../components/MonitorList';
import Button from '../components/ui/Button';
import EmptyState from '../components/ui/EmptyState';
import PageHeader from '../components/ui/PageHeader';
import InlineAlert from '../components/ui/InlineAlert';
import SelectControl from '../components/ui/SelectControl';
import { PanelSkeleton } from '../components/ui/PageSkeleton';

async function readAnalysis() {
  const result = await api.analysisPrompts();
  // 网络失败保留 query 中上次成功的数据，页面继续可读。
  if (!result) throw new Error('读取提示词分析失败，请刷新重试');
  return result;
}

const KIND_LABELS: Record<string, string> = {
  system: '系统提示词',
  tools: '工具定义',
  history: '历史',
  instructions: '指令',
};
const KIND_COLORS: Record<string, string> = {
  system: 'var(--brand)',
  tools: 'var(--info)',
  history: 'var(--ok)',
  instructions: 'var(--accent)',
};
const kindLabel = (kind?: string) => (kind ? KIND_LABELS[kind] || kind : '其他');
const partKey = (part: PromptPartReport, index: number) => `${part.kind}:${part.label}:${index}`;
function ratio(chars?: number, total?: number): number {
  return Number(total) > 0 ? Math.min(100, Math.max(0, (Number(chars || 0) / Number(total)) * 100)) : 0;
}
function formatGeneratedAt(ts?: number): string {
  return ts && isFinite(ts) ? new Date(ts * 1000).toLocaleString() : '';
}

function AgentInspector({ agent }: { agent: AgentPromptReport }) {
  const [selectedKey, setSelectedKey] = useState('');
  const [view, setView] = useState('sources');
  const parts = agent.parts || [];
  const selected = parts.find((part, index) => partKey(part, index) === selectedKey);
  const totalChars = Number(agent.total_chars || 0);
  const groups = Object.entries(
    parts.reduce<Record<string, number>>((acc, part) => {
      acc[part.kind || 'other'] = (acc[part.kind || 'other'] || 0) + Number(part.chars || 0);
      return acc;
    }, {}),
  );
  let offset = 0;

  if (agent.error)
    return (
      <section className="card analysis-error-card">
        <InlineAlert tone="error" title={agent.error} />
        {agent.note && <p className="muted">{agent.note}</p>}
      </section>
    );
  return (
    <div className="analysis-inspector" data-view={view}>
      <section className="card analysis-overview-card" aria-label="Agent 提示词概况">
        <div className="analysis-donut">
          <svg
            viewBox="0 0 120 120"
            role="img"
            aria-label={`提示词字符组成：${groups.map(([kind, chars]) => `${kindLabel(kind)} ${fmt1(ratio(chars, totalChars), '%')}`).join('，') || '暂无来源'}`}
          >
            <circle className="analysis-donut-track" cx="60" cy="60" r="48" />
            {groups.map(([kind, chars]) => {
              const share = Math.min(ratio(chars, totalChars), Math.max(0, 100 - offset));
              const start = offset;
              offset += share;
              return (
                <circle
                  key={kind}
                  cx="60"
                  cy="60"
                  r="48"
                  pathLength="100"
                  stroke={KIND_COLORS[kind] || 'var(--muted)'}
                  strokeDasharray={`${share} ${100 - share}`}
                  strokeDashoffset={-start}
                />
              );
            })}
          </svg>
          <div>
            <strong>{parts.length}</strong>
            <span>个来源</span>
          </div>
        </div>
        <dl className="analysis-overview-metrics">
          <div>
            <dt>总字符数</dt>
            <dd>{fmtNum(agent.total_chars)}</dd>
          </div>
          <div>
            <dt>估算 Token</dt>
            <dd>{fmt1(agent.total_tokens)}</dd>
          </div>
        </dl>
        <div className="analysis-agent-context">
          <span>当前模型</span>
          <strong title={agent.model || '未指定模型'}>{agent.model || '未指定模型'}</strong>
          <p>{agent.note || '查看装配后的提示词组成，选择来源阅读内容。'}</p>
        </div>
      </section>
      <div className="analytics-mobile-views analytics-segments" role="group" aria-label="分析视图">
        <button type="button" aria-pressed={view === 'sources'} onClick={() => setView('sources')}>
          来源组成
        </button>
        <button type="button" aria-pressed={view === 'text'} onClick={() => setView('text')}>
          来源文本
        </button>
      </div>
      <div className="analysis-source-workspace">
        <section className="card analytics-card analysis-source-list" aria-label="提示词来源">
          <div className="analytics-card-head">
            <h3>
              来源组成 <span>{parts.length}</span>
            </h3>
            <span>占总字符数</span>
          </div>
          <MonitorList
            items={parts}
            label="提示词来源"
            empty="该 Agent 没有可统计的提示词来源"
            rowHeight={76}
            renderItem={(part, index) => {
              const pct = ratio(part.chars, totalChars);
              const active = selectedKey === partKey(part, index);
              return (
                <button
                  type="button"
                  className="analysis-source-button"
                  aria-pressed={active}
                  aria-label={`查看 ${part.label || kindLabel(part.kind)}`}
                  style={{ '--source-color': KIND_COLORS[part.kind] || 'var(--muted)' } as CSSProperties}
                  onClick={() => {
                    setSelectedKey(partKey(part, index));
                    setView('text');
                  }}
                >
                  <span className="analysis-source-title">
                    <i />
                    <strong title={part.label || kindLabel(part.kind)}>
                      {part.label || kindLabel(part.kind)}
                    </strong>
                    <b>{fmt1(pct, '%')}</b>
                    <ChevronRight size={14} />
                  </span>
                  <span className="analysis-source-numbers">
                    <span>{kindLabel(part.kind)}</span>
                    <span>
                      {fmtNum(part.chars)} 字符 · {fmt1(part.tokens)} token
                    </span>
                  </span>
                  <span className="analysis-source-bar">
                    <i style={{ width: `${pct}%` }} />
                  </span>
                </button>
              );
            }}
          />
        </section>
        <section className="card analytics-card analysis-source-reader" aria-label="来源文本">
          <div className="analytics-card-head">
            <div className="analysis-reader-title">
              <button
                type="button"
                className="icon-btn analysis-back"
                aria-label="返回来源组成"
                onClick={() => setView('sources')}
              >
                <ArrowLeft size={15} />
              </button>
              <h3 title={selected?.label}>{selected?.label || '来源文本'}</h3>
            </div>
            {selected && <span>{fmtNum(selected.chars)} 字符</span>}
          </div>
          {selected ? (
            <>
              {selected.truncated && <InlineAlert tone="warning" title="已截断展示，统计按全文计算" />}
              {/* eslint-disable jsx-a11y/no-noninteractive-tabindex -- 长文本阅读区需要键盘滚动入口。 */}
              <div
                tabIndex={0}
                className="analysis-source-content"
                role="region"
                aria-label={`${selected.label}内容`}
              >
                {selected.text ? (
                  <pre>{selected.text}</pre>
                ) : (
                  <EmptyState compact>该来源没有可展示的文本</EmptyState>
                )}
              </div>
              {/* eslint-enable jsx-a11y/no-noninteractive-tabindex */}
              <div className="analysis-reader-foot">
                <span>{kindLabel(selected.kind)}</span>
                <span>
                  {fmt1(selected.tokens)} 估算 Token · {fmt1(ratio(selected.chars, totalChars), '%')}
                </span>
              </div>
            </>
          ) : (
            <div className="analysis-source-placeholder">
              <EmptyState icon="code" title="选择一个来源">
                查看具体提示词、工具定义或历史内容。
              </EmptyState>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

export default function Analysis() {
  const query = useQuery(QK.analysis, readAnalysis, { interval: POLL.analysis });
  const [agentId, setAgentId] = useState('');
  const [methodOpen, setMethodOpen] = useState(false);
  const data = query.data;
  const agents = data?.agents || [];
  const selectedIndex = Math.max(
    0,
    agents.findIndex((agent, index) => `${agent.name}:${index}` === agentId),
  );
  const agent = agents[selectedIndex];
  const selectedId = agent ? `${agent.name}:${selectedIndex}` : '';
  const unavailable = !query.loading && (!data || data.available === false || data.ok === false);
  const reason =
    data?.error ||
    (query.error && query.error !== 'no-data' ? query.error : '') ||
    '分析器未注入或接口暂不可用。';
  return (
    <div className="page page--viewport analytics-page analysis-page">
      <PageHeader title="提示词分析" />
      {agents.length > 0 && !unavailable && (
        <div className="analytics-toolbar analysis-toolbar">
          <div className="analysis-agent-select">
            <span>Agent</span>
            <SelectControl
              label="选择 Agent"
              value={selectedId}
              onValueChange={setAgentId}
              options={agents.map((item, index) => ({
                value: `${item.name}:${index}`,
                label: (item.name || '未命名 Agent') + (item.error ? ' · 装配失败' : ''),
              }))}
            />
            <small>{agents.length} 个</small>
          </div>
          <div className="analysis-toolbar-info">
            <span>{formatGeneratedAt(data?.generated_at)}</span>
            <Button size="sm" variant="ghost" onClick={() => setMethodOpen(true)}>
              <Info size={14} />
              统计口径
            </Button>
          </div>
        </div>
      )}
      {query.error && data?.available && (
        <InlineAlert
          tone="warning"
          title="刷新失败，正在展示上次结果"
          actions={
            <Button size="sm" disabled={query.loading} onClick={() => void query.refetch()}>
              重试读取
            </Button>
          }
        >
          {reason}
        </InlineAlert>
      )}
      {query.loading && !data && <PanelSkeleton label="正在读取提示词分析" kind="text" rows={5} />}
      {unavailable && (
        <EmptyState icon="code" title="提示词分析不可用">
          <p>{reason}</p>
          <Button disabled={query.loading} onClick={() => void query.refetch()}>
            重试读取
          </Button>
        </EmptyState>
      )}
      {!unavailable && agent && <AgentInspector key={selectedId} agent={agent} />}
      {!unavailable && !agent && !query.loading && <EmptyState compact>没有可分析的 Agent</EmptyState>}
      <Modal open={methodOpen} title="统计口径" onClose={() => setMethodOpen(false)}>
        <p>{data?.rule || '接口未提供统计口径。'}</p>
        {formatGeneratedAt(data?.generated_at) && (
          <p className="muted small">生成于 {formatGeneratedAt(data?.generated_at)}</p>
        )}
        <p className="muted small">占比按总字符数计算；截断只影响文本展示，合计与占比仍采用全文统计。</p>
      </Modal>
    </div>
  );
}
