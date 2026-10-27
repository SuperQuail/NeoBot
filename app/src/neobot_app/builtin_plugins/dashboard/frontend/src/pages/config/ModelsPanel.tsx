// pages/config/ModelsPanel.tsx —— 模型库增删改 + 连通性测试 + 供应商模型拉取
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Info } from 'lucide-react';
import { api } from '../../api/endpoints';
import type { FieldDescriptor, ModelItem, ModelProbeResult, ModelsPayload } from '../../api/types';
import { infoBar, notify } from '../../notifications/infoBar';
import Icon from '../../components/Icon';
import Modal, { ModalActions } from '../../components/Modal';
import Button from '../../components/ui/Button';
import EmptyState from '../../components/ui/EmptyState';
import { PanelSkeleton } from '../../components/ui/PageSkeleton';
import { defaultsFromFields } from '../../components/SchemaForm';
import { ConfigTreePanel } from './ConfigTreePanel';
import { setPath } from '../../utils/paths';
import { BillingSection } from './BillingSection';
import ModelProbeDetails from './ModelProbeDetails';
import { bindValues, useConfigAutoRead, useEditorGuard, useEditorOperation } from './shared';
import { confirmAction } from '../../components/ui/ConfirmDialog';

const EMPTY_LIBRARY: ModelItem[] = [];
const EMPTY_SCHEMA: FieldDescriptor[] = [];

/** 列表行上的计费标签：从完整条目里取 billing_script（留空 = 固定计费）。 */
function billingScriptOf(item: ModelItem): string {
  const entry = item.entry as { billing_script?: string } | undefined;
  return String(entry?.billing_script || '').trim();
}

/** 参数目录伪字段（settings.params）里携带的可编辑载荷（spec(4) Part B）。 */
interface ModelParamsPayload {
  enabled_params?: unknown;
  extra_body?: unknown;
  values?: unknown;
}

/**
 * 保存前把伪字段同步回真实配置键：
 * settings.params -> enabled_params / extra_body / 各可选参数值，并删除 params。
 * 未列入目录的参数名不落盘（后端只记 warning 忽略），避免写成未知配置项。
 */
function syncModelParams(entry: Record<string, any>, catalogNames: Set<string>): Record<string, any> {
  const settings = entry?.settings;
  if (!settings || typeof settings !== 'object' || !('params' in settings)) return entry;
  const params = (settings as Record<string, any>).params as ModelParamsPayload | undefined;
  const nextSettings: Record<string, any> = { ...(settings as Record<string, any>) };
  delete nextSettings.params;
  if (params && typeof params === 'object') {
    if (Array.isArray(params.enabled_params)) {
      nextSettings.enabled_params = (params.enabled_params as unknown[])
        .map((name) => String(name))
        .filter(Boolean);
    }
    if (params.extra_body && typeof params.extra_body === 'object') {
      nextSettings.extra_body = params.extra_body;
    }
    const values = params.values;
    if (values && typeof values === 'object' && !Array.isArray(values)) {
      for (const [name, value] of Object.entries(values as Record<string, unknown>)) {
        if (value === undefined) continue;
        if (catalogNames.has(name)) nextSettings[name] = value;
      }
    }
  }
  return { ...entry, settings: nextSettings };
}

