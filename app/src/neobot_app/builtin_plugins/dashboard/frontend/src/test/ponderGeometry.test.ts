import { describe, expect, it } from 'vitest';
import { ponderGeometry } from '../pages/plugins/ponderGeometry';

describe('思索高亮的可视范围', () => {
  it('贴满舞台的目标保留完整四边，描边不会落到舞台以外', () => {
    expect(ponderGeometry({ left: 0, top: 0, width: 400, height: 300 }, 400, 300)?.frame).toEqual({
      left: 4,
      top: 4,
      width: 392,
      height: 292,
    });
  });
  it('普通目标保持外扩间距，局部滚动区提供的可见范围不再外扩', () => {
    const rect = { left: 20, top: 30, width: 100, height: 50 };
    expect(ponderGeometry(rect, 400, 300)?.frame).toEqual({ left: 14, top: 24, width: 112, height: 62 });
    expect(ponderGeometry(rect, 400, 300, 0)?.frame).toEqual(rect);
  });
  it('超大、部分滚出的目标只绘制可见部分', () => {
    expect(ponderGeometry({ left: -50, top: -100, width: 600, height: 250 }, 400, 300)?.frame).toEqual({
      left: 4,
      top: 4,
      width: 392,
      height: 152,
    });
  });
  it.each([
    { left: -50, top: 20, width: 50, height: 20 },
    { left: 400, top: 20, width: 30, height: 20 },
    { left: 20, top: -50, width: 30, height: 50 },
    { left: 20, top: 300, width: 30, height: 20 },
    { left: 20, top: 20, width: 0, height: 20 },
    { left: NaN, top: 20, width: 30, height: 20 },
  ])('不可见的目标不留下贴边伪高亮：%j', (rect) => {
    expect(ponderGeometry(rect, 400, 300)).toBeNull();
  });
  it('右下角目标的指针整体留在可视范围内', () => {
    const result = ponderGeometry({ left: 395, top: 295, width: 5, height: 5 }, 400, 300)!;
    expect(result.cursor).toEqual({ left: 367, top: 267 });
    expect(result.frame.left + result.frame.width).toBeLessThanOrEqual(396);
    expect(result.frame.top + result.frame.height).toBeLessThanOrEqual(296);
  });
  it('零尺寸舞台不画边框，小舞台不放下溢出的指针', () => {
    const rect = { left: 0, top: 0, width: 20, height: 20 };
    expect(ponderGeometry(rect, 0, 0)).toBeNull();
    expect(ponderGeometry(rect, 20, 20)?.cursor).toBeNull();
  });
});
