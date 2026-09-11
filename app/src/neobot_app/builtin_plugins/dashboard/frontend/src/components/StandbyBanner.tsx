// StandbyBanner.tsx —— 全局待机横幅：待机中任意页面都能看到状态并一键启动运行
import { useMutation, useQuery } from '../data/useQuery';
import { POLL, QK } from '../data/queryKeys';
import { api } from '../api/endpoints';
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
        <strong>Bot 处于待机状态</strong>
        <span className="muted small">
          {state.reason ? `原因：${state.reason}` : '原因：未说明'}
          {state.operator ? ` · 操作者 ${state.operator}` : ''}
          {state.since_text ? ` · 始于 ${state.since_text}` : ''}
          {` · 已待机 ${formatDuration(state.standby_seconds)}`}
        </span>
      </div>
      <button className="btn primary" disabled={resume.busy} onClick={() => void resume.run()}>
        {resume.busy ? '启动中…' : '启动运行'}
      </button>
    </div>
  );
}
