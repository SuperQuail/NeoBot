// pages/config/AssignPanel.tsx —— 把主对话 / Agent / 视觉 / TTS / 生图改绑到模型库 key
import { useCallback, useEffect, useState } from 'react';
import { api } from '../../api/endpoints';
import type { ModelsPayload } from '../../api/types';
import { toast } from '../../components/Toast';
import Icon from '../../components/Icon';
import type { AssignDraft } from './shared';
function AssignPanel() {
  const [data, setData] = useState<ModelsPayload | null>(null);
  const [draft, setDraft] = useState<AssignDraft>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');

  const applyData = useCallback((payload: ModelsPayload) => {
    setData(payload);
    const roles = payload?.assignments?.roles || {};
    setDraft({
      ...roles,
      creator_image_models: [...(payload?.assignments?.creator_image_models || [])],
    });
  }, []);

  const read = useCallback(async () => {
    setLoading(true);
    const result = await api.configModels();
    setLoading(false);
    if (!result.ok || !result.data) {
      toast(result.error || '读取模型分配失败', 'err');
      return;
    }
    applyData(result.data);
  }, [applyData]);

  useEffect(() => {
    read();
  }, [read]);

  const library = data?.library || [];
  const roles = data?.roles_meta || [];

  const labelOf = (key: string) => {
    const item = library.find((entry) => entry.key === key);
    if (!item) return key + '（模型库中不存在）';
    const type = item.type_label ? '[' + item.type_label + '] ' : '';
    return type + item.key + ' · ' + (item.description || item.model_name || item.provider);
  };

  /** 与该角色类型匹配的模型排在前面，其余仍可选。 */
  const sortedLibrary = (role: string) => {
    const expected = data?.role_model_types?.[role] || '';
    return [...library].sort((left, right) => {
      const leftMatch = left.model_type === expected ? 0 : 1;
      const rightMatch = right.model_type === expected ? 0 : 1;
      if (leftMatch !== rightMatch) return leftMatch - rightMatch;
      return String(left.key).localeCompare(String(right.key));
    });
  };

  const save = async () => {
    setBusy('save');
    const result = await api.modelsAssignmentsSave({
      assignments: draft,
      revision: data?.revision,
    });
    setBusy('');
    if (!result.ok) {
      toast(result.error || '保存失败', 'err');
      return;
    }
    if (result.data?.models) setData((prev) => ({ ...(prev || {}), library: result.data?.models }));
    toast('模型分配已保存；重载配置后生效', 'ok');
  };

  if (loading && !data) {
    return <section className="card"><p className="empty muted" role="status">正在读取模型分配…</p></section>;
  }

  return (
    <section className="card config-card">
      <div className="card-head">
        <h3>模型分配</h3>
        <span className="muted small">{library.length} 个可选模型</span>
        <div className="spacer" />
        <button className="btn-sm" disabled={!!busy} onClick={read}>重新读取</button>
        <button className="btn-sm primary" disabled={!!busy} onClick={save}>
          <Icon name="save" /> {busy === 'save' ? '保存中…' : '保存分配'}
        </button>
      </div>
      <p className="muted small">每个调用方只保存一个模型 key；生图模型可多选，Agent 会按模型描述自行选择供应商。</p>

      <div className="assign-grid">
        {roles.map((meta) => (
          <div className="assign-row" key={meta.role}>
            <div className="assign-label">
              <strong>{meta.label}</strong>
              <code className="muted small">{meta.role}</code>
              {meta.model_type_label && <span className="tag info">{meta.model_type_label}</span>}
              {meta.required && <span className="meta-chip update-available">必须</span>}
            </div>
            <div className="assign-control">
              {meta.multi ? (
                <div className="assign-choices">
                  {library.length === 0 && <span className="muted small">模型库为空</span>}
                  {sortedLibrary(meta.role).map((item) => {
                    const checked = (draft.creator_image_models || []).includes(String(item.key || ""));
                    return (
                      <label className="assign-choice" key={item.key}>
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={!!busy}
                          onChange={() => setDraft((previous) => {
                            const current = previous.creator_image_models || [];
                            return {
                              ...previous,
                              creator_image_models: checked
                                ? current.filter((key) => key !== item.key)
                                : [...current, item.key],
                            };
                          })}
                        />
                        <span>{labelOf(String(item.key || ""))}</span>
                      </label>
                    );
                  })}
                </div>
              ) : (
                <select
                  className="input"
                  disabled={!!busy}
                  value={draft[meta.role] || ''}
                  onChange={(event) => setDraft((previous) => ({ ...previous, [meta.role]: event.target.value }))}
                >
                  {!meta.required && <option value="">（不指定）</option>}
                  {meta.required && !draft[meta.role] && <option value="">（请选择）</option>}
                  {sortedLibrary(meta.role).map((item) => (
                    <option key={item.key} value={item.key}>{labelOf(String(item.key || ""))}</option>
                  ))}
                </select>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="card-head">
        <h3>当前生效情况</h3>
        <span className="muted small">重载配置后生效</span>
      </div>
      <table className="model-table">
        <thead><tr><th>调用方</th><th>模型 key</th><th>供应商 / 模型</th><th>状态</th></tr></thead>
        <tbody>
          {(data?.roles || []).map((item, index) => (
            <tr key={item.role + '-' + index}>
              <td>{item.label}</td>
              <td><code>{item.key || '—'}</code></td>
              <td className="muted small">{[item.provider, item.model_name].filter(Boolean).join(' / ') || '—'}</td>
              <td>
                {item.missing && <span className="tag err">模型库中不存在</span>}
                {!item.missing && item.registered && <span className="tag ok">已注册</span>}
                {!item.missing && !item.registered && <span className="tag info">未注册</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}


export { AssignPanel };
