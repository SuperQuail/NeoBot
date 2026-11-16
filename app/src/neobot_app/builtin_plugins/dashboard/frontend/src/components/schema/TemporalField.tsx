// components/schema/TemporalField.tsx —— 日期 / 时间 / 日期时间设置项（本体与插件配置共用）
//
// 取值契约：字段值一律是 ISO 8601 字符串，与后端 config_parts/schema.py 的 _jsonable 对齐
//   kind=date     → YYYY-MM-DD
//   kind=time     → HH:MM:SS
//   kind=datetime → YYYY-MM-DDTHH:MM:SS
//
// 原生控件只接受「墙钟」部分（不带时区偏移，秒可能被省略），所以这里做两件事：
//   1) 读：宽松解析后端值（空格分隔、毫秒、Z / ±HH:MM 都接受），喂给控件；
//   2) 写：把控件值规范化后提交，缺秒补 :00。
// 时区不做换算 —— 配置里的时间就是本地面钟时间；带偏移的值按面钟展示，提交时丢弃偏移。
import { useEffect, useState } from 'react';
import type { FieldDescriptor } from '../../api/types';
import { FieldActions, FieldHeader } from './FieldChrome';
import type { FieldCallbacks } from './fieldTypes';

export type TemporalMode = 'date' | 'time' | 'datetime';

const DATE_PART = /^(\d{4}-\d{2}-\d{2})/;
const TIME_PART = /(\d{2}):(\d{2})(?::(\d{2}))?/;

const INPUT_TYPE: Record<TemporalMode, string> = {
  date: 'date',
  time: 'time',
  datetime: 'datetime-local',
};

const ISO_FORMAT: Record<TemporalMode, string> = {
  date: 'YYYY-MM-DD',
  time: 'HH:MM:SS',
  datetime: 'YYYY-MM-DDTHH:MM:SS',
};

/** descriptor.kind → 控件形态；不认识的值退回日期时间（后端新增同族 kind 时的保守默认）。 */
export function temporalMode(kind?: string): TemporalMode {
  if (kind === 'date' || kind === 'time') return kind;
  return 'datetime';
}

/** 后端值 → 原生控件的 value；解析不出墙钟时间就当空值，不把脏数据塞给控件。 */
export function toInputValue(raw: unknown, mode: TemporalMode): string {
  if (raw === null || raw === undefined) return '';
  const text = String(raw).trim();
  if (!text) return '';
  const date = DATE_PART.exec(text)?.[1] ?? '';
  const matched = TIME_PART.exec(text);
  const clock = matched ? `${matched[1]}:${matched[2]}:${matched[3] ?? '00'}` : '';
  if (mode === 'date') return date;
  if (mode === 'time') return clock;
  return date && clock ? `${date}T${clock}` : '';
}

/**
 * 原生控件的 value → 提交值（ISO 8601）。
 * 清空时：必填回空串（由后端校验给出字段级错误），可选回 null（= 不设置）。
 */
export function toSubmitValue(input: string, mode: TemporalMode, required: boolean): string | null {
  if (!input) return required ? '' : null;
  if (mode === 'date') return input;
  if (mode === 'time') return input.length === 5 ? `${input}:00` : input;
  return input.length === 16 ? `${input}:00` : input;
}

export default function TemporalField({
  descriptor,
  value,
  onChange,
  disabled,
  onRestore,
  onShowHistory,
  historyCount,
  filter,
}: { descriptor: FieldDescriptor } & FieldCallbacks) {
  const mode = temporalMode(descriptor.kind);
  const locked = disabled || descriptor.readonly;
  const required = descriptor.required !== false;
  const [text, setText] = useState(() => toInputValue(value, mode));

  // 外部值变更（撤销 / 恢复默认 / 重新读取）回灌控件
  useEffect(() => {
    setText(toInputValue(value, mode));
  }, [value, mode]);

  const id =
    typeof descriptor.input_id === 'string'
      ? descriptor.input_id
      : 'cfg-' + descriptor.path.map(encodeURIComponent).join('-');
  const submitted = toSubmitValue(text, mode, required);
  return (
    <div className="cfg-row">
      <FieldHeader descriptor={descriptor} filter={filter} />
      <div className="cfg-control cfg-control-with-actions">
        <div className="config-input-wrap">
          <input
            id={id}
            className="input"
            type={INPUT_TYPE[mode]}
            // 让浏览器给出秒级精度：契约里的 HH:MM:SS 不能因为控件默认 60s 步长被截断
            step={mode === 'date' ? undefined : 1}
            disabled={locked}
            value={text}
            aria-label={descriptor.label || descriptor.name}
            title={`ISO 8601：${ISO_FORMAT[mode]}${submitted ? `（当前 ${submitted}）` : ''}`}
            onChange={(event) => {
              if (locked) return;
              const next = event.target.value;
              setText(next);
              onChange(toSubmitValue(next, mode, required));
            }}
          />
        </div>
        <FieldActions
          descriptor={descriptor}
          value={value}
          disabled={locked}
          onRestore={onRestore}
          onShowHistory={onShowHistory}
          historyCount={historyCount}
        />
      </div>
    </div>
  );
}
