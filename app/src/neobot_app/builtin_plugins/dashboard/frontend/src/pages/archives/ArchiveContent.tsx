import type { ArchiveItemDetail, ArchiveSnapshot, ArchiveSummarizeTask } from '../../api/types';
import Icon from '../../components/Icon';
import Button from '../../components/ui/Button';
import InlineAlert from '../../components/ui/InlineAlert';
import { PanelSkeleton } from '../../components/ui/PageSkeleton';
import { DELETE_SWITCH, formatTime, tagText } from './archiveUtils';

interface ArchiveContentProps {
  item: ArchiveItemDetail;
  canManage: boolean;
  deleteEnabled: boolean;
  editing: boolean;
  saving: boolean;
  draft: string;
  tagsDraft: string;
  conflict: ArchiveItemDetail | null;
  task: ArchiveSummarizeTask | null;
  itemRunning: boolean;
  summarizeAvailable: boolean;
  starting: boolean;
  targetChars: string;
  minTarget: number;
  maxTarget: number;
  snapshots: ArchiveSnapshot[];
  snapshotsLoading: boolean;
  onStartEdit: () => void;
  onCancelEdit: () => void;
  onReloadConflict: () => void;
  onDraftChange: (value: string) => void;
  onTagsChange: (value: string) => void;
  onSave: () => void;
  onDelete: () => void;
  onTargetChange: (value: string) => void;
  onSummarize: () => void;
  onViewSnapshot: (snapshot: ArchiveSnapshot) => void;
}

