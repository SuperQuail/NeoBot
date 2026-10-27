// pages/config/EnvPanel.tsx —— .env 在线编辑（密钥只写不读）
import { useCallback, useEffect, useState } from 'react';
import { api } from '../../api/endpoints';
import type { EnvPayload } from '../../api/types';
import { infoBar, notify } from '../../notifications/infoBar';
import Icon from '../../components/Icon';
import Modal, { ModalActions } from '../../components/Modal';
import Button from '../../components/ui/Button';
import EmptyState from '../../components/ui/EmptyState';
import { PanelSkeleton } from '../../components/ui/PageSkeleton';
import FormField from '../../components/ui/FormField';
import InlineAlert from '../../components/ui/InlineAlert';
import { confirmAction } from '../../components/ui/ConfirmDialog';
import { useConfigAutoRead, useEditorGuard, useEditorOperation } from './shared';
function EnvPanel() {
  const [doc, setDoc] = useState<(EnvPayload & { revision?: number }) | null>(null);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [deletes, setDeletes] = useState<string[]>([]);
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');
  const [filter, setFilter] = useState('');
  const { busy, runOperation } = useEditorOperation();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const read = useCallback(
    () =>
      runOperation('read', async () => {
        setLoading(true);
        let result;
        try {
          result = await api.env();
        } catch (error) {
          setError(error instanceof Error ? error.message : '读取 .env 失败');
          return;
        } finally {
          setLoading(false);
        }
        if (!result.ok || !result.data) {
          setError(result.error || '读取 .env 失败');
          return;
        }
        setDoc(result.data);
        setEdits({});
        setDeletes([]);
        setError('');
      }),
    [runOperation],
  );

  useEffect(() => {
    read();
  }, [read]);

  const items = doc?.items || [];
  const visible = items.filter((item) => !filter || item.key.toLowerCase().includes(filter.toLowerCase()));
  const fileDirty = Object.keys(edits).length > 0 || deletes.length > 0;

  const [adding, setAdding] = useState(false);
  const [platform, setPlatform] = useState({ name: '', url: '', api_key: '' });
  const [platformBaseline, setPlatformBaseline] = useState(platform);
  const dirty =
    fileDirty ||
    !!newKey ||
    !!newValue ||
    (adding && JSON.stringify(platform) !== JSON.stringify(platformBaseline));
  useEditorGuard(dirty, !!busy || loading);
  const invalidateAutoRead = useConfigAutoRead({
    enabled: !dirty && !busy && !loading && !adding,
    identity: doc,
    read: api.env,
    apply: (payload) => {
      setDoc(payload);
      setError('');
    },
    onError: setError,
    fallback: '自动读取环境变量失败',
  });
  const reread = async () => {
    if (
      busy ||
      (dirty &&
        !(await confirmAction({
          title: '重新读取环境变量？',
          description: '当前未保存的环境变量修改会丢失。',
          confirmLabel: '重新读取',
          danger: true,
        })))
    )
      return;
    setNewKey('');
    setNewValue('');
    void read();
  };
  const closePlatform = async () => {
    if (
      busy ||
      (JSON.stringify(platform) !== JSON.stringify(platformBaseline) &&
        !(await confirmAction({
          title: '放弃供应商修改？',
          description: '尚未保存的平台地址与密钥修改会丢失。',
          confirmLabel: '放弃修改',
          danger: true,
        })))
    )
      return;
    setAdding(false);
  };

  const openPlatform = (item?: { name?: string; url?: string } | null) => {
    const next = { name: item?.name || '', url: item?.url || '', api_key: '' };
    setPlatform(next);
    setPlatformBaseline(next);
    setAdding(true);
  };

  const submitPlatform = () =>
    runOperation('platform', async () => {
      const result = await api.envAddPlatform({ ...platform, revision: doc?.revision });
      if (!result.ok || !result.data) {
        notify(result.error || '添加供应商失败', 'err');
        return;
      }
      setDoc(result.data);
      setAdding(false);
      setPlatform({ name: '', url: '', api_key: '' });
      setError('');
      notify('供应商已添加', 'ok');
    });

  const save = (reload: boolean) =>
    runOperation('save', async () => {
      const result = await api.envSave({ updates: edits, deletes, revision: doc?.revision, reload });
      if (!result.ok || !result.data) {
        if (result.status === 409) setError(result.error || '已被其它会话修改');
        else notify(result.error || '保存失败', 'err');
        return;
      }
      setDoc(result.data);
      setEdits({});
      setDeletes([]);
      setError('');
      // 生效范围集中通知；需重启状态与入口保留在固定底栏。
      const needsRestart = result.data.needs_restart === true;
      infoBar({
        title: needsRestart ? '环境变量已保存，部分配置待重启' : '环境变量已保存',
        tone: needsRestart ? 'warn' : 'ok',
        details: result.data.message ? <p>{result.data.message}</p> : undefined,
      });
    });

  const restart = async () => {
    if (
      !(await confirmAction({
        title: '重启 NeoBot？',
        description: '面板会短暂不可用。环境变量里的启动期配置只会在重启后生效。',
        confirmLabel: '重启 NeoBot',
        danger: true,
      }))
    )
      return;
    await runOperation('restart', async () => {
      const result = await api.restart();
      notify(
        result.ok ? result.data?.message || '已请求重启' : result.error || '重启失败',
        result.ok ? 'ok' : 'err',
      );
    });
  };

  const addCustom = () => {
    const key = newKey.trim();
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) {
      notify('环境变量名只能是字母、数字与下划线，且不能以数字开头', 'err');
      return;
    }
    setEdits((previous) => ({ ...previous, [key]: newValue }));
    setNewKey('');
    setNewValue('');
    notify('已加入待保存列表', 'info');
  };

  if (loading && !doc) {
    return <PanelSkeleton className="card" label="正在读取 .env…" rows={5} />;
  }

  return (
    <section
      className="card config-card env-panel"
      onClickCapture={invalidateAutoRead}
      onInputCapture={invalidateAutoRead}
      onChangeCapture={invalidateAutoRead}
    >
      <div className="config-panel-scroll">
        <div className="config-toolbar">
          <input
            className="input cfg-search"
            placeholder="搜索环境变量…"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
          />
          <div className="spacer" />
          <Button disabled={!!busy} onClick={() => openPlatform(null)}>
            <Icon name="plus" /> 一键添加 API 供应商
          </Button>
        </div>

        {error && (
          <InlineAlert
            tone="error"
            title={error}
            actions={
              <Button size="sm" disabled={!!busy} onClick={reread}>
                {doc ? '重新读取' : '重试'}
              </Button>
            }
          />
        )}

        <p className="muted small">
          平台密钥形如 <code>平台名_URL</code> / <code>平台名_APIKey</code>；自定义平台可直接新增，例如
          <code>MyProvider_URL</code> 与 <code>MyProvider_APIKey</code>。
        </p>

        <div className="env-table-scroll">
          <div className="env-table">
            <div className="env-row env-head">
              <span>变量</span>
              <span>值</span>
              <span>说明</span>
              <span>操作</span>
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
                      placeholder={
                        item.sensitive
                          ? item.has_value
                            ? '已设置 · 留空则不修改'
                            : '未设置'
                          : item.has_value
                            ? ''
                            : '未配置'
                      }
                      onChange={(event) =>
                        setEdits((previous) => ({ ...previous, [item.key]: event.target.value }))
                      }
                    />
                    {item.sensitive && (
                      <span className={'tag ' + (item.has_value ? 'ok' : 'err')}>
                        {item.has_value ? '已设置' : '未设置'}
                      </span>
                    )}
                  </span>
                  <span className="muted small env-desc">{item.description || '—'}</span>
                  <span className="env-actions">
                    {item.in_file ? (
                      <Button
                        variant="danger"
                        size="sm"
                        disabled={!!busy || removed}
                        onClick={async () => {
                          if (
                            !(await confirmAction({
                              title: '删除环境变量 ' + item.key + '？',
                              description: '保存后从 .env 删除该变量。',
                              confirmLabel: '删除变量',
                              danger: true,
                            }))
                          )
                            return;
                          setDeletes((previous) => [...previous, item.key]);
                          setEdits((previous) => {
                            const next = { ...previous };
                            delete next[item.key];
                            return next;
                          });
                        }}
                      >
                        删除
                      </Button>
                    ) : (
                      <span className="muted small">未写入 .env</span>
                    )}
                  </span>
                </div>
              );
            })}
            {visible.length === 0 && <EmptyState compact>没有匹配的环境变量</EmptyState>}

            <div className="env-row env-add">
              <input
                className="input"
                placeholder="新增变量名，如 MyProvider_URL"
                value={newKey}
                disabled={!!busy}
                onChange={(event) => setNewKey(event.target.value)}
              />
              <span className="env-value">
                <input
                  className="input"
                  placeholder="值"
                  value={newValue}
                  disabled={!!busy}
                  onChange={(event) => setNewValue(event.target.value)}
                />
              </span>
              <span className="env-desc muted small">添加后统一保存</span>
              <span className="env-actions">
                <Button disabled={!!busy || !newKey.trim()} onClick={addCustom}>
                  <Icon name="plus" /> 添加
                </Button>
              </span>
            </div>
          </div>
        </div>

        <div className="card-head env-platform-heading">
          <h3>API 供应商</h3>
          <span className="muted small">{(doc?.platforms || []).length} 个</span>
          <div className="spacer" />
          <span className="muted small">API Key 只写不读，保存后无法再次查看</span>
        </div>
        {(doc?.platforms || []).length === 0 && (
          <EmptyState compact>还没有平台，点击「一键添加 API 供应商」创建</EmptyState>
        )}
        {(doc?.platforms || []).length > 0 && (
          <div className="config-table-scroll env-platform-scroll">
            <table className="model-table env-platform-table">
              <colgroup>
                <col className="env-platform-name-column" />
                <col />
                <col className="env-platform-key-column" />
                <col className="env-platform-action-column" />
              </colgroup>
              <thead>
                <tr>
                  <th>平台名</th>
                  <th>API 地址</th>
                  <th>API Key</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {(doc?.platforms || []).map((item) => (
                  <tr key={item.name}>
                    <td>
                      <span className="env-key">
                        <code>{item.name}</code>
                        {item.builtin && <span className="meta-chip">内置</span>}
                      </span>
                    </td>
                    <td className="muted small env-platform-url">{item.url || '—'}</td>
                    <td>
                      <span className={'tag ' + (item.has_key ? 'ok' : 'err')}>
                        {item.has_key ? '已设置' : '未设置'}
                      </span>
                    </td>
                    <td>
                      <Button size="sm" disabled={!!busy} onClick={() => openPlatform(item)}>
                        更新 Key
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <div className="config-footer" role="status">
        <span className={dirty || doc?.needs_restart ? 'dirty-label' : 'muted'}>
          <i className={'plugin-status-dot' + (dirty ? ' pending' : '')} />
          {dirty ? '有未保存的修改' : doc?.needs_restart ? '部分配置待重启' : '环境变量与文件同步'}
        </span>
        {!doc?.needs_restart && <span className="muted small">密钥只写不读 · 留空保留原值</span>}
        <div className="spacer" />
        {doc?.needs_restart === true && (
          <Button
            type="button"
            size="sm"
            disabled={!!busy}
            onClick={restart}
            title="这些环境变量在启动时读取，必须重启进程才生效"
          >
            <Icon name="refresh" /> {busy === 'restart' ? '重启中…' : '重启 NeoBot'}
          </Button>
        )}
        <Button variant="primary" disabled={!!busy || !fileDirty} onClick={() => save(true)}>
          <Icon name="save" />
          {busy === 'save' ? '保存中…' : '保存并重载'}
        </Button>
      </div>
      <Modal open={adding} title="添加 / 更新 API 供应商" onClose={closePlatform}>
        <FormField
          label="平台名"
          htmlFor="platform-name"
          description={
            <>
              模型库里的「供应商」填这个名字，会写成 <code>平台名_URL</code> 与 <code>平台名_APIKey</code>
            </>
          }
        >
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
        </FormField>
        <FormField
          label="API 地址"
          htmlFor="platform-url"
          description="以 http:// 或 https:// 开头，例如 https://api.example.com/v1"
        >
          <input
            id="platform-url"
            className="input"
            spellCheck={false}
            disabled={!!busy}
            value={platform.url}
            placeholder="https://api.example.com/v1"
            onChange={(event) => setPlatform({ ...platform, url: event.target.value })}
          />
        </FormField>
        <FormField
          label="API Key"
          htmlFor="platform-key"
          description="只写不读：保存后无法查看，只能覆盖更新；留空则保持原有 Key"
        >
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
        </FormField>
        <ModalActions>
          <Button disabled={!!busy} onClick={closePlatform}>
            取消
          </Button>
          <Button variant="primary" disabled={!!busy} onClick={submitPlatform}>
            <Icon name="save" /> {busy === 'platform' ? '保存中…' : '保存供应商'}
          </Button>
        </ModalActions>
      </Modal>
    </section>
  );
}

export { EnvPanel };
