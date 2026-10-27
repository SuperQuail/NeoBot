import type { ArchiveItemDetail, ArchiveSnapshot } from '../../api/types';
import Icon from '../../components/Icon';
import Button from '../../components/ui/Button';
import Modal, { ModalActions } from '../../components/Modal';
import InlineAlert from '../../components/ui/InlineAlert';
import { formatTime } from './archiveUtils';

interface ArchiveDeleteDialogProps {
  deleteOpen: boolean;
  item: ArchiveItemDetail | null;
  deleteError: string;
  deleteText: string;
  deleteChecked: boolean;
  deleting: boolean;
  canManage: boolean;
  deleteEnabled: boolean;
  itemRunning: boolean;
  onClose: () => void;
  onTextChange: (value: string) => void;
  onCheckedChange: (checked: boolean) => void;
  onConfirm: () => void;
}

export function ArchiveDeleteDialog({
  deleteOpen,
  item,
  deleteError,
  deleteText,
  deleteChecked,
  deleting,
  canManage,
  deleteEnabled,
  itemRunning,
  onClose,
  onTextChange,
  onCheckedChange,
  onConfirm,
}: ArchiveDeleteDialogProps) {
  return (
    <Modal open={deleteOpen} title="删除档案（不可恢复）" onClose={() => onClose()}>
      {item && (
        <div className="archives-delete">
          <InlineAlert tone="error" title="硬删除，没有回收站">
            被删内容不可恢复；后端只会把前 500 字符写进 neobot.log 的审计日志。
          </InlineAlert>
          <p className="muted small">
            表 <code>{item.table_name}</code> · key <code>{item.key}</code> · version {item.version ?? 0} ·{' '}
            {item.total_chars ?? 0} 字符
          </p>
          {item.note && (
            <InlineAlert tone="warning" title="这张表的删除后果">
              {item.note}
            </InlineAlert>
          )}
          <div className="archives-value-head">
            <strong>以下内容将被永久删除</strong>
          </div>
          <pre className="prompt-preview-body archives-delete-body">{item.value || '（空）'}</pre>
          {deleteError && <InlineAlert tone="error" title={deleteError} />}
          <label className="cfg-label" htmlFor="archive-delete-key">
            二次确认（二者任一）：输入完整 key，或勾选确认
          </label>
          <input
            id="archive-delete-key"
            className="input"
            value={deleteText}
            placeholder={'输入 key：' + item.key}
            data-autofocus
            onChange={(event) => onTextChange(event.target.value)}
          />
          <label className="inline-check">
            <input
              type="checkbox"
              checked={deleteChecked}
              onChange={(event) => onCheckedChange(event.target.checked)}
            />
            我已确认：删除后无法恢复
          </label>
          <ModalActions>
            <Button type="button" disabled={deleting} onClick={() => onClose()}>
              取消
            </Button>
            <Button
              variant="danger"
              type="button"
              disabled={
                deleting ||
                !canManage ||
                !deleteEnabled ||
                itemRunning ||
                !(deleteChecked || deleteText.trim() === item.key)
              }
              onClick={() => void onConfirm()}
            >
              <Icon name="trash" />
              {deleting ? '删除中…' : '确认删除'}
            </Button>
          </ModalActions>
        </div>
      )}
    </Modal>
  );
}

interface ArchiveSnapshotDialogProps {
  snapshotOpen: boolean;
  snapshotDetail: (ArchiveSnapshot & { value?: string }) | null;
  snapshotError: string;
  onClose: () => void;
}

export function ArchiveSnapshotDialog({
  snapshotOpen,
  snapshotDetail,
  snapshotError,
  onClose,
}: ArchiveSnapshotDialogProps) {
  return (
    <Modal open={snapshotOpen} title={'压缩快照 #' + (snapshotDetail?.id ?? '')} onClose={() => onClose()}>
      <div className="archives-snapshot">
        <InlineAlert tone="info" title="只读快照（压缩前原文）">
          面板不提供「恢复到此快照」；确需恢复时请复制下面的内容，走编辑接口人工写回。
        </InlineAlert>
        {snapshotDetail && (
          <p className="muted small">
            {snapshotDetail.table_name}:{snapshotDetail.key} · {formatTime(snapshotDetail.created_at)} ·
            {snapshotDetail.total_chars ?? 0} 字符 ·
            {snapshotDetail.reason === 'auto' ? '自动压缩' : '手动压缩'} ·
            {snapshotDetail.operator_ip || '系统'}
          </p>
        )}
        {snapshotError && <InlineAlert tone="error" title={snapshotError} />}
        <pre className="prompt-preview-body archives-full">
          {snapshotDetail?.value || (snapshotError ? '（无法读取）' : '读取中…')}
        </pre>
      </div>
    </Modal>
  );
}
