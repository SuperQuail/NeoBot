// FreezeBanner.tsx —— 全局冻结横幅：事故中任意页面都能看到状态并一键解冻
import { useMutation, useQuery } from '../data/useQuery';
import { POLL, QK } from '../data/queryKeys';
import { api } from '../api/endpoints';
import Icon from './Icon';

export function formatRemaining(seconds?: number | null): string {
  if (seconds == null) return '需要手动解冻';
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) return `剩余 ${hours} 小时 ${minutes} 分`;
  if (minutes > 0) return `剩余 ${minutes} 分 ${secs} 秒`;
  return `剩余 ${secs} 秒`;
}

export default function FreezeBanner() {
  const status = useQuery(QK.freeze, () => api.freezeStatus(), { interval: POLL.freeze });
  const unfreeze = useMutation(() => api.unfreeze(), { invalidate: [QK.freeze] });
  const state = status.data;
  if (!state?.frozen) return null;

  return (
    <div className="freeze-banner" role="status">
      <Icon name="cpu" />
      <div className="freeze-banner-text">
        <strong>Bot 已冻结</strong>
        <span className="muted small">
          {state.reason ? `原因：${state.reason}` : '原因：未说明'}
          {state.operator ? ` · 操作者 ${state.operator}` : ''}
          {state.frozen_at_text ? ` · 始于 ${state.frozen_at_text}` : ''}
          {' · '}
          {formatRemaining(state.remaining_seconds)}
        </span>
      </div>
      <button
        className="btn primary"
        disabled={unfreeze.busy}
        onClick={() => void unfreeze.run()}
      >
        {unfreeze.busy ? '解冻中…' : '解冻 Bot'}
      </button>
    </div>
  );
}
