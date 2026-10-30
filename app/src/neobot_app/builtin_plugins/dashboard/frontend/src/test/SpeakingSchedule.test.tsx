import { useState } from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import SpeakingScheduleForm from '../pages/plugins/SpeakingScheduleForm';
import { scheduleErrors } from '../pages/plugins/speakingScheduleModel';

const window = { weekdays: [1], start: '08:13', end: '18:00', next_day: false };
function Harness({ disabled = false }: { disabled?: boolean }) {
  const [value, setValue] = useState<Record<string, unknown>>({
    timezone: 'Asia/Shanghai',
    windows: [window],
    overrides: [],
    extra: 'preserved',
  });
  return (
    <>
      <SpeakingScheduleForm
        value={value}
        disabled={disabled}
        onChange={(path, next) => setValue((old) => ({ ...old, [path[0]]: next }))}
      />
      <output data-testid="draft">{JSON.stringify(value)}</output>
    </>
  );
}

it('preserves exact minutes and moves sliders by five minutes with keyboard and pointer', () => {
  render(<Harness />);
  const slider = screen.getByRole('slider', { name: '默认窗口 1 开始滑块' });
  expect(slider).toHaveValue('493');
  fireEvent.change(screen.getByLabelText('默认窗口 1 开始时间'), { target: { value: '08:17' } });
  expect(slider).toHaveValue('497');
  fireEvent.keyDown(slider, { key: 'ArrowRight' });
  expect(screen.getByLabelText('默认窗口 1 开始时间')).toHaveValue('08:22');
  fireEvent.keyDown(slider, { key: 'ArrowLeft' });
  expect(slider).toHaveValue('497');
  fireEvent.change(slider, { target: { value: '509' } });
  expect(screen.getByLabelText('默认窗口 1 开始时间')).toHaveValue('08:30');
  expect(screen.getByTestId('draft')).toHaveTextContent('preserved');
});

it('edits weekdays, multiple windows, overnight segments and replacement scopes', () => {
  const { container } = render(<Harness />);
  fireEvent.click(screen.getByRole('button', { name: '工作日' }));
  expect(screen.getByLabelText('默认窗口 1 周五')).toBeChecked();
  fireEvent.click(screen.getByLabelText('默认窗口 1 周二'));
  expect(screen.getByLabelText('默认窗口 1 周二')).not.toBeChecked();
  fireEvent.change(screen.getByLabelText('默认窗口 1 开始时间'), { target: { value: '22:00' } });
  fireEvent.change(screen.getByLabelText('默认窗口 1 结束时间'), { target: { value: '02:00' } });
  fireEvent.click(screen.getByLabelText('默认窗口 1 结束于次日'));
  expect(container.querySelectorAll('.schedule-track-segment')).toHaveLength(2);
  fireEvent.click(screen.getByRole('button', { name: '默认添加窗口' }));
  expect(screen.getByLabelText('默认窗口 2 开始时间')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '添加覆盖范围' }));
  const scope = screen.getByRole('group', { name: '覆盖范围 1' });
  fireEvent.click(within(scope).getByRole('radio', { name: '私聊' }));
  fireEvent.change(within(scope).getByLabelText('会话 ID'), { target: { value: 'demo-person' } });
  expect(screen.getByTestId('draft')).toHaveTextContent('"kind":"private","id":"demo-person","windows":[]');
  expect(within(scope).getByText('空窗口表示无限制，替换默认时段。')).toBeInTheDocument();
  fireEvent.click(within(scope).getByRole('button', { name: '删除覆盖范围' }));
  expect(screen.queryByRole('group', { name: '覆盖范围 1' })).not.toBeInTheDocument();
});

it('disables every editing control and guards callbacks in readonly mode', () => {
  render(<Harness disabled />);
  expect(screen.getByRole('slider', { name: '默认窗口 1 开始滑块' })).toBeDisabled();
  fireEvent.change(screen.getByLabelText('时区'), { target: { value: 'UTC' } });
  expect(screen.getByTestId('draft')).toHaveTextContent('Asia/Shanghai');
  expect(screen.getByRole('button', { name: '添加覆盖范围' })).toBeDisabled();
});

it('validates durations, weekly wrap overlaps, timezone and duplicate scope identities', () => {
  expect(scheduleErrors({ timezone: 'Asia/Shanghai', windows: [], overrides: [] })).toEqual([]);
  expect(scheduleErrors({ timezone: 'bad/zone', windows: [window], overrides: [] }).join()).toMatch('时区');
  const overnight = { weekdays: [7], start: '22:00', end: '02:00', next_day: true };
  expect(
    scheduleErrors({
      timezone: 'UTC',
      windows: [overnight, { ...window, start: '01:00' }],
      overrides: [],
    }).join(),
  ).toMatch('重叠');
  expect(
    scheduleErrors({ timezone: 'UTC', windows: [{ ...window, next_day: true }], overrides: [] }).join(),
  ).toMatch('24');
  const scope = { kind: 'group', id: 'demo', windows: [] };
  expect(scheduleErrors({ timezone: 'UTC', windows: [], overrides: [scope, scope] }).join()).toMatch('重复');
});

it('shows backend defaults for omitted nested fields without changing the original draft', () => {
  const value = {
    timezone: 'UTC',
    windows: [{ weekdays: [1], start: '08:13', end: '18:00', note: 'keep-window' }],
    overrides: [{ kind: 'group', id: 'fictional-group', note: 'keep-scope' }],
  };
  const change = vi.fn();
  render(<SpeakingScheduleForm value={value} disabled={false} onChange={change} />);
  expect(screen.getByLabelText('默认窗口 1 结束于次日')).not.toBeChecked();
  expect(screen.getByLabelText('默认窗口 1 开始时间')).toHaveValue('08:13');
  expect(screen.getByText('空窗口表示无限制，替换默认时段。')).toBeInTheDocument();
  expect(change).not.toHaveBeenCalled();
  expect(scheduleErrors(value)).toEqual([]);
  fireEvent.keyDown(screen.getByRole('slider', { name: '默认窗口 1 开始滑块' }), { key: 'ArrowRight' });
  expect(change).toHaveBeenCalledWith(
    ['windows'],
    [{ ...value.windows[0], start: '08:18', next_day: false }],
  );
  expect(value.windows[0]).not.toHaveProperty('next_day');
});
