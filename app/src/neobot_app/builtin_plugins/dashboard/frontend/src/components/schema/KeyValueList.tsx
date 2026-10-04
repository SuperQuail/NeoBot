// KeyValueList.tsx —— 字典的键值表（group_response_coefficient / group_description …）
//
// 字典此前走 JsonField（一整块原始 JSON 文本）：改一个系数要手动改数字，
// 少个引号就报「请输入有效的 JSON 对象」。这里改成两列表格，逐行增删。
import { useState } from 'react';
import Icon from '../Icon';
import { Highlight } from './Highlight';

export interface KeyValueListProps {
  entries: Array<[string, string]>;
  filter?: string;
  keyPlaceholder?: string;
  valuePlaceholder?: string;
  onChange: (next: Array<[string, string]>) => void;
}

export default function KeyValueList({
  entries, filter, keyPlaceholder = '键', valuePlaceholder = '值', onChange,
}: KeyValueListProps) {
  const [pendingKey, setPendingKey] = useState('');
  const [pendingValue, setPendingValue] = useState('');

  const commit = (index: number, key: string, value: string) => {
    const next = entries.map((entry, i) => (i === index ? ([key, value] as [string, string]) : entry));
    onChange(next);
  };

  const add = () => {
    const key = pendingKey.trim();
    if (!key) return;
    onChange([...entries, [key, pendingValue]]);
    setPendingKey('');
    setPendingValue('');
  };

  return (
    <div className="cfg-kv">
      <div className="cfg-kv-row head">
        <span>{keyPlaceholder}</span>
        <span>{valuePlaceholder}</span>
        <span />
      </div>
      {entries.length === 0 && (
        <div className="cfg-kv-row empty"><span>暂无条目</span><span /><span /></div>
      )}
      {entries.map(([key, value], index) => (
        <div className="cfg-kv-row" key={index}>
          <input
            className="input cfg-kv-input mono"
            value={key}
            aria-label={'第 ' + (index + 1) + ' 行键'}
            onChange={(event) => commit(index, event.target.value, value)}
          />
          <input
            className="input cfg-kv-input"
            value={value}
            aria-label={'第 ' + (index + 1) + ' 行值'}
            onChange={(event) => commit(index, key, event.target.value)}
          />
          <button type="button" className="cfg-row-remove" aria-label={'删除 ' + key}
            onClick={() => onChange(entries.filter((_, i) => i !== index))}>×</button>
          {filter && (
            <span className="cfg-kv-hit">
              <Highlight text={key + ' ' + value} keyword={filter} />
            </span>
          )}
        </div>
      ))}
      <div className="cfg-kv-row add">
        <input
          className="input cfg-kv-input mono"
          value={pendingKey}
          placeholder={keyPlaceholder}
          onChange={(event) => setPendingKey(event.target.value)}
        />
        <input
          className="input cfg-kv-input"
          value={pendingValue}
          placeholder={valuePlaceholder}
          onChange={(event) => setPendingValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              add();
            }
          }}
        />
        <button type="button" className="btn-sm" disabled={!pendingKey.trim()} onClick={add}>
          <Icon name="plus" />
        </button>
      </div>
    </div>
  );
}
