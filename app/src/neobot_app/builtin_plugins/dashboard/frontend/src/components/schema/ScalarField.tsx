// components/schema/ScalarField.tsx —— 标量字段：布尔开关 / 下拉 / 长文本 / 数字 / 密码 / 恢复默认
import { useState } from 'react';
import Icon from '../Icon';
import type { FieldDescriptor } from '../../api/types';
import ComboboxField from './ComboboxField';
import { FieldActions, HotBadge } from './FieldChrome';
import { SECRET_RE, type FieldCallbacks } from './fieldTypes';
function ScalarField({ descriptor, value, onChange, disabled, changed, onRestore, onShowHistory, historyCount }: { descriptor: FieldDescriptor } & FieldCallbacks) {
  const [reveal, setReveal] = useState(false);
  const [text, setText] = useState(value === undefined || value === null ? '' : String(value));
  const [error, setError] = useState('');
  const id = 'cfg-' + descriptor.path.map(encodeURIComponent).join('-');
  const secret = SECRET_RE.test(descriptor.name);
  const locked = disabled || descriptor.readonly;
  const longText = typeof value === 'string' && (value.length > 120 || value.includes('\n'));

  const header = (
    <div className="cfg-label">
      <label htmlFor={id}>{descriptor.name}{descriptor.readonly && <span className="muted small"> · 只读</span>}</label>
      {descriptor.description && <p>{descriptor.description}</p>}
      <span className="cfg-badges"><HotBadge descriptor={descriptor} /></span>
    </div>
  );

  if (typeof value === 'boolean' || descriptor.type === 'bool') {
    return (
      <div className="cfg-row">
        {header}
        <div className="cfg-control">
          <label className="config-switch">
            <input id={id} type="checkbox" checked={!!value} disabled={disabled}
              onChange={(event) => onChange(event.target.checked)} />
            <span className="switch-track" />
            <span>{value ? '已开启' : '已关闭'}</span>
          </label>
          <FieldActions descriptor={descriptor} disabled={disabled} changed={changed}
            onRestore={onRestore} onShowHistory={onShowHistory} historyCount={historyCount} />
        </div>
      </div>
    );
  }

  const options = Array.isArray(descriptor.options) ? descriptor.options : null;
  if (options && options.length && !descriptor.options_strict) {
    return (
      <ComboboxField descriptor={descriptor} value={value} onChange={onChange} disabled={disabled}
        changed={changed} onRestore={onRestore} onShowHistory={onShowHistory} historyCount={historyCount} />
    );
  }
  if (options && options.length && descriptor.options_strict) {
    return (
      <div className="cfg-row">
        {header}
        <div className="cfg-control">
          <select id={id} className="input" disabled={locked} value={value ?? ''}
            onChange={(event) => onChange(event.target.value)}>
            {options.map((option) => (
              <option key={option} value={option}>{option}</option>
            ))}
          </select>
          <FieldActions descriptor={descriptor} disabled={disabled} changed={changed}
            onRestore={onRestore} onShowHistory={onShowHistory} historyCount={historyCount} />
        </div>
      </div>
    );
  }

  const numeric = descriptor.type === 'int' || descriptor.type === 'float';
  if (longText) {
    return (
      <div className="cfg-row">
        {header}
        <div className="cfg-control">
          <textarea id={id} className="input" spellCheck={false} disabled={locked} value={value ?? ''}
            rows={Math.min(8, Math.max(3, String(value).split('\n').length))}
            onChange={(event) => onChange(event.target.value)} />
          <FieldActions descriptor={descriptor} disabled={disabled} changed={changed}
            onRestore={onRestore} onShowHistory={onShowHistory} historyCount={historyCount} />
        </div>
      </div>
    );
  }
  return (
    <div className="cfg-row">
      {header}
      <div className="cfg-control">
        <div className="config-input-wrap">
          <input id={id} className="input" disabled={locked}
            type={numeric ? 'number' : secret && !reveal ? 'password' : 'text'}
            step={descriptor.type === 'float' ? 'any' : undefined}
            min={descriptor.min} max={descriptor.max}
            autoComplete="off" spellCheck={false} aria-invalid={!!error}
            value={numeric ? text : value ?? ''}
            onChange={(event) => {
              const raw = event.target.value;
              if (numeric) {
                setText(raw);
                const invalid = raw === '' || !Number.isFinite(Number(raw));
                setError(invalid ? '请输入有效数值' : '');
                if (!invalid) onChange(descriptor.type === 'int' ? Math.trunc(Number(raw)) : Number(raw));
              } else {
                onChange(raw);
              }
            }} />
          {secret && (
            <button type="button" className="icon-btn" aria-label={reveal ? '隐藏' : '显示'}
              aria-pressed={reveal} onClick={() => setReveal(!reveal)}><Icon name="eye" /></button>
          )}
        </div>

        {error && <span className="field-error" role="alert">{error}</span>}
        <FieldActions descriptor={descriptor} disabled={disabled} changed={changed}
          onRestore={onRestore} onShowHistory={onShowHistory} historyCount={historyCount} />
      </div>
    </div>
  );
}
export default ScalarField;
