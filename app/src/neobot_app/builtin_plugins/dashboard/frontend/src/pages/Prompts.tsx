// pages/Prompts.tsx —— 提示词模板编辑与「转义后内容」实时预览
// 提示词全部来自 data/prompts（默认文件 + 自定义文件合并）：这里只编辑自定义覆盖，
// 保存写进 custom/prompts.toml，不会改动内置默认文件。
import { useEffect, useMemo, useRef, useState } from 'react';
import Icon from '../components/Icon';
import InlineAlert from '../components/ui/InlineAlert';
import { toast } from '../components/Toast';
import { useQuery } from '../data/useQuery';
import { QK } from '../data/queryKeys';
import { api } from '../api/endpoints';
import type { PromptKeyView } from '../api/types';

const PREVIEW_DEBOUNCE_MS = 300;

interface Selection {
  section: string;
  path: string;
}

function keyLabel(item: PromptKeyView): string {
  return item.kind === 'template' ? item.path : item.path + '(纯文本)';
}

export default function Prompts() {
  const query = useQuery(QK.prompts, () => api.prompts());
  const payload = query.data?.data;
  const sections = useMemo(() => payload?.sections || [], [payload]);
  const editable = payload?.editable !== false;

  const [selection, setSelection] = useState<Selection | null>(null);
  // 本地「未保存的编辑」。编辑器内容由它和服务器值**派生**（见下方 draft），
  // 不再用 useEffect 把服务器值写回 state —— 那种写回是异步的，见下方注释。
  const [edit, setEdit] = useState<Selection & { value: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [preview, setPreview] = useState<{ rendered: string; unresolved: string[] } | null>(null);
  const [previewError, setPreviewError] = useState('');
  const previewSeq = useRef(0);

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
    if (!current || current.kind !== 'template') {
      setPreview(null);
      return undefined;
    }
    const seq = ++previewSeq.current;
    const timer = window.setTimeout(() => {
      void (async () => {
        const result = await api.promptsPreview({ template: draft });
        if (seq !== previewSeq.current) return;
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
    return () => window.clearTimeout(timer);
  }, [current, draft]);

  const dirty = !!current && draft !== current.value;

  /** 丢掉「正好是这一份值」的本地覆盖；若期间用户又改了则保留 */
  const dropOverride = (target: Selection, value: string) => {
    setEdit((prev) =>
      prev && prev.section === target.section && prev.path === target.path && prev.value === value
        ? null
        : prev,
    );
  };

  const save = async () => {
    if (!current || !selection) return;
    const target = { section: selection.section, path: selection.path };
    const value = draft;
    setSaving(true);
    const result = await api.promptsSave({ ...target, value });
    setSaving(false);
    if (!result.ok) {
      toast(result.error || '保存失败', 'err');
      return;
    }
    toast(result.data?.message || '已保存', 'ok');
    await query.refetch();
    // 存盘成功后丢掉本地覆盖，跟随服务器值（后端可能做了归一化）。
    // 用函数式更新比对「当时保存的那一份」：请求期间用户又改了就保留新输入。
    dropOverride(target, value);
  };

  const reset = async () => {
    if (!current || !selection) return;
    if (!window.confirm('恢复该键的内置默认提示词？自定义内容会被删除。')) return;
    const target = { section: selection.section, path: selection.path };
    const value = draft;
    setSaving(true);
    const result = await api.promptsReset(target);
    setSaving(false);
    if (!result.ok) {
      toast(result.error || '恢复失败', 'err');
      return;
    }
    toast(result.data?.message || '已恢复默认', 'ok');
    await query.refetch();
    // 恢复默认后编辑器要显示新的默认值：丢掉当时那一份本地覆盖
    dropOverride(target, value);
  };

  const unavailable = !query.loading && sections.length === 0;

  return (
    <div className="page prompts-page">
      <section className="card">
        <div className="card-head">
          <h3>提示词模板</h3>
          <div className="spacer" />
          <span className="muted small">{payload?.custom_file || ''}</span>
          <button className="btn" disabled={query.loading} onClick={() => void query.refetch()}>
            <Icon name="refresh" />
            {query.loading ? '读取中…' : '刷新'}
          </button>
        </div>
        <p className="muted small">
          占位符写作 {'{名字}'}；需要输出字面量花括号时写成双花括号；只含空白的区块渲染后会被自动删除。
        </p>
        {!editable && (
          <InlineAlert tone="warning" title="当前会话没有管理权限，只能查看">
            面板管理功能已关闭或远程管理被禁用。
          </InlineAlert>
        )}
      </section>

      {unavailable && (
        <div className="workspace-empty">
          <Icon name="code" />
          <h3>提示词存储不可用</h3>
          <p>{query.data?.error || '后端未注入 prompt_store。'}</p>
        </div>
      )}

      {sections.length > 0 && (
        <div className="prompt-layout">
          <section className="card prompt-list" aria-label="提示词分区">
            {sections.map((section) => (
              <div key={section.name} className="prompt-section">
                <div className="prompt-section-head">
                  <strong>{section.name}</strong>
                  {section.customized && <span className="tag info">已自定义</span>}
                </div>
                <ul>
                  {section.keys.map((item) => {
                    const active =
                      selection?.section === section.name && selection?.path === item.path;
                    return (
                      <li key={item.path}>
                        <button
                          type="button"
                          className={'prompt-key' + (active ? ' active' : '')}
                          aria-current={active}
                          onClick={() => {
                            // 重复点当前键保持无副作用（原先就如此）
                            if (active) return;
                            // 与 selection 同一批处理，顺序确定；切键即丢弃未保存的草稿
                            setSelection({ section: section.name, path: item.path });
                            setEdit(null);
                          }}
                        >
                          <span>{keyLabel(item)}</span>
                          {item.overridden && <span className="tag warn">已覆盖</span>}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </section>

          <section className="card prompt-editor" aria-label="提示词编辑">
            {current && selection ? (
              <>
                <div className="card-head">
                  <h3>
                    {selection.section}.{selection.path}
                  </h3>
                  <div className="spacer" />
                  {current.overridden && <span className="tag warn">自定义生效中</span>}
                  <button
                    className="btn"
                    disabled={!current.overridden || saving || !editable}
                    onClick={() => void reset()}
                  >
                    <Icon name="undo" />
                    恢复默认
                  </button>
                  <button
                    className="btn primary"
                    disabled={!dirty || saving || !editable}
                    onClick={() => void save()}
                  >
                    <Icon name="save" />
                    {saving ? '保存中…' : '保存'}
                  </button>
                </div>

                <textarea
                  className="toml-editor prompt-textarea"
                  aria-label="提示词内容"
                  spellCheck={false}
                  value={draft}
                  onChange={(event) => {
                    if (!selection) return;
                    setEdit({
                      section: selection.section,
                      path: selection.path,
                      value: event.target.value,
                    });
                  }}
                />

                {current.placeholders.length > 0 && (
                  <div className="prompt-placeholders">
                    <span className="muted small">可用占位符</span>
                    {current.placeholders.map((name) => (
                      <code key={name}>{'{' + name + '}'}</code>
                    ))}
                  </div>
                )}

                {current.kind === 'template' && (
                  <div className="prompt-preview">
                    <div className="prompt-preview-head">
                      <strong>预览（模拟取值渲染）</strong>
                      {dirty && <span className="tag warn">未保存</span>}
                    </div>
                    {previewError && <InlineAlert tone="error" title={previewError} />}
                    {preview?.unresolved && preview.unresolved.length > 0 && (
                      <InlineAlert tone="warning" title="以下占位符没有模拟取值，将原样输出">
                        {preview.unresolved.join('、')}
                      </InlineAlert>
                    )}
                    <pre className="prompt-preview-body">{preview?.rendered ?? '…'}</pre>
                  </div>
                )}
              </>
            ) : (
              <div className="empty muted">选择左侧的一个提示词键开始编辑</div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