function ModelsPanel() {
  const [helpOpen, setHelpOpen] = useState(false);
  const [data, setData] = useState<ModelsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [readError, setReadError] = useState('');
  const [editorError, setEditorError] = useState('');
  const [billingBusy, setBillingBusy] = useState(false);
  const { busy, runOperation } = useEditorOperation();
  const [editing, setEditing] = useState<{
    isNew: boolean;
    draft: Record<string, any>;
    baseline: Record<string, any>;
  } | null>(null);
  const [providerModels, setProviderModels] = useState<string[]>([]);
  const [pulledProvider, setPulledProvider] = useState('');
  const [pulling, setPulling] = useState('');
  const pulledRef = useRef('');
  const pullRequest = useRef(0);
  useEffect(
    () => () => {
      pullRequest.current++;
    },
    [],
  );
  // 模型/凭据变更后仍有组件必须重启才会用新模型（issue #75）：这是**常驻提示**，
  // 不能只用 notify —— 用户可能过一会儿才回来配 NapCat/重启。
  const [restartParts, setRestartParts] = useState<string[]>([]);
  // 模型条目表单与本体配置同款（左树 + 右区）：搜索词与分组折叠状态各自独立
  const [formFilter, setFormFilter] = useState('');
  const [formCollapse, setFormCollapse] = useState<Record<string, boolean>>({});
  const dirty = !!editing && JSON.stringify(editing.draft) !== JSON.stringify(editing.baseline);
  useEditorGuard(dirty, loading || !!busy || billingBusy);
  const invalidateAutoRead = useConfigAutoRead({
    // 打开编辑器时即固定模型库和 revision，包括尚未向父级提交的 JSON/计费草稿。
    enabled: !editing && !busy && !billingBusy && !loading,
    identity: data,
    read: api.configModels,
    apply: (payload) => {
      setData(payload);
      setReadError('');
    },
    onError: setReadError,
    fallback: '自动读取模型库失败',
  });

  const read = useCallback(
    () =>
      runOperation('read', async () => {
        setLoading(true);
        let result;
        try {
          result = await api.configModels();
        } catch (error) {
          setReadError(error instanceof Error ? error.message : '读取模型库失败');
          return;
        } finally {
          setLoading(false);
        }
        if (!result.ok || !result.data) {
          setReadError(result.error || '读取模型库失败');
          return;
        }
        setData(result.data);
        setReadError('');
      }),
    [runOperation],
  );

  useEffect(() => {
    read();
  }, [read]);

  // 兜底：library 必须是数组。后端契约是「视图对象里带 library 数组」，
  // 一旦上游误把对象塞进来，直接渲染会抛 "library.filter is not a function" 整页崩掉
  // （issue #65），这里退化成空列表而不是白屏。
  const library = Array.isArray(data?.library) ? data.library : EMPTY_LIBRARY;
  const schema = Array.isArray(data?.entry_schema) ? data.entry_schema : EMPTY_SCHEMA;

  // 参数目录里的可选参数名（保存时只把目录内的值写回 settings.<name>）
  const catalogNames = useMemo(() => {
    const names = new Set<string>();
    for (const field of schema) {
      if (field.kind !== 'group' || field.name !== 'settings') continue;
      for (const child of field.fields || []) {
        if (child.kind !== 'model_params') continue;
        for (const item of (child.catalog as Array<{ name?: unknown }>) || []) {
          if (item?.name) names.add(String(item.name));
        }
      }
    }
    return names;
  }, [schema]);

  const editingLibraryItem = editing
    ? library.find((item) => item.model_ref && item.model_ref === editing.draft?.model_ref)
    : undefined;

  const startNew = () => {
    const draft = defaultsFromFields(schema);
    setEditing({ isNew: true, draft, baseline: draft });
    pulledRef.current = '';
    setFormFilter('');
    setEditorError('');
  };

  const startEdit = (item: ModelItem) => {
    const draft = structuredClone((item.entry || {}) as Record<string, any>);
    setEditing({ isNew: false, draft, baseline: draft });
    pulledRef.current = '';
    setFormFilter('');
    setEditorError('');
  };
  const closeEditor = async () => {
    if (busy || billingBusy) return;
    if (
      dirty &&
      !(await confirmAction({
        title: '放弃模型修改？',
        description: '尚未保存的模型配置会丢失。',
        confirmLabel: '放弃修改',
        danger: true,
      }))
    )
      return;
    pullRequest.current++;
    setEditing(null);
  };

  const save = (reload = false) =>
    runOperation('save', async () => {
      if (!editing) return;
      const result = await api.modelsLibrarySave({
        action: 'upsert',
        entry: syncModelParams(editing.draft, catalogNames),
        revision: data?.revision,
        reload,
      });
      if (!result.ok) {
        if (result.status === 409) setReadError('模型库版本已变化，请重新读取后继续编辑。');
        setEditorError(
          result.status === 409
            ? '配置已被其他会话修改。请备份当前修改，关闭编辑器后重新读取模型库，再重新编辑。'
            : result.error || '保存模型失败',
        );
        notify(result.error || '保存模型失败', 'err');
        return;
      }
      // 后端的 models 是「模型视图对象」{library, assignments, roles, …}，不是数组；
      // 直接塞进 library 会让随后的 library.filter(...) 抛 TypeError（issue #65）。
      if (result.data?.models?.library) {
        setData((prev) => ({ ...(prev || {}), ...result.data, ...result.data?.models }));
      } else {
        const fresh = await api.configModels();
        if (fresh.ok && fresh.data) setData(fresh.data);
      }
      setEditing(null);
      setRestartParts(result.data?.needs_restart_parts || []);
      const savedRef = result.data?.saved_model_ref;
      const baseMessage =
        result.data?.message || (reload ? '模型已保存并重载' : '模型已保存；重载配置后生效');
      notify(savedRef ? baseMessage + '（引用名 ' + savedRef + '）' : baseMessage, 'ok');
    });

  const remove = async (item: any) => {
    if (
      !(await confirmAction({
        title: '删除模型 ' + item.model_ref + '？',
        description: '仍被调用方引用的模型不能删除。删除后会重载运行配置。',
        confirmLabel: '删除模型',
        danger: true,
      }))
    )
      return;
    await runOperation('delete', async () => {
      const result = await api.modelsLibrarySave({
        action: 'delete',
        model_ref: item.model_ref,
        revision: data?.revision,
        // 删除同样要重载：不重载的话运行期继续持有已删模型的 provider（issue #75）
        reload: true,
      });
      if (!result.ok) {
        notify(result.error || '删除失败', 'err');
        return;
      }
      setRestartParts(result.data?.needs_restart_parts || []);
      if (result.data?.models?.library) {
        setData((prev) => ({ ...(prev || {}), ...result.data, ...result.data?.models }));
      }
      notify('已删除 ' + item.model_ref, 'ok');
    });
  };

  const pullProviderModels = useCallback(
    async (provider: string, useSystemProxy?: boolean, { silent = false }: { silent?: boolean } = {}) => {
      const name = String(provider || '').trim();
      if (!name) return;
      const ticket = ++pullRequest.current;
      setPulling(name);
      setPulledProvider(name);
      let result;
      try {
        result = await api.modelsProviderModels({ provider: name, use_system_proxy: !!useSystemProxy });
      } catch (error) {
        if (ticket !== pullRequest.current) return;
        setProviderModels([]);
        setPulledProvider('');
        if (!silent) notify(error instanceof Error ? error.message : '拉取模型失败', 'err');
        return;
      } finally {
        if (ticket === pullRequest.current) setPulling('');
      }
      if (ticket !== pullRequest.current) return;
      const payload = result.data || {};
      if (!result.ok || !payload.ok) {
        // 拉取失败：回落到「该供应商在模型库中用过的模型」（等同于未拉取）
        setProviderModels([]);
        setPulledProvider('');
        if (!silent) notify(payload.message || result.error || '拉取供应商模型列表失败', 'err');
        return;
      }
      setProviderModels(payload.models || []);
      if (!silent) notify('已拉取 ' + (payload.models || []).length + ' 个模型', 'ok');
    },
    [],
  );

  const runProbe = (target: any) =>
    runOperation('test:' + (target.model_ref || target.entry?.model_ref || 'draft'), async () => {
      const result = await api.modelsTest(target);
      const payload = result.data || {};
      if (!result.ok && !payload.message) {
        notify(result.error || '测试失败', 'err');
        return;
      }
      const probe: ModelProbeResult = {
        ...payload,
        model_ref: payload.model_ref || target.model_ref || target.entry?.model_ref || '',
        provider: payload.provider || target.entry?.provider || '',
        model_name: payload.model_name || target.entry?.model_name || '',
      };
      infoBar({
        title: probe.ok ? '模型连接正常' : '模型测试未通过',
        tone: probe.ok ? 'ok' : 'err',
        message: probe.model_ref || probe.model_name || '未保存的模型草稿',
        details: <ModelProbeDetails probe={probe} />,
      });
    });

  const currentProvider = String(editing?.draft?.provider || '').trim();

  // 未拉取时：只列出「当前供应商在模型库里已用过」的模型名；拉取后：只用拉取到的列表
  const modelNameOptions = useMemo(() => {
    if (pulledProvider && pulledProvider.toLowerCase() === currentProvider.toLowerCase()) {
      return [...new Set(providerModels.filter(Boolean))].sort((a, b) => a.localeCompare(b));
    }
    const names = library
      .filter(
        (item) =>
          String(item.provider || '')
            .trim()
            .toLowerCase() === currentProvider.toLowerCase(),
      )
      .map((item) => String(item.model_name || '').trim())
      .filter(Boolean);
    return [...new Set(names)].sort((a, b) => a.localeCompare(b));
  }, [pulledProvider, providerModels, currentProvider, library]);

  // 引用名（key）不进表单：新建时按模型名自动生成，已有条目只读展示。
  // billing_script / billing_config 也不进通用表单：它们由下面的「计费」区专用控件编辑
  // （脚本是下拉而不是自由文本，且带试算按钮）。
  const fields = useMemo(() => {
    if (!editing) return [];
    return bindValues(schema, editing.draft)
      .filter(
        (field) =>
          field.name !== 'model_ref' &&
          field.name !== 'billing_script' &&
          field.name !== 'billing_config' &&
          !field.hidden,
      )
      .map((field) => {
        if (field.name === 'provider') return { ...field, options: data?.provider_options || [] };
        if (field.name === 'model_name') return { ...field, options: modelNameOptions };
        if (field.name === 'model_type')
          return { ...field, options: Object.keys(data?.model_type_labels || {}) };
        return field;
      });
  }, [editing, schema, data, modelNameOptions]);

  // 切换供应商时清掉上一个供应商的拉取结果
  useEffect(() => {
    if (!editing) return;
    if (pulledProvider && pulledProvider.toLowerCase() !== currentProvider.toLowerCase()) {
      pullRequest.current++;
      setPulling('');
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
    <section
      className="card config-card model-library-panel"
      onClickCapture={invalidateAutoRead}
      onInputCapture={invalidateAutoRead}
      onChangeCapture={invalidateAutoRead}
    >
      <div className="config-panel-scroll">
        <div className="card-head model-library-heading">
          <h3>模型库</h3>
          <span className="muted small">{library.length} 个模型</span>
          <div className="spacer" />
          <Button variant="ghost" size="sm" onClick={() => setHelpOpen(true)} aria-label="模型库说明">
            <Info size={15} aria-hidden="true" /> 说明
          </Button>
          <Button variant="primary" size="sm" disabled={!!busy || !schema.length} onClick={startNew}>
            <Icon name="plus" /> 新增模型
          </Button>
        </div>
        {restartParts.length > 0 && (
          <p className="config-notice warning" role="status">
            <Icon name="more" /> 模型/密钥已生效，但以下部分<b>需要重启进程</b>后才会用新模型：
            {restartParts.join('、')}
          </p>
        )}
        {readError && (
          <div className="workspace-error" role="alert">
            {readError}
            <Button size="sm" disabled={!!busy || billingBusy} onClick={read}>
              重试
            </Button>
          </div>
        )}
        {loading && !data && <PanelSkeleton label="正在读取模型库…" kind="list" rows={5} />}
        {data && library.length === 0 && <EmptyState compact>模型库为空，点击「新增模型」添加</EmptyState>}
        {library.length > 0 && (
          <div className="config-table-scroll">
            <table className="model-table model-library-table">
              <thead>
                <tr>
                  <th>模型</th>
                  <th>供应商 / 型号</th>
                  <th>运行与计费</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {library.map((item) => (
                  <tr key={item.model_ref}>
                    <td className="model-library-name">
                      <div className="model-library-title">
                        <strong>{item.display_name || item.model_ref}</strong>
                        <span className="model-library-type">
                          {item.type_label || item.model_type || '—'}
                        </span>
                      </div>
                      <code>{item.model_ref}</code>
                      {(item.native_vision || item.use_system_proxy) && (
                        <span className="model-library-capabilities">
                          {[item.native_vision && '原生视觉', item.use_system_proxy && '系统代理']
                            .filter(Boolean)
                            .join(' · ')}
                        </span>
                      )}
                    </td>
                    <td>
                      <strong className="model-library-provider">{item.provider || '未指定供应商'}</strong>
                      <code className="model-library-model">{item.model_name || '—'}</code>
                    </td>
                    <td className="model-library-status">
                      <div className="model-library-state-line">
                        <span className={'model-library-registration' + (item.registered ? ' is-ready' : '')}>
                          <i aria-hidden="true" />
                          {item.registered === true
                            ? '已注册'
                            : item.registered === false
                              ? '未注册'
                              : '注册待确认'}
                        </span>
                        <span>{item.assigned ? '已引用' : '未引用'}</span>
                      </div>
                      <div className="model-library-status-detail">
                        <span
                          className={item.api_key_configured === false ? 'model-library-warning' : undefined}
                          title={'密钥在环境变量 ' + item.provider + '_APIKey 中管理'}
                        >
                          {item.api_key_configured === true
                            ? '密钥已配置'
                            : item.api_key_configured === false
                              ? '缺少密钥'
                              : '密钥待确认'}
                        </span>
                        {item.url_configured === false && (
                          <span className="model-library-warning">缺少地址</span>
                        )}
                        <span
                          title={
                            billingScriptOf(item) ? '计价脚本：' + billingScriptOf(item) : '按模型价格表计费'
                          }
                        >
                          {billingScriptOf(item) ? '脚本：' + billingScriptOf(item) : '固定计费'}
                        </span>
                      </div>
                    </td>
                    <td>
                      <div className="model-library-actions">
                        <Button size="sm" disabled={!!busy || billingBusy} onClick={() => startEdit(item)}>
                          编辑
                        </Button>
                        <Button
                          size="sm"
                          disabled={!!busy || billingBusy}
                          onClick={() => runProbe({ model_ref: item.model_ref })}
                        >
                          {busy === 'test:' + item.model_ref ? '测试中…' : '测试'}
                        </Button>
                        <Button
                          variant="danger"
                          size="sm"
                          disabled={!!busy || billingBusy}
                          onClick={() => remove(item)}
                        >
                          删除
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <Modal open={helpOpen} title="模型库说明" onClose={() => setHelpOpen(false)}>
        <p>
          在「模型分配」中将模型用于对话、推理、视觉或创作。同一个模型可以被多个用途复用，修改后会一起更新。
        </p>
        <p className="muted small">
          供应商密钥在「环境变量」中管理；已注册表示运行时已加载，连通性可通过「测试」确认。
        </p>
      </Modal>
      <Modal
        open={!!editing}
        size="wide"
        title={editing?.isNew ? '新增模型' : '编辑模型 ' + (editing?.draft?.model_ref || '')}
        onClose={() => {
          void closeEditor();
        }}
      >
        {editing && (
          <>
            {editorError && (
              <div className="workspace-error" role="alert">
                {editorError}
              </div>
            )}
            <p className="muted small model-key-hint">
              引用名（model_ref）：
              <code>{editing.draft?.model_ref || '保存时按模型名自动生成'}</code>
              <span className="muted"> · 调用方通过它引用该模型，无需手动填写</span>
            </p>
            {editingLibraryItem?.params_inferred && (
              <p className="config-notice warning" role="status">
                <Icon name="more" />
                已按旧配置推断本模型启用的可选参数（值 ≠ 默认值视为已启用），请复核参数区后保存。
              </p>
            )}
            {/* 与「本体配置」同款表单（左树定位 + 右区渲染），不再用旧的嵌套折叠样式 */}
            <div className="config-toolbar">
              <input
                className="input cfg-search"
                placeholder="搜索模型字段（支持路径与说明）…"
                value={formFilter}
                onChange={(event) => setFormFilter(event.target.value)}
              />
            </div>
            <ConfigTreePanel
              schema={fields}
              draft={editing.draft}
              baseline={
                editing.isNew ? undefined : (editingLibraryItem?.entry as Record<string, any> | undefined)
              }
              history={{}}
              collapse={formCollapse}
              disabled={!!busy || billingBusy}
              filter={formFilter}
              onFilterChange={setFormFilter}
              onChange={(path, value) =>
                setEditing((previous) =>
                  previous ? { ...previous, draft: setPath(previous.draft, path, value) } : previous,
                )
              }
              onToggleCollapse={(key) =>
                setFormCollapse((previous) => ({ ...previous, [key]: !previous[key] }))
              }
            />
            <BillingSection
              onBusyChange={setBillingBusy}
              modelKey={editing.draft?.model_ref}
              script={String(editing.draft?.billing_script || '')}
              config={(editing.draft?.billing_config || {}) as Record<string, unknown>}
              disabled={!!busy || billingBusy}
              onChangeScript={(value) =>
                setEditing((previous) =>
                  previous ? { ...previous, draft: { ...previous.draft, billing_script: value } } : previous,
                )
              }
              onChangeConfig={(value) =>
                setEditing((previous) =>
                  previous ? { ...previous, draft: { ...previous.draft, billing_config: value } } : previous,
                )
              }
            />
            <ModalActions>
              <Button
                disabled={!!busy || !editing.draft?.provider}
                onClick={() => pullProviderModels(editing.draft?.provider, editing.draft?.use_system_proxy)}
              >
                <Icon name="download" /> {pulling ? '拉取中…' : '拉取供应商模型'}
              </Button>
              <Button
                disabled={!!busy || billingBusy}
                onClick={() => runProbe({ entry: editing.draft, model_ref: editing.draft?.model_ref })}
              >
                {busy === 'test:' + (editing.draft?.model_ref || 'draft') ? '测试中…' : '测试连通性'}
              </Button>
              <Button
                disabled={!!busy || billingBusy}
                onClick={() => {
                  void closeEditor();
                }}
              >
                取消
              </Button>
              <Button disabled={!!busy || billingBusy} onClick={() => save(false)}>
                <Icon name="save" /> {busy === 'save' ? '保存中…' : '仅保存'}
              </Button>
              <Button variant="primary" disabled={!!busy || billingBusy} onClick={() => save(true)}>
                <Icon name="save" /> {busy === 'save' ? '保存中…' : '保存并重载'}
              </Button>
            </ModalActions>
          </>
        )}
      </Modal>
    </section>
  );
}

export { ModelsPanel };
