import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../api/endpoints';
import type { DeployStatus } from '../../api/types';
import { notify } from '../../notifications/infoBar';
import { useEditorGuard } from '../../hooks/useEditorGuard';
import { isEditingSurfaceActive, useAutoRefresh } from '../../hooks/useAutoRefresh';
import { POLL } from '../../data/queryKeys';
import { confirmAction } from '../../components/ui/ConfirmDialog';
import { EMPTY_DRAFT, draftFromDocument, mergeDeployConfig, type DeployDraft } from './deployModel';
import { clearDeployDraft, loadDeployDraft, saveDeployDraft } from './deployDraftStorage';

type ReadSource = 'initial' | 'retry' | 'auto' | 'status' | 'discard';

/** 按写入结果分别推进草稿基线，保留配置成功但密钥失败的部分成功状态。 */
export function useDeployEditor(readOnly: boolean, onInvalidChance: () => void) {
  const [doc, setDoc] = useState<DeployStatus | null>(null);
  const [draft, setDraft] = useState<DeployDraft>(EMPTY_DRAFT);
  const [savedDraft, setSavedDraft] = useState<DeployDraft>(EMPTY_DRAFT);
  const [apiKey, setApiKey] = useState('');
  const [qqSecret, setQqSecret] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [loadError, setLoadError] = useState('');
  const [chanceError, setChanceError] = useState('');
  const [restored, setRestored] = useState(false);
  const draftChecked = useRef(false);

  const changed = (field: keyof DeployDraft) => draft[field] !== savedDraft[field];
  const configDirty = !!doc && (Object.keys(draft) as (keyof DeployDraft)[]).some(changed);
  const keyDirty = !!apiKey.trim();
  const secretDirty = !!qqSecret.trim();
  const dirty = configDirty || keyDirty || secretDirty;
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  const inputRevision = useRef(0);
  const readRevision = useRef(0);
  const operation = useRef(false);
  const invalidateReads = useCallback(() => {
    readRevision.current++;
  }, []);

  // 写后读取只推进状态；自动更新仅在没有输入变化时同步表单和基线。
  const read = useCallback(async (source: ReadSource = 'status') => {
    const hydrate = source !== 'status';
    const background = source === 'auto';
    const discard = source === 'discard';
    if (hydrate && !discard && (dirtyRef.current || operation.current)) return false;
    const request = ++readRevision.current;
    const inputAtStart = inputRevision.current;
    const canApply = () =>
      request === readRevision.current &&
      (!background || !isEditingSurfaceActive()) &&
      (!hydrate ||
        (inputAtStart === inputRevision.current && (discard || (!dirtyRef.current && !operation.current))));
    if (!background) setLoading(true);
    try {
      const result = await api.deployStatus();
      if (!result.ok || !result.data) throw new Error(result.error || '读取部署状态失败');
      if (!canApply()) return false;
      setLoadError('');
      setDoc(result.data);
      if (hydrate) {
        const values = draftFromDocument(result.data);
        const storedDraft = draftChecked.current ? null : loadDeployDraft();
        draftChecked.current = true;
        setDraft(storedDraft ?? values);
        setSavedDraft(values);
        setRestored(
          !!storedDraft &&
            Object.keys(values).some(
              (key) => storedDraft[key as keyof DeployDraft] !== values[key as keyof DeployDraft],
            ),
        );
      }
      return true;
    } catch (error) {
      if (canApply()) setLoadError(error instanceof Error ? error.message : '读取部署状态失败');
      return false;
    } finally {
      if (!background && request === readRevision.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void read('initial');
    return invalidateReads;
  }, [read, invalidateReads]);

  useEffect(() => {
    if (!doc) return;
    if (configDirty) saveDeployDraft(draft);
    else {
      clearDeployDraft();
      setRestored(false);
    }
  }, [doc, draft, configDirty]);

  useAutoRefresh(() => read('auto'), {
    enabled: !dirty && !busy && !loading,
    interval: POLL.editor,
  });

  const disabled = readOnly || !!busy || loading || !doc;
  const dirtySteps: Record<string, boolean> = {
    bot_identity: changed('account') || changed('nickName') || changed('aliases'),
    persona: changed('persona'),
    platform_key: keyDirty,
    admin: changed('adminQq') || changed('chance'),
    official: changed('qqAppId') || secretDirty,
  };
  useEditorGuard(dirty, !!busy);

  const updateDraft = (field: keyof DeployDraft, value: string) => {
    inputRevision.current++;
    setDraft((current) => ({ ...current, [field]: value }));
    if (field === 'chance') setChanceError('');
  };
  const updateApiKey = (value: string) => {
    inputRevision.current++;
    setApiKey(value);
  };
  const updateQqSecret = (value: string) => {
    inputRevision.current++;
    setQqSecret(value);
  };

  const discardDraft = async () => {
    if (
      disabled ||
      operation.current ||
      !(await confirmAction({
        title: '放弃部署草稿',
        description: '重新读取已保存的配置，当前未保存的身份和人设等输入将被丢弃。待填密钥继续保留。',
        confirmLabel: '放弃草稿',
        danger: true,
      }))
    )
      return;
    operation.current = true;
    invalidateReads();
    setBusy('discard');
    try {
      if (await read('discard')) {
        clearDeployDraft();
        setRestored(false);
      }
    } finally {
      operation.current = false;
      setBusy('');
    }
  };

  const saveAll = async () => {
    if (disabled || !dirty || operation.current) return;
    const parsedChance = Number(draft.chance);
    if (configDirty && (!Number.isFinite(parsedChance) || parsedChance < 0 || parsedChance > 1)) {
      setChanceError('群聊回复意愿应为 0 到 1 之间的数值。');
      onInvalidChance();
      return;
    }
    setChanceError('');
    operation.current = true;
    invalidateReads();
    let configSaved = false;
    let anySaved = false;
    const messages: string[] = [];
    try {
      if (configDirty || secretDirty) {
        setBusy('config');
        const current = await api.config();
        if (!current.ok || !current.data) throw new Error(current.error || '读取当前配置失败');
        // 读取最新文档后深合并，保留 bot / chat / adapter 中不属于快捷部署的配置。
        const config = (current.data.config || {}) as Record<string, unknown>;
        const merged = mergeDeployConfig(
          config,
          draft,
          savedDraft,
          parsedChance,
        ) as Record<string, unknown>;
        const officialDirty = changed('qqAppId') || secretDirty;
        if (officialDirty) {
          const adapter = { ...((config.adapter || {}) as Record<string, unknown>) };
          if (changed('qqAppId')) adapter.qq_appid = draft.qqAppId.trim();
          if (secretDirty) adapter.qq_client_secret = qqSecret.trim();
          // 扫码/手填都是官方通道；已在双通道并行时保留 dual。
          if (doc?.official?.mode !== 'dual') adapter.mode = 'official';
          merged.adapter = adapter;
        }
        const result = await api.configSave({
          revision: current.data.revision,
          mode: 'form',
          reload: true,
          config: merged,
        });
        if (!result.ok) throw new Error(result.error || '保存配置失败');
        setSavedDraft({ ...draft });
        clearDeployDraft();
        setRestored(false);
        if (secretDirty) setQqSecret('');
        configSaved = true;
        anySaved = true;
        messages.push(
          officialDirty
            ? '官方机器人信息已保存并重载'
            : result.data?.message || '配置已保存并重载',
        );
      }
      if (keyDirty) {
        setBusy('key');
        const result = await api.envSave({
          updates: { DeepSeek_APIKey: apiKey.trim(), DeepSeek_URL: 'https://api.deepseek.com' },
          deletes: [],
          revision: doc?.env_revision,
          reload: true,
        });
        if (!result.ok)
          throw new Error((configSaved ? '配置已保存；' : '') + (result.error || '保存密钥失败'));
        anySaved = true;
        setApiKey('');
        messages.push(result.data?.message || '密钥已保存并重载');
      }
      const message = messages.join('；');
      notify(message, 'ok');
    } catch (error) {
      const message = error instanceof Error ? error.message : '保存失败，请重试';
      notify(message, 'err');
    } finally {
      if (anySaved) await read();
      operation.current = false;
      setBusy('');
    }
  };

  const startOfficialBind = async () => {
    if (disabled || operation.current) return;
    operation.current = true;
    invalidateReads();
    setBusy('bind');
    try {
      const result = await api.deployOfficialBind({ revision: doc?.revision });
      if (!result.ok) throw new Error(result.error || '开始扫码绑定失败');
      const message = result.data?.message || '已切换官方通道并开始扫码绑定';
      notify(message, 'ok');
      await read('status');
    } catch (error) {
      const message = error instanceof Error ? error.message : '开始扫码绑定失败';
      notify(message, 'err');
    } finally {
      operation.current = false;
      setBusy('');
    }
  };

  return {
    doc,
    draft,
    apiKey,
    setApiKey: updateApiKey,
    qqSecret,
    setQqSecret: updateQqSecret,
    loading,
    busy,
    loadError,
    chanceError,
    restored,
    dirty,
    disabled,
    dirtySteps,
    updateDraft,
    read,
    saveAll,
    startOfficialBind,
    discardDraft,
  };
}
export type DeployEditor = ReturnType<typeof useDeployEditor>;
