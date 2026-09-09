// SchemaForm.jsx —— 由后端字段描述驱动的通用配置表单
// 支持：标量、布尔、数组、字典、嵌套对象（分组）、对象数组（如多个生图模型）。
import { useState } from 'react';
import Icon from './Icon.jsx';
import { getPath, joinPath, matchPath } from '../utils/paths.js';

const SECRET_RE = /token|password|secret|api[_-]?key|credential|access_key/i;

function defaultsFromFields(fields = []) {
  const value = {};
  for (const field of fields) {
    if (field.kind === 'group') value[field.name] = defaultsFromFields(field.fields);
    else if (field.kind === 'model_list') value[field.name] = [];
    else if (field.kind === 'list') value[field.name] = [];
    else if (field.kind === 'dict') value[field.name] = {};
    else value[field.name] = field.default ?? (field.type === 'bool' ? false : field.type === 'int' || field.type === 'float' ? 0 : '');
  }
  return value;
}

function ScalarField({ descriptor, value, onChange, disabled }) {
  const [reveal, setReveal] = useState(false);
  const [text, setText] = useState(value === undefined || value === null ? '' : String(value));
  const [error, setError] = useState('');
  const id = 'cfg-' + descriptor.path.map(encodeURIComponent).join('-');
  const secret = SECRET_RE.test(descriptor.name);

  if (typeof value === 'boolean' || descriptor.type === 'bool') {
    return (
      <div className="cfg-row">
        <div className="cfg-label">
          <label htmlFor={id}>{descriptor.name}</label>
          {descriptor.description && <p>{descriptor.description}</p>}
        </div>
        <div className="cfg-control">
          <label className="config-switch">
            <input
              id={id}
              type="checkbox"
              checked={!!value}
              disabled={disabled}
              onChange={(event) => onChange(event.target.checked)}
            />
            <span className="switch-track" />
            <span>{value ? '已开启' : '已关闭'}</span>
          </label>
        </div>
      </div>
    );
  }

  const numeric = descriptor.type === 'int' || descriptor.type === 'float';
  return (
    <div className="cfg-row">
      <div className="cfg-label">
        <label htmlFor={id}>{descriptor.name}</label>
        {descriptor.description && <p>{descriptor.description}</p>}
      </div>
      <div className="cfg-control">
        <div className="config-input-wrap">
          <input
            id={id}
            className="input"
            disabled={disabled}
            type={numeric ? 'number' : secret && !reveal ? 'password' : 'text'}
            step={descriptor.type === 'float' ? 'any' : undefined}
            autoComplete="off"
            spellCheck={false}
            aria-invalid={!!error}
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
            }}
          />
          {secret && (
            <button
              type="button"
              className="icon-btn"
              aria-label={reveal ? '隐藏' : '显示'}
              aria-pressed={reveal}
              onClick={() => setReveal(!reveal)}
            >
              <Icon name="eye" />
            </button>
          )}
        </div>
        {error && <span className="field-error" role="alert">{error}</span>}
      </div>
    </div>
  );
}

function JsonField({ descriptor, value, onChange, disabled, rows = 4 }) {
  const [text, setText] = useState(JSON.stringify(value ?? (descriptor.kind === 'dict' ? {} : []), null, 2));
  const [error, setError] = useState('');
  const id = 'cfg-' + descriptor.path.map(encodeURIComponent).join('-');
  return (
    <div className="cfg-row">
      <div className="cfg-label">
        <label htmlFor={id}>{descriptor.name}</label>
        <p>{descriptor.description || 'JSON 格式'}</p>
      </div>
      <div className="cfg-control">
        <textarea
          id={id}
          className="input config-array"
          rows={rows}
          spellCheck={false}
          disabled={disabled}
          aria-invalid={!!error}
          value={text}
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
          }}
        />
        {error && <span className="field-error" role="alert">{error}</span>}
      </div>
    </div>
  );
}

