// pages/ChatFlows.tsx —— 查看每条聊天流最近一次发给模型的内容与后台任务
// 数据来自回复管线写入的 ChatFlowRegistry 快照（纯内存、有界，不回放历史）。
import { useEffect, useMemo, useState } from 'react';
import Icon from '../components/Icon';
import { useQuery } from '../data/useQuery';
import { QK, POLL } from '../data/queryKeys';
import { api } from '../api/endpoints';
import type { ChatFlowMessage } from '../api/types';

function formatAge(seconds?: number | null): string {
  if (seconds === undefined || seconds === null) return '—';
  if (seconds < 60) return Math.max(0, Math.round(seconds)) + ' 秒前';
  if (seconds < 3600) return Math.round(seconds / 60) + ' 分钟前';
  return Math.round(seconds / 3600) + ' 小时前';
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

function MessageRow({ message, index }: { message: ChatFlowMessage; index: number }) {
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

export default function ChatFlows() {
  const list = useQuery(QK.chatFlows, () => api.chatFlows(), { interval: POLL.chatFlows });
  const flows = useMemo(() => list.data?.items || [], [list.data]);
  const [selected, setSelected] = useState('');

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

  return (
    <div className="page chat-flows-page">
      <section className="card">
        <div className="card-head">
          <h3>聊天流</h3>
          <div className="spacer" />
          <span className="muted small">最近一次发给模型的内容（内存快照，重启后清空）</span>
          <button className="btn" disabled={list.loading} onClick={() => void list.refetch()}>
            <Icon name="refresh" />
            {list.loading ? '读取中…' : '刷新'}
          </button>
        </div>
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
                      <span>
                        {flow.pipeline_key}
                        {flow.active && <span className="tag ok">运行中</span>}
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
                  <h3>{snapshot.pipeline_key}</h3>
                  <div className="spacer" />
                  <span className="tag info">{snapshot.model || '未知模型'}</span>
                  <span className="tag info">迭代 {snapshot.iterations ?? 0}</span>
                  <span className="tag info">{snapshot.message_count ?? 0} 条消息</span>
                </div>

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
                    <strong>最近一次模型请求</strong>
                    <span className="muted small">
                      共 {snapshot.total_messages ?? 0} 条，显示最近 {snapshot.message_count ?? 0} 条
                    </span>
                  </div>
                  <ul className="flow-messages">
                    {(snapshot.messages || []).map((message, index) => (
                      <MessageRow key={index} message={message} index={index + 1} />
                    ))}
                  </ul>
                </div>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
