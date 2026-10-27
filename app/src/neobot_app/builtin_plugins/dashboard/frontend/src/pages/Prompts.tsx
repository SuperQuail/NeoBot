// pages/Prompts.tsx —— 提示词模板编辑与「转义后内容」实时预览
// 提示词全部来自 data/prompts（默认文件 + 自定义文件合并）：这里只编辑自定义覆盖，
// 保存写进 custom/prompts.toml，不会改动内置默认文件。
import { useEffect, useMemo, useRef, useState } from 'react';
import Icon from '../components/Icon';
import Button from '../components/ui/Button';
import EmptyState from '../components/ui/EmptyState';
import InlineAlert from '../components/ui/InlineAlert';
import { notify } from '../notifications/infoBar';
import { setQueryData, useQuery } from '../data/useQuery';
import { QK } from '../data/queryKeys';
import { isEditingSurfaceActive, useAutoRefresh } from '../hooks/useAutoRefresh';
import { api } from '../api/endpoints';
import type { PromptKeyView } from '../api/types';
import PageHeader from '../components/ui/PageHeader';
import { confirmAction } from '../components/ui/ConfirmDialog';
import { useEditorGuard } from '../hooks/useEditorGuard';
import WorkspaceLayout from '../components/WorkspaceLayout';
import Modal from '../components/Modal';
import TomlEditor, { type CodeEditorHandle } from '../components/TomlEditor';
import { PanelSkeleton } from '../components/ui/PageSkeleton';
import { useAuthGate } from '../auth/AuthContext';

const PREVIEW_DEBOUNCE_MS = 300;
const SECTION_LABELS: Record<string, string> = {
  group_chat: '群聊人设',
  group_context: '群聊上下文',
  friend_chat: '私聊人设',
  private_chat: '私聊人设',
  friend_context: '私聊上下文',
  friend_chat_hint: '私聊补充说明',
  long_task_progress: '长任务进度',
  current_time: '当前时间',
  current_time_short: '简短时间',
  avoid_repeat: '避免重复回复',
  silent_nudge: '回复进度提醒',
  group_chat_resume: '群聊恢复',
  new_member_profiles: '新群友档案',
  native_vision: '原生视觉',
  tool_result_compressed: '工具结果摘要',
  tool_result_compressed_detail: '工具结果详细摘要',
  long_reply_fallback: '长回复兜底',
  problem_solver: '复杂问题解题',
  self_heal: '自动修复',
  maintenance: '维护任务',
  wake_up: '唤醒提醒',
  at_mention_wait: '提及等待',
  sleep_cmd: '休眠回复',
  awake_cmd: '唤醒回复',
  human_feel: '自然表达',
  stale_topic: '过期话题',
  live_chat: '实时对话',
};
const KEY_LABELS: Record<string, string> = {
  template: '提示词模板',
  system_prompt: '系统提示词',
  description: '功能描述',
  'runtime.template': '运行时模板',
};

interface Selection {
  section: string;
  path: string;
}

function keyLabel(item: PromptKeyView): string {
  return KEY_LABELS[item.path] || item.label || item.path;
}

