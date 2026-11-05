// components/schema/ScalarField.tsx —— 标量字段：布尔开关 / 下拉 / 长文本 / 数字 / 密码 / 恢复默认
import { useEffect, useRef, useState } from 'react';
import Icon from '../Icon';
import type { FieldDescriptor } from '../../api/types';
import ComboboxField from './ComboboxField';
import { FieldActions, HotBadge } from './FieldChrome';
import { Highlight } from './Highlight';
import LongTextField from './LongTextField';
import { SECRET_RE, type FieldCallbacks } from './fieldTypes';
function ScalarField({
  descriptor,
  value,
  onChange,
  disabled,
  onRestore,
  onShowHistory,
  historyCount,
  filter,
}: { descriptor: FieldDescriptor } & FieldCallbacks) {
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
  const id =
    typeof descriptor.input_id === 'string'
      ? descriptor.input_id
      : 'cfg-' + descriptor.path.map(encodeURIComponent).join('-');
  // 只有字符串才可能是密钥：max_output_tokens 这类数值字段不该出现眼睛按钮
  const secret =
    descriptor.type === 'str' && (descriptor.sensitive === true || SECRET_RE.test(descriptor.name));
  const locked = disabled || descriptor.readonly;
  const longText = text.length > 120 || text.includes('\n');
  /** 原生 input 事件在组字中会带 isComposing；React 的 Event 类型没声明它。 */
  const isComposingEvent = (event: { nativeEvent: Event }) =>
    (event.nativeEvent as Event & { isComposing?: boolean }).isComposing === true;

  /** LongTextField 的提交口：本地状态与草稿一起更新。 */
  const setTextAndEmit = (next: string) => {
    if (locked) return;
    setText(next);
    onChange(next);
  };

  // 组字生命周期：结束时把最终文本一次性提交（组字期间不提交）。
  const compositionProps = {
    onCompositionStart: () => {
      composing.current = true;
    },
    onCompositionEnd: (event: { currentTarget: { value: string } }) => {
      composing.current = false;
      if (locked) return;
      const next = event.currentTarget.value;
      setText(next);
      onChange(next);
    },
  };

  // 面板收敛为「左树选分区 + 右侧只渲染该分区」，字段名不再带前缀；
  // 搜索时把父路径补成灰色前缀，命中片段标黄，用户才看得出「命中在哪一层」。
  const parentPath = descriptor.path.slice(0, -1).join('.');
  const header = (
    <div className="cfg-label">
      <label htmlFor={id}>
        {parentPath && <span className="cfg-path-prefix">{parentPath}.</span>}
        <Highlight text={descriptor.label || descriptor.name} keyword={filter} />
        {descriptor.readonly && <span className="muted small"> · 只读</span>}
      </label>
      {descriptor.description && (
        <p>
          <Highlight text={descriptor.description} keyword={filter} />
        </p>
      )}
      <span className="cfg-badges">
        <HotBadge descriptor={descriptor} />
      </span>
    </div>
  );

  if (!descriptor.options?.length && (typeof value === 'boolean' || descriptor.type === 'bool')) {
    return (
      <div className="cfg-row">
        {header}
        <div className="cfg-control cfg-control-with-actions">
          <label className="config-switch">
            <input
              id={id}
              type="checkbox"
              checked={!!value}
              disabled={locked}
              onChange={(event) => {
                if (!locked) onChange(event.target.checked);
              }}
            />
            <span className="switch-track" />
            <span>{value ? '已开启' : '已关闭'}</span>
          </label>
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

  const options = Array.isArray(descriptor.options) ? descriptor.options : null;
  if (options && options.length && !descriptor.options_strict) {
    return (
      <ComboboxField
        descriptor={descriptor}
        value={value}
        onChange={onChange}
        disabled={locked}
        onRestore={onRestore}
        onShowHistory={onShowHistory}
        historyCount={historyCount}
      />
    );
  }
  if (options && options.length && descriptor.options_strict) {
    const labelOf = (option: string) => descriptor.option_labels?.[option] ?? option;
    // 旧/脏 API 数据可能把 option_groups 写成非数组：退回扁平下拉而不是整页崩掉。
    const groups = Array.isArray(descriptor.option_groups) ? descriptor.option_groups : [];
    // 分组只改变显示顺序：不属于任何分组的值（如「不设置」）排在分组前，
    // 其余按后端给定分组渲染，用户才能一眼分清 OpenAI 档位与 Claude 档位。
    const grouped = new Set(groups.flatMap((group) => group.options));
    // 枚举先精确匹配；仅旧 TOML 的 " HIGH " 这类值继续按大小写和空白宽容匹配。
    const rawValue = value === undefined || value === null ? '' : String(value);
    const normalizedValue = rawValue.trim().toLowerCase();
    const mapped =
      descriptor.option_values &&
      options.find((option) => Object.is(descriptor.option_values?.[option], value));
    const selected =
      mapped ??
      (options.includes(rawValue)
        ? rawValue
        : (options.find((option) => option.trim().toLowerCase() === normalizedValue) ?? rawValue));
    const renderOption = (option: string) => (
      <option key={option} value={option}>
        {labelOf(option)}
      </option>
    );
    return (
      <div className="cfg-row">
        {header}
        <div className="cfg-control cfg-control-with-actions">
          <select
            id={id}
            className="input"
            disabled={locked}
            value={selected}
            onChange={(event) => {
              if (!locked) {
                const key = event.target.value;
                onChange(
                  descriptor.option_values && key in descriptor.option_values
                    ? descriptor.option_values[key]
                    : key,
                );
              }
            }}
          >
            {options.filter((option) => !grouped.has(option)).map(renderOption)}
            {groups.map((group) => (
              <optgroup key={group.label} label={group.label}>
                {group.options.map(renderOption)}
              </optgroup>
            ))}
          </select>
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

  const numeric = descriptor.type === 'int' || descriptor.type === 'float';

  // 非数字、非密钥的字符串一律走 LongTextField：
  // 它永远是 textarea（类型不翻转 → 不会像旧实现那样在打字途中换控件、丢焦点），
  // 高度按实测 scrollHeight（含折行）自动增高。
  if (!numeric && !secret && descriptor.single_line !== true) {
    return (
      <div className="cfg-row">
        {header}
        <div className="cfg-control cfg-control-with-actions">
          <LongTextField
            id={id}
            value={text}
            onChange={setTextAndEmit}
            disabled={locked}
            minRows={longText ? 3 : 1}
            monospace={longText}
            // 短字段不显示行数/放大：它就是个单行框，多一行说明纯属噪音
            showCount={longText}
            expandable={longText}
            ariaLabel={descriptor.label || descriptor.name}
            placeholder={typeof descriptor.placeholder === 'string' ? descriptor.placeholder : undefined}
            ariaInvalid={!!error}
          />
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
  return (
    <div className="cfg-row">
      {header}
      <div className="cfg-control cfg-control-with-actions">
        <div className="config-input-wrap">
          <input
            id={id}
            className="input"
            disabled={locked}
            type={numeric ? 'number' : secret && !reveal ? 'password' : 'text'}
            step={descriptor.type === 'float' ? 'any' : undefined}
            min={descriptor.min}
            max={descriptor.max}
            autoComplete="off"
            spellCheck={false}
            aria-invalid={!!error}
            placeholder={typeof descriptor.placeholder === 'string' ? descriptor.placeholder : undefined}
            value={text}
            {...compositionProps}
            onChange={(event) => {
              if (locked) return;
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
            }}
          />
          {secret && (
            <button
              type="button"
              className="icon-btn"
              aria-label={reveal ? '隐藏' : '显示'}
              disabled={locked}
              aria-pressed={reveal}
              onClick={() => setReveal(!reveal)}
            >
              <Icon name="eye" />
            </button>
          )}
        </div>

        {error && (
          <span className="field-error" role="alert">
            {error}
          </span>
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
export default ScalarField;
