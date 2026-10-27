// 模型按用途分配；文件中的选择与运行时注册状态分别呈现。
import { useCallback, useEffect, useState } from 'react';
import { Bot, Check, Eye, Image, MessageSquare, Volume2, type LucideIcon } from 'lucide-react';
import { api } from '../../api/endpoints';
import type { ModelItem, ModelsPayload } from '../../api/types';
import { useAuthGate } from '../../auth/AuthContext';
import { notify } from '../../notifications/infoBar';
import Icon from '../../components/Icon';
import Button from '../../components/ui/Button';
import EmptyState from '../../components/ui/EmptyState';
import { PanelSkeleton } from '../../components/ui/PageSkeleton';
import InlineAlert from '../../components/ui/InlineAlert';
import SelectControl from '../../components/ui/SelectControl';
import { confirmAction } from '../../components/ui/ConfirmDialog';
import { useConfigAutoRead, useEditorGuard, useEditorOperation, type AssignDraft } from './shared';

type RoleMeta = NonNullable<ModelsPayload['roles_meta']>[number];
type RoleGroup = 'conversation' | 'perception' | 'creation';
interface RolePresentation {
  title: string;
  description: string;
  group: RoleGroup;
  icon: LucideIcon;
}

const ROLE_PRESENTATION: Record<string, RolePresentation> = {
  chat: {
    title: '主对话',
    description: '负责日常交流与主要对话回复。',
    group: 'conversation',
    icon: MessageSquare,
  },
  agent: {
    title: 'Agent 推理',
    description: '处理 Agent 推理与工具任务。',
    group: 'conversation',
    icon: Bot,
  },
  memory: {
    title: '记忆总结',
    description: '整理历史对话，生成长期记忆摘要。',
    group: 'conversation',
    icon: Bot,
  },
  vision: {
    title: '图像理解',
    description: '识别图片内容，为对话提供视觉信息。',
    group: 'perception',
    icon: Eye,
  },
  primary_chat_model: {
    title: '主对话',
    description: '负责主要对话回复，对应 Agent 编号 0。',
    group: 'conversation',
    icon: MessageSquare,
  },
  agent_model_1: {
    title: 'Agent 1',
    description: 'Agent 调用编号 1 时使用的模型。',
    group: 'conversation',
    icon: Bot,
  },
  agent_model_2: {
    title: 'Agent 2',
    description: 'Agent 调用编号 2 时使用的模型。',
    group: 'conversation',
    icon: Bot,
  },
  agent_model_3: {
    title: 'Agent 3',
    description: 'Agent 调用编号 3 时使用的模型。',
    group: 'conversation',
    icon: Bot,
  },
  vision_model: {
    title: '图像识别',
    description: '理解图片内容，为对话提供视觉信息。',
    group: 'perception',
    icon: Eye,
  },
  tts_model: { title: '语音合成', description: '将回复文字转换为语音。', group: 'perception', icon: Volume2 },
  creator_image_models: {
    title: '图像创作',
    description: '可选多个生图模型，Agent 会参考模型描述选择。',
    group: 'creation',
    icon: Image,
  },
};
const GROUPS: Array<{ key: RoleGroup; title: string; description: string }> = [
  { key: 'conversation', title: '对话与推理', description: '按调用用途搭配模型，也可以复用同一个模型。' },
  { key: 'perception', title: '视觉与语音', description: '按需要启用图片理解和语音回复。' },
  { key: 'creation', title: '图像创作', description: '为创作任务提供可选的图像生成模型。' },
];

function presentation(meta: RoleMeta): RolePresentation {
  if (ROLE_PRESENTATION[meta.role]) return ROLE_PRESENTATION[meta.role];
  if (meta.multi || meta.model_type === 'image')
    return {
      title: meta.label || meta.role,
      description: '选择可供此用途调用的模型。',
      group: 'creation',
      icon: Image,
    };
  if (meta.model_type === 'vision' || meta.model_type === 'tts')
    return {
      title: meta.label || meta.role,
      description: '为此用途选择合适的模型。',
      group: 'perception',
      icon: meta.model_type === 'vision' ? Eye : Volume2,
    };
  return {
    title: meta.label || meta.role,
    description: '为此调用用途选择对话模型。',
    group: 'conversation',
    icon: MessageSquare,
  };
}

