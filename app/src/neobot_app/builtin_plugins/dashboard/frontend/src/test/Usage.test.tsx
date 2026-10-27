// Usage.test.tsx —— 用量统计：悬停曲线图的数据点时给出该时间档的详细数据
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import Usage from '../pages/Usage';
import { api } from '../api/endpoints';
import { POLL } from '../data/queryKeys';

vi.mock('../api/endpoints', () => ({
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
  vi.clearAllMocks();
  seriesUsage.mockResolvedValue({ ok: true, data: PAYLOAD, error: null, status: 200 });
  usageRecords.mockResolvedValue({
    ok: true,
    data: { available: true, hours: 24, items: [] },
    error: null,
    status: 200,
  });
});

describe('Usage 用量页悬停提示', () => {
  it('每分钟自动更新趋势和最近调用，卸载后停止读取', async () => {
    vi.useFakeTimers();
    try {
      const view = render(<Usage />);
      await act(async () => {});
      expect(screen.queryByRole('button', { name: '刷新' })).not.toBeInTheDocument();
      seriesUsage.mockResolvedValue({
        ok: true,
        data: { ...PAYLOAD, totals: { ...PAYLOAD.totals, cost_cny: 8.2 } },
        error: null,
        status: 200,
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(POLL.usage);
      });
      expect(seriesUsage).toHaveBeenCalledTimes(2);
      expect(usageRecords).toHaveBeenCalledTimes(2);
      expect(screen.getByText('¥8.20', { selector: 'dd' })).toBeInTheDocument();
      view.unmount();
      await vi.advanceTimersByTimeAsync(POLL.usage * 2);
      expect(seriesUsage).toHaveBeenCalledTimes(2);
      expect(usageRecords).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it('自动更新保留已打开的计费详情，读取失败保留旧数据并可重试', async () => {
    vi.useFakeTimers();
    try {
      const record = { at: '2026-09-27T13:00:00Z', module: 'chat', model_name: 'model', cost_cny: 0.4 };
      usageRecords.mockResolvedValue({ ok: true, error: null, status: 200, data: { items: [record] } });
      const view = render(<Usage />);
      await act(async () => {});
      fireEvent.click(screen.getByRole('button', { name: '最近调用' }));
      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: '查看分项' }));
      });
      const dialog = screen.getByRole('dialog', { name: '调用计费详情' });
      seriesUsage.mockResolvedValueOnce({ ok: false, error: '趋势暂时不可用', status: 503, data: null });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(POLL.usage);
      });
      expect(dialog).toBeInTheDocument();
      fireEvent.click(within(dialog).getByRole('button', { name: '关闭对话框' }));
      expect(screen.getByText('趋势暂时不可用')).toBeInTheDocument();
      expect(screen.getByText('¥1.40', { selector: 'dd' })).toBeInTheDocument();
      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: '重试读取' }));
      });
      expect(screen.queryByText('趋势暂时不可用')).not.toBeInTheDocument();
      view.unmount();
    } finally {
      vi.useRealTimers();
    }
  });

  it('悬停到花费曲线的数据点上，显示完整时间 + 金额 + 该档的调用与 Token', async () => {
    stubRect();
    const { container } = render(<Usage />);

    await waitFor(() => expect(container.querySelectorAll('.lc-wrap').length).toBe(2));
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

    await waitFor(() => expect(container.querySelectorAll('.lc-wrap').length).toBe(2));
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

  it('输出 Token 可单独切换查看，保留同一时间档的完整提示', async () => {
    stubRect();
    const { container } = render(<Usage />);
    fireEvent.click(await screen.findByRole('button', { name: '输出' }));
    const chart = container.querySelectorAll('.lc-wrap')[1] as HTMLElement;
    fireEvent.mouseMove(chart, { clientX: 580, clientY: 100 });
    expect(screen.getByRole('tooltip')).toHaveTextContent('输出 Token');
    expect(screen.getByRole('tooltip').querySelector('.lc-tooltip-value')).toHaveTextContent('400');
    expect(screen.getByRole('tooltip')).toHaveTextContent('花费¥1.00');
  });

  it('模型和模块表分页后仍可访问全部记录', async () => {
    stubRect(600, 180);
    seriesUsage.mockResolvedValue({
      ok: true,
      status: 200,
      error: null,
      data: {
        ...PAYLOAD,
        models: Array.from({ length: 9 }, (_, i) => ({
          model_name: `model-${i}`,
          provider_name: 'provider',
          calls: i,
        })),
        modules: [{ module_name: 'private_chat', calls: 7 }],
      },
    });
    render(<Usage />);
    await screen.findByText('model-0');
    expect(screen.queryByText('model-8')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '按模型的用量明细下一页' }));
    fireEvent.click(screen.getByRole('button', { name: '按模型的用量明细下一页' }));
    expect(screen.getByText('model-8')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '按调用模块' }));
    expect(screen.getByText('private_chat')).toBeInTheDocument();
  });

  it('计费分项按需读取；新记录插入后仍展示选中调用的冲抵、来源、说明与错误', async () => {
    const record = {
      at: '2026-09-27T13:00:00Z',
      module: 'chat',
      model_name: 'model',
      cost_cny: -0.4,
      cost_source: 'script:credit',
      negative: true,
    };
    usageRecords.mockImplementation(async (_hours, _limit, details) => ({
      ok: true,
      error: null,
      status: 200,
      data: {
        items: details
          ? [
              { ...record, at: '2026-09-27T14:00:00Z', cost_detail: { note: '另一条记录' } },
              {
                ...record,
                cost_detail: { components: { refund: -0.4 }, note: '返还余额', error: '计价提示' },
              },
            ]
          : [record],
      },
    }));
    render(<Usage />);
    fireEvent.click(await screen.findByRole('button', { name: '最近调用' }));
    expect(usageRecords).toHaveBeenCalledWith(24, 20, false);
    expect(usageRecords).not.toHaveBeenCalledWith(24, 20, true);
    expect(screen.getByText('冲抵')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '查看分项' }));
    const dialog = screen.getByRole('dialog', { name: '调用计费详情' });
    expect(await within(dialog).findByText('说明：返还余额')).toBeInTheDocument();
    expect(within(dialog).getByText('错误：计价提示')).toBeInTheDocument();
    expect(within(dialog).getByText('refund')).toBeInTheDocument();
    expect(within(dialog).queryByText('另一条记录')).not.toBeInTheDocument();
    expect(usageRecords).toHaveBeenCalledWith(24, 20, true);
  });

  it('关闭分项对话框后迟到的响应不会重新打开它', async () => {
    const record = { at: '2026-09-27T13:00:00Z', module: 'chat', model_name: 'model', cost_cny: 0.4 };
    let resolveDetails: ((value: Awaited<ReturnType<typeof api.usageRecords>>) => void) | undefined;
    usageRecords.mockImplementation(async (_hours, _limit, details) =>
      details
        ? new Promise((resolve) => {
            resolveDetails = resolve;
          })
        : { ok: true, error: null, status: 200, data: { items: [record] } },
    );
    render(<Usage />);
    fireEvent.click(await screen.findByRole('button', { name: '最近调用' }));
    fireEvent.click(screen.getByRole('button', { name: '查看分项' }));
    fireEvent.click(screen.getByRole('button', { name: '关闭对话框' }));
    await act(async () =>
      resolveDetails?.({
        ok: true,
        error: null,
        status: 200,
        data: { items: [{ ...record, cost_detail: { note: '迟到结果' } }] },
      }),
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('切换时间范围后忽略旧范围迟到的趋势结果', async () => {
    let resolveOld: ((value: Awaited<ReturnType<typeof api.seriesUsage>>) => void) | undefined;
    seriesUsage.mockImplementation(async (hours) =>
      hours === 24
        ? new Promise((resolve) => {
            resolveOld = resolve;
          })
        : {
            ok: true,
            error: null,
            status: 200,
            data: { ...PAYLOAD, models: [{ model_name: '本周模型' }] },
          },
    );
    render(<Usage />);
    fireEvent.click(screen.getByRole('button', { name: '近 7 天' }));
    expect(await screen.findByText('本周模型')).toBeInTheDocument();
    await act(async () =>
      resolveOld?.({
        ok: true,
        error: null,
        status: 200,
        data: { ...PAYLOAD, models: [{ model_name: '旧范围模型' }] },
      }),
    );
    expect(screen.queryByText('旧范围模型')).not.toBeInTheDocument();
    expect(screen.getByText('本周模型')).toBeInTheDocument();
    expect(seriesUsage).toHaveBeenCalledWith(168, 'hour');
    expect(usageRecords).toHaveBeenCalledWith(168, 20, false);
  });

  it('最近调用读取失败在分类入口标记，打开后展示接口错误', async () => {
    usageRecords.mockResolvedValue({
      ok: true,
      status: 200,
      error: null,
      data: { available: false, error: '用量数据库暂不可用', items: [] },
    });
    render(<Usage />);
    const tab = await screen.findByRole('button', { name: '最近调用 读取失败' });
    fireEvent.click(tab);
    expect(screen.getByText('用量数据库暂不可用')).toBeInTheDocument();
  });
});
