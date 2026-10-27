import type { Ref } from 'react';
import { UserRound, UsersRound } from 'lucide-react';
import type { ChatFlowItem } from '../../api/types';
import { formatAge } from './chatFlowUtils';

interface ChatFlowListProps {
  flows: ChatFlowItem[];
  selected: string;
  flowListRef: Ref<HTMLUListElement>;
  onSelect: (key: string) => void;
}

export function ChatFlowList({ flows, selected, flowListRef, onSelect }: ChatFlowListProps) {
  return (
    <section className="card viewer-list chat-flow-list" aria-label="聊天流列表">
      <div className="viewer-panel-heading">
        <h2>会话</h2>
        <span className="muted small">{flows.length} 个聊天流</span>
      </div>
      <ul ref={flowListRef} className="viewer-list-scroll" tabIndex={-1} aria-label="聊天流记录">
        {flows.map((flow) => {
          const active = flow.pipeline_key === selected;
          return (
            <li key={flow.pipeline_key}>
              <button
                type="button"
                className={'record-list-item chat-flow-item' + (active ? ' active' : '')}
                aria-current={active}
                aria-label={[
                  flow.display_name || flow.pipeline_key,
                  flow.active ? '运行中' : '',
                  flow.pipeline_key,
                  formatAge(flow.age_seconds),
                ]
                  .filter(Boolean)
                  .join(' ')}
                onClick={() => onSelect(flow.pipeline_key)}
              >
                <span className="record-list-icon" aria-hidden="true">
                  {flow.pipeline_key.startsWith('group:') ? (
                    <UsersRound size={17} />
                  ) : (
                    <UserRound size={17} />
                  )}
                </span>
                <span className="record-list-copy">
                  <span className="record-list-title">
                    <strong title={flow.display_name || flow.pipeline_key}>
                      {flow.display_name || flow.pipeline_key}
                    </strong>
                  </span>
                  <code className="chat-flow-item-key" title={flow.pipeline_key}>
                    {flow.pipeline_key}
                  </code>
                  <span className="record-list-subtitle chat-flow-item-footer">
                    {flow.active ? (
                      <span className="record-running">
                        <i />
                        运行中
                      </span>
                    ) : (
                      <span>最近活动</span>
                    )}
                    <time>{formatAge(flow.age_seconds)}</time>
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
