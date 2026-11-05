import Button from '../../components/ui/Button';
import { minutes, time, weekdays, type ScheduleWindow } from './speakingScheduleModel';

export default function ScheduleWindowEditor({
  value,
  label,
  disabled,
  onChange,
  onRemove,
}: {
  value: ScheduleWindow;
  label: string;
  disabled: boolean;
  onChange: (value: ScheduleWindow) => void;
  onRemove: () => void;
}) {
  const change = (patch: Partial<ScheduleWindow>) => {
    if (!disabled) onChange({ ...value, next_day: value.next_day ?? false, ...patch });
  };
  const start = minutes(value.start),
    end = minutes(value.end);
  const valid = Number.isFinite(start) && Number.isFinite(end);
  const segments = !valid
    ? []
    : value.next_day
      ? [
          [start, 1440],
          [0, end],
        ]
      : end > start
        ? [[start, end]]
        : [];
  return (
    <fieldset className="schedule-window" disabled={disabled}>
      <legend>{label}</legend>
      <div className="schedule-weekdays">
        {weekdays.map((day, index) => (
          <label key={day}>
            <input
              type="checkbox"
              aria-label={`${label} ${day}`}
              checked={value.weekdays.includes(index + 1)}
              onChange={(e) =>
                change({
                  weekdays: e.target.checked
                    ? [...value.weekdays, index + 1].sort()
                    : value.weekdays.filter((item) => item !== index + 1),
                })
              }
            />
            {day}
          </label>
        ))}
      </div>
      <div className="schedule-actions">
        <Button size="sm" onClick={() => change({ weekdays: [1, 2, 3, 4, 5, 6, 7] })}>
          每天
        </Button>
        <Button size="sm" onClick={() => change({ weekdays: [1, 2, 3, 4, 5] })}>
          工作日
        </Button>
        <Button size="sm" onClick={() => change({ weekdays: [6, 7] })}>
          周末
        </Button>
      </div>
      <div className="schedule-track" aria-hidden="true">
        {segments.map(([left, right], index) => (
          <span
            key={index}
            className="schedule-track-segment"
            style={{ left: `${left / 14.4}%`, width: `${(right - left) / 14.4}%` }}
          />
        ))}
      </div>
      <div className="schedule-time-fields">
        {(['start', 'end'] as const).map((key) => {
          const name = key === 'start' ? '开始' : '结束';
          const current = Number.isFinite(minutes(value[key])) ? minutes(value[key]) : 0;
          return (
            <div className="schedule-time" key={key}>
              <label>
                {name}时间
                <input
                  type="time"
                  step={60}
                  aria-label={`${label} ${name}时间`}
                  value={value[key]}
                  onChange={(e) => change({ [key]: e.target.value })}
                />
              </label>
              <input
                type="range"
                min={0}
                max={1439}
                step={1}
                value={current}
                aria-label={`${label} ${name}滑块`}
                aria-valuetext={value[key]}
                onChange={(e) => change({ [key]: time(Math.round(Number(e.target.value) / 5) * 5) })}
                onKeyDown={(e) => {
                  const delta = {
                    ArrowRight: 5,
                    ArrowUp: 5,
                    ArrowLeft: -5,
                    ArrowDown: -5,
                    PageUp: 60,
                    PageDown: -60,
                  }[e.key];
                  if (delta !== undefined || e.key === 'Home' || e.key === 'End') {
                    e.preventDefault();
                    change({
                      [key]: time(e.key === 'Home' ? 0 : e.key === 'End' ? 1439 : current + (delta ?? 0)),
                    });
                  }
                }}
              />
            </div>
          );
        })}
      </div>
      <div className="schedule-window-footer">
        <label>
          <input
            type="checkbox"
            aria-label={`${label} 结束于次日`}
            checked={value.next_day ?? false}
            onChange={(e) => change({ next_day: e.target.checked })}
          />
          结束于次日
        </label>
        <Button size="sm" variant="danger" onClick={onRemove}>
          删除窗口
        </Button>
      </div>
    </fieldset>
  );
}
