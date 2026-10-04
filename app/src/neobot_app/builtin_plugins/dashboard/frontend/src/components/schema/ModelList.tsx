// components/schema/ModelList.tsx —— 对象数组编辑（如多个生图模型）：增删改、上移下移、复制
import { useState } from 'react';
import Icon from '../Icon';
import type { FieldDescriptor } from '../../api/types';
import { HotBadge } from './FieldChrome';
import { matchPath } from '../../utils/paths';
import Field from './Field';
import { defaultsFromFields, type FieldCallbacks } from './fieldTypes';
function ModelList({ descriptor, disabled, onChange, filter }: { descriptor: FieldDescriptor; filter?: string } & Pick<FieldCallbacks, 'onChange' | 'disabled'>) {
  const [collapsed, setCollapsed] = useState(false);
  const list: any[] = Array.isArray(descriptor.value) ? descriptor.value : [];
  const items: Array<{ index: number; fields: FieldDescriptor[] }> = (descriptor.items as any) || [];
  const setList = (next: any[]) => onChange(next);
  const add = () => setList([...list, defaultsFromFields(descriptor.item_fields)]);
  const remove = (index: number) => {
    if (!confirm('确认删除该配置项？')) return;
    setList(list.filter((_, i) => i !== index));
  };
  const duplicate = (index: number) => {
    const copy = structuredClone(list[index]);
    setList([...list.slice(0, index + 1), copy, ...list.slice(index + 1)]);
  };
  const move = (index: number, delta: number) => {
    const target = index + delta;
    if (target < 0 || target >= list.length) return;
    const next = [...list];
    [next[index], next[target]] = [next[target], next[index]];
    setList(next);
  };
  // 搜索过滤：路径命中，或该项的任一字段值命中关键词。
  // 注意别写成 String(getPath(entry.fields, [])) —— 空路径会取回整个 fields 数组，
  // String(...) 永远非空，条件恒真，等于没过滤（issue #66）。
  const keyword = String(filter || '').trim().toLowerCase();
  const entryMatches = (entry: { fields: FieldDescriptor[] }) =>
    !keyword ||
    entry.fields.some(
      (field) =>
        matchPath(field.path, keyword) ||
        String(field.value ?? '').toLowerCase().includes(keyword),
    );
  const visible = items.filter(entryMatches);

  return (
    <section className="cfg-group cfg-list">
      <div className="cfg-section-heading">
        <button type="button" className="cfg-collapse" aria-expanded={!collapsed}
          onClick={() => setCollapsed(!collapsed)}><Icon name="chevron" /></button>
        <h3>{descriptor.name}</h3>
        <span>{list.length} 项</span>
        <span className="cfg-badges"><HotBadge descriptor={descriptor} /></span>
        <div className="spacer" />
        <button type="button" className="btn-sm primary" disabled={disabled} onClick={add}>
          <Icon name="plus" /> 新增
        </button>
      </div>
      {descriptor.description && <p className="muted small cfg-hint">{descriptor.description}</p>}
      {!collapsed && list.length === 0 && <div className="empty muted">还没有配置项，点击「新增」添加</div>}
      {!collapsed && (filter ? visible : items).map((entry) => {
        const index = entry.index;
        const item = list[index] || {};
        const title = item.description || item.name || item.provider || ('第 ' + (index + 1) + ' 项');
        return (
          <div className="cfg-item" key={descriptor.path.join('.') + ':' + index}>
            <div className="cfg-item-head">
              <span className="meta-chip">#{index + 1}</span>
              <strong>{String(title)}</strong>
              <div className="spacer" />
              <button type="button" className="icon-btn" title="上移" disabled={disabled || index === 0} onClick={() => move(index, -1)}>↑</button>
              <button type="button" className="icon-btn" title="下移" disabled={disabled || index === list.length - 1} onClick={() => move(index, 1)}>↓</button>
              <button type="button" className="icon-btn" title="复制" disabled={disabled} onClick={() => duplicate(index)}><Icon name="save" /></button>
              <button type="button" className="icon-btn danger" title="删除" disabled={disabled} onClick={() => remove(index)}><Icon name="trash" /></button>
            </div>
            {entry.fields.map((field) => (
              // force_visible：这一项已经被判定命中（可能是靠某个字段的值命中的），
              // 它的子字段就不要再按路径各自过滤一遍 —— 否则整项渲染出来却没有控件。
              <Field key={field.path.join('.')} descriptor={{ ...field, force_visible: true }} disabled={disabled} filter={filter}
                onChange={(next) => {
                  const cloned: Record<string, any>[] = structuredClone(list);
                  let node: Record<string, any> = cloned[index];
                  for (const key of field.path.slice(descriptor.path.length + 1, -1)) node = node[key as string];
                  node[field.path[field.path.length - 1] as string] = next;
                  setList(cloned);
                }} />
            ))}
          </div>
        );
      })}
    </section>
  );
}
export default ModelList;
