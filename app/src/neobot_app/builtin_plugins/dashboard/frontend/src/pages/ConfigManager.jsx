// ConfigManager.jsx —— 本体配置 / 环境变量 / 模型注册 在线管理
import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../api/endpoints.js';
import { toast } from '../components/Toast.jsx';
import Icon from '../components/Icon.jsx';
import SchemaForm from '../components/SchemaForm.jsx';
import { setPath } from '../utils/paths.js';

const TABS = [
  ['config', '本体配置'],
  ['env', '环境变量'],
  ['models', '模型注册'],
];

export default function ConfigManager() {
  const [tab, setTab] = useState('config');
  return (
    <div className="page config-page">
      <div className="config-tabs cfg-top-tabs">
        <div role="tablist" aria-label="配置管理">
          {TABS.map(([key, label]) => (
            <button
              key={key}
              role="tab"
              aria-selected={tab === key}
              className={tab === key ? 'active' : ''}
              onClick={() => setTab(key)}
            >
              {label}
            </button>
          ))}
        </div>
        <span className="muted small">config.toml / .env / 模型注册表</span>
      </div>
      {tab === 'config' && <BotConfigPanel />}
      {tab === 'env' && <EnvPanel />}
      {tab === 'models' && <ModelsPanel />}
    </div>
  );
}

