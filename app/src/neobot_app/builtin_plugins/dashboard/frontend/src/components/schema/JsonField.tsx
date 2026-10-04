// components/schema/JsonField.tsx —— list / dict 的 JSON 文本编辑（带即时校验与格式化）
//
// 这个入口现在只作为「兜底」：数组/字典默认可视化编辑（ListField / DictField），
// 元素是对象/数组时才引导到这里。
//
// 与旧实现的差别：
//   - 用 LongTextField（自动增高、折行友好、组字安全），不再固定 rows=4 挤在小框里；
//   - 外部值变更会回灌（撤销 / 恢复默认 / 重新读取）——旧实现只 useState 初始化一次，
//     撤销后文本框内容不跟着变，属于「看着改了其实没改」的假象。
import { useEffect, useRef, useState } from 'react';
import type { FieldDescriptor } from '../../api/types';
import { HotBadge } from './FieldChrome';
import LongTextField from './LongTextField';
import type { FieldCallbacks } from './fieldTypes';

function stringify(value: unknown, kind?: string): string {
  const fallback = kind === 'dict' ? {} : [];
  return JSON.stringify(value ?? fallback, null, 2);
}

function JsonField({
  descriptor,
  value,
  onChange,
  disabled,
}: { descriptor: FieldDescriptor } & Pick<FieldCallbacks, 'onChange' | 'disabled' | 'value'>) {
  const [text, setText] = useState(() => stringify(value, descriptor.kind));
  const [error, setError] = useState('');
  // 记住「自己最后一次提交出去的文本」：只有外部值与它不同时才算真的被外部改过，
  // 否则每敲一个字都会因为父级 value 变化而回灌、把光标弹到末尾。
  const lastSubmitted = useRef(stringify(value, descriptor.kind));

  useEffect(() => {
    const external = stringify(value, descriptor.kind);
    if (external === lastSubmitted.current) return;
    lastSubmitted.current = external;
    setText(external);
    setError('');
  }, [value, descriptor.kind]);

  const validate = (raw: string): { ok: boolean; parsed?: unknown; message: string } => {
    try {
      const parsed = JSON.parse(raw);
      const expectArray = descriptor.kind === 'list';
      if (expectArray && !Array.isArray(parsed)) {
        return { ok: false, message: '请输入有效的 JSON 数组' };
      }
      if (!expectArray && (Array.isArray(parsed) || typeof parsed !== 'object' || parsed === null)) {
        return { ok: false, message: '请输入有效的 JSON 对象' };
      }
      return { ok: true, parsed, message: '' };
    } catch {
      return { ok: false, message: descriptor.kind === 'list' ? '请输入有效的 JSON 数组' : '请输入有效的 JSON 对象' };
    }
  };

  const handleChange = (raw: string) => {
    setText(raw);
    const result = validate(raw);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setError('');
    lastSubmitted.current = stringify(result.parsed, descriptor.kind);
    onChange(result.parsed);
  };

  const format = () => {
    const result = validate(text);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    const pretty = stringify(result.parsed, descriptor.kind);
    setText(pretty);
    setError('');
    lastSubmitted.current = pretty;
    onChange(result.parsed);
  };

  return (
    <div className="cfg-row">
      <div className="cfg-label">
        <label htmlFor={'cfg-' + descriptor.path.map(encodeURIComponent).join('-')}>{descriptor.name}</label>
        <p>{descriptor.description || 'JSON 格式'}</p>
        <span className="cfg-badges"><HotBadge descriptor={descriptor} /></span>
      </div>
      <div className="cfg-control">
        <LongTextField
          value={text}
          onChange={handleChange}
          disabled={disabled}
          minRows={6}
          maxRows={24}
          monospace
          ariaLabel={descriptor.name}
          ariaInvalid={!!error}
        />
        <div className="cfg-json-actions">
          <button type="button" className="btn-sm" disabled={disabled} onClick={format}>格式化</button>
          <span className="muted small">改完即时校验，格式错误不会写进配置</span>
        </div>
        {error && <span className="field-error" role="alert">{error}</span>}
      </div>
    </div>
  );
}
export default JsonField;
