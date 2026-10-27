import type { ChatFlowDetailPayload } from '../../api/types';
import Icon from '../../components/Icon';
import Button from '../../components/ui/Button';
import Modal, { ModalActions } from '../../components/Modal';
import TaskStatusList from '../../components/TaskStatusList';
import EmptyState from '../../components/ui/EmptyState';
import InlineAlert from '../../components/ui/InlineAlert';
import { formatBytes } from './chatFlowUtils';

export type ChatContextPanel = 'system' | 'tasks' | 'info' | null;

interface ChatFlowHelpDialogProps {
  helpOpen: boolean;
  limit: number;
  promptCount: number;
  storageBytes: number;
  imageRefs: number;
  onClose: () => void;
}

export function ChatFlowHelpDialog({
  helpOpen,
  limit,
  promptCount,
  storageBytes,
  imageRefs,
  onClose,
}: ChatFlowHelpDialogProps) {
  return (
    <Modal open={helpOpen} title="隐私与记录说明" onClose={() => onClose()}>
      <div className="chat-help-content">
        <section>
          <h4>聊天内容包含隐私数据，请谨慎分享</h4>
          <p>
            记录的是完整聊天内容（含私聊），<strong>属隐私数据</strong>。只向可信任的人分享记录与截图。
          </p>
        </section>
        <section>
          <h4>快速预览</h4>
          <p>
            来自内存快照，不读盘，重启后清空。只保留最近 80 条消息，单条上限 4000 字符，可能有截断。system
            指令与后台任务可在正文上方按需查看。
          </p>
        </section>
        <section>
          <h4>完整提示词</h4>
          <p>
            每 5
            秒自动跟随最新一份。一轮对话结束（回复发出或取消）后，这里显示该轮最后一次模型调用的完整提示词。
            <strong>完整提示词也只存在内存里</strong>，重启即清空，全局保留最近 {limit > 0 ? limit : '—'}{' '}
            份，逐份只存相对上一份的 diff。图片只保留 sha256 哈希、不保留 base64，正文完整渲染，不再截断。
          </p>
          <p className="muted small">
            当前 {promptCount} 份 · 常驻 {formatBytes(storageBytes)} · 图片哈希 {imageRefs} 个
          </p>
        </section>
      </div>
    </Modal>
  );
}

interface ChatFlowContextDialogProps {
  contextPanel: ChatContextPanel;
  snapshot: ChatFlowDetailPayload | null;
  onClose: () => void;
}

export function ChatFlowContextDialog({ contextPanel, snapshot, onClose }: ChatFlowContextDialogProps) {
  const background = Object.entries(snapshot?.background_tasks || {}).filter(
    ([, value]) => value !== null && value !== undefined,
  );
  return (
    <Modal
      open={contextPanel !== null}
      title={
        contextPanel === 'system' ? '最新 system 提示词' : contextPanel === 'tasks' ? '后台任务' : '会话信息'
      }
      onClose={() => onClose()}
      size={contextPanel === 'system' ? 'wide' : 'default'}
    >
      {contextPanel === 'system' && (
        <>
          <p className="muted small">{snapshot?.prompt_chars ?? 0} 字符 · 当前聊天流的 system 指令</p>
          <pre className="chat-context-text">{snapshot?.system_prompt || '（空）'}</pre>
        </>
      )}
      {contextPanel === 'tasks' &&
        (background.length === 0 ? (
          <EmptyState compact>当前没有后台任务</EmptyState>
        ) : (
          <TaskStatusList snapshot={snapshot?.background_tasks || {}} />
        ))}
      {contextPanel === 'info' && snapshot && (
        <dl className="chat-info-list">
          {(
            [
              ['会话', snapshot.display_name || snapshot.pipeline_key],
              ['pipeline_key', snapshot.pipeline_key],
              ['模型', snapshot.model || '未知模型'],
              ['迭代', String(snapshot.iterations ?? 0)],
              ['快照消息', String(snapshot.message_count ?? 0)],
              ['请求消息总数', String(snapshot.total_messages ?? 0)],
              ['system 字符数', String(snapshot.prompt_chars ?? 0)],
            ] as const
          ).map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      )}
    </Modal>
  );
}

interface ClearPromptHistoryDialogProps {
  clearOpen: boolean;
  clearing: boolean;
  clearChecked: boolean;
  readOnly: boolean;
  promptCount: number;
  limit: number;
  onClose: () => void;
  onCheckedChange: (checked: boolean) => void;
  onConfirm: () => void;
}

export function ClearPromptHistoryDialog({
  clearOpen,
  clearing,
  clearChecked,
  readOnly,
  promptCount,
  limit,
  onClose,
  onCheckedChange,
  onConfirm,
}: ClearPromptHistoryDialogProps) {
  return (
    <Modal
      open={clearOpen}
      title="清空提示词历史"
      onClose={() => {
        if (!clearing) onClose();
      }}
    >
      <InlineAlert tone="error" title="清空后不可恢复">
        将丢弃内存里的全部提示词历史（当前 {promptCount} 份，全局上限
        {limit > 0 ? limit : '—'} 份），并顺带删除旧版本遗留的落盘文件
        <code>{'<DATA_DIR>/chat_flows/prompts/'}</code>。 正在进行的对话不受影响，之后的新请求会重新开始记录。
      </InlineAlert>
      <label className="inline-check">
        <input
          type="checkbox"
          checked={clearChecked}
          disabled={readOnly}
          onChange={(event) => onCheckedChange(event.target.checked)}
        />
        我已确认：清空后这些完整聊天记录无法恢复
      </label>
      <ModalActions>
        <Button type="button" disabled={clearing} onClick={() => onClose()}>
          取消
        </Button>
        <Button
          variant="danger"
          type="button"
          disabled={readOnly || clearing || !clearChecked}
          onClick={() => void onConfirm()}
        >
          <Icon name="trash" />
          {clearing ? '清空中…' : '确认清空'}
        </Button>
      </ModalActions>
    </Modal>
  );
}
