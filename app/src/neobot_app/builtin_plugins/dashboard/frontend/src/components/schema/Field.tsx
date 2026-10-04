// components/schema/Field.tsx —— 按 descriptor.kind 查注册表渲染（新增 kind 只需在 registry 注册）
import Icon from '../Icon';
import { HotBadge } from './FieldChrome';
import { Highlight } from './Highlight';
import { fieldMatches } from './searchHit';
import { resolveFieldComponent } from './fieldRegistry';
import { pathKey, type FieldProps } from './fieldTypes';

export default function Field(props: FieldProps) {
  const { descriptor, disabled, onChange, filter, globallyFiltered, changedPaths, onRestore, onShowHistory, history, collapse, onToggleCollapse } = props;
  const key = pathKey(descriptor.path);
  const changed = changedPaths ? changedPaths.has(key) : false;
  const historyCount = history?.[key]?.length || 0;
  // 命中高亮：搜索时把路径里命中的片段标出来，用户能一眼看到「命中在哪」。
  const showHit = !!filter && !globallyFiltered;

  // 判定必须与 ConfigTreePanel 的 gatherField 一致（路径 / 说明 / 集合值），
  // 否则「只命中说明」的字段会在标题统计里算命中、渲染时又被这里丢掉。
  // force_visible：父级（model_list 条目）已判定命中，不再二次过滤。
  if (filter && !descriptor.force_visible && descriptor.kind === 'scalar' && !fieldMatches(descriptor, filter)) return null;

  // 分组不是「一种控件」，而是递归容器，因此不放进注册表
  if (descriptor.kind === 'group') {
    // 含参数目录伪字段的分组（settings）：被标记 hidden 的可选字段由伪字段接管
    // （在「已添加参数」区按 enabled_params 呈现），这里不再单独渲染，避免重复。
    const paramCatalog = (descriptor.fields || []).some((field) => field.kind === 'model_params');
    const inherited = descriptor.force_visible === true;
    const visible = (descriptor.fields || []).filter(
      (field) =>
        (!filter || inherited || field.kind !== 'scalar' || fieldMatches(field, filter)) &&
        !(paramCatalog && field.hidden),
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
          <h3><Highlight text={descriptor.name} keyword={showHit ? filter : undefined} /></h3>
          <span>{visible.length} 项</span>
          <span className="cfg-badges"><HotBadge descriptor={descriptor} /></span>
        </div>
        {descriptor.description && <p className="muted small cfg-hint">{descriptor.description}</p>}
        {!collapsed && visible.map((field) => (
          <Field key={field.path.join('.')} descriptor={inherited ? { ...field, force_visible: true } : field} disabled={disabled} filter={filter}
            globallyFiltered={globallyFiltered}
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
    <Component descriptor={descriptor} value={descriptor.value} disabled={disabled}
      filter={globallyFiltered ? undefined : filter}
      changed={changed} onRestore={onRestore} onShowHistory={onShowHistory}
      historyCount={historyCount} onChange={onChange} />
  );
}
