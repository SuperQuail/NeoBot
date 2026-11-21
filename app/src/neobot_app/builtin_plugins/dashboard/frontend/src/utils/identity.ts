// identity.ts —— 本地 ID 的展示与头像规则。
//
// OneBot 通道的 user_id/group_id 是数字 QQ 号；官方通道是 openid 字符串。
// openid 不是 QQ 号：不能拿去请求 qlogo 头像，展示时要带上 "ID" 前缀并保留全量。

export function isNumericId(value: string | number | null | undefined): boolean {
  const text = String(value ?? '').trim();
  return text !== '' && text !== '0' && /^\d+$/.test(text);
}

/** 前缀：真实数字号显示 QQ，其余（官方 openid 等）显示 ID。 */
export function idLabel(value: string | number | null | undefined): string {
  return isNumericId(value) ? 'QQ' : 'ID';
}

/** 完整 ID 的展示文本（openid 不截断，便于复制/核对）。 */
export function displayId(value: string | number | null | undefined): string {
  const text = String(value ?? '').trim();
  if (!text) return '—';
  return `${idLabel(text)} ${text}`;
}

/** qlogo 头像地址：只有纯数字的真实 QQ 号才请求，openid 返回 null（不对外发请求）。 */
export function qqAvatarUrl(
  value: string | number | null | undefined,
  size = 100,
): string | null {
  if (!isNumericId(value)) return null;
  return `https://q1.qlogo.cn/g?b=qq&nk=${String(value).trim()}&s=${size}`;
}
