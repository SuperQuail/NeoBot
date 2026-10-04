// ListField.tsx —— 数组编辑器：按内容自动在「chip 墙」与「拖拽列表」之间选形态
//
// 此前 list/dict 都走 JsonField（原始 JSON 文本域），用户得手写 ["a","b"]，
// 少个逗号就报错；而 allowed_read_dirs / engines 这类顺序还有语义。
//
// 形态判定（可用右上角切换覆盖，覆盖后本次会话记住）：
//   - 元素含路径分隔符（/ \\ 或 ://）  -> 拖拽列表（路径/URL 长且顺序有意义）
//   - 任一元素超过 24 字符             -> 拖拽列表（chip 墙会挤成一团）
//   - 其余（QQ 号、短名称、开关名）      -> chip 墙（紧凑、一屏看全）
import { useState } from 'react';
import JsonField from './JsonField';
import ChipList from './ChipList';
import DragList from './DragList';
import type { FieldDescriptor } from '../../api/types';
import type { FieldCallbacks } from './fieldTypes';

const LONG_VALUE = 24;
const PATH_RE = /[\\/]|:\/\//;

/** 自动判定该用哪种形态；导出来便于单测与预览脚本复用同一套规则。 */
export function preferDragList(values: string[]): boolean {
  if (values.length === 0) return false;
  if (values.some((value) => PATH_RE.test(value))) return true;
  return values.some((value) => value.length > LONG_VALUE);
}

export function listValues(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => (item === null || item === undefined ? '' : String(item)));
}

/**
 * 元素里含对象/数组时，可视化编辑表达不了结构。
 * 这种情况**不能**渲染成 "[object Object]" 假装能编辑——那会把错误数据写回配置。
 * 直接引导走 JSON 文本模式。
 */
export function hasComplexItems(value: unknown): boolean {
  if (!Array.isArray(value)) return false;
  return value.some((item) => item !== null && typeof item === 'object');
}

/**
 * 类型是否会因可视化编辑而改变。
 *
 * chip/拖拽编辑产出的一定是**字符串**，但配置里可能是数字/布尔。
 * 目前写配置没有类型强转，所以一旦编辑就会把 5 变成 "5"、true 变成 "true"。
 * 与其「看起来能编辑、实际改坏类型」，不如提前说清楚并引导去 JSON 模式。
 */
export function typeWillChange(values: string[], raw: unknown, elementType?: unknown): boolean {
  if (Array.isArray(raw) && raw.some((item) => item !== null && typeof item !== 'string')) return true;
  const expected = String(elementType || '');
  return (expected === 'int' || expected === 'float' || expected === 'bool') && values.length > 0;
}

export default function ListField({ descriptor, value, onChange, disabled, filter }: { descriptor: FieldDescriptor } & FieldCallbacks) {
  const values = listValues(value);
  const auto = preferDragList(values) ? 'drag' : 'chip';
  const [override, setOverride] = useState<'chip' | 'drag' | null>(null);
  const [showJson, setShowJson] = useState(false);
  const mode = override ?? auto;
  // 复杂元素：不给可视化编辑，直接落 JSON 模式并说明原因
  const complex = hasComplexItems(value);
  const forcedJson = complex || showJson;
  const typeRisk = !complex && typeWillChange(values, value, (descriptor as { element_type?: unknown }).element_type);

  if (forcedJson) {
    return (
      <div className="cfg-collection">
        <div className="cfg-collection-bar">
          <span className="muted small">
            {complex
              ? '元素里含对象/数组，只能用 JSON 编辑'
              : 'JSON 文本模式'}
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
        <span className="muted small">{values.length} 项 · {mode === 'chip' ? '紧凑' : '列表（可拖排序）'}</span>
        <div className="spacer" />
        <button type="button" className="btn-sm" disabled={disabled}
          title="在紧凑 chip 与可拖拽列表之间切换"
          onClick={() => setOverride(mode === 'chip' ? 'drag' : 'chip')}>
          {mode === 'chip' ? '切换为列表' : '切换为紧凑'}
        </button>
        <button type="button" className="btn-sm" disabled={disabled} title="内容嵌套时用 JSON 直接编辑"
          onClick={() => setShowJson(true)}>JSON</button>
      </div>
      {typeRisk && (
        <p className="cfg-collection-warn" role="note">
          该数组的元素不是字符串（或 schema 声明为 int/bool）。可视化编辑会把它们转成文本，
          需要保持原类型请用 <b>JSON</b> 模式编辑。
        </p>
      )}
      {mode === 'chip' ? (
        <ChipList items={values} filter={filter} onChange={onChange} placeholder="新值" />
      ) : (
        <DragList items={values} filter={filter} onChange={onChange} />
      )}
    </div>
  );
}
