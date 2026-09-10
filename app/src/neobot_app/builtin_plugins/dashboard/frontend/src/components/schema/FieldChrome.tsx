// components/schema/FieldChrome.tsx —— 字段外框件：热重载徽标、字段级操作（历史 / 恢复默认）
import type { FieldDescriptor } from '../../api/types';
import type { FieldCallbacks } from './fieldTypes';
function HotBadge({ descriptor }: { descriptor: FieldDescriptor }) {
  if (descriptor.hot_reload === undefined) return null;
  if (descriptor.partial_hot_reload) {
    return <span className="hot-badge partial" title="该分组内部分配置项需要重启">部分热重载</span>;
  }
  return descriptor.hot_reload ? (
    <span className="hot-badge hot" title={descriptor.restart_reason || '修改后重载配置即可生效'}>热重载</span>
  ) : (
    <span className="hot-badge cold" title={descriptor.restart_reason || '修改后需要重启 NeoBot'}>需重启</span>
  );
}

function FieldActions({
  descriptor,
  disabled,
  changed,
  onRestore,
  onShowHistory,
  historyCount,
}: {
  descriptor: FieldDescriptor;
  disabled?: boolean;
  changed?: boolean;
  onRestore?: FieldCallbacks['onRestore'];
  onShowHistory?: FieldCallbacks['onShowHistory'];
  historyCount?: number;
}) {
  const hasDefault = descriptor.default !== undefined;
  const historyTotal = historyCount ?? 0;
  if (!hasDefault && !historyTotal) return null;
  return (
    <span className="cfg-field-actions">
      {historyTotal > 0 && (
        <button type="button" className="btn-sm" disabled={disabled} title="查看历史数值"
          onClick={() => onShowHistory?.(descriptor)}>历史 {historyTotal}</button>
      )}
      {hasDefault && (
        <button type="button" className="btn-sm" disabled={disabled || !changed}
          title="恢复该配置项的默认值"
          onClick={() => onRestore?.(descriptor.path, descriptor.default)}>恢复默认</button>
      )}
    </span>
  );
}
export { HotBadge, FieldActions };
