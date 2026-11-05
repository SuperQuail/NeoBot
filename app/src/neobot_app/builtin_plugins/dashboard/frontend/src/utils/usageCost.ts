import type { UsageTotals } from '../api/types';

export const fmtCost = (value = 0) => {
  if (value !== 0 && Math.abs(value) < 0.00000001) return value < 0 ? '−<¥0.00000001' : '<¥0.00000001';
  return '¥' + value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 8 });
};
const unknownCalls = (item: UsageTotals) => (item.unpriced_calls || 0) + (item.unverified_zero_calls || 0);
export const pendingCalls = (item: UsageTotals) => unknownCalls(item) + (item.partial_calls || 0);
export const aggregateAmount = (item: UsageTotals) =>
  unknownCalls(item) > 0 && unknownCalls(item) === item.calls ? '—' : fmtCost(item.cost_cny);
