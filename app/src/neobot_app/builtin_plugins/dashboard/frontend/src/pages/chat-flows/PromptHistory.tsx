import { useId, useState, type Ref } from 'react';
import { Info } from 'lucide-react';
import type { ChatFlowLatestPrompt, ChatFlowPromptEntry, ChatFlowPromptMeta } from '../../api/types';
import Icon from '../../components/Icon';
import Button from '../../components/ui/Button';
import EmptyState from '../../components/ui/EmptyState';
import InlineAlert from '../../components/ui/InlineAlert';
import { PanelSkeleton } from '../../components/ui/PageSkeleton';
import { PromptEntryView } from './PromptEntryView';
import { formatBytes, formatTime } from './chatFlowUtils';

interface PromptHistoryProps {
  historyRef: Ref<HTMLDivElement>;
  promptItems: ChatFlowPromptMeta[];
  limit: number;
  onlyCurrent: boolean;
  showingLatest: boolean;
  latestSeq: number | null;
  loading: boolean;
  activeSeq: number | null;
  onOnlyCurrentChange: (checked: boolean) => void;
  onFollowLatest: () => void;
  onPick: (seq: number) => void;
}

export function PromptHistory({
  historyRef,
  promptItems,
  limit,
  onlyCurrent,
  showingLatest,
  latestSeq,
  loading,
  activeSeq,
  onOnlyCurrentChange,
  onFollowLatest,
  onPick,
}: PromptHistoryProps) {
  const [detailsSeq, setDetailsSeq] = useState<number | null>(null);
  const detailsPrefix = useId();
  const followLabel = latestSeq === null ? '暂无记录' : `已跟随最新一份（#${latestSeq}）`;
  return (
    <div ref={historyRef} className="chat-prompt-history" tabIndex={-1} aria-label="提示词历史">
      <div className="chat-prompt-history-head">
        <strong>提示词历史</strong>
        <span className="muted small">
          {promptItems.length} / {limit > 0 ? limit : '—'} 份
        </span>
      </div>
      <div className="chat-history-controls">
        <label className="chat-history-filter" title="只看当前聊天流">
          <input
            type="checkbox"
            aria-label="只看当前聊天流"
            checked={onlyCurrent}
            onChange={(event) => onOnlyCurrentChange(event.target.checked)}
          />
          当前会话
        </label>
        {showingLatest || latestSeq === null ? (
          <span className="chat-follow-state" role="status" aria-label={followLabel} title={followLabel}>
            {latestSeq !== null && <i aria-hidden="true" />}
            {latestSeq === null ? '暂无记录' : '跟随最新'}
          </span>
        ) : (
          <Button
            size="sm"
            variant="ghost"
            type="button"
            className="chat-follow-button"
            aria-label={`回到最新一份（#${latestSeq}）`}
            title={`回到最新一份（#${latestSeq}）`}
            onClick={() => onFollowLatest()}
          >
            <Icon name="refresh" size={13} />
            跟随最新
          </Button>
        )}
      </div>
      {loading && promptItems.length === 0 ? (
        <PanelSkeleton kind="list" rows={4} label="正在读取提示词历史" />
      ) : promptItems.length === 0 ? (
        <EmptyState compact>还没有记录完整提示词</EmptyState>
      ) : (
        <ul className="chat-history-list" aria-label="提示词历史记录">
          {promptItems.map((meta, index) => {
            const active = meta.seq === activeSeq;
            const latest = meta.seq === latestSeq;
            const recordedAt = formatTime(meta.recorded_at);
            const day = recordedAt === '—' ? '未记录日期' : recordedAt.slice(0, 10);
            const previous = promptItems[index - 1];
            const showDay =
              !previous || formatTime(previous.recorded_at).slice(0, 10) !== recordedAt.slice(0, 10);
            const expanded = detailsSeq === meta.seq;
            const detailsId = `${detailsPrefix}-${meta.seq}`;
            const metadata = [
              ['记录时间', recordedAt],
              ['聊天流', meta.pipeline_key || '—'],
              ['模型', meta.model || '未知模型'],
              ['完整篇幅', formatBytes(meta.bytes)],
              ['驻留补丁', meta.patch_bytes === undefined ? '—' : formatBytes(meta.patch_bytes)],
              ['图片引用', `${meta.images ?? 0} 个`],
            ];
            return (
              <li key={meta.seq}>
                {showDay && (
                  <div className="chat-history-day">
                    <time dateTime={meta.recorded_at ? day : undefined}>{day}</time>
                  </div>
                )}
                <div className={'chat-history-row' + (active ? ' is-active' : '')}>
                  <button
                    type="button"
                    className="chat-history-key"
                    aria-current={active}
                    aria-label={`#${meta.seq} ${recordedAt.slice(11) || '—'}${active ? ' 当前记录' : ''}${latest ? ' 最新记录' : ''} ${meta.total_messages ?? 0} 条消息 迭代 ${meta.iteration ?? 0}`}
                    title={metadata.map(([name, value]) => `${name}：${value}`).join('\n')}
                    onClick={() => onPick(meta.seq)}
                  >
                    <span className="chat-history-heading">
                      <code title={`#${meta.seq}`}>#{meta.seq}</code>
                      <time className="chat-history-time" dateTime={meta.recorded_at || undefined}>
                        {recordedAt.slice(11) || '—'}
                      </time>
                      {(active || latest) && (
                        <span
                          className="chat-history-marker"
                          title={active && latest ? '当前阅读的最新记录' : undefined}
                        >
                          {latest ? '最新' : '当前'}
                        </span>
                      )}
                    </span>
                    <span className="chat-history-stats">
                      <span>{meta.total_messages ?? 0} 条消息</span>
                      <span>迭代 {meta.iteration ?? 0}</span>
                    </span>
                    {!onlyCurrent && (
                      <code className="chat-history-pipeline" title={meta.pipeline_key || '—'}>
                        {meta.pipeline_key || '—'}
                      </code>
                    )}
                  </button>
                  <button
                    type="button"
                    className="chat-history-inspect"
                    aria-label={`查看记录 ${meta.seq} 的详情`}
                    aria-expanded={expanded}
                    aria-controls={expanded ? detailsId : undefined}
                    title="记录详情"
                    onClick={() => setDetailsSeq(expanded ? null : meta.seq)}
                  >
                    <Info size={14} aria-hidden="true" />
                  </button>
                </div>
                {expanded && (
                  <dl id={detailsId} className="chat-history-details" aria-label={`记录 ${meta.seq} 的详情`}>
                    {metadata.map(([name, value]) => (
                      <div key={name}>
                        <dt>{name}</dt>
                        <dd>{value}</dd>
                      </div>
                    ))}
                  </dl>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

interface PromptReaderProps {
  promptEntryRef: Ref<HTMLDivElement>;
  promptData: ChatFlowLatestPrompt | null;
  loading: boolean;
  activeSeq: number | null;
  entryLoading: boolean;
  activeEntry: ChatFlowPromptEntry | null;
  onRetry: () => void;
}

export function PromptReader({
  promptEntryRef,
  promptData,
  loading,
  activeSeq,
  entryLoading,
  activeEntry,
  onRetry,
}: PromptReaderProps) {
  return (
    <div
      ref={promptEntryRef}
      className="chat-prompt-entry viewer-body"
      tabIndex={-1}
      aria-label="完整提示词正文"
    >
      {loading && promptData === null ? (
        <PanelSkeleton label="正在读取完整提示词" kind="text" rows={5} />
      ) : promptData === null ? (
        <InlineAlert tone="warning" title="完整提示词历史不可用">
          后端未注入 context_recorder，或提示词历史记录被关闭 （chat.chat_flow_prompt_history_enabled =
          false）。
        </InlineAlert>
      ) : activeSeq === null ? (
        <EmptyState compact>还没有完整提示词记录；Bot 下次调用模型后会在这里出现。</EmptyState>
      ) : entryLoading && !activeEntry ? (
        <PanelSkeleton label="正在读取完整提示词" kind="text" rows={5} />
      ) : !activeEntry ? (
        <InlineAlert
          tone="error"
          title={'读取完整提示词失败：seq=' + activeSeq}
          actions={
            <Button size="sm" type="button" onClick={onRetry}>
              重新读取
            </Button>
          }
        />
      ) : (
        <PromptEntryView seq={activeSeq} entry={activeEntry} />
      )}
    </div>
  );
}
