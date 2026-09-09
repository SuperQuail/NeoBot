// SchemaForm.jsx —— 由后端字段描述驱动的通用配置表单
// 支持：标量、布尔、数组、字典、嵌套对象（分组，可折叠）、对象数组（如多个生图模型）。
// 另支持：恢复默认值、数值历史、热重载标记（hot_reload / restart_reason）。
import { useMemo, useState } from 'react';
import Icon from './Icon.jsx';
import Modal from './Modal.jsx';
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

function pathKey(path) {
  return (path || []).join('.');
}

function formatValue(value) {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'object') {
    const text = JSON.stringify(value);
    return text.length > 160 ? text.slice(0, 160) + '…' : text;
  }
  const text = String(value);
  return text.length > 160 ? text.slice(0, 160) + '…' : text;
}

function HotBadge({ descriptor }) {
  if (descriptor.hot_reload === undefined) return null;
  if (descriptor.partial_hot_reload) {
    return <span className="hot-badge partial" title="该分组内部分配置项需要重启">部分热重载</span>;
  }
  return descriptor.hot_reload ? (
    <span className="hot-badge hot" title={descriptor.restart_reason || '修改后重载配置即可生效'}>热重载</span>
  ) : (
    <span className="hot-badge cold" title={descriptor.restart_reason || '修改后需要重启 NeoBot'}>需重启</span>
  );
}

function FieldActions({ descriptor, disabled, changed, onRestore, onShowHistory, historyCount }) {
  const hasDefault = descriptor.default !== undefined;
  if (!hasDefault && !historyCount) return null;
  return (
    <span className="cfg-field-actions">
      {historyCount > 0 && (
        <button type="button" className="btn-sm" disabled={disabled} title="查看历史数值"
          onClick={() => onShowHistory(descriptor)}>历史 {historyCount}</button>
      )}
      {hasDefault && (
        <button type="button" className="btn-sm" disabled={disabled || !changed}
          title="恢复该配置项的默认值"
          onClick={() => onRestore(descriptor.path, descriptor.default)}>恢复默认</button>
      )}
    </span>
  );
}

function ScalarField({ descriptor, value, onChange, disabled, changed, onRestore, onShowHistory, historyCount }) {
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
            list={options && options.length ? id + '-options' : undefined}
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
        {options && options.length > 0 && (
          <datalist id={id + '-options'}>
            {options.map((option) => <option key={option} value={option} />)}
          </datalist>
        )}
        {error && <span className="field-error" role="alert">{error}</span>}
        <FieldActions descriptor={descriptor} disabled={disabled} changed={changed}
          onRestore={onRestore} onShowHistory={onShowHistory} historyCount={historyCount} />
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

function ModelList({ descriptor, disabled, onChange, filter }) {
  const [collapsed, setCollapsed] = useState(false);
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
        <button type="button" className="cfg-collapse" aria-expanded={!collapsed}
          onClick={() => setCollapsed(!collapsed)}><Icon name="chevron" /></button>
        <h3>{descriptor.name}</h3>
        <span>{list.length} 项</span>
        <span className="cfg-badges"><HotBadge descriptor={descriptor} /></span>
        <div className="spacer" />
        <button type="button" className="btn-sm primary" disabled={disabled} onClick={add}>
          <Icon name="plus" /> 新增
        </button>
      </div>
      {descriptor.description && <p className="muted small cfg-hint">{descriptor.description}</p>}
      {!collapsed && list.length === 0 && <div className="empty muted">还没有配置项，点击「新增」添加</div>}
      {!collapsed && (filter ? visible : items).map((entry) => {
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
              <Field key={field.path.join('.')} descriptor={field} disabled={disabled} filter={filter}
                onChange={(next) => {
                  const cloned = structuredClone(list);
                  let node = cloned[index];
                  for (const key of field.path.slice(descriptor.path.length + 1, -1)) node = node[key];
                  node[field.path.at(-1)] = next;
                  setList(cloned);
                }} />
            ))}
          </div>
        );
      })}
    </section>
  );
}

function Field(props) {
  const { descriptor, disabled, onChange, filter, changedPaths, onRestore, onShowHistory, history, collapse, onToggleCollapse } = props;
  const key = pathKey(descriptor.path);
  const changed = changedPaths ? changedPaths.has(key) : false;
  const historyCount = history?.[key]?.length || 0;

  if (filter && !matchPath(descriptor.path, filter) && descriptor.kind === 'scalar') return null;

  if (descriptor.kind === 'group') {
    const visible = (descriptor.fields || []).filter(
      (field) => !filter || field.kind !== 'scalar' || matchPath(field.path, filter)
    );
    if (filter && visible.length === 0) return null;
    const collapsed = collapse?.[key] ?? false;
    return (
      <section className="cfg-group">
        <div className="cfg-section-heading">
          {onToggleCollapse && (
            <button type="button" className="cfg-collapse" aria-expanded={!collapsed}
              aria-label={collapsed ? '展开分组' : '折叠分组'}
              onClick={() => onToggleCollapse(key)}><Icon name="chevron" /></button>
          )}
          <h3>{descriptor.name}</h3>
          <span>{visible.length} 项</span>
          <span className="cfg-badges"><HotBadge descriptor={descriptor} /></span>
        </div>
        {descriptor.description && <p className="muted small cfg-hint">{descriptor.description}</p>}
        {!collapsed && visible.map((field) => (
          <Field key={field.path.join('.')} descriptor={field} disabled={disabled} filter={filter}
            changedPaths={changedPaths} onRestore={onRestore} onShowHistory={onShowHistory}
            history={history} collapse={collapse} onToggleCollapse={onToggleCollapse}
            onChange={(next) => {
              const path = field.path.slice(descriptor.path.length);
              let node = structuredClone(descriptor.value ?? {});
              let cursor = node;
              for (const key of path.slice(0, -1)) cursor = cursor[key];
              cursor[path.at(-1)] = next;
              onChange(node);
            }} />
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
  return (
    <ScalarField descriptor={descriptor} value={descriptor.value} disabled={disabled}
      changed={changed} onRestore={onRestore} onShowHistory={onShowHistory}
      historyCount={historyCount} onChange={onChange} />
  );
}

export default function SchemaForm({
  fields = [], values, onChange, disabled, filter, baseline, history = {}, onRestore, onToggleCollapse, collapse = {},
}) {
  const [historyTarget, setHistoryTarget] = useState(null);

  const changedPaths = useMemo(() => {
    const changed = new Set();
    if (!baseline) return changed;
    const walk = (list) => {
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

  const showHistory = (descriptor) => setHistoryTarget(descriptor);

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
                    onRestore?.(historyTarget.path, entry.value);
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

export { defaultsFromFields, joinPath };
