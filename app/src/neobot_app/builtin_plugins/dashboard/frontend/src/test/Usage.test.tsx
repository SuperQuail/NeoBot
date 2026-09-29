// Usage.test.tsx —— 用量统计：悬停曲线图的数据点时给出该时间档的详细数据
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import Usage from '../pages/Usage';
import { api } from '../api/endpoints';

vi.mock('../api/endpoints.js', () => ({
  api: {
    seriesUsage: vi.fn(),
    usageRecords: vi.fn(),
  },
}));

const seriesUsage = vi.mocked(api.seriesUsage);
const usageRecords = vi.mocked(api.usageRecords);

const PAYLOAD = {
  available: true,
  hours: 24,
  bucket: 'hour',
  totals: { calls: 4, input_tokens: 3000, output_tokens: 600, cost_cny: 1.4 },
  points: [
    {
      at: '2026-09-27T13:00:00Z',
      calls: 1,
      input_tokens: 1000,
      output_tokens: 200,
      cost_cny: 0.4,
    },
    {
      at: '2026-09-27T14:00:00Z',
      calls: 3,
      input_tokens: 2000,
      output_tokens: 400,
      cost_cny: 1.0,
    },
  ],
  models: [],
  modules: [],
};

/** jsdom 没有布局：把容器宽度伪装成 600px，viewBox 与像素 1:1（两个点分别在 x=40 / x=580） */
function stubRect(width = 600, height = 180) {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
    width,
    height,
    top: 0,
    left: 0,
    right: width,
    bottom: height,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  } as DOMRect);
}

beforeEach(() => {
  seriesUsage.mockResolvedValue({ ok: true, data: PAYLOAD, error: null, status: 200 });
  usageRecords.mockResolvedValue({
    ok: true,
    data: { available: true, hours: 24, items: [] },
    error: null,
    status: 200,
  });
});

describe('Usage 用量页悬停提示', () => {
  it('悬停到花费曲线的数据点上，显示完整时间 + 金额 + 该档的调用与 Token', async () => {
    stubRect();
    const { container } = render(<Usage />);

    await waitFor(() => expect(container.querySelectorAll('.lc-wrap').length).toBe(3));
    const costChart = container.querySelectorAll('.lc-wrap')[0] as HTMLElement;

    fireEvent.mouseMove(costChart, { clientX: 580, clientY: 100 });

    const tip = screen.getByRole('tooltip');
    expect(tip.querySelector('.lc-tooltip-name')).toHaveTextContent('花费');
    // 完整时间（x 轴下方只显示「09-27 14」，提示里给全）
    expect(tip.querySelector('.lc-tooltip-label')).toHaveTextContent('2026-09-27 14:00');
    expect(tip.querySelector('.lc-tooltip-value')).toHaveTextContent('¥1.00');
    // 该时间档的其它指标一起给出
    expect(Array.from(tip.querySelectorAll('.lc-tooltip-row')).map((row) => row.textContent)).toEqual([
      '调用3',
      '输入 Token2.0 K',
      '输出 Token400',
      '花费¥1.00',
    ]);
  });

  it('悬停到 Token 曲线也带着该档的花费与调用次数', async () => {
    stubRect();
    const { container } = render(<Usage />);

    await waitFor(() => expect(container.querySelectorAll('.lc-wrap').length).toBe(3));
    const inputChart = container.querySelectorAll('.lc-wrap')[1] as HTMLElement;

    fireEvent.mouseMove(inputChart, { clientX: 40, clientY: 100 });

    const tip = screen.getByRole('tooltip');
    expect(tip.querySelector('.lc-tooltip-name')).toHaveTextContent('输入 Token');
    expect(tip.querySelector('.lc-tooltip-label')).toHaveTextContent('2026-09-27 13:00');
    expect(tip.querySelector('.lc-tooltip-value')).toHaveTextContent('1.0 K');
    expect(Array.from(tip.querySelectorAll('.lc-tooltip-row')).map((row) => row.textContent)).toEqual([
      '调用1',
      '输入 Token1.0 K',
      '输出 Token200',
      '花费¥0.40',
    ]);
  });
});
