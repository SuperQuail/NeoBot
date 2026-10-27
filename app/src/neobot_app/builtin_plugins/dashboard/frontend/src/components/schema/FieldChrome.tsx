// components/schema/FieldChrome.tsx —— 生效方式摘要、重启例外与字段级操作
import type { FieldDescriptor } from '../../api/types';
import type { FieldCallbacks } from './fieldTypes';
import { Highlight } from './Highlight';

/** 默认的重载方式只说明一次；字段上保留需要额外操作的例外。 */
function ReloadSummary({ fields }: { fields: FieldDescriptor[] }) {
  let hot = false;
  let cold = false;
  let unknown = false;
  const walk = (descriptors: FieldDescriptor[]) => {
    for (const field of descriptors) {
      // group 能力是子字段汇总；搜索收拢后以实际展示字段为准。
      if (field.kind === 'group' && field.fields?.length) {
        walk(field.fields);
        continue;
      }
      if (field.partial_hot_reload) {
        hot = true;
        cold = true;
      } else if (field.hot_reload === true) hot = true;
      else if (field.hot_reload === false) cold = true;
      else unknown = true;
      // 对象数组增删是整体改动，不能被子字段的可重载能力覆盖。
      if (field.kind === 'model_list') {
        if (field.item_fields?.length) walk(field.item_fields);
        for (const item of field.items || []) walk(item.fields);
      }
    }
  };
  walk(fields);
  if (!hot && !cold) return null;
  const description =
    hot && cold
      ? '支持重载配置；需重启项已单独标注'
      : hot
        ? unknown
          ? '已声明支持重载的配置，保存后重载生效'
          : '保存后重载配置生效，无需重启'
        : unknown
          ? '需重启的配置已单独标注'
          : '当前配置修改后需重启 NeoBot';
  return (
    <p className="cfg-reload-policy">
      <span>生效方式</span>
      {description}
    </p>
  );
}

function HotBadge({ descriptor }: { descriptor: FieldDescriptor }) {
  if (descriptor.partial_hot_reload) {
    return (
      <span className="hot-badge partial" title="该分组内部分配置项需要重启">
        部分需重启
      </span>
    );
  }
  if (descriptor.hot_reload !== false) return null;
  return (
    <span className="hot-badge cold" title={descriptor.restart_reason || '修改后需要重启 NeoBot'}>
      需重启
    </span>
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
        <button
          type="button"
          className="btn-sm"
          disabled={disabled}
          title="查看历史数值"
          onClick={() => onShowHistory?.(descriptor)}
        >
          历史 {historyTotal}
        </button>
      )}
      {hasDefault && (
        <button
          type="button"
          className="btn-sm"
          disabled={disabled || descriptor.readonly || !changed}
          title="恢复该配置项的默认值"
          onClick={() => onRestore?.(descriptor.path, descriptor.default)}
        >
          恢复默认
        </button>
      )}
    </span>
  );
}
/** 集合字段共享名称、路径与说明，JSON/可视化切换时保持标题稳定。 */
function FieldHeader({ descriptor, filter }: { descriptor: FieldDescriptor; filter?: string }) {
  const parentPath = descriptor.path.slice(0, -1).join('.');
  return (
    <div className="cfg-label">
      <span className="cfg-field-name">
        {parentPath && <span className="cfg-path-prefix">{parentPath}.</span>}
        <Highlight text={descriptor.name} keyword={filter} />
        {descriptor.readonly && <span className="cfg-readonly">只读</span>}
      </span>
      {descriptor.description && (
        <p>
          <Highlight text={descriptor.description} keyword={filter} />
        </p>
      )}
      <span className="cfg-badges">
        <HotBadge descriptor={descriptor} />
      </span>
    </div>
  );
}

export { FieldHeader, HotBadge, ReloadSummary, FieldActions };
