import { describe, expect, it } from 'vitest';
import { fireEvent, render } from '@testing-library/react';
import { useState } from 'react';
import SchemaForm from '../components/SchemaForm';
import type { FieldDescriptor } from '../api/types';

// model_list 简化自后端 describe_dataclass：item_fields 带绝对路径 + index 段
function listDescriptor(): FieldDescriptor {
  const mk = (index: number) => ({
    index,
    fields: [
      { name: 'enabled', path: ['models', 'registry', String(index), 'enabled'], kind: 'scalar', type: 'bool', value: index === 0, default: false },
      { name: 'provider', path: ['models', 'registry', String(index), 'provider'], kind: 'scalar', type: 'str', value: index === 0 ? 'DeepSeek' : 'SiliconFlow', default: '' },
    ],
  });
  return {
    name: 'registry',
    path: ['models', 'registry'],
    kind: 'model_list',
    value: [{ enabled: true, provider: 'DeepSeek' }, { enabled: false, provider: 'SiliconFlow' }],
    items: [mk(0), mk(1)],
    item_fields: [
      { name: 'enabled', path: ['models', 'registry', 'enabled'], kind: 'scalar', type: 'bool', value: false, default: false },
      { name: 'provider', path: ['models', 'registry', 'provider'], kind: 'scalar', type: 'str', value: '', default: '' },
    ],
  } as FieldDescriptor;
}

function Harness({ filter }: { filter: string }) {
  const [values, setValues] = useState({ models: { registry: [{ enabled: true, provider: 'DeepSeek' }, { enabled: false, provider: 'SiliconFlow' }] } });
  const fields = [{ ...listDescriptor(), value: values.models.registry }];
  return <SchemaForm fields={fields} values={values} filter={filter} onChange={(path, v) => setValues((p) => ({ ...p, models: { registry: v as any } }))} />;
}

describe('model_list 搜索过滤', () => {
  it('搜索 provider=DeepSeek 时，只应显示匹配的那一项', () => {
    render(<Harness filter="DeepSeek" />);
    const items = document.querySelectorAll('.cfg-item');
    // 关键：不匹配的项必须被过滤掉
    expect(items.length).toBe(1);
  });

  it('过滤后切换开关，不应崩溃/清空', () => {
    render(<Harness filter="DeepSeek" />);
    const box = document.querySelector('input[type="checkbox"]') as HTMLInputElement;
    expect(box).toBeTruthy();
    fireEvent.click(box);
    expect(document.querySelectorAll('.cfg-item').length).toBe(1);
  });
});