function BotConfigPanel() {
  const [doc, setDoc] = useState(null);
  const [draft, setDraft] = useState({});
  const [source, setSource] = useState('');
  const [mode, setMode] = useState('form');
  const [filter, setFilter] = useState('');
  const [errors, setErrors] = useState([]);
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState('');
  const [loading, setLoading] = useState(true);

  const applyDoc = useCallback((data) => {
    setDoc(data);
    setDraft(data.config || {});
    setSource(data.source || '');
    setErrors([]);
    setNotice(null);
  }, []);

  const read = useCallback(async () => {
    setLoading(true);
    const result = await api.config();
    setLoading(false);
    if (!result.ok) {
      setNotice({ text: result.error || '读取配置失败', warning: true });
      return;
    }
    applyDoc(result.data);
  }, [applyDoc]);

  useEffect(() => {
    read();
  }, [read]);

  const dirty = useMemo(() => {
    if (!doc) return false;
    return mode === 'toml'
      ? source !== doc.source
      : JSON.stringify(draft) !== JSON.stringify(doc.config);
  }, [doc, draft, source, mode]);

  const changeField = useCallback((path, value) => {
    setDraft((previous) => setPath(previous, path, value));
  }, []);

  const validate = async () => {
    setBusy('validate');
    const body = mode === 'toml' ? { source } : { config: draft };
    const result = await api.configValidate(body);
    setBusy('');
    if (result.ok) {
      setErrors([]);
      toast('配置校验通过', 'ok');
    } else {
      setErrors(result.data?.errors || []);
      toast(result.error || '配置校验未通过', 'err');
    }
  };

  const save = async (reload) => {
    if (!doc) return;
    setBusy('save');
    const body = {
      revision: doc.revision,
      mode,
      reload,
      ...(mode === 'toml' ? { source } : { config: draft }),
    };
    const result = await api.configSave(body);
    setBusy('');
    if (!result.ok) {
      if (result.status === 409) {
        setNotice({ text: result.error, warning: true });
        toast('配置已被其它会话修改，请重新读取', 'err');
      } else {
        setErrors(result.data?.errors || []);
        toast(result.error || '保存失败', 'err');
      }
      return;
    }
    applyDoc(result.data);
    setNotice({ text: result.data.message || '配置已保存', warning: !result.data.applied && reload });
    toast(result.data.message || '配置已保存', 'ok');
  };

  const reloadRuntime = async () => {
    setBusy('reload');
    const result = await api.configReload();
    setBusy('');
    if (result.ok) toast(result.data?.message || '配置已重载', 'ok');
    else toast(result.error || '重载失败', 'err');
  };

  const restart = async () => {
    if (!confirm('确认重启 NeoBot？面板会短暂不可用。')) return;
    setBusy('restart');
    const result = await api.restart();
    setBusy('');
    toast(result.ok ? result.data?.message || '已请求重启' : result.error || '重启失败', result.ok ? 'ok' : 'err');
  };

  if (loading && !doc) {
    return <section className="card"><p className="empty muted" role="status">正在读取 config.toml…</p></section>;
  }
  if (!doc) {
    return (
      <section className="card">
        <div className="workspace-error" role="alert">
          {notice?.text || '无法读取配置'}
          <button className="btn-sm" onClick={read}>重试</button>
        </div>
      </section>
    );
  }

  return (
    <section className="card config-card">
      <div className="config-toolbar">
        <div className="config-tabs">
          <div role="tablist" aria-label="编辑方式">
            <button
              role="tab"
              aria-selected={mode === 'form'}
              className={mode === 'form' ? 'active' : ''}
              disabled={!!busy}
              onClick={() => setMode('form')}
            >
              <Icon name="settings" /> 表单
            </button>
            <button
              role="tab"
              aria-selected={mode === 'toml'}
              className={mode === 'toml' ? 'active' : ''}
              disabled={!!busy}
              onClick={() => setMode('toml')}
            >
              <Icon name="code" /> TOML
            </button>
          </div>
        </div>
        {mode === 'form' && (
          <input
            className="input cfg-search"
            placeholder="搜索配置项…"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
          />
        )}
        <div className="spacer" />
        <button className="btn" disabled={!!busy} onClick={validate}>校验</button>
        <button className="btn" disabled={!!busy || !dirty} onClick={() => setDraft(doc.config)}>放弃修改</button>
        <button className="btn" disabled={!!busy} onClick={read}>重新读取</button>
        <button className="btn primary" disabled={!!busy || !dirty} onClick={() => save(true)}>
          <Icon name="save" /> {busy === 'save' ? '保存中…' : '保存并重载'}
        </button>
      </div>

      {notice && (
        <div className={'config-notice' + (notice.warning ? ' warning' : '')} role="status">
          <Icon name={notice.warning ? 'more' : 'check'} />
          {notice.text}
        </div>
      )}
      {errors.length > 0 && (
        <div className="workspace-error" role="alert">
          <strong>校验失败：</strong>
          <ul className="cfg-errors">
            {errors.slice(0, 12).map((item, index) => (
              <li key={index}><code>{item.path || '?'}</code> {item.message}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="config-body">
        {mode === 'form' ? (
          <SchemaForm
            fields={doc.schema || []}
            values={draft}
            disabled={!!busy}
            filter={filter}
            onChange={changeField}
          />
        ) : (
          <>
            <p className="muted small">直接编辑整份 config.toml；保存前会做语法与类型校验，并自动备份旧文件。</p>
            <textarea
              className="toml-editor"
              aria-label="config.toml"
              spellCheck={false}
              disabled={!!busy}
              value={source}
              onChange={(event) => setSource(event.target.value)}
            />
          </>
        )}
      </div>

      <div className="config-footer">
        <span className={dirty ? 'dirty-label' : 'muted'}>
          <i className={'plugin-status-dot' + (dirty ? ' pending' : '')} />
          {dirty ? '有未保存的修改' : '与文件同步'}
        </span>
        <span className="muted small">{doc.path}</span>
        <div className="spacer" />
        <button className="btn" disabled={!!busy} onClick={reloadRuntime}>
          <Icon name="refresh" /> 重载运行时配置
        </button>
        <button className="btn danger" disabled={!!busy} onClick={restart}>重启 NeoBot</button>
      </div>
    </section>
  );
}

function EnvPanel() {
  const [doc, setDoc] = useState(null);
  const [edits, setEdits] = useState({});
  const [deletes, setDeletes] = useState([]);
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');
  const [filter, setFilter] = useState('');
  const [busy, setBusy] = useState('');
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState(null);

  const read = useCallback(async () => {
    setLoading(true);
    const result = await api.env();
    setLoading(false);
    if (!result.ok) {
      setNotice({ text: result.error || '读取 .env 失败', warning: true });
      return;
    }
    setDoc(result.data);
    setEdits({});
    setDeletes([]);
    setNotice(null);
  }, []);

  useEffect(() => {
    read();
  }, [read]);

  const items = doc?.items || [];
  const visible = items.filter((item) => !filter || item.key.toLowerCase().includes(filter.toLowerCase()));
  const dirty = Object.keys(edits).length > 0 || deletes.length > 0;

  const reveal = async (key) => {
    const result = await api.envReveal(key);
    if (!result.ok) {
      toast(result.error || '无法显示该值', 'err');
      return;
    }
    setEdits((previous) => ({ ...previous, [key]: result.data.value }));
    toast('已显示明文（操作已记录日志）', 'info');
  };

  const save = async (reload) => {
    setBusy('save');
    const result = await api.envSave({ updates: edits, deletes, revision: doc?.revision, reload });
    setBusy('');
    if (!result.ok) {
      if (result.status === 409) setNotice({ text: result.error, warning: true });
      toast(result.error || '保存失败', 'err');
      return;
    }
    setDoc(result.data);
    setEdits({});
    setDeletes([]);
    setNotice({ text: result.data.message || '已保存', warning: false });
    toast(result.data.message || '已保存', 'ok');
  };

  const addCustom = () => {
    const key = newKey.trim();
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) {
      toast('环境变量名只能是字母、数字与下划线，且不能以数字开头', 'err');
      return;
    }
    setEdits((previous) => ({ ...previous, [key]: newValue }));
    setNewKey('');
    setNewValue('');
    toast('已加入待保存列表', 'info');
  };

  if (loading && !doc) {
    return <section className="card"><p className="empty muted" role="status">正在读取 .env…</p></section>;
  }

  return (
    <section className="card config-card">
      <div className="config-toolbar">
        <input
          className="input cfg-search"
          placeholder="搜索环境变量…"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
        />
        <div className="spacer" />
        <button className="btn" disabled={!!busy} onClick={read}>重新读取</button>
        <button className="btn primary" disabled={!!busy || !dirty} onClick={() => save(true)}>
          <Icon name="save" /> {busy === 'save' ? '保存中…' : '保存并重载'}
        </button>
      </div>

      {notice && (
        <div className={'config-notice' + (notice.warning ? ' warning' : '')} role="status">
          <Icon name="check" /> {notice.text}
        </div>
      )}

      <p className="muted small">
        平台密钥形如 <code>平台名_URL</code> / <code>平台名_APIKey</code>；自定义平台可直接新增，例如
        <code>MyProvider_URL</code> 与 <code>MyProvider_APIKey</code>。
      </p>

      <div className="env-table">
        <div className="env-row env-head">
          <span>变量</span><span>值</span><span>说明</span><span>操作</span>
        </div>
        {visible.map((item) => {
          const edited = Object.prototype.hasOwnProperty.call(edits, item.key);
          const removed = deletes.includes(item.key);
          const value = edited ? edits[item.key] : item.value;
          return (
            <div className={'env-row' + (removed ? ' removed' : '')} key={item.key}>
              <span className="env-key">
                <code>{item.key}</code>
                {item.builtin && <span className="meta-chip">内置</span>}
                {item.required && <span className="meta-chip update-available">必须</span>}
              </span>
              <span className="env-value">
                <input
                  className="input"
                  type={item.sensitive && !edited ? 'password' : 'text'}
                  value={removed ? '' : value || ''}
                  disabled={removed || !!busy}
                  placeholder={item.has_value ? '' : '未配置'}
                  onChange={(event) => setEdits((previous) => ({ ...previous, [item.key]: event.target.value }))}
                />
              </span>
              <span className="muted small env-desc">{item.description || '—'}</span>
              <span className="env-actions">
                {item.sensitive && item.has_value && (
                  <button className="btn-sm" disabled={!!busy} onClick={() => reveal(item.key)}>显示</button>
                )}
                {item.builtin ? (
                  <span className="muted small">内置</span>
                ) : (
                  <button
                    className="btn-sm danger"
                    disabled={!!busy || removed}
                    onClick={() => {
                      if (!confirm('确认删除 ' + item.key + '？保存后生效。')) return;
                      setDeletes((previous) => [...previous, item.key]);
                    }}
                  >
                    删除
                  </button>
                )}
              </span>
            </div>
          );
        })}
        {visible.length === 0 && <div className="empty muted">没有匹配的环境变量</div>}
      </div>

      <div className="env-add">
        <input
          className="input"
          placeholder="新增变量名，如 MyProvider_URL"
          value={newKey}
          onChange={(event) => setNewKey(event.target.value)}
        />
        <input
          className="input"
          placeholder="值"
          value={newValue}
          onChange={(event) => setNewValue(event.target.value)}
        />
        <button className="btn" onClick={addCustom}><Icon name="plus" /> 添加</button>
      </div>
    </section>
  );
}

function ModelsPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const read = useCallback(async () => {
    setLoading(true);
    const result = await api.configModels();
    setLoading(false);
    if (result.ok) setData(result.data);
  }, []);

  useEffect(() => {
    read();
  }, [read]);

  const models = data?.models || [];
  const platforms = data?.platforms || [];

  return (
    <section className="card config-card">
      <div className="card-head">
        <h3>已注册模型</h3>
        <span className="muted small">{models.length} 个</span>
        <div className="spacer" />
        <button className="btn-sm" onClick={read}>刷新</button>
      </div>
      {loading && !data && <p className="empty muted">正在读取模型注册表…</p>}
      {data && models.length === 0 && <div className="empty muted">当前没有已注册的模型</div>}
      {models.length > 0 && (
        <table className="model-table">
          <thead>
            <tr><th>注册名</th><th>描述</th><th>供应商</th><th>模型</th><th>凭据</th></tr>
          </thead>
          <tbody>
            {models.map((model) => (
              <tr key={model.name}>
                <td><code>{model.name}</code></td>
                <td>{model.description || '—'}</td>
                <td>{model.provider}</td>
                <td>{model.model_name}</td>
                <td>
                  <span className={'tag ' + (model.api_key_configured ? 'ok' : 'err')}>
                    {model.api_key_configured ? 'Key 已配置' : '缺 APIKey'}
                  </span>
                  {!model.base_url_configured && <span className="tag err">缺 URL</span>}
                  {model.native_vision && <span className="tag info">原生视觉</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="card-head">
        <h3>平台凭据</h3>
        <span className="muted small">{platforms.length} 个</span>
      </div>
      {platforms.length === 0 && <div className="empty muted">没有读取到平台配置</div>}
      {platforms.length > 0 && (
        <table className="model-table">
          <thead><tr><th>平台</th><th>URL</th><th>APIKey</th></tr></thead>
          <tbody>
            {platforms.map((platform) => (
              <tr key={platform.name}>
                <td>{platform.name}</td>
                <td className="muted small">{platform.url || '—'}</td>
                <td>
                  <span className={'tag ' + (platform.has_key ? 'ok' : 'err')}>
                    {platform.has_key ? '已配置' : '未配置'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