export function ArchiveContent({
  item,
  canManage,
  deleteEnabled,
  editing,
  saving,
  draft,
  tagsDraft,
  conflict,
  task,
  itemRunning,
  summarizeAvailable,
  starting,
  targetChars,
  minTarget,
  maxTarget,
  snapshots,
  snapshotsLoading,
  onStartEdit,
  onCancelEdit,
  onReloadConflict,
  onDraftChange,
  onTagsChange,
  onSave,
  onDelete,
  onTargetChange,
  onSummarize,
  onViewSnapshot,
}: ArchiveContentProps) {
  return (
    <>
      <details className="archive-item-info">
        <summary className="archive-item-heading" aria-label="档案信息">
          <h3>
            <code title={item.key}>{item.key}</code>
          </h3>
          <span className="archive-item-version">version {item.version ?? 0}</span>
          {item.internal && <span className="tag warn">内部表</span>}
          <span className="archive-info-toggle">
            档案信息
            <Icon name="chevron" size={14} />
          </span>
        </summary>
        <dl className="archive-item-metadata">
          <div className="archive-meta-wide">
            <dt>条目 key</dt>
            <dd>
              <code>{item.key}</code>
            </dd>
          </div>
          <div className="archive-meta-wide">
            <dt>档案表</dt>
            <dd>
              <code>{item.table_name}</code>
            </dd>
          </div>
          <div>
            <dt>创建时间</dt>
            <dd>{formatTime(item.created_at)}</dd>
          </div>
          <div>
            <dt>更新时间</dt>
            <dd>{formatTime(item.updated_at)}</dd>
          </div>
          <div className="archive-meta-wide">
            <dt>标签</dt>
            <dd>{tagText(item.tags)}</dd>
          </div>
        </dl>
        {(item.note || !deleteEnabled) && (
          <div className="archive-protection-note">
            <strong>删除保护</strong>
            {item.note && <p>{item.note}</p>}
            {!deleteEnabled && (
              <p>
                删除已禁用：dashboard 插件配置 <code>{DELETE_SWITCH}</code> = false
              </p>
            )}
          </div>
        )}
      </details>

      <div className="archive-detail-toolbar">
        <div className="archive-edit-tools" role="group" aria-label="档案编辑操作">
          <Button
            variant="primary"
            size="sm"
            type="button"
            disabled={editing || item.editable === false || !canManage || itemRunning}
            onClick={onStartEdit}
          >
            <Icon name="edit" />
            编辑
          </Button>
          <Button
            variant="danger"
            size="sm"
            type="button"
            disabled={editing || !deleteEnabled || !canManage || itemRunning}
            title={!deleteEnabled ? '删除未开启，原因可在档案信息中查看' : undefined}
            onClick={onDelete}
          >
            <Icon name="trash" />
            删除
          </Button>
        </div>
        <div className="archive-compress-tools" role="group" aria-label="AI 压缩操作">
          <label htmlFor="archive-target">
            目标<span className="sr-only">字符数</span>
          </label>
          <div className="archive-target-field">
            <input
              id="archive-target"
              className="input archives-target-input"
              type="number"
              min={minTarget}
              max={maxTarget}
              value={targetChars}
              disabled={itemRunning}
              onChange={(event) => onTargetChange(event.target.value)}
            />
            <span aria-hidden="true">字</span>
          </div>
          <Button
            size="sm"
            type="button"
            disabled={editing || itemRunning || !canManage || !summarizeAvailable || starting}
            onClick={() => void onSummarize()}
          >
            <Icon name="bot" />
            {itemRunning ? '压缩中…' : 'AI 压缩'}
          </Button>
        </div>
      </div>
      {itemRunning && <p className="archive-operation-note">该条目正在压缩，暂不可编辑或删除。</p>}
      {item.editable === false && (
        <p className="archive-operation-note">内部表禁止手工编辑，避免影响自动总结。</p>
      )}

      {conflict && (
        <InlineAlert
          tone="error"
          title="档案已被他人修改，保存未生效"
          actions={
            <Button variant="primary" size="sm" type="button" onClick={onReloadConflict}>
              重新加载（放弃我的修改）
            </Button>
          }
        >
          服务端当前 version={conflict.version ?? 0}
          {(item.version ?? 0) !== (conflict.version ?? 0) ? '（比你读取时更新）' : ''}
          ，已拒绝写入以避免覆盖。你的修改仍保留在下面的编辑框里，不会自动提交。
          <pre className="prompt-preview-body archives-conflict-body">{conflict.value || '（空）'}</pre>
        </InlineAlert>
      )}

      {task && task.kind !== 'batch' && task.table === item.table_name && task.key === item.key && (
        <InlineAlert
          tone={task.status === 'failed' ? 'error' : task.status === 'running' ? 'info' : 'success'}
          title={
            task.status === 'running'
              ? 'AI 压缩进行中…'
              : task.status === 'failed'
                ? '压缩失败，已保留原文'
                : '压缩完成'
          }
        >
          {task.status === 'running'
            ? (task.chars_before ?? 0) +
              ' 字 → 目标 ' +
              (task.target_chars ?? 0) +
              ' 字（后台任务，完成后自动刷新）'
            : task.status === 'failed'
              ? task.error || '模型未压到目标字数，原文未被修改'
              : (task.chars_before ?? 0) +
                ' → ' +
                (task.chars_after ?? 0) +
                ' 字（目标 ' +
                (task.target_chars ?? 0) +
                '，快照 id ' +
                (task.snapshot_id ?? '无') +
                '）'}
        </InlineAlert>
      )}

      {editing ? (
        <>
          <label className="cfg-label" htmlFor="archive-value">
            档案正文（原样保存，不截断）
          </label>
          <textarea
            id="archive-value"
            className="input prompt-textarea archives-textarea"
            value={draft}
            readOnly={saving || !canManage || itemRunning}
            onChange={(event) => onDraftChange(event.target.value)}
          />
          <label className="cfg-label" htmlFor="archive-tags">
            tags（逗号分隔）
          </label>
          <input
            id="archive-tags"
            className="input"
            value={tagsDraft}
            readOnly={saving || !canManage || itemRunning}
            onChange={(event) => onTagsChange(event.target.value)}
          />
          <div className="archives-actions archive-edit-actions">
            <Button
              variant="primary"
              size="sm"
              type="button"
              disabled={saving || !canManage || itemRunning}
              title={!canManage ? '当前会话只读，已保留你的草稿' : undefined}
              onClick={() => void onSave()}
            >
              <Icon name="save" />
              {saving ? '保存中…' : '保存（带 version ' + (item.version ?? 0) + '）'}
            </Button>
            <Button size="sm" type="button" disabled={saving} onClick={onCancelEdit}>
              取消
            </Button>
          </div>
        </>
      ) : (
        <>
          <div className="archives-value-head">
            <strong>全文</strong>
            <span className="muted small">{item.total_chars ?? 0} 字符</span>
          </div>
          <pre className="prompt-preview-body archives-full">{item.value || '（空）'}</pre>
        </>
      )}

      <div className="archives-history">
        <div className="archives-value-head">
          <strong>压缩历史</strong>
          <span className="muted small">保留最近 10 份只读快照。需要恢复时，查看全文并复制到编辑区。</span>
        </div>
        {snapshotsLoading && snapshots.length === 0 ? (
          <PanelSkeleton kind="list" rows={2} label="正在读取压缩历史" />
        ) : snapshots.length === 0 ? (
          <p className="muted small">还没有压缩快照</p>
        ) : (
          <table className="model-table archives-table">
            <thead>
              <tr>
                <th>时间</th>
                <th>压缩前</th>
                <th>压缩后</th>
                <th>来源</th>
                <th>操作者</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {snapshots.map((row) => (
                <tr key={row.id}>
                  <td className="muted small">{formatTime(row.created_at)}</td>
                  <td>{row.chars_before ?? row.total_chars ?? 0}</td>
                  <td>{row.chars_after ?? '—'}</td>
                  <td>{row.reason === 'auto' ? '自动压缩' : '手动压缩'}</td>
                  <td className="muted small">{row.operator_ip || '—'}</td>
                  <td>
                    <Button size="sm" type="button" onClick={() => void onViewSnapshot(row)}>
                      <Icon name="eye" />
                      查看全文
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
