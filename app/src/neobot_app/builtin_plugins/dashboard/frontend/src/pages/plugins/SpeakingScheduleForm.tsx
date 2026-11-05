import Button from '../../components/ui/Button';
import FormField from '../../components/ui/FormField';
import ScheduleWindowEditor from './ScheduleWindowEditor';
import {
  newWindow,
  overrideShape,
  scheduleErrors,
  windowShape,
  type ScheduleOverride,
  type ScheduleWindow,
} from './speakingScheduleModel';

export default function SpeakingScheduleForm({
  value,
  disabled,
  onChange,
}: {
  value: Record<string, unknown>;
  disabled: boolean;
  onChange: (path: string[], value: unknown) => void;
}) {
  const update = (key: string, next: unknown) => {
    if (!disabled) onChange([key], next);
  };
  const windows = Array.isArray(value.windows) ? value.windows : [];
  const overrides = Array.isArray(value.overrides) ? value.overrides : [];
  const errors = scheduleErrors(value);
  function windowList(items: unknown[], label: string, change: (items: ScheduleWindow[]) => void) {
    return (
      <>
        {!items.length && (
          <p className="muted">空窗口表示无限制{label === '默认' ? '。' : '，替换默认时段。'}</p>
        )}
        {items.map(
          (item, index) =>
            windowShape(item) && (
              <ScheduleWindowEditor
                key={index}
                label={`${label}窗口 ${index + 1}`}
                value={item}
                disabled={disabled}
                onChange={(next) =>
                  change(items.map((old, i) => (i === index ? next : old)) as ScheduleWindow[])
                }
                onRemove={() => change(items.filter((_, i) => i !== index) as ScheduleWindow[])}
              />
            ),
        )}
        <Button
          size="sm"
          disabled={disabled}
          aria-label={`${label}添加窗口`}
          onClick={() => change([...items, newWindow()] as ScheduleWindow[])}
        >
          添加窗口
        </Button>
      </>
    );
  }
  function changeScope(index: number, next: ScheduleOverride) {
    update(
      'overrides',
      overrides.map((scope, i) => (i === index ? next : scope)),
    );
  }
  return (
    <fieldset className="speaking-schedule" disabled={disabled}>
      <legend>发言时段</legend>
      <p className="muted">
        管理 Bot 发言时段，星期按窗口开始日计算。拖动或方向键调整 5
        分钟，时间框可精确到分钟。修改后点击现有保存按钮生效。
      </p>
      <FormField label="时区">
        <input
          aria-label="时区"
          value={typeof value.timezone === 'string' ? value.timezone : ''}
          placeholder="Asia/Shanghai"
          onChange={(e) => update('timezone', e.target.value)}
        />
      </FormField>
      {errors.length > 0 && (
        <div className="schedule-errors" role="alert">
          {errors.map((error) => (
            <p key={error}>{error}</p>
          ))}
        </div>
      )}
      <section aria-label="默认时段">
        <h3>默认时段</h3>
        {windowList(windows, '默认', (next) => update('windows', next))}
      </section>
      <section aria-label="覆盖时段">
        <h3>群聊与私聊覆盖</h3>
        <p className="muted">匹配的覆盖范围会替换默认时段；相同类型与会话 ID 只能有一条。</p>
        {overrides.map(
          (scope, index) =>
            overrideShape(scope) && (
              <fieldset
                className="schedule-scope"
                key={index}
                aria-label={`覆盖范围 ${index + 1}`}
                disabled={disabled}
              >
                <legend>覆盖范围 {index + 1}</legend>
                <div className="schedule-actions">
                  {(['group', 'private'] as const).map((kind) => (
                    <label key={kind}>
                      <input
                        type="radio"
                        name={`schedule-kind-${index}`}
                        checked={scope.kind === kind}
                        onChange={() => changeScope(index, { ...scope, kind })}
                      />
                      {kind === 'group' ? '群聊' : '私聊'}
                    </label>
                  ))}
                </div>
                <FormField label="会话 ID">
                  <input
                    aria-label="会话 ID"
                    value={scope.id}
                    onChange={(e) => changeScope(index, { ...scope, id: e.target.value })}
                  />
                </FormField>
                {windowList(scope.windows ?? [], `覆盖 ${index + 1}`, (next) =>
                  changeScope(index, { ...scope, windows: next }),
                )}
                <Button
                  size="sm"
                  variant="danger"
                  disabled={disabled}
                  onClick={() =>
                    update(
                      'overrides',
                      overrides.filter((_, i) => i !== index),
                    )
                  }
                >
                  删除覆盖范围
                </Button>
              </fieldset>
            ),
        )}
        <Button
          size="sm"
          disabled={disabled}
          onClick={() => update('overrides', [...overrides, { kind: 'group', id: '', windows: [] }])}
        >
          添加覆盖范围
        </Button>
      </section>
    </fieldset>
  );
}
