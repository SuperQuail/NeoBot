// pages/config/EnvPanel.tsx —— .env 在线编辑（密钥只写不读）
import { useCallback, useEffect, useState } from 'react';
import { api } from '../../api/endpoints';
import type { EnvPayload } from '../../api/types';
import { toast } from '../../components/Toast';
import Icon from '../../components/Icon';
import Modal from '../../components/Modal';
import type { Notice } from './shared';
function EnvPanel() {
  const [doc, setDoc] = useState<(EnvPayload & { revision?: number }) | null>(null);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [deletes, setDeletes] = useState<string[]>([]);
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');
  const [filter, setFilter] = useState('');
  const [busy, setBusy] = useState('');
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<Notice | null>(null);

  const read = useCallback(async () => {
    setLoading(true);
    const result = await api.env();
    setLoading(false);
    if (!result.ok || !result.data) {
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

  const [adding, setAdding] = useState(false);
  const [platform, setPlatform] = useState({ name: '', url: '', api_key: '' });

  const openPlatform = (item?: { name?: string; url?: string } | null) => {
    setPlatform({ name: item?.name || '', url: item?.url || '', api_key: '' });
    setAdding(true);
  };

  const submitPlatform = async () => {
    setBusy('platform');
    const result = await api.envAddPlatform({ ...platform, revision: doc?.revision });
    setBusy('');
    if (!result.ok || !result.data) {
      toast(result.error || '添加供应商失败', 'err');
      return;
    }
    setDoc(result.data);
    setAdding(false);
    setPlatform({ name: '', url: '', api_key: '' });
    setNotice({ text: result.data.message || '供应商已添加', warning: false });
    toast('供应商已添加', 'ok');
  };

  const save = async (reload: boolean) => {
    setBusy('save');
    const result = await api.envSave({ updates: edits, deletes, revision: doc?.revision, reload });
    setBusy('');
    if (!result.ok || !result.data) {
      if (result.status === 409) setNotice({ text: result.error || '已被其它会话修改', warning: true });
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
        <button className="btn" disabled={!!busy} onClick={() => openPlatform(null)}>
          <Icon name="plus" /> 一键添加 API 供应商
        </button>
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
                  type={item.sensitive ? 'password' : 'text'}
                  value={removed ? '' : value || ''}
                  disabled={removed || !!busy}
                  autoComplete="new-password"
                  spellCheck={false}
                  placeholder={item.sensitive
                    ? (item.has_value ? '已设置 · 留空则不修改' : '未设置')
                    : (item.has_value ? '' : '未配置')}
                  onChange={(event) => setEdits((previous) => ({ ...previous, [item.key]: event.target.value }))}
                />
              </span>
              <span className="muted small env-desc">{item.description || '—'}</span>
              <span className="env-actions">
                {item.sensitive && (
                  <span className={'tag ' + (item.has_value ? 'ok' : 'err')}>
                    {item.has_value ? '已设置' : '未设置'}
                  </span>
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

      <div className="card-head">
        <h3>API 供应商</h3>
        <span className="muted small">{(doc?.platforms || []).length} 个</span>
        <div className="spacer" />
        <span className="muted small">API Key 只写不读，保存后无法再次查看</span>
      </div>
      {(doc?.platforms || []).length === 0 && (
        <div className="empty muted">还没有平台，点击「一键添加 API 供应商」创建</div>
      )}
      {(doc?.platforms || []).length > 0 && (
        <table className="model-table">
          <thead><tr><th>平台名</th><th>API 地址</th><th>API Key</th><th>操作</th></tr></thead>
          <tbody>
            {(doc?.platforms || []).map((item) => (
              <tr key={item.name}>
                <td>
                  <code>{item.name}</code>
                  {item.builtin && <span className="meta-chip">内置</span>}
                </td>
                <td className="muted small">{item.url || '—'}</td>
                <td>
                  <span className={'tag ' + (item.has_key ? 'ok' : 'err')}>
                    {item.has_key ? '已设置' : '未设置'}
                  </span>
                </td>
                <td>
                  <button className="btn-sm" disabled={!!busy} onClick={() => openPlatform(item)}>
                    更新 Key
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <Modal open={adding} title="添加 / 更新 API 供应商" onClose={() => setAdding(false)}>
        <div className="cfg-row">
          <div className="cfg-label">
            <label htmlFor="platform-name">平台名</label>
            <p>模型库里的「供应商」填这个名字，会写成 <code>平台名_URL</code> 与 <code>平台名_APIKey</code></p>
          </div>
          <div className="cfg-control">
            <input
              id="platform-name"
              className="input"
              data-autofocus
              spellCheck={false}
              disabled={!!busy}
              value={platform.name}
              placeholder="例如 MyProvider"
              onChange={(event) => setPlatform({ ...platform, name: event.target.value })}
            />
          </div>
        </div>
        <div className="cfg-row">
          <div className="cfg-label">
            <label htmlFor="platform-url">API 地址</label>
            <p>以 http:// 或 https:// 开头，例如 https://api.example.com/v1</p>
          </div>
          <div className="cfg-control">
            <input
              id="platform-url"
              className="input"
              spellCheck={false}
              disabled={!!busy}
              value={platform.url}
              placeholder="https://api.example.com/v1"
              onChange={(event) => setPlatform({ ...platform, url: event.target.value })}
            />
          </div>
        </div>
        <div className="cfg-row">
          <div className="cfg-label">
            <label htmlFor="platform-key">API Key</label>
            <p>只写不读：保存后无法查看，只能覆盖更新；留空则保持原有 Key</p>
          </div>
          <div className="cfg-control">
            <input
              id="platform-key"
              className="input"
              type="password"
              autoComplete="new-password"
              spellCheck={false}
              disabled={!!busy}
              value={platform.api_key}
              placeholder="sk-..."
              onChange={(event) => setPlatform({ ...platform, api_key: event.target.value })}
            />
          </div>
        </div>
        <div className="modal-actions">
          <button className="btn" disabled={!!busy} onClick={() => setAdding(false)}>取消</button>
          <button className="btn primary" disabled={!!busy} onClick={submitPlatform}>
            <Icon name="save" /> {busy === 'platform' ? '保存中…' : '保存供应商'}
          </button>
        </div>
      </Modal>
    </section>
  );
}


export { EnvPanel };