function selections(source: AssignDraft, meta: RoleMeta): string[] {
  const value = source[meta.role];
  if (meta.multi)
    return Array.isArray(value)
      ? value.filter((item): item is string => typeof item === 'string' && !!item)
      : [];
  return typeof value === 'string' && value ? [value] : [];
}

function modelLabel(model: ModelItem): string {
  return model.display_name || model.model_name || model.model_ref || '未命名模型';
}

function ModelInformation({ model }: { model: ModelItem }) {
  return (
    <div className="assignment-model-info">
      <dl className="assignment-model-facts">
        <div>
          <dt>供应商</dt>
          <dd>{model.provider || '未指定'}</dd>
        </div>
        <div>
          <dt>模型</dt>
          <dd>
            <code>{model.model_name || model.model_ref || '—'}</code>
          </dd>
        </div>
      </dl>
      <div className="assignment-capabilities">
        {(model.type_label || model.model_type) && <span>{model.type_label || model.model_type}</span>}
        {(model.native_vision || model.model_type === 'vision') && (
          <span>
            <Eye size={12} aria-hidden="true" />
            支持看图
          </span>
        )}
        {model.api_key_configured === false && <span className="assignment-warning">密钥未配置</span>}
        {model.url_configured === false && <span className="assignment-warning">接口地址未配置</span>}
      </div>
    </div>
  );
}

