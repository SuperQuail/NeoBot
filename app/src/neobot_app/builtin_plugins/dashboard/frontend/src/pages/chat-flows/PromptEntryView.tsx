import { memo, useMemo, useState } from 'react';
import type { ChatFlowPromptEntry } from '../../api/types';
import Modal from '../../components/Modal';
import Icon from '../../components/Icon';
import Button from '../../components/ui/Button';
import { formatTime, roleLabel } from './chatFlowUtils';

type RawMessage = Record<string, unknown>;

/** 完整提示词里的消息：content 原样渲染，另附原始 JSON（tool_calls 参数不丢；图片只留哈希） */
function FullMessageRow({ message, index }: { message: RawMessage; index: number }) {
  const role = typeof message.role === 'string' ? message.role : '';
  const content = message.content;
  const isText = typeof content === 'string';
  const text = isText ? content : JSON.stringify(content ?? '', null, 2);
  return (
    <li className={'flow-message role-' + (role || 'unknown')}>
      <div className="flow-message-head">
        <span className={'tag ' + (role === 'assistant' ? 'ok' : 'info')}>{roleLabel(role)}</span>
        <span className="chat-message-index">#{index}</span>
        <span className="muted small chat-message-stats">{text.length} 字符</span>
      </div>
      {isText ? (
        <pre className="flow-message-body">{text}</pre>
      ) : (
        <pre className="flow-message-body chat-raw-body">{text}</pre>
      )}
      <details className="chat-raw">
        <summary className="muted small" title="含 tool_calls 参数；图片部件只保留 sha256 哈希">
          原始 JSON
        </summary>
        <pre className="flow-message-body chat-raw-body">{JSON.stringify(message, null, 2)}</pre>
      </details>
    </li>
  );
}

/**
 * 一份完整提示词（= 一次模型请求的完整 messages + response + usage），全部原样展示。
 *
 * memo：提示词历史按轮询刷新，只要 seq 与内容没变就复用上一次的渲染结果——
 * 一份提示词动辄上百条消息（每条还要 `JSON.stringify` 原始 JSON），无谓重渲染很贵。
 */
export const PromptEntryView = memo(function PromptEntryView({
  seq,
  entry,
}: {
  seq: number;
  entry: ChatFlowPromptEntry;
}) {
  const [infoOpen, setInfoOpen] = useState(false);
  const messages = useMemo(() => (Array.isArray(entry.messages) ? entry.messages : []), [entry.messages]);
  const extra = useMemo(
    () => ({
      stage: entry.stage ?? '',
      mode: entry.mode ?? '',
      event_id: entry.event_id ?? '',
      conversation_kind: entry.conversation_kind ?? '',
      conversation_id: entry.conversation_id ?? '',
      output_estimated_tokens: entry.output_estimated_tokens ?? null,
      cache_hit_tokens: entry.cache_hit_tokens ?? null,
      cache_miss_tokens: entry.cache_miss_tokens ?? null,
      cache_hit_rate: entry.cache_hit_rate ?? null,
      usage: entry.usage ?? null,
    }),
    [entry],
  );
  return (
    <div className="chat-entry">
      <div className="chat-entry-meta">
        <strong>#{seq}</strong>
        <span>{formatTime(entry.recorded_at)}</span>
        <span>{entry.messages_count ?? messages.length} 条消息</span>
        <span className="chat-complete-label">完整未截断</span>
        <Button size="sm" variant="ghost" onClick={() => setInfoOpen(true)}>
          调用信息
          <Icon name="chevron" size={13} />
        </Button>
      </div>

      <ul className="flow-messages" aria-label="完整请求消息">
        {messages.map((message, index) => (
          <FullMessageRow key={index} message={message} index={index + 1} />
        ))}
      </ul>

      <details className="chat-collapse">
        <summary>response（模型原始返回）</summary>
        <pre className="prompt-preview-body">{JSON.stringify(entry.response ?? null, null, 2)}</pre>
      </details>
      <Modal open={infoOpen} title="调用信息" onClose={() => setInfoOpen(false)}>
        <dl className="chat-info-list">
          {(
            [
              ['记录', '#' + seq],
              ['时间', formatTime(entry.recorded_at)],
              ['模型', entry.model || '未知模型'],
              ['迭代', String(entry.iteration ?? 0)],
              ['消息数', String(entry.messages_count ?? messages.length)],
              ['总字符数', String(entry.total_chars ?? 0)],
              ['估算 Token', String(entry.estimated_tokens ?? 0)],
              ['输出字符数', String(entry.output_chars ?? 0)],
              ['pipeline_key', entry.pipeline_key || '—'],
            ] as const
          ).map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      </Modal>

      <details className="chat-collapse">
        <summary>usage 与其它元数据</summary>
        <pre className="prompt-preview-body">{JSON.stringify(extra, null, 2)}</pre>
      </details>
    </div>
  );
});
