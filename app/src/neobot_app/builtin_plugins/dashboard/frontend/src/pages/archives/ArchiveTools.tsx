import type { ArchiveSummarizeTask } from '../../api/types';
import Icon from '../../components/Icon';
import Button from '../../components/ui/Button';
import InlineAlert from '../../components/ui/InlineAlert';
import { BATCH_STATUS_TEXT, DELETE_SWITCH } from './archiveUtils';

interface ArchiveToolsProps {
  task: ArchiveSummarizeTask | null;
  taskRunning: boolean;
  maxTotalChars: number;
  deleteEnabled: boolean;
  canManage: boolean;
  summarizeAvailable: boolean;
  minTarget: number;
  maxTarget: number;
  targetChars: string;
  starting: boolean;
  onTargetChange: (value: string) => void;
  onStartBatch: () => void;
}

export function ArchiveTools({
  task,
  taskRunning,
  maxTotalChars,
  deleteEnabled,
  canManage,
  summarizeAvailable,
  minTarget,
  maxTarget,
  targetChars,
  starting,
  onTargetChange,
  onStartBatch,
}: ArchiveToolsProps) {
  return (
    <details className="viewer-disclosure archives-overview">
      <summary>
        <Icon name="archive" size={16} />
        <span>档案工具</span>
        <span className="viewer-disclosure-hint">档案包含隐私数据</span>
        {taskRunning && task?.kind === 'batch' && <span className="tag info">压缩中</span>}
      </summary>
      <div className="viewer-disclosure-body">
        <div className="archives-status">
          {maxTotalChars > 0 && <span className="tag debug">单条上限 {maxTotalChars} 字符</span>}
          <span className={'tag ' + (deleteEnabled ? 'warn' : 'debug')}>
            删除开关 {deleteEnabled ? '已开启' : '已关闭'}
          </span>
        </div>
        <InlineAlert tone="warning" title="档案包含隐私数据">
          这里的用户 / 群档案与记忆摘要都是高敏感内容，面板默认监听
          0.0.0.0；请勿随意截图外发，生产环境建议只监听 127.0.0.1 或置于带鉴权的反向代理之后。
          列表会自动更新；编辑中的正文与版本保持不变。
        </InlineAlert>
        {!canManage && (
          <InlineAlert tone="info" title="当前会话没有管理权限">
            面板管理功能已关闭或远程管理被禁用，只能查看档案（编辑 / 删除按钮已禁用）。
          </InlineAlert>
        )}
        {!deleteEnabled && (
          <InlineAlert tone="warning" title={'面板档案删除未开启（' + DELETE_SWITCH + '）'}>
            请在 dashboard 插件配置里把 <code>{DELETE_SWITCH}</code> 设为 true 才能删除档案；该开关与模型侧的
            <code>agent.memory.archive.allow_delete</code> 完全独立。
          </InlineAlert>
        )}
        {canManage && summarizeAvailable && (
          <section className="archives-compression" aria-label="批量压缩工具">
            <div className="card-head">
              <label className="cfg-label" htmlFor="archive-batch-target">
                批量目标字符数
              </label>
              <input
                id="archive-batch-target"
                className="input archives-target-input"
                type="number"
                min={minTarget}
                max={maxTarget}
                value={targetChars}
                onChange={(event) => onTargetChange(event.target.value)}
              />
              <Button type="button" disabled={starting || taskRunning} onClick={() => void onStartBatch()}>
                <Icon name="archive" />
                批量压缩超限档案
              </Button>
            </div>
            <p className="muted small">
              逐条串行压缩当前超限档案，一次最多 20 条，统一使用上面的目标字符数（{minTarget}–{maxTarget}
              ）。 目标只对本次压缩生效，<b>不会改写</b>全局配置 agent.memory.archive.max_total_chars。
            </p>
            {task && task.kind === 'batch' && (
              <div className="archives-batch">
                <InlineAlert
                  tone={task.status === 'failed' ? 'error' : task.status === 'running' ? 'info' : 'success'}
                  title={task.message || '批量压缩进行中…'}
                >
                  成功 {task.succeeded ?? 0} 条 / 失败 {task.failed ?? 0} 条 / 跳过{' '}
                  {(task.skipped || []).length} 条
                  {task.truncated ? '；本次还有 ' + task.truncated + ' 条超出上限未处理' : ''}
                </InlineAlert>
                {(task.items || []).length > 0 && (
                  <table className="model-table archives-table">
                    <thead>
                      <tr>
                        <th>档案</th>
                        <th>状态</th>
                        <th>字数</th>
                        <th>说明</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(task.items || []).map((entry) => (
                        <tr key={entry.table + ':' + entry.key}>
                          <td>
                            <code>
                              {entry.table}:{entry.key}
                            </code>
                          </td>
                          <td>{BATCH_STATUS_TEXT[entry.status || 'pending']}</td>
                          <td>
                            {entry.chars_before ?? 0} → {entry.chars_after ?? '…'}
                          </td>
                          <td className="muted small">{entry.error || ''}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {(task.skipped || []).length > 0 && (
                  <p className="muted small">
                    跳过明细：
                    {(task.skipped || []).map((row) => row.table + ':' + row.key).join('、')}
                  </p>
                )}
              </div>
            )}
          </section>
        )}
      </div>
    </details>
  );
}
