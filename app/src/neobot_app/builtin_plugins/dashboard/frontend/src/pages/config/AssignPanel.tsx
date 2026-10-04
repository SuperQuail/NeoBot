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

  // 兜底：library 必须是数组，否则下面的 .find / [...library] 会整页崩（issue #65）
  const library = Array.isArray(data?.library) ? data.library : [];
  const roles = Array.isArray(data?.roles_meta) ? data.roles_meta : [];

  const labelOf = (modelRef: string) => {
    const item = library.find((entry) => entry.model_ref === modelRef);
    if (!item) return modelRef + '（模型库中不存在）';
    const type = item.type_label ? '[' + item.type_label + '] ' : '';
    return (
      type +
      item.model_ref +
      ' · ' +
      (item.display_name || item.model_name || item.provider)
    );
  };

  /** 与该角色类型匹配的模型排在前面，其余仍可选。 */
  const sortedLibrary = (role: string) => {
    const expected = data?.role_model_types?.[role] || '';
    return [...library].sort((left, right) => {
      const leftMatch = left.model_type === expected ? 0 : 1;
      const rightMatch = right.model_type === expected ? 0 : 1;
      if (leftMatch !== rightMatch) return leftMatch - rightMatch;
      return String(left.model_ref).localeCompare(String(right.model_ref));
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
    // 后端的 models 是「模型视图对象」{library, assignments, roles, …}，不是数组；
    // 同 ModelsPanel 一样取 .library，并顺带刷新分配与角色视图（issue #65）。
    const view = result.data?.models;
    if (view) {
      setData((prev) => ({
        ...(prev || {}),
        library: view.library ?? prev?.library,
        assignments: view.assignments ?? prev?.assignments,
        roles: view.roles ?? prev?.roles,
      }));
    }
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
                    const checked = (draft.creator_image_models || []).includes(String(item.model_ref || ""));
                    return (
                      <label className="assign-choice" key={item.model_ref}>
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={!!busy}
                          onChange={() => setDraft((previous) => {
                            const current = previous.creator_image_models || [];
                            return {
                              ...previous,
                              creator_image_models: checked
                                ? current.filter((ref) => ref !== item.model_ref)
                                : [...current, String(item.model_ref)],
                            };
                          })}
                        />
                        <span>{labelOf(String(item.model_ref || ""))}</span>
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
                    <option key={item.model_ref} value={item.model_ref}>{labelOf(String(item.model_ref || ""))}</option>
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
        <thead><tr><th>调用方</th><th>模型引用名</th><th>供应商 / 模型</th><th>状态</th></tr></thead>
        <tbody>
          {(data?.roles || []).map((item, index) => (
            <tr key={item.role + '-' + index}>
              <td>{item.label}</td>
              <td><code>{item.model_ref || '—'}</code></td>
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
