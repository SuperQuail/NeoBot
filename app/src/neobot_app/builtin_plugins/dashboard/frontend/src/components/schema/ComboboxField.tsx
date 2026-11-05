// components/schema/ComboboxField.tsx —— 下拉 + 自定义输入（候选来自后端，仍允许手填新值）
import { useEffect, useMemo, useRef, useState } from 'react';
import type { FieldDescriptor } from '../../api/types';
import { FieldActions, HotBadge } from './FieldChrome';
import type { FieldCallbacks } from './fieldTypes';
function ComboboxField({
  descriptor,
  value,
  onChange,
  disabled,
  onRestore,
  onShowHistory,
  historyCount,
}: { descriptor: FieldDescriptor } & FieldCallbacks) {
  const options = useMemo(
    () => (Array.isArray(descriptor.options) ? descriptor.options : []),
    [descriptor.options],
  );
  const current = value === undefined || value === null ? '' : String(value);
  const inOptions = options.includes(current);
  // 无候选时直接进入自定义输入；有候选时展示下拉（当前值不在候选里则作为「（自定义）」选项保留）
  const [custom, setCustom] = useState(options.length === 0);
  const previousCount = useRef(options.length);
  const fieldId = 'cfg-' + descriptor.path.map(encodeURIComponent).join('-');
  const locked = !!disabled || !!descriptor.readonly;

  useEffect(() => {
    const had = previousCount.current;
    previousCount.current = options.length;
    if (options.length === 0) {
      setCustom(true);
      return;
    }
    // 刚拉取到候选（0 -> N）：用户没输入过内容就回到下拉
    if (had === 0) {
      setCustom((active) => (active && current !== '' && !options.includes(current) ? active : false));
    }
  }, [options, current]);

  const header = (
    <div className="cfg-label">
      <label htmlFor={fieldId}>
        {descriptor.label || descriptor.name}
        {descriptor.readonly && <span className="muted small"> · 只读</span>}
      </label>
      {descriptor.description && <p>{descriptor.description}</p>}
      <span className="cfg-badges">
        <HotBadge descriptor={descriptor} />
      </span>
    </div>
  );

  return (
    <div className="cfg-row">
      {header}
      <div className="cfg-control cfg-control-with-actions">
        {custom ? (
          <div className="config-input-wrap">
            <input
              id={fieldId}
              className="input"
              disabled={locked}
              spellCheck={false}
              autoComplete="off"
              value={current}
              placeholder="输入自定义值"
              onChange={(event) => {
                if (!locked) onChange(event.target.value);
              }}
            />
            {options.length > 0 && (
              <button type="button" className="btn-sm" disabled={locked} onClick={() => setCustom(false)}>
                从列表选择
              </button>
            )}
          </div>
        ) : (
          <select
            id={fieldId}
            className="input"
            disabled={locked}
            value={inOptions ? current : current ? '__current__' : ''}
            onChange={(event) => {
              if (locked) return;
              const next = event.target.value;
              if (next === '__custom__') {
                setCustom(true);
                return;
              }
              if (next === '__current__') return;
              onChange(next);
            }}
          >
            {!inOptions && current !== '' && <option value="__current__">{current}（自定义）</option>}
            <option value="">（未选择）</option>
            {options.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
            <option value="__custom__">自定义…</option>
          </select>
        )}
        <FieldActions
          descriptor={descriptor}
          value={value}
          disabled={locked}
          onRestore={onRestore}
          onShowHistory={onShowHistory}
          historyCount={historyCount}
        />
      </div>
    </div>
  );
}
export default ComboboxField;
