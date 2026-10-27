import type { ChatFlowDetailPayload, ChatFlowMessage } from '../../api/types';
import Button from '../../components/ui/Button';
import EmptyState from '../../components/ui/EmptyState';
import { roleLabel } from './chatFlowUtils';

/** 内存快照里的消息（可能已被裁剪 / 截断） */
function QuickMessageRow({ message, index }: { message: ChatFlowMessage; index: number }) {
  const calls = message.tool_calls || [];
  const content = (
    <>
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
    </>
  );
  return (
    <li className={'flow-message role-' + (message.role || 'unknown')}>
      <div className="flow-message-head">
        <span className={'tag ' + (message.role === 'assistant' ? 'ok' : 'info')}>
          {roleLabel(message.role)}
        </span>
        <span className="chat-message-index">#{index}</span>
        <span className="muted small chat-message-stats">
          {message.chars ?? (message.content || '').length} 字符
          {message.images ? ' · ' + message.images + ' 张图片' : ''}
        </span>
        {message.truncated && <span className="tag warn">已截断</span>}
      </div>
      {message.role === 'system' ? (
        <details className="chat-system-message">
          <summary>展开 system 指令</summary>
          {content}
        </details>
      ) : (
        content
      )}
    </li>
  );
}

interface QuickPreviewProps {
  snapshot: ChatFlowDetailPayload;
  onOpenContext: (panel: 'system' | 'tasks') => void;
}

export function QuickPreview({ snapshot, onOpenContext }: QuickPreviewProps) {
  return (
    <div className="viewer-body chat-quick-view" tabIndex={-1} aria-label="聊天流快速预览">
      <div className="chat-content-toolbar">
        <span
          className="chat-snapshot-caption"
          title={`共 ${snapshot.total_messages ?? 0} 条，快照只保留最近 ${snapshot.message_count ?? 0} 条；单条上限 4000 字符，可能有截断`}
        >
          最近请求 · {snapshot.message_count ?? 0} / {snapshot.total_messages ?? 0} 条
        </span>
        <div>
          <Button size="sm" variant="ghost" onClick={() => onOpenContext('system')}>
            system 提示词<small>{snapshot.prompt_chars ?? 0} 字符</small>
          </Button>
          <Button size="sm" variant="ghost" onClick={() => onOpenContext('tasks')}>
            后台任务
          </Button>
        </div>
      </div>
      <ul className="flow-messages" aria-label="内存快照消息">
        {(snapshot.messages || []).map((message, index) => (
          <QuickMessageRow key={index} message={message} index={index + 1} />
        ))}
      </ul>
      {(snapshot.messages || []).length === 0 && <EmptyState compact>这个聊天流暂时没有请求消息</EmptyState>}
      <p className="chat-snapshot-footnote">
        共 {snapshot.total_messages ?? 0} 条，快照只保留最近 {snapshot.message_count ?? 0} 条。单条上限 4000
        字符，可能有截断；完整消息与工具参数可在「完整提示词」查看。
      </p>
    </div>
  );
}
