// components/schema/ScalarField.tsx —— 标量字段：布尔开关 / 下拉 / 长文本 / 数字 / 密码 / 恢复默认
import { useEffect, useRef, useState } from 'react';
import Icon from '../Icon';
import type { FieldDescriptor } from '../../api/types';
import ComboboxField from './ComboboxField';
import { FieldActions, HotBadge } from './FieldChrome';
import { SECRET_RE, type FieldCallbacks } from './fieldTypes';
function ScalarField({ descriptor, value, onChange, disabled, changed, onRestore, onShowHistory, historyCount }: { descriptor: FieldDescriptor } & FieldCallbacks) {
  const [reveal, setReveal] = useState(false);
  const [text, setText] = useState(value === undefined || value === null ? '' : String(value));
  const [error, setError] = useState('');
  // IME 组字中：期间绝不向上提交，也绝不用外部 value 回写输入框。
  // 受控值在组字途中被改写是打断中文输入法（候选被截断）的经典原因。
  const composing = useRef(false);

  // 外部值变更（撤销 / 恢复默认 / 重新读取）回灌本地状态 —— 但组字期间不回灌，
  // 否则会把正在拼的字冲掉。
  useEffect(() => {
    if (composing.current) return;
    setText(value === undefined || value === null ? '' : String(value));
  }, [value]);
  const id = 'cfg-' + descriptor.path.map(encodeURIComponent).join('-');
  const secret = SECRET_RE.test(descriptor.name);
  const locked = disabled || descriptor.readonly;
  const longText = text.length > 120 || text.includes('\n');
  /** 原生 input 事件在组字中会带 isComposing；React 的 Event 类型没声明它。 */
  const isComposingEvent = (event: { nativeEvent: Event }) =>
    (event.nativeEvent as Event & { isComposing?: boolean }).isComposing === true;

  // 组字生命周期：结束时把最终文本一次性提交（组字期间不提交）。
  const compositionProps = {
    onCompositionStart: () => {
      composing.current = true;
    },
    onCompositionEnd: (event: { currentTarget: { value: string } }) => {
      composing.current = false;
      const next = event.currentTarget.value;
      setText(next);
      onChange(next);
    },
  };

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
          <textarea id={id} className="input" spellCheck={false} disabled={locked}
            value={text}
            // rows 也走本地状态：组字期间按外部 value 重算会让换行边界抖动、打断候选词
            rows={Math.min(8, Math.max(3, text.split('\n').length))}
            {...compositionProps}
            onChange={(event) => {
              const raw = event.target.value;
              setText(raw);
              // 组字中的中间态只留在本地，不写草稿/撤销栈，也不触发受控回写
              if (composing.current || isComposingEvent(event)) return;
              onChange(raw);
            }} />
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
            value={text}
            {...compositionProps}
            onChange={(event) => {
              const raw = event.target.value;
              setText(raw);
              if (numeric) {
                const invalid = raw === '' || !Number.isFinite(Number(raw));
                setError(invalid ? '请输入有效数值' : '');
                if (!invalid) onChange(descriptor.type === 'int' ? Math.trunc(Number(raw)) : Number(raw));
                return;
              }
              // 同上：组字中的中间态不提交
              if (composing.current || isComposingEvent(event)) return;
              onChange(raw);
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