function ModelList({ descriptor, disabled, onChange, filter }) {
  const list = Array.isArray(descriptor.value) ? descriptor.value : [];
  const items = descriptor.items || [];
  const setList = (next) => onChange(next);
  const add = () => setList([...list, defaultsFromFields(descriptor.item_fields)]);
  const remove = (index) => {
    if (!confirm('确认删除该配置项？')) return;
    setList(list.filter((_, i) => i !== index));
  };
  const duplicate = (index) => {
    const copy = structuredClone(list[index]);
    setList([...list.slice(0, index + 1), copy, ...list.slice(index + 1)]);
  };
  const move = (index, delta) => {
    const target = index + delta;
    if (target < 0 || target >= list.length) return;
    const next = [...list];
    [next[index], next[target]] = [next[target], next[index]];
    setList(next);
  };
  const visible = items.filter((entry) =>
    !filter || entry.fields.some((field) => matchPath(field.path, filter) || String(getPath(entry.fields, []) ?? ''))
  );

  return (
    <section className="cfg-group cfg-list">
      <div className="cfg-section-heading">
        <h3>{descriptor.name}</h3>
        <span>{list.length} 项</span>
        <div className="spacer" />
        <button type="button" className="btn-sm primary" disabled={disabled} onClick={add}>
          <Icon name="plus" /> 新增
        </button>
      </div>
      {descriptor.description && <p className="muted small cfg-hint">{descriptor.description}</p>}
      {list.length === 0 && <div className="empty muted">还没有配置项，点击「新增」添加</div>}
      {(filter ? visible : items).map((entry) => {
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
              <Field
                key={field.path.join('.')}
                descriptor={field}
                disabled={disabled}
                filter={filter}
                onChange={(next) => {
                  const cloned = structuredClone(list);
                  let node = cloned[index];
                  for (const key of field.path.slice(descriptor.path.length + 1, -1)) node = node[key];
                  node[field.path.at(-1)] = next;
                  setList(cloned);
                }}
              />
            ))}
          </div>
        );
      })}
    </section>
  );
}

function Field({ descriptor, disabled, onChange, filter }) {
  if (filter && !matchPath(descriptor.path, filter) && descriptor.kind === 'scalar') return null;
  if (descriptor.kind === 'group') {
    const visible = (descriptor.fields || []).filter(
      (field) => !filter || field.kind !== 'scalar' || matchPath(field.path, filter)
    );
    if (filter && visible.length === 0) return null;
    return (
      <section className="cfg-group">
        <div className="cfg-section-heading">
          <h3>{descriptor.name}</h3>
          <span>{visible.length} 项</span>
        </div>
        {descriptor.description && <p className="muted small cfg-hint">{descriptor.description}</p>}
        {visible.map((field) => (
          <Field
            key={field.path.join('.')}
            descriptor={field}
            disabled={disabled}
            filter={filter}
            onChange={(next) => {
              const path = field.path.slice(descriptor.path.length);
              let node = structuredClone(descriptor.value ?? {});
              let cursor = node;
              for (const key of path.slice(0, -1)) cursor = cursor[key];
              cursor[path.at(-1)] = next;
              onChange(node);
            }}
          />
        ))}
      </section>
    );
  }
  if (descriptor.kind === 'model_list') {
    return <ModelList descriptor={descriptor} disabled={disabled} onChange={onChange} filter={filter} />;
  }
  if (descriptor.kind === 'list' || descriptor.kind === 'dict') {
    return <JsonField descriptor={descriptor} value={descriptor.value} disabled={disabled} onChange={onChange} />;
  }
  return <ScalarField descriptor={descriptor} value={descriptor.value} disabled={disabled} onChange={onChange} />;
}

export default function SchemaForm({ fields = [], values, onChange, disabled, filter }) {
  if (!fields.length) {
    return (
      <div className="workspace-empty">
        <Icon name="settings" />
        <h3>没有可编辑的字段</h3>
        <p>可以切换到 TOML 模式直接编辑原始配置。</p>
      </div>
    );
  }
  return (
    <div className="cfg-root">
      {fields.map((descriptor) => (
        <Field
          key={descriptor.path.join('.')}
          descriptor={descriptor}
          disabled={disabled}
          filter={filter}
          onChange={(next) => onChange(descriptor.path, next)}
        />
      ))}
    </div>
  );
}

export { defaultsFromFields, joinPath };
