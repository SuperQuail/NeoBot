// components/schema/ModelParamsField.tsx —— 模型参数三段式（spec(4) Part B）
//
// 后端把参数目录内嵌在 kind=model_params 的伪字段里（settings 组末尾），
// 模型库面板与本体配置页共用同一份 schema，因此这里只需要消费描述符：
//   ① 基础参数（常显，不可移除，仍在 settings 组里编辑）
//   ② 已添加参数（enabled_params 里的每项一支，可改值、可移除）
//   ③ 添加参数（按 scope 过滤的候选项） + 添加自定义参数（extra_body 键值行）
//
// 移除只从 enabled_params 删名，不删配置里的值（值已保留，重新添加即恢复）。
// 未知参数 / 不适用的参数渲染成警告行，绝不静默隐藏。
import { useMemo, useState } from 'react';
import type { FieldDescriptor } from '../../api/types';
import type { FieldCallbacks } from './fieldTypes';

interface ParamScope {
  providers?: string[];
  model_types?: string[];
}

interface ParamEntry {
  name: string;
  group?: string;
  label?: string;
  description?: string;
  type?: string;
  default?: unknown;
  options?: string[];
  scope?: ParamScope;
}

interface ParamsValue {
  enabled_params: string[];
  extra_body: Record<string, unknown>;
  values: Record<string, unknown>;
}

const GROUP_LABELS: Record<string, string> = {
  openai: 'OpenAI 兼容',
  deepseek: 'DeepSeek',
  image: '生图',
  custom: '自定义',
};

const GROUP_TAGS: Record<string, string> = {
  openai: 'info',
  deepseek: 'info',
  image: 'info',
  custom: '',
};

/** provider 归一（与后端 _normalize_provider_kind 同判据） */
function normalizeProvider(value: unknown): string {
  const text = String(value ?? '').trim().toLowerCase().replace(/-/g, '_');
  if (text === 'anthropic') return 'anthropic';
  if (text === 'deepseek' || text === 'deepseek_offical' || text === 'deepseek_official') return 'deepseek';
  if (text === 'openai') return 'openai';
  return 'openai';
}

/** model_type 归一（与后端 normalize_model_type 同判据） */
function normalizeModelType(value: unknown): string {
  return String(value ?? '').trim().toLowerCase() || 'chat';
}

function scopeApplies(entry: ParamEntry, provider: unknown, modelType: unknown): boolean {
  const scope = entry.scope;
  if (!scope || typeof scope !== 'object') return true;
  const providers = Array.isArray(scope.providers) ? scope.providers : [];
  if (providers.length && !providers.some((item) => normalizeProvider(item) === normalizeProvider(provider))) {
    return false;
  }
  const types = Array.isArray(scope.model_types) ? scope.model_types : [];
  if (types.length && !types.some((item) => normalizeModelType(item) === normalizeModelType(modelType))) {
    return false;
  }
  return true;
}

