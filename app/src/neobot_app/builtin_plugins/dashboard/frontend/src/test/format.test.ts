// format.ts —— mapTag 必须把 DEBUG 与 INFO 分成两个级别。
//
// 旧实现里 DEBUG 落到默认分支被归成 info：控制台的级别 pill 与行样式完全一致，
// 于是没有任何办法单独过滤掉 DEBUG 噪音。
import { describe, expect, it } from 'vitest';

import { mapTag } from '../utils/format';

describe('mapTag', () => {
  it('DEBUG/TRACE 是独立级别，不再归到 info', () => {
    expect(mapTag('debug')).toBe('debug');
    expect(mapTag('DEBUG')).toBe('debug');
    expect(mapTag('trace')).toBe('debug');
  });

  it('其余级别映射保持不变', () => {
    expect(mapTag('info')).toBe('info');
    expect(mapTag('success')).toBe('ok');
    expect(mapTag('warning')).toBe('warn');
    expect(mapTag('error')).toBe('err');
    expect(mapTag('critical')).toBe('err');
    expect(mapTag(undefined)).toBe('info');
  });
});
