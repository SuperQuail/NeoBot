// pages/ChatFlows.tsx —— 聊天流：内存快速预览 + 落盘的完整提示词历史（features/spec(3)）
//
// 两个数据来源，职责不同：
// 1) /api/chat-flows(+detail)：回复管线写入 ChatFlowRegistry 的**内存快照**（有界、只保留
//    最近 80 条消息、单条 4000 字符），默认视图之外不读盘 —— 保留原有「快速预览」能力；
// 2) /api/chat-flows/prompts(+prompt)：每次模型调用**完整落盘**一份的完整提示词
//    （<DATA_DIR>/chat_flows/prompts/，全局保留最近 N 份）。列表只给元数据，
//    正文按需读取、**完整渲染不做任何截断**，切换历史时才请求全量接口。
//
// 名称：列表与详情标题都用后端解析好的 display_name（群名 / 昵称），
// pipeline_key 作为副标题常驻，便于在日志 / 配置里定位。
import { useEffect, useMemo, useState } from 'react';
import Icon from '../components/Icon';
import Modal from '../components/Modal';
import InlineAlert from '../components/ui/InlineAlert';
import { toast } from '../components/Toast';
import { useQuery } from '../data/useQuery';
import { QK, POLL } from '../data/queryKeys';
import { api } from '../api/endpoints';
import type { ChatFlowMessage, ChatFlowPromptEntry, ChatFlowPromptMeta } from '../api/types';

type RawMessage = Record<string, unknown>;

function formatAge(seconds?: number | null): string {
  if (seconds === undefined || seconds === null) return '—';
  if (seconds < 60) return Math.max(0, Math.round(seconds)) + ' 秒前';
  if (seconds < 3600) return Math.round(seconds / 60) + ' 分钟前';
  return Math.round(seconds / 3600) + ' 小时前';
}

function formatTime(value?: string | null): string {
  if (!value) return '—';
  return value.replace('T', ' ').slice(0, 19);
}

