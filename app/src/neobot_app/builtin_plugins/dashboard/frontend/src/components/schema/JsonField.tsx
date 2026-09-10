// components/schema/JsonField.tsx —— list / dict 以 JSON 文本编辑，带即时校验
import { useState } from 'react';
import type { FieldDescriptor } from '../../api/types';
import { HotBadge } from './FieldChrome';
import type { FieldCallbacks } from './fieldTypes';
function JsonField({
  descriptor,
  value,
  onChange,
  disabled,
  rows = 4,
}: { descriptor: FieldDescriptor; rows?: number } & Pick<FieldCallbacks, 'onChange' | 'disabled' | 'value'>) {
  const [text, setText] = useState(JSON.stringify(value ?? (descriptor.kind === 'dict' ? {} : []), null, 2));
  const [error, setError] = useState('');
  const id = 'cfg-' + descriptor.path.map(encodeURIComponent).join('-');
  return (
    <div className="cfg-row">
      <div className="cfg-label">
        <label htmlFor={id}>{descriptor.name}</label>
        <p>{descriptor.description || 'JSON 格式'}</p>
        <span className="cfg-badges"><HotBadge descriptor={descriptor} /></span>
      </div>
      <div className="cfg-control">
        <textarea id={id} className="input config-array" rows={rows} spellCheck={false} disabled={disabled}
          aria-invalid={!!error} value={text}
          onChange={(event) => {
            const raw = event.target.value;
            setText(raw);
            try {
              const parsed = JSON.parse(raw);
              const expectArray = descriptor.kind === 'list';
              if (expectArray && !Array.isArray(parsed)) throw new Error();
              if (!expectArray && (Array.isArray(parsed) || typeof parsed !== 'object')) throw new Error();
              setError('');
              onChange(parsed);
            } catch {
              setError(descriptor.kind === 'list' ? '请输入有效的 JSON 数组' : '请输入有效的 JSON 对象');
            }
          }} />
        {error && <span className="field-error" role="alert">{error}</span>}
      </div>
    </div>
  );
}
export default JsonField;
