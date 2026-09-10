// pages/config/ModelsPanel.tsx —— 模型库增删改 + 连通性测试 + 供应商模型拉取
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../../api/endpoints';
import type { ModelItem, ModelProbeResult, ModelsPayload } from '../../api/types';
import { toast } from '../../components/Toast';
import Icon from '../../components/Icon';
import Modal from '../../components/Modal';
import SchemaForm, { defaultsFromFields } from '../../components/SchemaForm';
import { setPath } from '../../utils/paths';
import { bindValues } from './shared';
function ModelsPanel() {
  const [data, setData] = useState<ModelsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [editing, setEditing] = useState<{ isNew: boolean; draft: Record<string, any> } | null>(null);
  const [probe, setProbe] = useState<ModelProbeResult | null>(null);
  const [providerModels, setProviderModels] = useState<string[]>([]);
  const [pulledProvider, setPulledProvider] = useState('');
  const [pulling, setPulling] = useState('');
  const pulledRef = useRef('');

  const read = useCallback(async () => {
    setLoading(true);
    const result = await api.configModels();
    setLoading(false);
    if (!result.ok || !result.data) {
      toast(result.error || '读取模型库失败', 'err');
      return;
    }
    setData(result.data);
  }, []);

  useEffect(() => {
    read();
  }, [read]);

  const library = data?.library || [];
  const schema = data?.entry_schema || [];

  const startNew = () => setEditing({ isNew: true, draft: defaultsFromFields(schema) });

  const startEdit = (item: any) => setEditing({ isNew: false, draft: structuredClone(item.entry || {}) });

  const save = async (reload = false) => {
    if (!editing) return;
    setBusy('save');
    const result = await api.modelsLibrarySave({
      action: 'upsert',
      entry: editing.draft,
      revision: data?.revision,
      reload,
    });
    setBusy('');
    if (!result.ok) {
      toast(result.error || '保存模型失败', 'err');
      return;
    }
    if (result.data?.models) setData((prev) => ({ ...(prev || {}), library: result.data?.models }));
    else await read();
    setEditing(null);
    const savedKey = result.data?.saved_key;
    const baseMessage = result.data?.message || (reload ? '模型已保存并重载' : '模型已保存；重载配置后生效');
    toast(savedKey ? baseMessage + '（引用名 ' + savedKey + '）' : baseMessage, 'ok');
  };

  const remove = async (item: any) => {
    if (!confirm('确认从模型库删除 ' + item.key + '？')) return;
    setBusy('delete');
    const result = await api.modelsLibrarySave({
      action: 'delete',
      key: item.key,
      revision: data?.revision,
    });
    setBusy('');
    if (!result.ok) {
      toast(result.error || '删除失败', 'err');
      return;
    }
    if (result.data?.models) setData((prev) => ({ ...(prev || {}), library: result.data?.models }));
    toast('已删除 ' + item.key, 'ok');
  };

  const pullProviderModels = useCallback(async (provider: string, useSystemProxy?: boolean, { silent = false }: { silent?: boolean } = {}) => {
    const name = String(provider || '').trim();
    if (!name) return;
    setPulling(name);
    setPulledProvider(name);
    const result = await api.modelsProviderModels({
      provider: name,
      use_system_proxy: !!useSystemProxy,
    });
    setPulling('');
    const payload = result.data || {};
    if (!result.ok || !payload.ok) {
      // 拉取失败：回落到「该供应商在模型库中用过的模型」（等同于未拉取）
      setProviderModels([]);
      setPulledProvider('');
      if (!silent) toast(payload.message || result.error || '拉取供应商模型列表失败', 'err');
      return;
    }
    setProviderModels(payload.models || []);
    if (!silent) toast('已拉取 ' + (payload.models || []).length + ' 个模型', 'ok');
  }, []);

  const runProbe = async (target: any) => {
    const label = target.key || target.entry?.key || 'draft';
    setBusy('test:' + label);
    const result = await api.modelsTest(target);
    setBusy('');
    const payload = result.data || {};
    if (!result.ok && !payload.message) {
      toast(result.error || '测试失败', 'err');
      return;
    }
    setProbe({
      ...payload,
      key: payload.key || target.key || target.entry?.key || '',
      provider: payload.provider || target.entry?.provider || '',
      model_name: payload.model_name || target.entry?.model_name || '',
    });
  };

  const currentProvider = String(editing?.draft?.provider || '').trim();

  // 未拉取时：只列出「当前供应商在模型库里已用过」的模型名；拉取后：只用拉取到的列表
  const modelNameOptions = useMemo(() => {
    if (pulledProvider && pulledProvider.toLowerCase() === currentProvider.toLowerCase()) {
      return [...new Set(providerModels.filter(Boolean))].sort((a, b) => a.localeCompare(b));
    }
    const names = library
      .filter(
        (item) =>
          String(item.provider || '').trim().toLowerCase() === currentProvider.toLowerCase()
      )
      .map((item) => String(item.model_name || '').trim())
      .filter(Boolean);
    return [...new Set(names)].sort((a, b) => a.localeCompare(b));
  }, [pulledProvider, providerModels, currentProvider, library]);

  // 引用名（key）不进表单：新建时按模型名自动生成，已有条目只读展示
  const fields = useMemo(() => {
    if (!editing) return [];
    return bindValues(schema, editing.draft)
      .filter((field) => field.name !== 'key' && !field.hidden)
      .map((field) => {
        if (field.name === 'provider') return { ...field, options: data?.provider_options || [] };
        if (field.name === 'model_name') return { ...field, options: modelNameOptions };
        if (field.name === 'model_type') return { ...field, options: Object.keys(data?.model_type_labels || {}) };
        return field;
      });
  }, [editing, schema, data, modelNameOptions]);

  // 切换供应商时清掉上一个供应商的拉取结果
  useEffect(() => {
    if (!editing) return;
    if (pulledProvider && pulledProvider.toLowerCase() !== currentProvider.toLowerCase()) {
      setProviderModels([]);
      setPulledProvider('');
    }
  }, [editing, currentProvider, pulledProvider]);

  // 打开编辑器或切换供应商时，自动拉取该供应商的模型列表（失败不阻塞）
  useEffect(() => {
    if (!editing) return;
    const provider = String(editing.draft?.provider || '').trim();
    if (!provider) return;
    const token = provider + '|' + (editing.draft?.use_system_proxy ? '1' : '0');
    if (pulledRef.current === token) return;
    pulledRef.current = token;
    pullProviderModels(provider, editing.draft?.use_system_proxy, { silent: true });
  }, [editing, pullProviderModels]);

  return (
    <section className="card config-card">
      <div className="card-head">
        <h3>模型库</h3>
        <span className="muted small">{library.length} 个模型</span>
        <div className="spacer" />
        <button className="btn-sm" disabled={!!busy} onClick={read}>刷新</button>
        <button className="btn-sm primary" disabled={!!busy || !schema.length} onClick={startNew}>
          <Icon name="plus" /> 新增模型
        </button>
      </div>
      <p className="muted small">
        模型单独存储在 <code>[models.registry]</code>，主对话 / Agent / 视觉 / TTS / 生图只引用 key；
        同一个模型可被多个调用方复用，改一处全局生效。
      </p>
      {loading && !data && <p className="empty muted" role="status">正在读取模型库…</p>}
      {data && library.length === 0 && <div className="empty muted">模型库为空，点击「新增模型」添加</div>}
      {library.length > 0 && (
        <table className="model-table">
          <thead>
            <tr><th>引用名</th><th>类型</th><th>描述</th><th>供应商 / 模型</th><th>状态</th><th>操作</th></tr>
          </thead>
          <tbody>
            {library.map((item) => (
              <tr key={item.key}>
                <td><code>{item.key}</code></td>
                <td><span className="tag info">{item.type_label || item.model_type || '—'}</span></td>
                <td>{item.description || '—'}</td>
                <td>
                  <div>{item.provider}</div>
                  <div className="muted small">{item.model_name}</div>
                </td>
                <td>
                  <span className={'tag ' + (item.key_configured ? 'ok' : 'err')}
                    title={'API Key 来自供应商环境变量 ' + item.provider + '_APIKey，模型本身不保存密钥'}>
                    {item.key_configured ? '供应商 Key 已配置' : '供应商缺 Key'}
                  </span>
                  {!item.url_configured && (
                    <span className="tag err" title={'请在环境变量中配置 ' + item.provider + '_URL'}>
                      供应商缺 URL
                    </span>
                  )}
                  {item.registered && <span className="tag ok">已注册</span>}
                  {item.assigned && <span className="tag info">已引用</span>}
                  {item.native_vision && <span className="tag info">原生视觉</span>}
                  {item.use_system_proxy && <span className="tag info">系统代理</span>}
                </td>
                <td>
                  <button className="btn-sm" disabled={!!busy} onClick={() => startEdit(item)}>编辑</button>
                  <button className="btn-sm" disabled={!!busy} onClick={() => runProbe({ key: item.key })}>
                    {busy === 'test:' + item.key ? '测试中…' : '测试'}
                  </button>
                  <button className="btn-sm danger" disabled={!!busy} onClick={() => remove(item)}>删除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <Modal
        open={!!editing}
        size="wide"
        title={editing?.isNew ? '新增模型' : '编辑模型 ' + (editing?.draft?.key || '')}
        onClose={() => setEditing(null)}
      >
        {editing && (
          <>
            <p className="muted small model-key-hint">
              引用名（key）：
              <code>{editing.draft?.key || '保存时按模型名自动生成'}</code>
              <span className="muted"> · 调用方通过它引用该模型，无需手动填写</span>
            </p>
            <SchemaForm
              fields={fields}
              disabled={!!busy}
              onChange={(path, value) =>
                setEditing((previous) =>
                  previous ? { ...previous, draft: setPath(previous.draft, path, value) } : previous,
                )
              }
            />
            <div className="modal-actions">
              <button className="btn" disabled={!!busy || !editing.draft?.provider}
                onClick={() => pullProviderModels(editing.draft?.provider, editing.draft?.use_system_proxy)}>
                <Icon name="download" /> {pulling ? '拉取中…' : '拉取供应商模型'}
              </button>
              <button className="btn" disabled={!!busy}
                onClick={() => runProbe({ entry: editing.draft, key: editing.draft?.key })}>
                {busy === 'test:' + (editing.draft?.key || 'draft') ? '测试中…' : '测试连通性'}
              </button>
              <button className="btn" disabled={!!busy} onClick={() => setEditing(null)}>取消</button>
              <button className="btn" disabled={!!busy} onClick={() => save(false)}>
                <Icon name="save" /> {busy === 'save' ? '保存中…' : '仅保存'}
              </button>
              <button className="btn primary" disabled={!!busy} onClick={() => save(true)}>
                <Icon name="save" /> {busy === 'save' ? '保存中…' : '保存并重载'}
              </button>
            </div>
          </>
        )}
      </Modal>

      <Modal open={!!probe} size="wide" title="模型连通性测试" onClose={() => setProbe(null)}>
        {probe && (
          <div className="probe-result">
            <p className={'probe-headline ' + (probe.ok ? 'ok' : 'err')}>
              <Icon name={probe.ok ? 'check' : 'more'} /> {probe.message || (probe.ok ? '连接正常' : '测试未通过')}
            </p>
            <table className="model-table">
              <tbody>
                <tr><th>模型</th><td><code>{probe.key || '（未保存草稿）'}</code></td></tr>
                <tr><th>供应商 / 模型名</th><td>{probe.provider || '—'} / <code>{probe.model_name || '—'}</code></td></tr>
                <tr><th>请求地址</th><td className="muted small">{probe.url || '—'}</td></tr>
                <tr><th>代理</th><td>{probe.proxy ? '跟随系统代理' : '直连（不使用代理）'}</td></tr>
                <tr><th>网络可达</th><td>{probe.reachable ? '是' : '否'}</td></tr>
                <tr><th>鉴权</th><td>{probe.authorized ? '通过' : '未通过'}</td></tr>
                <tr>
                  <th>模型是否存在</th>
                  <td>{probe.model_found === true ? '已找到' : probe.model_found === false ? '未在模型列表中' : '未检查'}</td>
                </tr>
                <tr><th>HTTP / 耗时</th><td>{probe.status ?? '—'} / {probe.latency_ms != null ? probe.latency_ms + ' ms' : '—'}</td></tr>
                {probe.detail && <tr><th>详情</th><td className="muted small">{probe.detail}</td></tr>}
              </tbody>
            </table>
            <div className="modal-actions">
              <button className="btn" onClick={() => setProbe(null)}>关闭</button>
            </div>
          </div>
        )}
      </Modal>
    </section>
  );
}


export { ModelsPanel };
