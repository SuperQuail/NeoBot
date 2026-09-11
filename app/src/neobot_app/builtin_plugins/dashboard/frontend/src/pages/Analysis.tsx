// Analysis.tsx —— 提示词分析：各 Agent 装配出的提示词字符数与估算 token
// 数据来自 /api/analysis/prompts；估算口径直接展示接口返回的 rule，不在前端硬编码。
import { useState } from 'react';
import { api } from '../api/endpoints';
import type { AgentPromptReport, PromptPartReport } from '../api/types';
import { useQuery } from '../data/useQuery';
import { POLL, QK } from '../data/queryKeys';
import { fmt1, fmtNum } from '../utils/format';
import Icon from '../components/Icon';
import StatCard from '../components/StatCard';

/** part.kind → 中文标签；未登记的 kind 原样显示 */
const KIND_LABELS: Record<string, string> = {
  system: '系统提示词',
  tools: '工具定义',
  history: '历史',
  instructions: '指令',
};

const kindLabel = (kind?: string): string => (kind ? KIND_LABELS[kind] || kind : '其他');

/** 相对该 agent 总字符数的占比（0-100；总量为 0 时按 0 处理，避免除零） */
function ratio(chars?: number, total?: number): number {
  const sum = Number(total || 0);
  if (!(sum > 0)) return 0;
  const part = Number(chars || 0);
  return Math.min(100, Math.max(0, (part / sum) * 100));
}

function formatGeneratedAt(ts?: number): string {
  if (!ts || !isFinite(ts)) return '';
  return new Date(ts * 1000).toLocaleString();
}

interface PartRowProps {
  part: PromptPartReport;
  totalChars?: number;
  open: boolean;
  onToggle: () => void;
}

function PartRow({ part, totalChars, open, onToggle }: PartRowProps) {
  const pct = ratio(part.chars, totalChars);
  const label = part.label || kindLabel(part.kind);
  const text = part.text ?? '';
  return (
    <li className="analysis-part">
      <div className="analysis-part-head">
        <button
          type="button"
          className="cfg-collapse"
          aria-expanded={open}
          aria-label={(open ? '收起 ' : '展开 ') + label}
          onClick={onToggle}
        >
          <Icon name="chevron" />
        </button>
        <span className="tag info">{kindLabel(part.kind)}</span>
        <span className="analysis-part-label">{label}</span>
        <span className="muted small analysis-part-stats">
          {fmtNum(part.chars)} 字符 · {fmt1(part.tokens)} token · {fmt1(pct, '%')}
        </span>
      </div>
      {/* 占比条：仅作视觉提示，百分比已在上一行以文本给出 */}
      <div className="bar-track" aria-hidden="true">
        <div className="bar-fill ok" style={{ width: pct.toFixed(1) + '%' }} />
      </div>
      {open && (
        <div className="analysis-part-text">
          {part.truncated && <p className="muted small analysis-truncated">已截断展示，统计按全文计算</p>}
          {text ? <pre className="analysis-pre">{text}</pre> : <p className="muted small">该来源没有可展示的文本</p>}
        </div>
      )}
    </li>
  );
}

function AgentCard({ agent }: { agent: AgentPromptReport }) {
  const [openParts, setOpenParts] = useState<Record<number, boolean>>({});
  const parts = agent.parts || [];
  return (
    <section className="card analysis-agent">
      <div className="card-head">
        <h3>{agent.name || '未命名 Agent'}</h3>
        <div className="spacer" />
        {agent.model ? <span className="tag info">{agent.model}</span> : null}
      </div>
      {agent.note && <p className="muted small analysis-note">{agent.note}</p>}

      {agent.error ? (
        <div className="workspace-error" role="alert">{agent.error}</div>
      ) : (
        <>
          <div className="analysis-totals">
            <StatCard label="总字符数" value={fmtNum(agent.total_chars)} sub={parts.length + ' 个来源'} />
            <StatCard label="估算 Token" value={fmt1(agent.total_tokens)} sub="按接口口径估算" />
          </div>
          {parts.length === 0 ? (
            <div className="empty muted">该 Agent 没有可统计的提示词来源</div>
          ) : (
            <ul className="analysis-parts">
              {parts.map((part, index) => (
                <PartRow
                  key={part.kind + ':' + (part.label || index) + ':' + index}
                  part={part}
                  totalChars={agent.total_chars}
                  open={!!openParts[index]}
                  onToggle={() => setOpenParts((prev) => ({ ...prev, [index]: !prev[index] }))}
                />
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}

export default function Analysis() {
  const query = useQuery(QK.analysis, () => api.analysisPrompts(), { interval: POLL.analysis });
  const data = query.data;
  const agents = data?.agents || [];
  const unavailable = !query.loading && (!data || data.available === false || data.ok === false);
  const reason =
    data?.error || (query.error && query.error !== 'no-data' ? query.error : '') || '分析器未注入或接口暂不可用。';

  return (
    <div className="page analysis-page">
      <section className="card">
        <div className="card-head">
          <h3>提示词分析</h3>
          <div className="spacer" />
          {formatGeneratedAt(data?.generated_at) && (
            <span className="muted small">生成于 {formatGeneratedAt(data?.generated_at)}</span>
          )}
          <button className="btn" disabled={query.loading} onClick={() => void query.refetch()}>
            <Icon name="refresh" />{query.loading ? '读取中…' : '刷新'}
          </button>
        </div>
        <p className="muted small analysis-rule">{data?.rule || '—'}</p>
      </section>

      {query.loading && !data && <div className="empty muted">正在读取提示词分析…</div>}

      {unavailable && (
        <div className="workspace-empty">
          <Icon name="code" />
          <h3>提示词分析不可用</h3>
          <p>{reason}</p>
        </div>
      )}

      {!unavailable &&
        (agents.length === 0 ? (
          !query.loading && <div className="empty muted">没有可分析的 Agent</div>
        ) : (
          agents.map((agent, index) => <AgentCard key={agent.name + ':' + index} agent={agent} />)
        ))}
    </div>
  );
}
