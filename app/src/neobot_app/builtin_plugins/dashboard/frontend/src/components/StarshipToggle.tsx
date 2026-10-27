import { useState } from 'react';
import { api } from '../api/endpoints';
import { POLL, QK } from '../data/queryKeys';
import { setQueryData, useQuery } from '../data/useQuery';
import Button from './ui/Button';
import InlineAlert from './ui/InlineAlert';

export interface StarshipToggleProps {
  /** 会话只读，或外层运行操作尚未结束时禁止切换。 */
  readOnly?: boolean;
  disabled?: boolean;
}

export default function StarshipToggle({ readOnly = false, disabled = false }: StarshipToggleProps) {
  const plugins = useQuery(QK.plugins, () => api.plugins(), { interval: POLL.plugins, refetchOnMount: true });
  const extensions = useQuery(QK.extensions, () => api.extensions(), { interval: POLL.plugins });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [verified, setVerified] = useState(true);
  const plugin = plugins.data?.items?.find((item) => item.name === 'starship');
  const enabled = plugin?.enabled === true;
  const loaded = plugin?.status === 'loaded' || plugin?.status === 'running';
  const mounted = !!extensions.data?.items?.some((item) => item.name === 'starship');
  const loading = plugins.loading || extensions.loading;
  const unavailable =
    !loading && (!plugins.data || !extensions.data || !!plugins.error || !!extensions.error || !verified);
  const locked = readOnly || plugins.data?.manage_enabled !== true;
  const stateLabel = loading
    ? '读取中…'
    : unavailable
      ? '状态待确认'
      : !plugin
        ? '未安装'
        : !enabled
          ? '已关闭'
          : loaded && mounted
            ? '已启用'
            : '启用异常';

  const readBack = async () => {
    // 直接读回，避免复用切换前已经发出的轮询结果。
    const [nextPlugins, nextExtensions] = await Promise.all([api.plugins(), api.extensions()]);
    if (nextPlugins) setQueryData(QK.plugins, nextPlugins);
    if (nextExtensions) setQueryData(QK.extensions, nextExtensions);
    setVerified(!!nextPlugins && !!nextExtensions);
    return { nextPlugins, nextExtensions };
  };

  const change = async (target: boolean) => {
    if (!plugin || locked || disabled || busy || unavailable) return;
    setBusy(true);
    setError('');
    setNotice('');
    let failure = '';
    try {
      const result = await api.pluginToggle('starship', { enabled: target, expected_enabled: enabled });
      if (!result.ok) failure = result.error || '星舰状态修改失败';
      const { nextPlugins, nextExtensions } = await readBack();
      const next = nextPlugins?.items?.find((item) => item.name === 'starship');
      const nextMounted = nextExtensions?.items?.some((item) => item.name === 'starship') === true;
      const nextLoaded = next?.status === 'loaded' || next?.status === 'running';
      if (failure) {
        setError(failure);
      } else if (!nextPlugins || !nextExtensions || !next) {
        setError('操作已提交，但未能确认当前状态，请重试读取。');
      } else if (
        next.enabled !== target ||
        (target ? !nextLoaded || !nextMounted : nextLoaded || nextMounted)
      ) {
        setError(next.error || next.disabled_reason || '插件运行状态尚未符合请求，请检查插件详情。');
      } else {
        setNotice(target ? '星舰已加载，入口已注册。' : '星舰已卸载，入口已移除。游戏数据已保留。');
      }
    } catch (cause) {
      setVerified(false);
      setError(failure || (cause instanceof Error ? cause.message : '无法确认星舰状态，请重试读取。'));
    } finally {
      setBusy(false);
    }
  };

  const retry = async () => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const result = await readBack();
      if (!result.nextPlugins || !result.nextExtensions) setError('无法读取星舰状态，请稍后重试。');
    } catch {
      setVerified(false);
      setError('无法读取星舰状态，请稍后重试。');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="starship-setting">
      <div className="starship-setting-row">
        <div className="starship-setting-copy">
          <div className="starship-setting-title">
            <label htmlFor="starship-enabled">启用星舰</label>
            <span>{busy ? '处理中…' : stateLabel}</span>
          </div>
          <p id="starship-setting-description">3D 星舰扩展。关闭后卸载并隐藏入口，保留游戏数据。</p>
        </div>
        <div className="starship-setting-switch">
          <input
            id="starship-enabled"
            type="checkbox"
            role="switch"
            checked={enabled}
            aria-describedby="starship-setting-description"
            disabled={locked || disabled || busy || loading || unavailable || !plugin}
            onChange={(event) => void change(event.target.checked)}
          />
          <span aria-hidden="true" />
        </div>
      </div>
      {locked && !loading && <p className="starship-setting-hint">当前会话只读，切换星舰需要管理权限。</p>}
      {!plugin && !loading && !unavailable && (
        <p className="starship-setting-hint">当前安装中没有找到 starship 插件。</p>
      )}
      {!error && enabled && !loading && !unavailable && (!loaded || !mounted) && (
        <InlineAlert tone="warning" title="星舰尚未正常运行">
          {plugin?.error ||
            plugin?.disabled_reason ||
            '插件未完成加载或入口挂载，可以关闭后重新启用，或到插件管理查看原因。'}
        </InlineAlert>
      )}
      {(error || unavailable) && (
        <InlineAlert
          tone="error"
          title={error || '无法读取星舰状态'}
          actions={
            <Button size="sm" disabled={busy} onClick={() => void retry()}>
              重试读取
            </Button>
          }
        />
      )}
      {!error && !unavailable && notice && <InlineAlert tone="success" title={notice} />}
    </div>
  );
}
