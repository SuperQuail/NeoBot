// FreezeBanner.jsx —— 全局冻结横幅：任何页面都能看到状态并一键解冻。
// 事故中最重要的能力是「立刻停火/立刻恢复」，因此不能只藏在系统页里。
import { useCallback, useState } from 'react';
import { api } from '../api/endpoints.js';
import { useApi } from '../hooks/useApi.js';
import { toast } from './Toast.jsx';

export default function FreezeBanner() {
  const [busy, setBusy] = useState(false);
  const status = useApi(
    async () => {
      const result = await api.freezeStatus();
      return result.ok ? result.data : null;
    },
    { interval: 10000 },
  );

  const state = status.data;
  const frozen = !!state?.frozen;

  const unfreeze = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    try {
      const result = await api.unfreeze();
      toast(result.ok ? (result.data?.message || '已解冻') : '解冻失败：' + (result.error || ''), result.ok ? 'ok' : 'err');
      status.reload();
    } finally {
      setBusy(false);
    }
  }, [busy, status]);

  if (!frozen) return null;

  const remaining = state?.remaining_seconds;
  const tail = remaining == null ? '需要手动解冻' : '剩余约 ' + remaining + ' 秒自动解冻';

  return (
    <div className="freeze-banner" role="alert">
      <span className="freeze-dot" aria-hidden="true" />
      <span className="freeze-text">
        <strong>Bot 已冻结</strong>
        <span className="muted small">
          {state?.frozen_at_text ? '自 ' + state.frozen_at_text : ''}
          {state?.reason ? ' · 原因：' + state.reason : ''}
          {' · ' + tail}
        </span>
      </span>
      <button className="btn" disabled={busy} onClick={unfreeze}>解冻 Bot</button>
    </div>
  );
}
