// identity.ts —— 本地 ID 展示：OneBot 数字号与官方 openid 字符串的区分。
//
// 官方通道 user_id/group_id 是 openid 字符串：展示要带 ID 前缀并保留全量，
// 且绝不能拿去请求只认 QQ 号的 qlogo 头像。
import { describe, expect, it } from 'vitest';

import { displayId, idLabel, isNumericId, qqAvatarUrl } from '../utils/identity';

describe('isNumericId', () => {
  it('纯数字 QQ 号才是数字 ID', () => {
    expect(isNumericId(10001)).toBe(true);
    expect(isNumericId('10001')).toBe(true);
  });

  it('openid / 空值 / 0 不是数字 ID', () => {
    expect(isNumericId('2F1B3C4D5E6F7A8B')).toBe(false);
    expect(isNumericId('')).toBe(false);
    expect(isNumericId(null)).toBe(false);
    expect(isNumericId(0)).toBe(false);
  });
});

describe('displayId / idLabel', () => {
  it('数字号显示 QQ 且保留全量', () => {
    expect(idLabel(10001)).toBe('QQ');
    expect(displayId(10001)).toBe('QQ 10001');
  });

  it('openid 显示 ID 且不截断', () => {
    expect(idLabel('2F1B3C4D5E6F7A8B')).toBe('ID');
    expect(displayId('2F1B3C4D5E6F7A8B')).toBe('ID 2F1B3C4D5E6F7A8B');
  });

  it('空值显示占位符', () => {
    expect(displayId('')).toBe('—');
    expect(displayId(null)).toBe('—');
  });
});

describe('qqAvatarUrl', () => {
  it('纯数字才拼 qlogo 地址', () => {
    expect(qqAvatarUrl(10001)).toBe('https://q1.qlogo.cn/g?b=qq&nk=10001&s=100');
  });

  it('openid 不发 qlogo 请求', () => {
    expect(qqAvatarUrl('2F1B3C4D5E6F7A8B')).toBeNull();
  });
});