function toText(value: unknown): string {
  if (value === undefined || value === null) return '';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function paramsValue(descriptor: FieldDescriptor, value: unknown): ParamsValue {
  const raw = (value && typeof value === 'object' ? value : {}) as Partial<ParamsValue>;
  const fallbackEnabled = Array.isArray(descriptor.enabled_params)
    ? (descriptor.enabled_params as unknown[]).map(String)
    : [];
  const fallbackExtra =
    descriptor.extra_body && typeof descriptor.extra_body === 'object'
      ? (descriptor.extra_body as Record<string, unknown>)
      : {};
  return {
    enabled_params: Array.isArray(raw.enabled_params) ? raw.enabled_params.map(String) : fallbackEnabled,
    extra_body:
      raw.extra_body && typeof raw.extra_body === 'object'
        ? (raw.extra_body as Record<string, unknown>)
        : fallbackExtra,
    values: raw.values && typeof raw.values === 'object' ? (raw.values as Record<string, unknown>) : {},
  };
}

function parseJsonValue(text: string): { ok: true; value: unknown } | { ok: false } {
  try {
    return { ok: true, value: JSON.parse(text) };
  } catch {
    return { ok: false };
  }
}

function ModelParamsField({
  descriptor,
  value,
  onChange,
  disabled,
}: { descriptor: FieldDescriptor } & FieldCallbacks) {
  const catalog = useMemo(
    () => (Array.isArray(descriptor.catalog) ? (descriptor.catalog as ParamEntry[]) : []),
    [descriptor.catalog],
  );
  const current = paramsValue(descriptor, value);
  const provider = descriptor.provider;
  const modelType = descriptor.model_type;
  const [pending, setPending] = useState('');
  const [customKey, setCustomKey] = useState('');
  const [customValue, setCustomValue] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [drafts, setDrafts] = useState<Record<string, string>>({});

  const byName = useMemo(() => {
    const map = new Map<string, ParamEntry>();
    for (const entry of catalog) map.set(String(entry.name), entry);
    return map;
  }, [catalog]);

  const enabled = current.enabled_params;
  const extraEntries = Object.entries(current.extra_body || {});
  const baseNames = Array.isArray(descriptor.base_param_names)
    ? (descriptor.base_param_names as unknown[]).map(String)
    : [];

  const emit = (next: ParamsValue) => onChange(next);

  const setEnabled = (names: string[]) => emit({ ...current, enabled_params: names });
  const setParamValue = (name: string, next: unknown) =>
    emit({ ...current, values: { ...current.values, [name]: next } });
  const setExtraBody = (next: Record<string, unknown>) => emit({ ...current, extra_body: next });

  const warnings = useMemo(() => {
    const list: Array<{ name: string; label: string; hint: string }> = [];
    const declaredUnknown = Array.isArray(descriptor.unknown_params)
      ? (descriptor.unknown_params as unknown[]).map(String)
      : [];
    const declaredInapplicable = Array.isArray(descriptor.inapplicable_params)
      ? (descriptor.inapplicable_params as unknown[]).map(String)
      : [];
    for (const name of enabled) {
      const entry = byName.get(name);
      if (!entry) {
        list.push({ name, label: name, hint: '不在参数目录中（未知参数不会下发，请改用自定义参数）' });
        continue;
      }
      if (!scopeApplies(entry, provider, modelType)) {
        list.push({ name, label: entry.label || name, hint: '当前模型不适用，不会下发到请求体' });
      }
    }
    for (const name of declaredUnknown) {
      if (!list.some((item) => item.name === name)) {
        list.push({ name, label: name, hint: '不在参数目录中（未知参数不会下发）' });
      }
    }
    for (const name of declaredInapplicable) {
      if (!list.some((item) => item.name === name)) {
        const entry = byName.get(name);
        list.push({ name, label: entry?.label || name, hint: '当前模型不适用，不会下发到请求体' });
      }
    }
    return list;
  }, [enabled, byName, provider, modelType, descriptor.unknown_params, descriptor.inapplicable_params]);

  const candidates = useMemo(() => {
    const taken = new Set(enabled);
    return catalog.filter(
      (entry) => !taken.has(String(entry.name)) && scopeApplies(entry, provider, modelType),
    );
  }, [catalog, enabled, provider, modelType]);

  const grouped = useMemo(() => {
    const map = new Map<string, ParamEntry[]>();
    for (const entry of candidates) {
      const group = String(entry.group || 'custom');
      const list = map.get(group) || [];
      list.push(entry);
      map.set(group, list);
    }
    return [...map.entries()];
  }, [candidates]);

  const addPending = () => {
    const name = pending.trim();
    if (!name) return;
    setError('');
    setNotice('');
    // 一次 emit 同时写 enabled_params 与参数值（分两次会互相覆盖）
    const entry = byName.get(name);
    const nextValues =
      entry && current.values[name] === undefined
        ? { ...current.values, [name]: entry.default }
        : current.values;
    emit({ ...current, enabled_params: [...enabled, name], values: nextValues });
    setPending('');
  };

  const removeParam = (name: string) => {
    setError('');
    setEnabled(enabled.filter((item) => item !== name));
    setNotice('已从启用清单移除「' + name + '」：值已保留，重新添加即恢复。');
  };

  const addCustom = () => {
    const key = customKey.trim();
    if (!key) return;
    if (key.startsWith('__')) {
      setError('自定义参数键名不得以 __ 开头（内部命名空间）');
      return;
    }
    if (Object.prototype.hasOwnProperty.call(current.extra_body, key)) {
      setError('自定义参数「' + key + '」已存在');
      return;
    }
    const parsed = parseJsonValue(customValue);
    if (!parsed.ok) {
      setError('自定义参数值必须是合法 JSON（字符串需带引号，如 "high"）');
      return;
    }
    setError('');
    setNotice('');
    setExtraBody({ ...current.extra_body, [key]: parsed.value });
    setCustomKey('');
    setCustomValue('');
  };

  const commitExtraValue = (key: string, text: string) => {
    setDrafts((previous) => ({ ...previous, ['extra:' + key]: text }));
    const parsed = parseJsonValue(text);
    if (!parsed.ok) {
      setError('自定义参数「' + key + '」的值必须是合法 JSON（字符串需带引号）');
      return;
    }
    setError('');
    setExtraBody({ ...current.extra_body, [key]: parsed.value });
  };

  const commitParamText = (name: string, entry: ParamEntry, text: string) => {
    setDrafts((previous) => ({ ...previous, [name]: text }));
    const type = entry.type;
    if (type === 'int' || type === 'float') {
      if (text.trim() === '' || !Number.isFinite(Number(text))) {
        setError('参数「' + (entry.label || name) + '」需要数值');
        return;
      }
      setError('');
      setParamValue(name, type === 'int' ? Math.trunc(Number(text)) : Number(text));
      return;
    }
    setError('');
    setParamValue(name, text);
  };

  const renderParamControl = (entry: ParamEntry) => {
    const name = String(entry.name);
    const options = Array.isArray(entry.options) ? entry.options : [];
    if (options.length) {
      return (
        <select
          className="input"
          disabled={!!disabled}
          value={toText(current.values[name] ?? entry.default)}
          onChange={(event) => setParamValue(name, event.target.value)}
        >
          {options.map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
      );
    }
    const type = entry.type;
    const text = drafts[name] ?? toText(current.values[name] ?? entry.default);
    return (
      <input
        className="input"
        type={type === 'int' || type === 'float' ? 'number' : 'text'}
        step={type === 'float' ? 'any' : undefined}
        disabled={!!disabled}
        value={text}
        onChange={(event) => commitParamText(name, entry, event.target.value)}
        onBlur={() =>
          setDrafts((previous) => {
            const next = { ...previous };
            delete next[name];
            return next;
          })
        }
      />
    );
  };

  return (
    <section className="cfg-group model-params">
      <div className="cfg-section-heading">
        <h3>{String(descriptor.label || descriptor.name || '模型参数')}</h3>
        <span className="muted small">{enabled.length} 项已添加</span>
      </div>
      {descriptor.description && <p className="muted small cfg-hint">{String(descriptor.description)}</p>}

      <div className="cfg-row model-params-base">
        <div className="cfg-label"><span>基础参数（常显）</span></div>
        <div className="cfg-control">
          <div className="model-params-tags">
            {baseNames.map((name) => (
              <span className="tag" key={name}>{name}</span>
            ))}
          </div>
          <p className="muted small cfg-hint">基础参数始终下发，不在此处增删（在上方设置组里编辑）。</p>
        </div>
      </div>

      {warnings.map((item) => (
        <p className="field-error model-params-warning" role="alert" key={'warn:' + item.name}>
          {item.label}（{item.name}）：已配置，但{item.hint}
        </p>
      ))}

      {notice && <p className="muted small" role="status">{notice}</p>}
      {error && <p className="field-error" role="alert">{error}</p>}

      <div className="cfg-row">
        <div className="cfg-label"><span>已添加参数</span></div>
        <div className="cfg-control">
          {enabled.length === 0 && <p className="muted small">还没有添加可选参数；未添加的可选参数不会下发到请求体。</p>}
          {enabled.map((name) => {
            const entry = byName.get(name);
            return (
              <div className="model-params-row" key={'param:' + name}>
                <span className={'tag ' + (entry ? GROUP_TAGS[String(entry.group || '')] || 'info' : 'err')}>
                  {entry ? GROUP_LABELS[String(entry.group || '')] || String(entry.group || '参数') : '未知'}
                </span>
                <span className="model-params-name">{entry?.label || name}</span>
                {entry ? renderParamControl(entry) : <span className="muted small">不在参数目录中</span>}
                <button
                  type="button"
                  className="icon-btn danger"
                  title="移除（只从启用清单删名，值保留）"
                  disabled={!!disabled}
                  onClick={() => removeParam(name)}
                >
                  移除
                </button>
              </div>
            );
          })}
          {extraEntries.map(([key, item]) => (
            <div className="model-params-row" key={'extra:' + key}>
              <span className="tag">自定义</span>
              <span className="model-params-name">{key}</span>
              <input
                className="input"
                type="text"
                disabled={!!disabled}
                value={drafts['extra:' + key] ?? toText(item)}
                onChange={(event) => commitExtraValue(key, event.target.value)}
                onBlur={() =>
                  setDrafts((previous) => {
                    const next = { ...previous };
                    delete next['extra:' + key];
                    return next;
                  })
                }
              />
              <button
                type="button"
                className="icon-btn danger"
                title="删除自定义参数"
                disabled={!!disabled}
                onClick={() => {
                  const next = { ...current.extra_body };
                  delete next[key];
                  setExtraBody(next);
                }}
              >
                移除
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="cfg-row">
        <div className="cfg-label"><span>添加参数</span></div>
        <div className="cfg-control model-params-add">
          <select
            className="input"
            disabled={!!disabled || candidates.length === 0}
            value={pending}
            onChange={(event) => setPending(event.target.value)}
          >
            <option value="">{candidates.length ? '选择要添加的参数…' : '当前模型没有可添加的可选参数'}</option>
            {grouped.map(([group, entries]) => (
              <optgroup key={group} label={GROUP_LABELS[group] || group}>
                {entries.map((entry) => (
                  <option key={String(entry.name)} value={String(entry.name)}>
                    {entry.label || entry.name}（{entry.name}）
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
          <button type="button" className="btn-sm" disabled={!!disabled || !pending} onClick={addPending}>
            添加
          </button>
          <span className="muted small">候选按当前模型的 model_type / provider 过滤（归一化后比较）</span>
        </div>
      </div>

      <div className="cfg-row">
        <div className="cfg-label"><span>添加自定义参数</span></div>
        <div className="cfg-control model-params-add">
          <input
            className="input"
            type="text"
            placeholder="键名（如 top_k，不得以 __ 开头）"
            disabled={!!disabled}
            value={customKey}
            onChange={(event) => setCustomKey(event.target.value)}
          />
          <input
            className="input"
            type="text"
            placeholder={'值（JSON，如 40 或 "high"）'}
            disabled={!!disabled}
            value={customValue}
            onChange={(event) => setCustomValue(event.target.value)}
          />
          <button
            type="button"
            className="btn-sm"
            disabled={!!disabled || !customKey.trim()}
            onClick={addCustom}
          >
            添加自定义
          </button>
          <span className="muted small">
            原样并入请求体（聊天进聊天请求体、生图进生图 payload）；与标准参数重名时标准参数优先。
          </span>
        </div>
      </div>

    </section>
  );
}

export default ModelParamsField;
