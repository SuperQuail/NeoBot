// StandbyBanner.tsx —— 全局待机横幅：待机中任意页面都能看到状态并一键启动运行
import { useMutation, useQuery } from '../data/useQuery';
import { POLL, QK } from '../data/queryKeys';
import { api, type PowerState } from '../api/endpoints';
import Icon from './Icon';
import { toast } from './Toast';

/** 已待机时长的人话格式：未知/0 → 「—」，>1h 到小时+分，>1m 到分+秒 */
export function formatDuration(seconds?: number | null): string {
  if (seconds == null || !Number.isFinite(seconds)) return '—';
  const total = Math.max(0, Math.floor(seconds));
  if (total === 0) return '—';
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) return `${hours} 小时 ${minutes} 分`;
  if (minutes > 0) return `${minutes} 分 ${secs} 秒`;
  return `${secs} 秒`;
}

export function powerStateLabel(state?: PowerState | null): string {
  if (state?.transition) {
    const phases: Record<string, string> = {
      starting: '正在启动',
      stopping: '正在停止',
      startup_cleanup: '正在清理启动资源',
      onebot_starting: '正在连接 OneBot',
      onebot_stopping: '正在断开 OneBot',
    };
    return phases[state.phase || state.state || ''] || '运行时切换中';
  }
  if (state?.state === 'failed') return '运行时操作失败';
  return state?.standby ? '待机中' : '运行中';
}

export default function StandbyBanner() {
  const status = useQuery(QK.power, () => api.powerStatus(), { interval: POLL.power });
  const resume = useMutation(() => api.resume(), {
    invalidate: [QK.power],
    onSuccess: (result) => {
      if (result?.ok === false) toast(result.error || '启动运行失败', 'err');
    },
  });
  const state = status.data;
  if (!state?.standby) return null;

  return (
    <div className="standby-banner" role="status">
      <Icon name="cpu" />
      <div className="standby-banner-text">
        <strong>{state.transition || state.state === 'failed'
          ? `Bot ${powerStateLabel(state)}` : 'Bot 处于待机状态'}</strong>
        <span className="muted small">
          {state.reason ? `原因：${state.reason}` : '原因：未说明'}
          {state.operator ? ` · 操作者 ${state.operator}` : ''}
          {state.since_text ? ` · 始于 ${state.since_text}` : ''}
          {state.transition ? ' · 清理完成前不能启动新实例' : ` · 已待机 ${formatDuration(state.standby_seconds)}`}
        </span>
      </div>
      <button className="btn primary" disabled={resume.busy || !!state.transition} onClick={() => void resume.run()}>
        {state.transition ? '等待清理完成' : resume.busy ? '启动中…' : '启动运行'}
      </button>
    </div>
  );
}
