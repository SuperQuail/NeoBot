// DictField.tsx —— 字典编辑器：键值表 + JSON 兜底
import { useState } from 'react';
import JsonField from './JsonField';
import KeyValueList from './KeyValueList';
import type { FieldDescriptor } from '../../api/types';
import type { FieldCallbacks } from './fieldTypes';

export function dictEntries(value: unknown): Array<[string, string]> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return [];
  return Object.entries(value as Record<string, unknown>).map(([key, item]) => [
    key,
    item === null || item === undefined ? '' : String(item),
  ]);
}

/** 值是对象/数组时键值表表达不了，必须走 JSON（否则会把 [object Object] 写回配置）。 */
export function hasComplexValues(value: unknown): boolean {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  return Object.values(value as Record<string, unknown>).some(
    (item) => item !== null && typeof item === 'object',
  );
}

export default function DictField({ descriptor, value, onChange, disabled, filter }: { descriptor: FieldDescriptor } & FieldCallbacks) {
  const entries = dictEntries(value);
  const [showJson, setShowJson] = useState(false);
  const complex = hasComplexValues(value);
  const forcedJson = complex || showJson;

  if (forcedJson) {
    return (
      <div className="cfg-collection">
        <div className="cfg-collection-bar">
          <span className="muted small">
            {complex ? '值是对象/数组，只能用 JSON 编辑' : 'JSON 文本模式'}
          </span>
          {!complex && (
            <button type="button" className="btn-sm" onClick={() => setShowJson(false)}>返回可视化编辑</button>
          )}
        </div>
        <JsonField descriptor={descriptor} value={value} onChange={onChange} disabled={disabled} />
      </div>
    );
  }

  return (
    <div className={'cfg-collection' + (disabled ? ' is-disabled' : '')}>
      <div className="cfg-collection-bar">
        <span className="muted small">{entries.length} 条 · 键值表</span>
        <div className="spacer" />
        <button type="button" className="btn-sm" disabled={disabled} title="值是对象/数组时用 JSON 直接编辑"
          onClick={() => setShowJson(true)}>JSON</button>
      </div>
      <KeyValueList
        entries={entries}
        filter={filter}
        onChange={(next) => onChange(Object.fromEntries(next))}
      />
    </div>
  );
}