function formatBytes(value?: number): string {
  const bytes = Number(value || 0);
  if (bytes >= 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
  if (bytes >= 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return bytes + ' B';
}

function roleLabel(role?: string): string {
  switch (role) {
    case 'system':
      return 'system';
    case 'user':
      return 'user';
    case 'assistant':
      return 'assistant';
    case 'tool':
      return 'tool';
    default:
      return role || '未知';
  }
}

/** 内存快照里的消息（可能已被裁剪 / 截断） */
function QuickMessageRow({ message, index }: { message: ChatFlowMessage; index: number }) {
  const calls = message.tool_calls || [];
  return (
    <li className={'flow-message role-' + (message.role || 'unknown')}>
      <div className="flow-message-head">
        <span className={'tag ' + (message.role === 'assistant' ? 'ok' : 'info')}>
          {roleLabel(message.role)}
        </span>
        <span className="muted small">
          #{index} · {message.chars ?? (message.content || '').length} 字符
          {message.truncated ? ' · 已截断' : ''}
          {message.images ? ' · ' + message.images + ' 张图片' : ''}
        </span>
      </div>
      {message.content && <pre className="flow-message-body">{message.content}</pre>}
      {calls.length > 0 && (
        <ul className="flow-tool-calls">
          {calls.map((call, callIndex) => (
            <li key={(call.id || '') + callIndex}>
              <code>{call.name || '未知工具'}</code>
              {call.arguments && <span className="muted small">{call.arguments}</span>}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

/** 完整提示词里的消息：content 原样渲染，另附原始 JSON（图片部件 / tool_calls 参数不丢） */
function FullMessageRow({ message, index }: { message: RawMessage; index: number }) {
  const role = typeof message.role === 'string' ? message.role : '';
  const content = message.content;
  const isText = typeof content === 'string';
  const text = isText ? content : JSON.stringify(content ?? '', null, 2);
  return (
    <li className={'flow-message role-' + (role || 'unknown')}>
      <div className="flow-message-head">
        <span className={'tag ' + (role === 'assistant' ? 'ok' : 'info')}>{roleLabel(role)}</span>
        <span className="muted small">
          #{index} · {text.length} 字符 · 完整未截断
        </span>
      </div>
      {isText ? (
        <pre className="flow-message-body">{text}</pre>
      ) : (
        <pre className="flow-message-body chat-raw-body">{text}</pre>
      )}
      <details className="chat-raw">
        <summary className="muted small">原始 JSON（含图片部件 / tool_calls 参数）</summary>
        <pre className="flow-message-body chat-raw-body">{JSON.stringify(message, null, 2)}</pre>
      </details>
    </li>
  );
}

/** 一份完整提示词（= 一次模型请求的完整 messages + response + usage），全部原样展示 */
function PromptEntryView({ seq, entry }: { seq: number; entry: ChatFlowPromptEntry }) {
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
        <span className="tag info">#{seq}</span>
        <span className="tag debug">{formatTime(entry.recorded_at)}</span>
        <span className="tag debug">{entry.model || '未知模型'}</span>
        <span className="tag debug">迭代 {entry.iteration ?? 0}</span>
        <span className="tag debug">{entry.messages_count ?? messages.length} 条消息</span>
        <span className="tag debug">{entry.total_chars ?? 0} 字符</span>
        <span className="tag debug">≈{entry.estimated_tokens ?? 0} tokens</span>
        <span className="tag debug">输出 {entry.output_chars ?? 0} 字符</span>
        {entry.pipeline_key && <span className="tag debug">{entry.pipeline_key}</span>}
      </div>

      <details className="chat-collapse" open>
        <summary>
          messages（{messages.length} 条，完整未截断）
        </summary>
        <ul className="flow-messages">
          {messages.map((message, index) => (
            <FullMessageRow key={index} message={message} index={index + 1} />
          ))}
        </ul>
      </details>

      <details className="chat-collapse">
        <summary>response（模型原始返回）</summary>
        <pre className="prompt-preview-body">{JSON.stringify(entry.response ?? null, null, 2)}</pre>
      </details>

      <details className="chat-collapse">
        <summary>usage 与其它元数据</summary>
        <pre className="prompt-preview-body">{JSON.stringify(extra, null, 2)}</pre>
      </details>
    </div>
  );
}

export default function ChatFlows() {
  const list = useQuery(QK.chatFlows, () => api.chatFlows(), { interval: POLL.chatFlows });
  const flows = useMemo(() => list.data?.items || [], [list.data]);
  const [selected, setSelected] = useState('');
  const [tab, setTab] = useState<'full' | 'quick'>('full');
  /** 历史列表是否只看当前聊天流 */
  const [onlyCurrent, setOnlyCurrent] = useState(true);
  /** 历史里被手动切换到的 seq；null = 跟随最新一份 */
  const [pickedSeq, setPickedSeq] = useState<number | null>(null);
  const [clearOpen, setClearOpen] = useState(false);
  const [clearChecked, setClearChecked] = useState(false);
  const [clearing, setClearing] = useState(false);

  useEffect(() => {
    if (selected || flows.length === 0) return;
    setSelected(flows[0].pipeline_key);
  }, [flows, selected]);

  // 选中的聊天流被淘汰后回落到第一条
  useEffect(() => {
    if (selected && flows.length > 0 && !flows.some((flow) => flow.pipeline_key === selected)) {
      setSelected(flows[0].pipeline_key);
    }
  }, [flows, selected]);

  const detail = useQuery(
    QK.chatFlowDetail(selected || 'none'),
    () => (selected ? api.chatFlowDetail(selected) : Promise.resolve(null)),
    { interval: POLL.chatFlows, deps: [selected] },
  );
  const snapshot = detail.data || null;
  const background = useMemo(() => {
    const tasks = snapshot?.background_tasks || {};
    return Object.entries(tasks).filter(([, value]) => value !== null && value !== undefined);
  }, [snapshot]);

  // 完整提示词历史：进页面 / 切换聊天流时取「元数据列表 + 最新一份全文」（不轮询）
  const promptKey = onlyCurrent ? selected : '';
  const prompts = useQuery(QK.chatFlowPrompts(promptKey), () => api.chatFlowPromptLatest(promptKey), {
    deps: [promptKey],
  });
  const promptData = prompts.data;
  const promptItems = useMemo(() => promptData?.items || [], [promptData]);
  const limit = promptData?.limit || 0;
  const latestSeq = promptData?.seq ?? null;
  // 手动选中的份仍存在就用它，否则回落到最新一份（切换聊天流后自然重置）
  const activeSeq =
    pickedSeq !== null && promptItems.some((item) => item.seq === pickedSeq) ? pickedSeq : latestSeq;
  const showingLatest = activeSeq !== null && activeSeq === latestSeq;

  // **切换历史时才请求全量接口**；最新那一份已由 chatFlowPromptLatest 读回，不再重复请求
  const entry = useQuery(
    QK.chatFlowPrompt(activeSeq ?? 0),
    () => (activeSeq === null || showingLatest ? Promise.resolve(null) : api.chatFlowPrompt(activeSeq)),
    { deps: [activeSeq, showingLatest] },
  );
  const activeEntry = showingLatest ? promptData?.entry ?? null : entry.data?.entry ?? null;
  const entryLoading = showingLatest ? prompts.loading : entry.loading;

  async function clearHistory() {
    setClearing(true);
    const result = await api.chatFlowPromptClear();
    setClearing(false);
    if (!result.ok) {
      toast(result.error || '清空提示词历史失败', 'err');
      return;
    }
    toast(result.data?.message || '已清空完整提示词历史', 'ok');
    setClearOpen(false);
    setClearChecked(false);
    setPickedSeq(null);
    await prompts.refetch();
  }

  return (
    <div className="page chat-flows-page">
      <section className="card">
        <div className="card-head">
          <h3>聊天流</h3>
          <div className="spacer" />
          <button className="btn" disabled={list.loading} onClick={() => void list.refetch()}>
            <Icon name="refresh" />
            {list.loading ? '读取中…' : '刷新'}
          </button>
          <button
            className="btn danger"
            type="button"
            onClick={() => {
              setClearChecked(false);
              setClearOpen(true);
            }}
          >
            <Icon name="trash" />
            清空提示词历史
          </button>
        </div>
        <p className="muted small">
          上方「快速预览」来自内存快照（重启后清空，只保留最近 80 条消息）；
          <strong>完整提示词会写入本地磁盘</strong> <code>{'<DATA_DIR>/chat_flows/prompts/'}</code>
          ，全局保留最近 {limit > 0 ? limit : '—'} 份。落盘的是完整聊天内容（含私聊与图片引用），
          <strong>属隐私数据</strong>，请谨慎分享。
        </p>
      </section>

      {list.data && list.data.ok === false && (
        <div className="workspace-empty">
          <Icon name="bot" />
          <h3>聊天流不可用</h3>
          <p>{list.data.error || '后端未注入 chat_flow_registry。'}</p>
        </div>
      )}

      {(!list.data || list.data.ok !== false) && flows.length === 0 && !list.loading && (
        <div className="empty muted">还没有聊天流记录。Bot 收到消息并构建提示词后这里就会出现。</div>
      )}

      {flows.length > 0 && (
        <div className="prompt-layout">
          <section className="card prompt-list" aria-label="聊天流列表">
            <ul>
              {flows.map((flow) => {
                const active = flow.pipeline_key === selected;
                return (
                  <li key={flow.pipeline_key}>
                    <button
                      type="button"
                      className={'prompt-key' + (active ? ' active' : '')}
                      aria-current={active}
                      onClick={() => setSelected(flow.pipeline_key)}
                    >
                      <span className="chat-flow-label">
                        <span className="chat-flow-name">
                          {flow.display_name || flow.pipeline_key}
                          {flow.active && <span className="tag ok">运行中</span>}
                        </span>
                        <span className="muted small chat-flow-key">
                          <code>{flow.pipeline_key}</code>
                        </span>
                      </span>
                      <span className="muted small">{formatAge(flow.age_seconds)}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>

          <section className="card prompt-editor" aria-label="聊天流详情">
            {!snapshot ? (
              <div className="empty muted">{detail.loading ? '读取中…' : '选择左侧的聊天流查看详情'}</div>
            ) : (
              <>
                <div className="card-head">
                  <h3>{snapshot.display_name || snapshot.pipeline_key}</h3>
                  <div className="spacer" />
                  <span className="tag info">{snapshot.model || '未知模型'}</span>
                  <span className="tag info">迭代 {snapshot.iterations ?? 0}</span>
                  <span className="tag info">{snapshot.message_count ?? 0} 条消息</span>
                </div>
                <p className="muted small chat-flow-subtitle">
                  <span className="tag debug">pipeline_key</span>
                  <code>{snapshot.pipeline_key}</code>
                  <span className="muted small">（用于在日志 / 配置里定位该聊天流）</span>
                </p>

                <div className="config-tabs chat-flow-tabs">
                  <div role="tablist" aria-label="聊天流视图">
                    <button
                      type="button"
                      role="tab"
                      aria-selected={tab === 'full'}
                      className={tab === 'full' ? 'active' : ''}
                      onClick={() => setTab('full')}
                    >
                      完整提示词
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={tab === 'quick'}
                      className={tab === 'quick' ? 'active' : ''}
                      onClick={() => setTab('quick')}
                    >
                      快速预览（内存）
                    </button>
                  </div>
                </div>

                {tab === 'quick' ? (
                  <>
                    <div className="prompt-preview">
                      <div className="prompt-preview-head">
                        <strong>最新 system 提示词</strong>
                        <span className="muted small">{snapshot.prompt_chars ?? 0} 字符</span>
                      </div>
                      <pre className="prompt-preview-body">{snapshot.system_prompt || '（空）'}</pre>
                    </div>

                    <div className="prompt-preview">
                      <div className="prompt-preview-head">
                        <strong>后台任务</strong>
                      </div>
                      {background.length === 0 ? (
                        <div className="empty muted">当前没有后台任务</div>
                      ) : (
                        <ul className="flow-tasks">
                          {background.map(([name, value]) => (
                            <li key={name}>
                              <code>{name}</code>
                              <span className="muted small">{JSON.stringify(value)}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>

                    <div className="prompt-preview">
                      <div className="prompt-preview-head">
                        <strong>最近一次模型请求（内存快照，不读盘）</strong>
                        <span className="muted small">
                          共 {snapshot.total_messages ?? 0} 条，快照只保留最近 {snapshot.message_count ?? 0} 条
                          （单条上限 4000 字符，可能有截断）
                        </span>
                      </div>
                      <ul className="flow-messages">
                        {(snapshot.messages || []).map((message, index) => (
                          <QuickMessageRow key={index} message={message} index={index + 1} />
                        ))}
                      </ul>
                      <p className="muted small">
                        需要完整、未截断的内容（188 条全在、图片部件与 tool_calls 参数原样）请切到「完整提示词」。
                      </p>
                    </div>
                  </>
                ) : (
                  <div className="chat-prompt-layout">
                    <div className="chat-prompt-history">
                      <div className="chat-prompt-history-head">
                        <strong>提示词历史</strong>
                        <span className="muted small">最近 {limit > 0 ? limit : '—'} 份</span>
                      </div>
                      <label className="inline-check muted small">
                        <input
                          type="checkbox"
                          checked={onlyCurrent}
                          onChange={(event) => setOnlyCurrent(event.target.checked)}
                        />
                        只看当前聊天流
                      </label>
                      <button
                        className="btn-sm"
                        type="button"
                        disabled={prompts.loading}
                        onClick={() => void prompts.refetch()}
                      >
                        <Icon name="refresh" />
                        {prompts.loading ? '读取中…' : '刷新'}
                      </button>
                      {promptItems.length === 0 ? (
                        <div className="empty muted">
                          {prompts.loading ? '读取中…' : '还没有落盘的完整提示词'}
                        </div>
                      ) : (
                        <ul className="chat-history-list">
                          {promptItems.map((meta: ChatFlowPromptMeta) => {
                            const active = meta.seq === activeSeq;
                            return (
                              <li key={meta.seq}>
                                <button
                                  type="button"
                                  className={'prompt-key chat-history-key' + (active ? ' active' : '')}
                                  aria-current={active}
                                  onClick={() => setPickedSeq(meta.seq)}
                                >
                                  <span className="chat-history-meta">
                                    <span>
                                      <code>#{meta.seq}</code> {formatTime(meta.recorded_at)}
                                    </span>
                                    <span className="muted small">
                                      {meta.pipeline_key || '—'} · 迭代 {meta.iteration ?? 0} ·{' '}
                                      {meta.total_messages ?? 0} 条 · {formatBytes(meta.bytes)}
                                    </span>
                                  </span>
                                </button>
                              </li>
                            );
                          })}
                        </ul>
                      )}
                    </div>

                    <div className="chat-prompt-entry">
                      {prompts.loading && promptData === null ? (
                        <div className="empty muted">读取中…</div>
                      ) : promptData === null ? (
                        <InlineAlert tone="warning" title="完整提示词历史不可用">
                          后端未注入 context_recorder，或聊天流提示词落盘被关闭
                          （chat.chat_flow_prompt_history_enabled = false）。
                        </InlineAlert>
                      ) : activeSeq === null ? (
                        <div className="empty muted">
                          还没有落盘的完整提示词；Bot 下次调用模型后会在这里出现。
                        </div>
                      ) : entryLoading && !activeEntry ? (
                        <div className="empty muted">读取中…</div>
                      ) : !activeEntry ? (
                        <InlineAlert
                          tone="error"
                          title={'读取完整提示词失败：seq=' + activeSeq}
                          actions={
                            <button className="btn-sm" type="button" onClick={() => void prompts.refetch()}>
                              重新读取
                            </button>
                          }
                        />
                      ) : (
                        <PromptEntryView seq={activeSeq} entry={activeEntry} />
                      )}
                    </div>
                  </div>
                )}
              </>
            )}
          </section>
        </div>
      )}

      <Modal open={clearOpen} title="清空完整提示词历史" onClose={() => setClearOpen(false)}>
        <InlineAlert tone="error" title="清空后不可恢复">
          将删除磁盘上 <code>{'<DATA_DIR>/chat_flows/prompts/'}</code> 里的全部完整提示词文件
          （当前列表 {promptItems.length} 份，全局上限 {limit > 0 ? limit : '—'} 份）。
          正在进行的对话不受影响，之后的新请求会重新开始记录。
        </InlineAlert>
        <label className="inline-check">
          <input
            type="checkbox"
            checked={clearChecked}
            onChange={(event) => setClearChecked(event.target.checked)}
          />
          我已确认：清空后这些完整聊天记录无法恢复
        </label>
        <div className="modal-actions">
          <button className="btn" type="button" disabled={clearing} onClick={() => setClearOpen(false)}>
            取消
          </button>
          <button
            className="btn danger"
            type="button"
            disabled={clearing || !clearChecked}
            onClick={() => void clearHistory()}
          >
            <Icon name="trash" />
            {clearing ? '清空中…' : '确认清空'}
          </button>
        </div>
      </Modal>
    </div>
  );
}
