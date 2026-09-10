// components/schema/Field.tsx —— 按 descriptor.kind 查注册表渲染（新增 kind 只需在 registry 注册）
import Icon from '../Icon';
import { matchPath } from '../../utils/paths';
import { HotBadge } from './FieldChrome';
import { resolveFieldComponent } from './fieldRegistry';
import { pathKey, type FieldProps } from './fieldTypes';

export default function Field(props: FieldProps) {
  const { descriptor, disabled, onChange, filter, changedPaths, onRestore, onShowHistory, history, collapse, onToggleCollapse } = props;
  const key = pathKey(descriptor.path);
  const changed = changedPaths ? changedPaths.has(key) : false;
  const historyCount = history?.[key]?.length || 0;

  if (filter && !matchPath(descriptor.path, filter) && descriptor.kind === 'scalar') return null;

  // 分组不是「一种控件」，而是递归容器，因此不放进注册表
  if (descriptor.kind === 'group') {
    const visible = (descriptor.fields || []).filter(
      (field) => !filter || field.kind !== 'scalar' || matchPath(field.path, filter)
    );
    if (filter && visible.length === 0) return null;
    const collapsed = collapse?.[key] ?? false;
    return (
      <section className="cfg-group">
        <div className="cfg-section-heading">
          {onToggleCollapse && (
            <button type="button" className="cfg-collapse" aria-expanded={!collapsed}
              aria-label={collapsed ? '展开分组' : '折叠分组'}
              onClick={() => onToggleCollapse(key)}><Icon name="chevron" /></button>
          )}
          <h3>{descriptor.name}</h3>
          <span>{visible.length} 项</span>
          <span className="cfg-badges"><HotBadge descriptor={descriptor} /></span>
        </div>
        {descriptor.description && <p className="muted small cfg-hint">{descriptor.description}</p>}
        {!collapsed && visible.map((field) => (
          <Field key={field.path.join('.')} descriptor={field} disabled={disabled} filter={filter}
            changedPaths={changedPaths} onRestore={onRestore} onShowHistory={onShowHistory}
            history={history} collapse={collapse} onToggleCollapse={onToggleCollapse}
            onChange={(next) => {
              const path = field.path.slice(descriptor.path.length);
              const node: Record<string, any> = structuredClone(descriptor.value ?? {});
              let cursor: Record<string, any> = node;
              for (const key of path.slice(0, -1)) cursor = cursor[key as string];
              cursor[path[path.length - 1] as string] = next;
              onChange(node);
            }} />
        ))}
      </section>
    );
  }

  // 其余 kind 交给注册表：未知 kind 由 resolveFieldComponent 兜底为标量展示
  const Component = resolveFieldComponent(descriptor.kind);
  return (
    <Component descriptor={descriptor} value={descriptor.value} disabled={disabled} filter={filter}
      changed={changed} onRestore={onRestore} onShowHistory={onShowHistory}
      historyCount={historyCount} onChange={onChange} />
  );
}