function AssignPanel() {
  const { canManage } = useAuthGate();
  const [data, setData] = useState<ModelsPayload | null>(null);
  const [draft, setDraft] = useState<AssignDraft>({});
  const [baseline, setBaseline] = useState<AssignDraft>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [savedNotice, setSavedNotice] = useState(false);
  const [imageSearch, setImageSearch] = useState('');
  const { busy, runOperation } = useEditorOperation();
  const readOnly = canManage === false || data?.can_manage === false;
  const dirty = JSON.stringify(draft) !== JSON.stringify(baseline);
  useEditorGuard(dirty, loading || !!busy);

  const applyData = useCallback((payload: ModelsPayload) => {
    setData(payload);
    const next = {
      ...(payload.assignments?.roles || {}),
      creator_image_models: [...(payload.assignments?.creator_image_models || [])],
    };
    setDraft(next);
    setBaseline(next);
  }, []);
  const invalidateAutoRead = useConfigAutoRead({
    enabled: !dirty && !busy && !loading,
    identity: data,
    read: api.configModels,
    apply: (payload) => {
      applyData(payload);
      setError('');
    },
    onError: setError,
    fallback: '自动读取模型分配失败',
  });

  const read = useCallback(
    () =>
      runOperation('read', async () => {
        setLoading(true);
        try {
          const result = await api.configModels();
          if (!result.ok || !result.data) {
            setError(result.error || '读取模型分配失败');
            return;
          }
          applyData(result.data);
          setError('');
        } catch (error) {
          setError(error instanceof Error ? error.message : '读取模型分配失败');
        } finally {
          setLoading(false);
        }
      }),
    [applyData, runOperation],
  );
  useEffect(() => {
    void read();
  }, [read]);

  // 上游返回异常形状时保留页面与重读入口，避免白屏（issue #65）。
  const library = Array.isArray(data?.library) ? data.library.filter((item) => !!item.model_ref) : [];
  const roles = Array.isArray(data?.roles_meta) ? data.roles_meta : [];
  const runtimeRoles = Array.isArray(data?.roles) ? data.roles : [];
  const libraryByRef = new Map(library.map((item) => [String(item.model_ref), item]));
  const invalidRoles = roles.filter((meta) => {
    const refs = selections(draft, meta);
    return (meta.required && refs.length === 0) || refs.some((ref) => !libraryByRef.has(ref));
  });
  const changedCount = roles.filter(
    (meta) => JSON.stringify(selections(draft, meta)) !== JSON.stringify(selections(baseline, meta)),
  ).length;

  const save = () => {
    if (readOnly || !dirty || invalidRoles.length) return;
    return runOperation('save', async () => {
      const submitted = structuredClone(draft);
      try {
        const result = await api.modelsAssignmentsSave({ assignments: submitted, revision: data?.revision });
        if (!result.ok) {
          setError(
            result.status === 409
              ? '配置已被其他会话修改。当前分配草稿已保留，请核对后重新读取。'
              : result.error || '保存失败',
          );
          return;
        }
        const view = result.data?.models;
        if (view)
          applyData({
            ...(data || {}),
            ...result.data,
            ...view,
            revision: result.data?.revision ?? data?.revision,
          });
        else {
          setBaseline(submitted);
          setData((previous) => ({ ...previous, ...result.data }));
        }
        setSavedNotice(true);
        notify('模型分配已保存；重载配置后生效', 'ok');
        setError('');
      } catch (error) {
        setError(error instanceof Error ? error.message : '保存失败，当前分配草稿已保留');
      }
    });
  };

  const reread = async () => {
    if (
      busy ||
      (dirty &&
        !(await confirmAction({
          title: '重新读取模型分配？',
          description: '当前未保存的模型分配会丢失。',
          confirmLabel: '重新读取',
          danger: true,
        })))
    )
      return;
    await read();
  };

  if (loading && !data) return <PanelSkeleton className="card" label="正在读取模型分配…" rows={4} />;

  return (
    <section
      className="card config-card assignment-panel"
      onClickCapture={invalidateAutoRead}
      onInputCapture={invalidateAutoRead}
      onChangeCapture={invalidateAutoRead}
    >
      <div className="assignment-heading">
        <div>
          <h2>按用途分配模型</h2>
          <p>每种用途独立选择，图像创作支持多选。</p>
        </div>
        <div className="assignment-heading-actions">
          <span className="assignment-library-count">{library.length} 个可选模型</span>
        </div>
      </div>
      <div className="config-panel-scroll assignment-scroll">
        {error && (
          <InlineAlert
            tone="error"
            title={error}
            actions={
              <Button size="sm" disabled={!!busy} onClick={reread}>
                {data ? '重新读取' : '重试'}
              </Button>
            }
          />
        )}
        {readOnly && (
          <InlineAlert tone="info" title="当前会话只读">
            可以查看用途与模型状态，修改分配需要管理权限。
          </InlineAlert>
        )}
        {data && library.length === 0 && (
          <InlineAlert tone="info" title="模型库为空">
            先在「模型库」添加模型，再为各个用途进行分配。
          </InlineAlert>
        )}
        {data && roles.length === 0 && (
          <EmptyState icon="bot" title="暂无可分配的用途">
            当前接口没有返回用途信息，恢复后将自动更新。
          </EmptyState>
        )}
        {GROUPS.map((group) => {
          const groupRoles = roles.filter((meta) => presentation(meta).group === group.key);
          if (groupRoles.length === 0) return null;
          return (
            <section
              className="assignment-group"
              key={group.key}
              aria-labelledby={`assignment-group-${group.key}`}
            >
              <div className="assignment-group-heading">
                <h3 id={`assignment-group-${group.key}`}>{group.title}</h3>
                <p>{group.description}</p>
              </div>
              <div className="assignment-cards">
                {groupRoles.map((meta) => {
                  const detail = presentation(meta);
                  const Glyph = detail.icon;
                  const refs = selections(draft, meta);
                  const savedRefs = selections(baseline, meta);
                  const changed = JSON.stringify(refs) !== JSON.stringify(savedRefs);
                  const missing = refs.filter((ref) => !libraryByRef.has(ref));
                  const selected = refs.length ? libraryByRef.get(refs[0]) : undefined;
                  const expected = data?.role_model_types?.[meta.role] || meta.model_type || '';
                  const expectedLabel =
                    meta.model_type_label || data?.model_type_labels?.[expected] || expected;
                  const sorted = [...library].sort(
                    (left, right) =>
                      Number(right.model_type === expected) - Number(left.model_type === expected) ||
                      String(left.model_ref).localeCompare(String(right.model_ref)),
                  );
                  const recommended = sorted.filter((model) => model.model_type === expected);
                  const others = sorted.filter((model) => model.model_type !== expected);
                  const noRequiredSelection = !!meta.required && refs.length === 0;
                  const mismatch =
                    !meta.multi &&
                    selected &&
                    expected &&
                    selected.model_type &&
                    selected.model_type !== expected;
                  const runtime = runtimeRoles.filter(
                    (role) => role.role === meta.role && refs.includes(role.model_ref || ''),
                  );
                  const registrationStates = refs.map(
                    (ref) =>
                      libraryByRef.get(ref)?.registered ??
                      runtime.find((role) => role.model_ref === ref)?.registered,
                  );
                  const registered = refs.length > 0 && registrationStates.every((value) => value === true);
                  const hasUnregistered = registrationStates.some((value) => value === false);
                  const filtered = sorted.filter(
                    (model) =>
                      !imageSearch.trim() ||
                      `${modelLabel(model)} ${model.model_ref} ${model.provider}`
                        .toLowerCase()
                        .includes(imageSearch.trim().toLowerCase()),
                  );
                  return (
                    <article
                      className={`assignment-card${meta.multi ? ' assignment-card--multi' : ''}${changed ? ' is-dirty' : ''}`}
                      key={meta.role}
                      aria-labelledby={`assignment-title-${meta.role}`}
                    >
                      <div className="assignment-card-heading">
                        <span className="assignment-role-icon">
                          <Glyph size={18} aria-hidden="true" />
                        </span>
                        <div className="assignment-role-title">
                          <h4 id={`assignment-title-${meta.role}`}>{detail.title}</h4>
                          <p>{detail.description}</p>
                        </div>
                        <span className={`assignment-requirement${meta.required ? ' is-required' : ''}`}>
                          {meta.required ? '必需' : '可选'}
                        </span>
                      </div>
                      {meta.multi ? (
                        <fieldset className="assignment-multiple" disabled={readOnly || !!busy}>
                          <legend className="sr-only">{detail.title}使用的模型</legend>
                          <div className="assignment-multiple-heading">
                            <span>已选 {refs.length} 个模型</span>
                            {expectedLabel && <span className="muted">推荐类型：{expectedLabel}</span>}
                          </div>
                          {library.length > 6 && (
                            <input
                              className="input assignment-choice-search"
                              aria-label="筛选生图模型"
                              placeholder="按名称或供应商筛选…"
                              value={imageSearch}
                              onChange={(event) => setImageSearch(event.target.value)}
                            />
                          )}
                          <div className="assignment-choices">
                            {missing.map((ref) => (
                              <label className="assignment-choice is-missing" key={ref}>
                                <input
                                  type="checkbox"
                                  checked
                                  aria-label={`移除缺失模型 ${ref}`}
                                  onChange={() =>
                                    setDraft((previous) => ({
                                      ...previous,
                                      [meta.role]: refs.filter((value) => value !== ref),
                                    }))
                                  }
                                />
                                <span>
                                  <strong>{ref}</strong>
                                  <small>模型库中不存在，取消选择即可移除</small>
                                </span>
                              </label>
                            ))}
                            {filtered.map((model) => {
                              const ref = String(model.model_ref);
                              const checked = refs.includes(ref);
                              return (
                                <label
                                  className={`assignment-choice${checked ? ' is-selected' : ''}`}
                                  key={ref}
                                >
                                  <input
                                    type="checkbox"
                                    checked={checked}
                                    aria-label={`${modelLabel(model)} (${ref})`}
                                    onChange={() =>
                                      setDraft((previous) => ({
                                        ...previous,
                                        [meta.role]: checked
                                          ? refs.filter((value) => value !== ref)
                                          : [...refs, ref],
                                      }))
                                    }
                                  />
                                  <span>
                                    <strong>{modelLabel(model)}</strong>
                                    <small>
                                      {model.provider || '未指定供应商'}
                                      <span aria-hidden="true"> / </span>
                                      {model.model_name || ref}
                                    </small>
                                    <span className="assignment-choice-meta">
                                      <code>{ref}</code>
                                      {(model.type_label || model.model_type) && (
                                        <span>{model.type_label || model.model_type}</span>
                                      )}
                                    </span>
                                  </span>
                                  {checked && (
                                    <Check className="assignment-choice-check" size={14} aria-hidden="true" />
                                  )}
                                </label>
                              );
                            })}
                          </div>
                          {filtered.length === 0 && missing.length === 0 && (
                            <p className="assignment-empty-choice">
                              {library.length
                                ? '没有匹配的模型，试试其他名称或供应商。'
                                : '添加模型后，可在这里选择一个或多个模型。'}
                            </p>
                          )}
                        </fieldset>
                      ) : (
                        <>
                          <SelectControl
                            id={`assignment-select-${meta.role}`}
                            label={`${detail.title}使用的模型`}
                            className="assignment-select"
                            title={selected ? modelLabel(selected) : refs[0] || undefined}
                            disabled={readOnly || !!busy || (library.length === 0 && refs.length === 0)}
                            value={refs[0] || ''}
                            aria-invalid={missing.length > 0 || noRequiredSelection}
                            aria-describedby={`assignment-feedback-${meta.role}`}
                            onValueChange={(value) => {
                              invalidateAutoRead();
                              setDraft((previous) => ({ ...previous, [meta.role]: value }));
                            }}
                            options={[
                              {
                                value: '',
                                label: meta.required ? '请选择模型' : '不指定模型',
                                disabled: meta.required,
                              },
                              ...missing.map((ref) => ({ value: ref, label: `${ref}（模型库中不存在）` })),
                              ...recommended.map((model) => ({
                                value: String(model.model_ref),
                                label: `${modelLabel(model)} · ${model.model_ref}`,
                                group: `推荐类型${expectedLabel ? ` · ${expectedLabel}` : ''}`,
                              })),
                              ...others.map((model) => ({
                                value: String(model.model_ref),
                                label: `${modelLabel(model)} · ${model.model_ref}`,
                                group: recommended.length > 0 ? '其他类型（仍可选择）' : '可用模型',
                              })),
                            ]}
                          />
                          {selected && <ModelInformation model={selected} />}
                          {!selected && !missing.length && !noRequiredSelection && (
                            <p className="assignment-empty-choice">暂不指定，需要使用时再选择模型。</p>
                          )}
                        </>
                      )}
                      <div id={`assignment-feedback-${meta.role}`} className="assignment-feedback">
                        {missing.length > 0 && (
                          <p className="assignment-warning">
                            模型库中不存在：{missing.join('、')}。请重新选择。
                          </p>
                        )}
                        {noRequiredSelection && <p className="assignment-warning">此用途必须指定模型。</p>}
                        {mismatch && (
                          <p className="assignment-type-hint">
                            此用途推荐{expectedLabel}模型，当前选择仍可保存。
                          </p>
                        )}
                      </div>
                      <div className="assignment-card-status">
                        <span className={changed ? 'assignment-draft-state' : 'muted'}>
                          {changed ? '未保存' : '已保存'}
                        </span>
                        {changed ? (
                          <span className="assignment-saved-value">
                            已保存：<code>{savedRefs.join('、') || '不指定'}</code>
                          </span>
                        ) : refs.length > 0 && !missing.length ? (
                          <span
                            className={`assignment-runtime-state${registered ? ' is-registered' : ''}`}
                            title="注册状态表示模型是否已加载；修改分配后仍需保存并重载。"
                          >
                            {registered
                              ? '运行时已注册'
                              : hasUnregistered
                                ? meta.multi
                                  ? '有模型未注册'
                                  : '运行时未注册'
                                : '注册状态未知'}
                          </span>
                        ) : (
                          <span className="muted">{meta.required ? '等待配置' : '未启用'}</span>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
      <div className="config-footer assignment-footer">
        <div className="assignment-save-state" role="status">
          <strong>
            {readOnly
              ? '只读模式'
              : dirty
                ? `${changedCount} 项分配待保存`
                : savedNotice
                  ? '已保存，待重载'
                  : '分配与文件同步'}
          </strong>
          <span>
            {invalidRoles.length ? `${invalidRoles.length} 个用途需要补充或修正模型` : '保存后重载配置生效'}
          </span>
        </div>
        <Button
          variant="primary"
          disabled={readOnly || !!busy || !dirty || invalidRoles.length > 0}
          onClick={save}
        >
          <Icon name="save" />
          {busy === 'save' ? '保存中…' : '保存分配'}
        </Button>
      </div>
    </section>
  );
}

export { AssignPanel };
