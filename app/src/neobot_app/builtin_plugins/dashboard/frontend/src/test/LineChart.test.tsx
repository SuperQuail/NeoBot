// LineChart.test.tsx —— 折线图悬停：最近数据点高亮 + 详细数据提示（时间标签 / 数值 / 列名）
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import LineChart from '../components/LineChart';

/** jsdom 没有布局：把容器宽度伪装成 600px，viewBox 与像素 1:1 */
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

const LABELS = ['09-27 10:00', '09-27 11:00', '09-27 12:00'];
/** W=600 → PAD.l=40, innerW=540, n=3 → 每个点相距 270px：x = 40 / 310 / 580 */
const X = [40, 310, 580];

function wrapper(container: HTMLElement): HTMLElement {
  const el = container.querySelector('.lc-wrap');
  if (!el) throw new Error('未渲染 .lc-wrap');
  return el as HTMLElement;
}

describe('LineChart 悬停提示', () => {
  it('负金额位于绘图区内，面积回到零基线，完整时间不受轴格式化影响', () => {
    stubRect(600, 180);
    const { container } = render(
      <LineChart
        fit
        showXAxis
        values={[-0.4, 0.8]}
        labels={['2026-09-27 13:00', '2026-09-27 14:00']}
        xTickFormatter={(label) => label.slice(11)}
        fmtTick={(value) => '¥' + value.toFixed(2)}
      />,
    );
    expect(screen.getByText('13:00')).toBeInTheDocument();
    expect(screen.getByText('¥-0.50')).toBeInTheDocument();
    fireEvent.mouseMove(wrapper(container), { clientX: 40, clientY: 100 });
    const pointY = Number(container.querySelector('.lc-dot')?.getAttribute('cy'));
    expect(pointY).toBeGreaterThanOrEqual(20);
    expect(pointY).toBeLessThanOrEqual(160);
    expect(screen.getByRole('tooltip')).toHaveTextContent('2026-09-27 13:00');
    expect(screen.getByRole('tooltip')).toHaveTextContent('¥-0.40');
    const path = container.querySelector('.lc-area')?.getAttribute('d') || '';
    expect(path).not.toMatch(/,160 Z$/);
  });

  it('全为负值或小额花费也使用有效量级绘图', () => {
    stubRect();
    const negative = render(<LineChart fit values={[-4, -2]} />);
    fireEvent.mouseMove(wrapper(negative.container), { clientX: 40, clientY: 100 });
    expect(Number(negative.container.querySelector('.lc-dot')?.getAttribute('cy'))).toBeLessThanOrEqual(160);
    negative.unmount();
    const small = render(<LineChart fit values={[0.01, 0.03]} fmtTick={(value) => '¥' + value.toFixed(2)} />);
    expect(screen.getByText('¥0.04')).toBeInTheDocument();
    fireEvent.mouseMove(wrapper(small.container), { clientX: 580, clientY: 100 });
    expect(Number(small.container.querySelector('.lc-dot')?.getAttribute('cy'))).toBeLessThan(100);
  });

  it('工作区图表按实际高度绘制，并显示日期刻度', () => {
    stubRect(800, 260);
    const { container } = render(
      <LineChart fit showXAxis values={[10, 20, 30]} labels={['2026-10-01', '2026-10-02', '2026-10-03']} />,
    );
    expect(screen.getByRole('img')).toHaveAttribute('viewBox', '0 0 800 260');
    expect(screen.getByText('10/01')).toBeInTheDocument();
    expect(screen.getByText('10/03')).toBeInTheDocument();
    fireEvent.mouseMove(wrapper(container), { clientX: 780, clientY: 160 });
    expect(screen.getByRole('tooltip')).toHaveTextContent('2026-10-03');
    expect(container.querySelector('.lc-guide')).toHaveAttribute('y2', '240');
  });

  it('悬停到数据点上显示该点的时间与数值', () => {
    stubRect();
    const { container } = render(
      <LineChart values={[10, 20, 30]} labels={LABELS} name="花费" fmtTick={(v) => '¥' + v.toFixed(2)} />,
    );

    fireEvent.mouseMove(wrapper(container), { clientX: X[1], clientY: 100 });

    const tip = screen.getByRole('tooltip');
    expect(tip.querySelector('.lc-tooltip-name')).toHaveTextContent('花费');
    expect(tip.querySelector('.lc-tooltip-label')).toHaveTextContent('09-27 11:00');
    expect(tip.querySelector('.lc-tooltip-value')).toHaveTextContent('¥20.00');
    // 参考线 / 高亮点落在同一个点上
    expect(container.querySelector('.lc-guide')).toHaveAttribute('x1', '310');
    expect(container.querySelector('.lc-dot')).toHaveAttribute('cx', '310');
  });

  it('鼠标落在点之间时吸附到最近的数据点', () => {
    stubRect();
    const { container } = render(<LineChart values={[10, 20, 30]} labels={LABELS} />);

    // 比第一个点更靠左 → 吸附到 #0
    fireEvent.mouseMove(wrapper(container), { clientX: 10, clientY: 40 });
    expect(container.querySelector('.lc-guide')).toHaveAttribute('x1', '40');

    // 比第三个点更靠右 → 吸附到 #2
    fireEvent.mouseMove(wrapper(container), { clientX: 590, clientY: 40 });
    expect(container.querySelector('.lc-guide')).toHaveAttribute('x1', '580');
  });

  it('fmtValue 覆盖提示里的数值格式；缺 labels 时回退成序号', () => {
    stubRect();
    const { container } = render(
      <LineChart values={[1234, 5678]} fmtValue={(v) => v.toLocaleString('en-US')} />,
    );

    fireEvent.mouseMove(wrapper(container), { clientX: 580, clientY: 100 });

    const tip = screen.getByRole('tooltip');
    expect(tip.querySelector('.lc-tooltip-label')).toHaveTextContent('#1');
    expect(tip.querySelector('.lc-tooltip-value')).toHaveTextContent('5,678');
  });

  it('断点（null）只显示参考线，提示里写「无数据」', () => {
    stubRect();
    const { container } = render(<LineChart values={[10, null, 30]} labels={LABELS} name="输入 Token" />);

    fireEvent.mouseMove(wrapper(container), { clientX: X[1], clientY: 100 });

    expect(container.querySelector('.lc-guide')).toHaveAttribute('x1', '310');
    expect(container.querySelector('.lc-dot')).toBeNull();
    expect(screen.getByRole('tooltip').querySelector('.lc-tooltip-value')).toHaveTextContent('无数据');
  });

  it('extraRows 追加该数据点的其它明细行', () => {
    stubRect();
    const { container } = render(
      <LineChart
        values={[10, 20, 30]}
        labels={LABELS}
        name="花费"
        extraRows={(index) => [
          { label: '调用', value: String(index + 1) },
          { label: '输入 Token', value: '2.0 K' },
        ]}
      />,
    );

    fireEvent.mouseMove(wrapper(container), { clientX: X[2], clientY: 100 });

    const tip = screen.getByRole('tooltip');
    expect(Array.from(tip.querySelectorAll('.lc-tooltip-row')).map((row) => row.textContent)).toEqual([
      '调用3',
      '输入 Token2.0 K',
    ]);
  });

  it('鼠标移出后提示与参考线一起消失', () => {
    stubRect();
    const { container } = render(<LineChart values={[10, 20, 30]} labels={LABELS} />);
    const wrap = wrapper(container);

    fireEvent.mouseMove(wrap, { clientX: X[0], clientY: 100 });
    expect(screen.getByRole('tooltip')).toBeInTheDocument();

    fireEvent.mouseOut(wrap, { relatedTarget: document.body });
    expect(screen.queryByRole('tooltip')).toBeNull();
    expect(container.querySelector('.lc-guide')).toBeNull();
  });

  it('无数据时给出空态；有数据时给图补一段可读摘要', () => {
    stubRect();
    const empty = render(<LineChart values={[null, null]} name="花费" />);
    expect(empty.getByText('暂无数据')).toBeInTheDocument();
    empty.unmount();

    render(<LineChart values={[10, 20, 30]} name="花费" fmtTick={(v) => '¥' + v.toFixed(2)} />);
    expect(screen.getByRole('img')).toHaveAttribute(
      'aria-label',
      '花费折线图：共 3 个数据点，最新 ¥30.00，峰值 ¥30.00',
    );
  });
});
