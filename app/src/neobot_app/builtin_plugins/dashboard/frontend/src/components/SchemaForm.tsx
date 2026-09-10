// components/SchemaForm.tsx —— 由后端字段描述驱动的通用配置表单（对外入口）
// 支持：标量、布尔、数组、字典、嵌套对象（分组，可折叠）、对象数组（如多个生图模型）。
// 另支持：恢复默认值、数值历史、热重载标记（hot_reload / restart_reason）。
//
// 结构：本文件只做编排（变更检测 + 历史弹窗 + 遍历字段）；
//       字段渲染在 ./schema 下按 kind 拆分，并通过 fieldRegistry 注册，后端新增 kind 无需改这里。
import { useMemo, useState } from 'react';
import Icon from './Icon';
import Modal from './Modal';
import { getPath, joinPath } from '../utils/paths';
import type { FieldDescriptor } from '../api/types';
import Field from './schema/Field';
import { defaultsFromFields, formatValue, pathKey, type SchemaFormProps } from './schema/fieldTypes';

export default function SchemaForm({
  fields = [], values, onChange, disabled, filter, baseline, history = {}, onRestore, onToggleCollapse, collapse = {},
}: SchemaFormProps) {
  const [historyTarget, setHistoryTarget] = useState<FieldDescriptor | null>(null);

  const changedPaths = useMemo(() => {
    const changed = new Set<string>();
    if (!baseline) return changed;
    const walk = (list?: FieldDescriptor[]) => {
      for (const field of list || []) {
        const key = pathKey(field.path);
        const current = getPath(values, field.path);
        const base = getPath(baseline, field.path);
        if (field.kind === 'group') walk(field.fields);
        else if (JSON.stringify(current ?? null) !== JSON.stringify(base ?? null)) changed.add(key);
      }
    };
    walk(fields);
    return changed;
  }, [fields, values, baseline]);

  const showHistory = (descriptor: FieldDescriptor) => setHistoryTarget(descriptor);

  if (!fields.length) {
    return (
      <div className="workspace-empty">
        <Icon name="settings" />
        <h3>没有可编辑的字段</h3>
        <p>可以切换到 TOML 模式直接编辑原始配置。</p>
      </div>
    );
  }

  const entries = historyTarget ? (history[pathKey(historyTarget.path)] || []) : [];

  return (
    <div className="cfg-root">
      {fields.map((descriptor) => (
        <Field key={descriptor.path.join('.')} descriptor={descriptor} disabled={disabled} filter={filter}
          changedPaths={changedPaths} history={history} collapse={collapse}
          onToggleCollapse={onToggleCollapse}
          onRestore={onRestore} onShowHistory={showHistory}
          onChange={(next) => onChange(descriptor.path, next)} />
      ))}
      <Modal open={!!historyTarget} title={'历史数值 · ' + (historyTarget?.name || '')}
        onClose={() => setHistoryTarget(null)}>
        {entries.length === 0 && <p className="empty muted">暂无历史记录</p>}
        {entries.length > 0 && (
          <ul className="cfg-history">
            {entries.map((entry, index) => (
              <li key={index}>
                <code>{formatValue(entry.value)}</code>
                <span className="muted small">{entry.at}</span>
                <button type="button" className="btn-sm" disabled={disabled}
                  onClick={() => {
                    if (historyTarget) onRestore?.(historyTarget.path, entry.value);
                    setHistoryTarget(null);
                  }}>恢复</button>
              </li>
            ))}
          </ul>
        )}
      </Modal>
    </div>
  );
}

// 对外契约保持不变：既有调用点（pages/config/*、pages/plugins/*）无需改动
export { defaultsFromFields, joinPath };
export type { FieldCallbacks, FieldProps, FieldValue, SchemaFormProps } from './schema/fieldTypes';
export { fieldRegistry, resolveFieldComponent } from './schema/fieldRegistry';