export default function Prompts() {
  const { canManage } = useAuthGate();
  const query = useQuery(QK.prompts, () => api.prompts());
  const payload = query.data?.data;
  const sections = useMemo(() => payload?.sections || [], [payload]);
  const editable = payload?.editable !== false && canManage !== false;

  const [selection, setSelection] = useState<Selection | null>(null);
  const [mobileDetail, setMobileDetail] = useState(false);
  const [pane, setPane] = useState<'edit' | 'preview'>('edit');
  const [search, setSearch] = useState('');
  const [helpOpen, setHelpOpen] = useState(false);
  const editorRef = useRef<CodeEditorHandle>(null);
  const placeholdersRef = useRef<HTMLDetailsElement>(null);
  const operationRef = useRef(false);
  const editableRef = useRef(editable);
  editableRef.current = editable;
  // 本地「未保存的编辑」。编辑器内容由它和服务器值**派生**（见下方 draft），
  // 不再用 useEffect 把服务器值写回 state —— 那种写回是异步的，见下方注释。
  const [edit, setEdit] = useState<(Selection & { value: string }) | null>(null);
  const [saving, setSaving] = useState(false);
  const [preview, setPreview] = useState<{ rendered: string; unresolved: string[] } | null>(null);
  const [previewError, setPreviewError] = useState('');
  const [syncError, setSyncError] = useState('');
  const syncRevision = useRef(0);
  const syncPending = useRef(false);
  const [syncing, setSyncing] = useState(false);
  const syncState = useRef({ dirty: false, edit, saving, mounted: true });
  useEffect(() => {
    syncState.current.mounted = true;
    return () => {
      syncState.current.mounted = false;
    };
  }, []);

  // 首次拿到数据时选中第一个可编辑键
  useEffect(() => {
    if (selection || sections.length === 0) return;
    const first = sections.find((section) => section.keys.length > 0);
    if (first) setSelection({ section: first.name, path: first.keys[0].path });
  }, [sections, selection]);

  const current = useMemo(() => {
    if (!selection) return null;
    const section = sections.find((item) => item.name === selection.section);
    return section?.keys.find((item) => item.path === selection.path) || null;
  }, [sections, selection]);

  // 编辑器内容 = 本地覆盖（如果有）优先，否则跟随服务器当前值。
  //
  // 这里必须是**纯派生**，不能再用 useEffect 去 setDraft(服务器值)：被动副作用是
  // 异步冲刷的（commit 之后才跑，测试环境里还会跨一个宏任务），一旦这次写入排在用户
  // 输入之后落地，就会把刚敲进去的草稿冲回编辑前的旧值 —— 防抖预览和保存于是都拿到
  // 旧模板（CI 上偶发失败就是这个顺序问题，仅靠「依赖写成键+值」治不了根）。
  // 派生之后不存在任何会覆盖用户输入的写入，谁先谁后都不再影响结果；
  // 刷新拿到「同键同值的新对象」同样不打扰草稿（值没变，派生结果就不变）。
  const currentValue = current?.value ?? '';
  const override =
    edit && selection && edit.section === selection.section && edit.path === selection.path
      ? edit.value
      : null;
  const draft = override ?? currentValue;

  // 切换键时丢掉上一个键的预览（纯展示状态，不碰草稿）
  useEffect(() => {
    setPreview(null);
    setPreviewError('');
  }, [selection?.section, selection?.path]);

  // 实时预览：纯文本键不渲染模板
  useEffect(() => {
    let cancelled = false;
    if (!current || current.kind !== 'template') {
      setPreview(null);
      return undefined;
    }
    const timer = window.setTimeout(() => {
      void (async () => {
        const result = await api.promptsPreview({ template: draft });
        if (cancelled) return;
        if (!result.ok || !result.data) {
          setPreviewError(result.error || '预览失败');
          setPreview(null);
          return;
        }
        setPreviewError('');
        setPreview({
          rendered: result.data.rendered || '',
          unresolved: result.data.unresolved || [],
        });
      })();
    }, PREVIEW_DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      cancelled = true;
    };
  }, [current, draft]);

  const dirty = !!current && draft !== current.value;
  useEditorGuard(dirty, saving);
  syncState.current = { ...syncState.current, dirty, edit, saving };
  const sync = async () => {
    const editAtStart = syncState.current.edit;
    const revision = syncRevision.current;
    if (syncPending.current || syncState.current.dirty || operationRef.current || isEditingSurfaceActive())
      return;
    syncPending.current = true;
    setSyncing(true);
    const canApply = () =>
      syncState.current.mounted &&
      syncRevision.current === revision &&
      !syncState.current.dirty &&
      !operationRef.current &&
      syncState.current.edit === editAtStart &&
      !isEditingSurfaceActive();
    try {
      const result = await api.prompts();
      if (!canApply()) return;
      if (!result?.ok || !result.data) {
        setSyncError(result?.error || '暂时无法同步提示词模板');
        return;
      }
      setQueryData(QK.prompts, result);
      setSyncError('');
    } catch {
      if (canApply()) setSyncError('暂时无法同步提示词模板');
    } finally {
      syncPending.current = false;
      if (syncState.current.mounted) setSyncing(false);
    }
  };
  useAutoRefresh(sync, { enabled: !dirty && !saving && !query.loading });

  /** 丢掉「正好是这一份值」的本地覆盖；若期间用户又改了则保留 */
  const dropOverride = (target: Selection, value: string) => {
    setEdit((prev) =>
      prev && prev.section === target.section && prev.path === target.path && prev.value === value
        ? null
        : prev,
    );
  };

  const save = async () => {
    if (!current || !selection || !editableRef.current || !dirty || operationRef.current) return;
    const target = { section: selection.section, path: selection.path };
    const value = draft;
    syncRevision.current++;
    operationRef.current = true;
    setSaving(true);
    try {
      const result = await api.promptsSave({ ...target, value });
      if (!result.ok) {
        notify(result.error || '保存失败', 'err');
        return;
      }
      notify(result.data?.message || '已保存', 'ok');
      await query.refetch();
      // 存盘期间的新输入继续保留，只有正好是已保存的那份覆盖才被清除。
      dropOverride(target, value);
    } catch (error) {
      notify(error instanceof Error ? error.message : '保存失败', 'err');
    } finally {
      operationRef.current = false;
      setSaving(false);
    }
  };

  const reset = async () => {
    if (!current || !selection || !editableRef.current || operationRef.current) return;
    if (
      !(await confirmAction({
        title: '恢复默认提示词',
        description: '该键的自定义内容会被删除，并恢复内置默认值。',
        confirmLabel: '恢复默认',
        danger: true,
      }))
    )
      return;
    if (!editableRef.current || operationRef.current) return;
    const target = { section: selection.section, path: selection.path };
    const value = draft;
    syncRevision.current++;
    operationRef.current = true;
    setSaving(true);
    try {
      const result = await api.promptsReset(target);
      if (!result.ok) {
        notify(result.error || '恢复失败', 'err');
        return;
      }
      notify(result.data?.message || '已恢复默认', 'ok');
      await query.refetch();
      dropOverride(target, value);
    } catch (error) {
      notify(error instanceof Error ? error.message : '恢复失败', 'err');
    } finally {
      operationRef.current = false;
      setSaving(false);
    }
  };

  const unavailable = !query.loading && sections.length === 0;
  const visibleSections = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return sections;
    return sections.flatMap((section) => {
      if (`${section.name} ${SECTION_LABELS[section.name] || ''}`.toLowerCase().includes(term))
        return [section];
      const keys = section.keys.filter((item) =>
        `${item.path} ${keyLabel(item)}`.toLowerCase().includes(term),
      );
      return keys.length ? [{ ...section, keys }] : [];
    });
  }, [sections, search]);

  const insertPlaceholder = (name: string) => {
    if (!selection || !editable || saving) return;
    editorRef.current?.insertText(`{${name}}`);
    if (placeholdersRef.current) placeholdersRef.current.open = false;
  };

  return (
    <div className="page prompts-page page--viewport">
      <PageHeader title="提示词模板" actions={<Button onClick={() => setHelpOpen(true)}>使用帮助</Button>} />
      {(query.error || syncError) && (
        <InlineAlert
          tone="warning"
          title={syncError || '暂时无法读取提示词模板'}
          actions={
            <Button
              size="sm"
              disabled={dirty || saving || query.loading || syncing}
              onClick={() => void sync()}
            >
              重试读取
            </Button>
          }
        />
      )}
      {query.loading && sections.length === 0 && (
        <PanelSkeleton className="card" kind="text" rows={7} label="正在读取提示词模板" />
      )}
      {!editable && (
        <InlineAlert tone="warning" title="当前会话没有管理权限，只能查看">
          面板管理功能已关闭或远程管理被禁用。
        </InlineAlert>
      )}

      {unavailable && (
        <EmptyState icon="code" title="提示词存储不可用">
          <p>{query.data?.error || '后端未注入 prompt_store。'}</p>
          {!query.error && !syncError && (
            <Button disabled={query.loading} onClick={() => void sync()}>
              重试读取
            </Button>
          )}
        </EmptyState>
      )}

      {sections.length > 0 && (
        <WorkspaceLayout
          className="prompt-workspace"
          showDetail={mobileDetail}
          panel={
            <section className="workspace-panel" aria-label="提示词分区">
              <div className="prompt-nav-heading">
                模板目录 <span>{sections.length} 个分区</span>
              </div>
              <div className="prompt-nav-search">
                <Icon name="search" size={15} />
                <input
                  aria-label="搜索提示词"
                  placeholder="搜索名称或键名"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </div>
              <div className="workspace-scroll prompt-nav-scroll">
                {visibleSections.length === 0 && <EmptyState compact>没有匹配的模板</EmptyState>}
                {visibleSections.map((section) => {
                  const sectionLabel = SECTION_LABELS[section.name] || section.name;
                  const singleKey = sections.find((item) => item.name === section.name)?.keys.length === 1;
                  return (
                    <div
                      key={section.name}
                      className={'prompt-nav-section' + (singleKey ? ' is-single' : '')}
                    >
                      {!singleKey && (
                        <div className="prompt-nav-section-heading" title={section.name}>
                          <strong>{sectionLabel}</strong>
                          <span>{section.keys.length}</span>
                        </div>
                      )}
                      <ul>
                        {section.keys.map((item) => {
                          const active = selection?.section === section.name && selection?.path === item.path;
                          return (
                            <li key={item.path}>
                              <button
                                type="button"
                                className={'prompt-nav-key' + (active ? ' active' : '')}
                                aria-current={active}
                                aria-label={`${sectionLabel} · ${keyLabel(item)}`}
                                title={`${section.name}.${item.path}`}
                                onClick={async () => {
                                  // 重复点当前键保持无副作用（原先就如此）
                                  if (active) {
                                    setMobileDetail(true);
                                    return;
                                  }
                                  if (saving || operationRef.current) return;
                                  if (
                                    dirty &&
                                    !(await confirmAction({
                                      title: '放弃未保存的提示词',
                                      description: '切换模板会丢弃当前修改。',
                                      confirmLabel: '放弃修改',
                                      danger: true,
                                    }))
                                  )
                                    return;
                                  // 与 selection 同一批处理，顺序确定；切键即丢弃未保存的草稿
                                  setSelection({ section: section.name, path: item.path });
                                  syncRevision.current++;
                                  setEdit(null);
                                  setPane('edit');
                                  setMobileDetail(true);
                                }}
                              >
                                <strong>{singleKey ? sectionLabel : keyLabel(item)}</strong>
                                {item.overridden || (singleKey && section.customized) ? (
                                  <span
                                    className="prompt-override-dot"
                                    role="img"
                                    aria-label="已自定义"
                                    title="已有自定义内容"
                                  />
                                ) : (
                                  <Icon name="chevron" size={13} />
                                )}
                              </button>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  );
                })}
              </div>
            </section>
          }
          editor={
            <section className="workspace-editor prompt-detail" aria-label="提示词编辑">
              {current && selection ? (
                <>
                  <div className="prompt-workbench-heading">
                    <Button className="prompt-back" size="sm" onClick={() => setMobileDetail(false)}>
                      <Icon name="back" /> 目录
                    </Button>
                    <div className="prompt-workbench-title">
                      <h3>
                        {SECTION_LABELS[selection.section] || selection.section} · {keyLabel(current)}
                      </h3>
                      <code>
                        {selection.section}.{selection.path}
                      </code>
                    </div>
                    {current.kind === 'template' && (
                      <div className="prompt-view-switch" role="group" aria-label="工作区视图">
                        <button aria-pressed={pane === 'edit'} onClick={() => setPane('edit')}>
                          <Icon name="edit" size={14} />
                          编辑
                        </button>
                        <button aria-pressed={pane === 'preview'} onClick={() => setPane('preview')}>
                          <Icon name="eye" size={14} />
                          预览
                        </button>
                      </div>
                    )}
                  </div>
                  <div
                    className={'prompt-workbench' + (current.kind === 'text' ? ' is-text' : '')}
                    data-view={pane}
                    key={selection.section + '.' + selection.path}
                  >
                    <section className="prompt-source-pane" aria-label="模板编辑区">
                      <TomlEditor
                        ref={editorRef}
                        ariaLabel="提示词内容"
                        language="text"
                        fileName={current.kind === 'template' ? '模板内容' : '文本内容'}
                        filePath={`${selection.section}.${selection.path}`}
                        placeholders={current.kind === 'template' ? current.placeholders : undefined}
                        readOnly={!editable}
                        value={draft}
                        onChange={(value) => {
                          if (editableRef.current) {
                            syncRevision.current++;
                            setEdit({ ...selection, value });
                          }
                        }}
                        onSave={() => void save()}
                        saveDisabled={!dirty || saving || !editable}
                        toolbarActions={
                          current.placeholders.length > 0 && (
                            /* 原生 details 负责键盘展开，Escape 补充关闭行为。 */
                            /* eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions */
                            <details
                              className="prompt-placeholder-picker"
                              ref={placeholdersRef}
                              onKeyDown={(event) => {
                                if (event.key === 'Escape') {
                                  event.currentTarget.open = false;
                                  event.currentTarget.querySelector('summary')?.focus();
                                }
                              }}
                            >
                              <summary>
                                插入占位符 <span>{current.placeholders.length}</span>
                              </summary>
                              <div className="prompt-placeholder-options">
                                <span>点击插入到光标位置</span>
                                {current.placeholders.map((name) => (
                                  <button
                                    key={name}
                                    disabled={!editable || saving}
                                    onClick={() => insertPlaceholder(name)}
                                  >
                                    <code>{`{${name}}`}</code>
                                    <Icon name="plus" size={13} />
                                  </button>
                                ))}
                              </div>
                            </details>
                          )
                        }
                      />
                    </section>
                    {current.kind === 'template' && (
                      <section className="prompt-preview-pane" aria-label="渲染预览">
                        <div className="prompt-pane-toolbar">
                          <strong>实时预览</strong>
                          <span>使用模拟取值</span>
                        </div>
                        <div className="prompt-preview-content">
                          {previewError && <InlineAlert tone="error" title={previewError} />}
                          {preview?.unresolved && preview.unresolved.length > 0 && (
                            <InlineAlert tone="warning" title="以下占位符没有模拟取值，将原样输出">
                              {preview.unresolved.join('、')}
                            </InlineAlert>
                          )}
                          <pre>
                            {preview?.rendered ?? (previewError ? '暂时无法生成预览' : '正在生成预览…')}
                          </pre>
                        </div>
                      </section>
                    )}
                  </div>
                  <footer className="prompt-workbench-footer">
                    <div className="prompt-save-state">
                      <span className={dirty ? 'dirty-label' : ''}>
                        {saving
                          ? '正在保存…'
                          : dirty
                            ? '未保存的修改'
                            : current.overridden
                              ? '已保存自定义内容'
                              : '使用默认内容'}
                      </span>
                      <span>{draft.length.toLocaleString()} 字符</span>
                    </div>
                    <div className="prompt-save-actions">
                      <Button
                        size="sm"
                        disabled={!current.overridden || saving || !editable}
                        onClick={() => void reset()}
                      >
                        <Icon name="undo" size={15} />
                        <span>恢复默认</span>
                      </Button>
                      <Button
                        size="sm"
                        variant="primary"
                        disabled={!dirty || saving || !editable}
                        onClick={() => void save()}
                      >
                        <Icon name="save" size={15} />
                        {saving ? '保存中…' : '保存'}
                      </Button>
                    </div>
                  </footer>
                </>
              ) : (
                <EmptyState compact>选择左侧的一个提示词键开始编辑</EmptyState>
              )}
            </section>
          }
        />
      )}
      <Modal open={helpOpen} title="提示词使用帮助" onClose={() => setHelpOpen(false)}>
        <div className="prompt-help-content">
          <h4>模板与实时预览</h4>
          <p>左侧编辑模板，预览会用模拟取值替换占位符。保存后使用自定义内容，恢复默认会移除当前键的覆盖。</p>
          <h4>占位符语法</h4>
          <p>
            占位符写作 <code>{'{名字}'}</code>，可从编辑工具栏插入。需要输出花括号时写成 <code>{'{{'}</code>{' '}
            或 <code>{'}}'}</code>；只含空白的区块会在渲染时自动删除。
          </p>
          {payload?.custom_file && (
            <>
              <h4>自定义文件</h4>
              <p>只保存修改过的键，其他内容继续继承内置默认值。</p>
              <code className="prompt-storage-path">{payload.custom_file}</code>
            </>
          )}
        </div>
      </Modal>
    </div>
  );
}
